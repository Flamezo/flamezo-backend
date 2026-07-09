# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Story Media Generator
=====================
Generates shareable Instagram Story media (image / video) with the Flamezo
overlay composited at native CDN resolution via server-side ffmpeg / Pillow.

Why server-side?
  - No CORS limitations (CDN video fetched directly from server)
  - Overlay rendered at native resolution — no upscaling, crisp text/logo
  - Background job — Frappe workers are never blocked; 100 concurrent requests
    just queue up and process without degrading the API
  - Result uploaded to R2 and served via CDN — fast download, no Frappe bandwidth

Flow:
  start_story_download()          → enqueues job → returns {job_id}
  get_story_download_status()     → returns {status, url?, error?}
  _run_job()                      → (background) composite → R2 upload → cache URL
"""

import os
import uuid
import base64
import subprocess
import tempfile
import shutil
from urllib.parse import urlparse

import frappe

# ─── Constants ────────────────────────────────────────────────────────────────

CACHE_TTL        = 7200          # job result kept in Redis for 2 h
TEMP_KEY_PREFIX  = "temp/story-previews"
WA_CHANNEL_URL   = "https://whatsapp.com/channel/0029VbDInYjE50Up33JZob10"
MONTHS           = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

_ALLOWED_CDN     = {"dinematters.com", "flamezo.in"}

LOGO_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",   # api → flamezo → flamezo_backend(pkg) → flamezo_backend(app root)
    "frontend", "public", "images", "main-logo-dark.png",
))


# ─── Public API Endpoints ─────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def start_story_download(
    template_url, media_type,
    restaurant_name="",
    coupon_code=None, discount_type=None, discount_value=None,
    offer_description=None, valid_until=None,
):
    """
    Validate inputs, enqueue the generation job, return {job_id} immediately.
    The frontend polls get_story_download_status() until status == 'done'.

    allow_guest: diners in the consumer app (authenticated via X-Customer-Token,
    so session.user is Guest) download their story with the overlay burned in.
    Safe because template_url is restricted to allowed CDN domains below.
    """
    if not _cdn_url_allowed(template_url):
        frappe.throw("Media URL is not from an allowed CDN domain.", frappe.PermissionError)

    if media_type not in ("image", "video"):
        frappe.throw("Invalid media_type.")

    job_id = str(uuid.uuid4())
    _set_cache(job_id, {"status": "pending"})

    # Run the compositing INLINE (no background-worker dependency). This is an
    # on-demand download action and a 720p clip composites in a few seconds, so we
    # do it synchronously and the client's first status poll gets the finished URL.
    # Running via a worker was unreliable — jobs sat un-consumed on local benches.
    try:
        _run_job(
            job_id=job_id,
            template_url=template_url,
            media_type=media_type,
            restaurant_name=restaurant_name or "",
            coupon_code=coupon_code,
            discount_type=discount_type,
            discount_value=discount_value,
            offer_description=offer_description,
            valid_until=valid_until,
        )
    except Exception:
        # Fall back to the async queue if the inline run itself blows up.
        frappe.log_error(frappe.get_traceback(), "Story inline run failed — using queue")
        frappe.enqueue(
            "flamezo_backend.flamezo.api.story_generator._run_job",
            queue="default", timeout=300, job_id=job_id,
            template_url=template_url, media_type=media_type,
            restaurant_name=restaurant_name or "", coupon_code=coupon_code,
            discount_type=discount_type, discount_value=discount_value,
            offer_description=offer_description, valid_until=valid_until,
        )

    return {"job_id": job_id}


@frappe.whitelist(allow_guest=True)
def get_story_download_status(job_id):
    """
    Returns {status, url?, error?} for a previously enqueued job.
    status: 'pending' | 'processing' | 'done' | 'error' | 'not_found'
    """
    return _get_cache(job_id) or {"status": "not_found"}


# ─── Background Job ───────────────────────────────────────────────────────────

def _run_job(
    job_id, template_url, media_type, restaurant_name="",
    coupon_code=None, discount_type=None, discount_value=None,
    offer_description=None, valid_until=None,
):
    _set_cache(job_id, {"status": "processing"})

    try:
        import requests as _req
        from flamezo_backend.flamezo.media.storage import upload_object, get_cdn_url

        _CDN_HEADERS = {
            "User-Agent": "Mozilla/5.0 (compatible; Flamezo/1.0; story-generator)",
        }

        with tempfile.TemporaryDirectory() as tmp:

            # 1. Download source media from CDN (server-side — no CORS).
            #    If the raw file was cleaned up after processing, the processed
            #    variant usually survives in the same folder — try it as a fallback.
            src_ext  = "mp4" if media_type == "video" else "jpg"
            src_path = os.path.join(tmp, f"source.{src_ext}")

            candidates = [template_url]
            if "/raw." in template_url:
                base = template_url.rsplit("/", 1)[0]
                if media_type == "video":
                    candidates.append(f"{base}/video_720p.mp4")
                else:
                    candidates += [f"{base}/large.webp", f"{base}/medium.webp"]

            downloaded = False
            last_status = None
            for cand in candidates:
                resp = _req.get(cand, timeout=120, stream=True, headers=_CDN_HEADERS)
                last_status = resp.status_code
                if resp.status_code == 200:
                    with open(src_path, "wb") as f:
                        for chunk in resp.iter_content(65536):
                            f.write(chunk)
                    downloaded = True
                    resp.close()
                    break
                resp.close()

            if not downloaded:
                # Media genuinely missing from the CDN — clear message beats a
                # generic "generation failed" so the merchant knows to re-upload.
                _set_cache(job_id, {
                    "status": "error",
                    "error": f"Template media not found (HTTP {last_status}). Please re-upload the media.",
                })
                return

            # 2. Get native dimensions
            if media_type == "video":
                w, h = _video_dims(src_path)
            else:
                from PIL import Image as _PIL
                with _PIL.open(src_path) as im:
                    w, h = im.size

            # 3. Render overlay PNG at native resolution
            overlay_path = os.path.join(tmp, "overlay.png")
            _render_overlay(
                tmp, overlay_path, w, h,
                restaurant_name, coupon_code, discount_type,
                discount_value, offer_description, valid_until,
            )

            # 4. Composite media + overlay
            out_ext  = "mp4" if media_type == "video" else "jpg"
            out_path = os.path.join(tmp, f"output.{out_ext}")
            if media_type == "video":
                _composite_video(src_path, overlay_path, w, h, out_path)
            else:
                _composite_image(src_path, overlay_path, out_path)

            # 5. Upload to R2 (temp prefix, lifecycle rule cleans up after 24 h)
            object_key   = f"{TEMP_KEY_PREFIX}/{job_id}.{out_ext}"
            content_type = "video/mp4" if media_type == "video" else "image/jpeg"
            upload_object(out_path, object_key, content_type=content_type)
            cdn_url = get_cdn_url(object_key)

        _set_cache(job_id, {"status": "done", "url": cdn_url, "ext": out_ext})

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Story Generator Job Failed")
        _set_cache(job_id, {"status": "error", "error": "Generation failed. Please try again."})


# ─── Overlay Rendering ────────────────────────────────────────────────────────

def _render_overlay(tmp, out_png, w, h, restaurant_name, coupon_code,
                    discount_type, discount_value, offer_description, valid_until):
    """
    Render the overlay at w×h resolution.
    Tries Chrome headless first (best quality — matches React component exactly).
    Falls back to Pillow-based compositing (no frosted glass, but functional).
    """
    chrome = _find_chrome()
    if chrome:
        html_path = os.path.join(tmp, "overlay.html")
        _write_overlay_html(html_path, w, h, restaurant_name, coupon_code,
                            discount_type, discount_value, offer_description, valid_until)
        result = subprocess.run(
            [
                chrome,
                "--headless=new", "--disable-gpu",
                f"--screenshot={out_png}",
                f"--window-size={w},{h}",
                "--hide-scrollbars",
                "--default-background-color=00000000",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                html_path,
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and os.path.exists(out_png):
            return

        frappe.log_error(result.stderr.decode()[:2000], "Chrome headless overlay failed — using Pillow fallback")

    # Pillow fallback
    _render_overlay_pillow(out_png, w, h, restaurant_name, coupon_code,
                           discount_type, discount_value, offer_description, valid_until)


def _write_overlay_html(path, w, h, restaurant_name, coupon_code,
                        discount_type, discount_value, offer_description, valid_until):
    """Generate the overlay HTML at native resolution — mirrors StoryTemplateFrame.tsx."""

    # Embed logo as base64 data URL
    logo_b64 = ""
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    # Generate QR code
    import qrcode, io
    qr_img = qrcode.make(WA_CHANNEL_URL)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    logo_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""
    qr_src   = f"data:image/png;base64,{qr_b64}"

    # Typography helpers (same ratios as React component)
    def fz(ratio):
        return max(7, round(w * ratio))

    pad       = round(w * 0.038)
    logo_w    = round(w * 0.28)
    chip_py   = round(w * 0.014)
    chip_px   = round(w * 0.020)
    chip_br   = round(w * 0.04)
    qr_size   = round(w * 0.17)
    qr_pad    = max(2, round(w * 0.008))
    qr_gap    = round(w * 0.018)
    strip_w   = round(w * 0.82)
    strip_bot = round(h * 0.22)
    strip_py  = round(w * 0.024)
    strip_px  = round(w * 0.032)
    row_gap   = round(w * 0.010)
    chip2_br  = round(w * 0.014)

    # Discount headline
    dv = float(discount_value) if discount_value else 0
    if dv:
        discount_line  = f"{int(dv)}% OFF" if discount_type == "percentage" else f"₹{int(dv)} OFF"
        headline_fs    = fz(0.058)
        headline_ls    = "-0.01em"
    elif coupon_code:
        discount_line  = "Exclusive Offer"
        headline_fs    = fz(0.038)
        headline_ls    = "0.01em"
    else:
        discount_line  = None
        headline_fs    = fz(0.038)
        headline_ls    = "0"

    # Validity label
    validity_label = ""
    if valid_until:
        try:
            from datetime import datetime
            d = datetime.strptime(str(valid_until)[:10], "%Y-%m-%d")
            validity_label = f"Valid till {d.day} {MONTHS[d.month - 1]}"
        except Exception:
            pass

    # Build HTML pieces
    desc_html = ""
    if offer_description:
        desc_html = f"""
        <p style="color:rgba(255,255,255,0.55);font-size:{fz(0.026)}px;margin:0;line-height:1.3;font-weight:400;
                   display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">
          {offer_description}
        </p>"""

    tnc_text = f"{validity_label} · T&amp;C apply" if validity_label else "T&amp;C apply"
    validity_html = f"""
        <p style="color:rgba(183,65,14,1);font-size:{fz(0.021)}px;margin:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          {tnc_text}
        </p>"""

    coupon_chip_html = ""
    if coupon_code:
        coupon_chip_html = f"""
        <div style="border:1px dashed rgba(183,65,14,0.85);border-radius:{chip2_br}px;
                    padding:{round(w*0.006)}px {round(w*0.014)}px;background:rgba(183,65,14,0.20);
                    flex-shrink:0;max-width:{round(w*0.44)}px;overflow:hidden;">
          <span style="color:#fff;font-size:{fz(0.024)}px;font-weight:800;letter-spacing:0.04em;
                       font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;">
            {coupon_code}
          </span>
        </div>"""

    headline_html = ""
    if discount_line:
        headline_html = f"""
        <p style="color:#fff;font-size:{headline_fs}px;font-weight:800;line-height:1;margin:0;
                  letter-spacing:{headline_ls};white-space:nowrap;">
          {discount_line}
        </p>"""

    restaurant_html = ""
    if restaurant_name:
        restaurant_html = f"""
        <p style="color:rgba(255,255,255,0.45);font-size:{fz(0.021)}px;margin:0;font-weight:600;
                  letter-spacing:0.055em;text-transform:uppercase;white-space:nowrap;
                  overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;">
          {restaurant_name}
        </p>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{w}px; height:{h}px; background:transparent; overflow:hidden; position:relative;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
</style></head><body>

<!-- Bottom vignette -->
<div style="position:absolute;inset:0;pointer-events:none;
            background:linear-gradient(to bottom,rgba(0,0,0,0) 25%,rgba(0,0,0,0.25) 50%,rgba(0,0,0,0.65) 75%,rgba(0,0,0,0.88) 100%);"></div>


<!-- Coupon strip -->
<div style="position:absolute;bottom:{strip_bot}px;left:50%;transform:translateX(-50%);
            width:{strip_w}px;background:rgba(10,10,12,0.55);
            backdrop-filter:blur(24px) saturate(1.6);-webkit-backdrop-filter:blur(24px) saturate(1.6);
            border-radius:{round(w*0.035)}px;border:0.5px solid rgba(255,255,255,0.14);
            padding:{strip_py}px {strip_px}px;display:flex;flex-direction:column;gap:{row_gap}px;overflow:hidden;">

  <!-- Row 1: restaurant name + coupon chip -->
  <div style="display:flex;flex-direction:row;align-items:center;justify-content:space-between;gap:{round(w*0.02)}px;">
    {restaurant_html}
    {coupon_chip_html}
  </div>

  {headline_html}
  {desc_html}
  {validity_html}

  <!-- CTA -->
  <p style="color:rgba(255,255,255,0.3);font-size:{fz(0.019)}px;margin:0;line-height:1.3;">
    Show at checkout · Take a screenshot now
  </p>
</div>

</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def _render_overlay_pillow(out_png, w, h, restaurant_name, coupon_code,
                            discount_type, discount_value, offer_description, valid_until):
    """Pillow fallback overlay — draws the full FLAMEZO frame (logo + QR + coupon
    card) burned into the media. Used when headless Chrome is unavailable so the
    downloaded/shared story still carries the frame."""
    from PIL import Image, ImageDraw, ImageFont
    import qrcode

    _F_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    _F_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def font(size, bold=True):
        try:
            return ImageFont.truetype(_F_BOLD if bold else _F_REG, max(8, int(size)))
        except Exception:
            return ImageFont.load_default()

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Bottom vignette gradient — keeps the coupon card readable over any media.
    for y in range(h):
        t = max(0.0, (y / h - 0.35) / 0.65)
        alpha = int(min(235, t * t * 235))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    pad = int(w * 0.04)

    # ── Logo (top-left) on a frosted chip ──
    try:
        if os.path.exists(LOGO_PATH):
            logo = Image.open(LOGO_PATH).convert("RGBA")
            lw = int(w * 0.30)
            lh = max(1, int(lw * logo.height / logo.width))
            logo = logo.resize((lw, lh), Image.LANCZOS)
            cp = int(w * 0.02)
            draw.rounded_rectangle(
                (pad - cp, pad - cp, pad + lw + cp, pad + lh + cp),
                radius=int(w * 0.03), fill=(255, 255, 255, 55),
            )
            overlay.alpha_composite(logo, (pad, pad))
    except Exception:
        pass

    # ── QR (top-right) + caption ──
    try:
        qs = int(w * 0.18)
        qr_img = qrcode.make(WA_CHANNEL_URL).convert("RGBA").resize((qs, qs), Image.NEAREST)
        qx, qy = w - pad - qs, pad
        qp = max(2, int(qs * 0.06))
        draw.rounded_rectangle(
            (qx - qp, qy - qp, qx + qs + qp, qy + qs + qp),
            radius=int(w * 0.015), fill=(255, 255, 255, 255),
        )
        overlay.alpha_composite(qr_img, (qx, qy))
        cap, cf = "Scan to join", font(int(w * 0.026), bold=False)
        cw = draw.textlength(cap, font=cf)
        draw.text((qx + qs / 2 - cw / 2, qy + qs + qp + int(h * 0.006)),
                  cap, font=cf, fill=(255, 255, 255, 220))
    except Exception:
        pass

    # ── Coupon card (bottom) ──
    is_percent = (discount_type or "").lower() in ("percent", "percentage")
    if discount_value:
        discount_line = f"{int(discount_value)}% OFF" if is_percent else f"₹{int(discount_value)} OFF"
    elif coupon_code:
        discount_line = "Exclusive Offer"
    else:
        discount_line = ""

    rows = []
    if restaurant_name:
        rows.append((restaurant_name.upper(), font(int(w * 0.028)), (255, 255, 255, 150)))
    if discount_line:
        rows.append((discount_line, font(int(w * 0.075)), (255, 255, 255, 255)))
    rows.append((offer_description or "on your next visit", font(int(w * 0.030), bold=False), (255, 255, 255, 175)))
    rows.append(("T&C apply", font(int(w * 0.026)), (218, 165, 32, 255)))
    rows.append(("Show at checkout · Take a screenshot now", font(int(w * 0.024), bold=False), (255, 255, 255, 110)))

    gap = int(h * 0.011)
    heights = [draw.textbbox((0, 0), t, font=f)[3] for t, f, _ in rows]
    card_w = int(w * 0.86)
    card_x = int((w - card_w) / 2)
    card_h = sum(heights) + gap * (len(rows) + 1)
    card_y = h - int(h * 0.075) - card_h
    inset  = int(w * 0.045)

    draw.rounded_rectangle(
        (card_x, card_y, card_x + card_w, card_y + card_h),
        radius=int(w * 0.035), fill=(10, 10, 12, 185),
    )

    # Coupon-code chip on the first row (dashed-gold look → solid gold outline)
    if coupon_code:
        code_f = font(int(w * 0.026))
        code_w = draw.textlength(coupon_code, font=code_f)
        cpx, cpy = int(w * 0.018), int(h * 0.006)
        ch = draw.textbbox((0, 0), coupon_code, font=code_f)[3]
        chip_x2 = card_x + card_w - inset
        chip_x1 = chip_x2 - code_w - cpx * 2
        chip_y1 = card_y + gap
        draw.rounded_rectangle(
            (chip_x1, chip_y1, chip_x2, chip_y1 + ch + cpy * 2),
            radius=int(w * 0.012), outline=(218, 165, 32, 230), width=2, fill=(218, 165, 32, 45),
        )
        draw.text((chip_x1 + cpx, chip_y1 + cpy), coupon_code, font=code_f, fill=(255, 255, 255, 255))

    ty = card_y + gap
    tx = card_x + inset
    for (txt, f, color), hgt in zip(rows, heights):
        draw.text((tx, ty), txt, font=f, fill=color)
        ty += hgt + gap

    overlay.save(out_png, "PNG")


# ─── Video / Image Compositing ────────────────────────────────────────────────

def _video_dims(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


def _composite_video(src, overlay, vw, vh, out):
    filter_complex = f"[1:v]scale={vw}:{vh}[ov];[0:v][ov]overlay=0:0"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", src,
            "-i", overlay,
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-threads", "0",
            "-c:a", "copy",
            "-movflags", "+faststart",
            out,
        ],
        capture_output=True, timeout=180,
    )
    if result.returncode != 0:
        frappe.log_error(result.stderr.decode()[:3000], "ffmpeg composite failed")
        frappe.throw("Video compositing failed.")


def _composite_image(src, overlay, out):
    from PIL import Image
    base    = Image.open(src).convert("RGBA")
    ov      = Image.open(overlay).convert("RGBA").resize(base.size, Image.LANCZOS)
    result  = Image.alpha_composite(base, ov).convert("RGB")
    result.save(out, "JPEG", quality=92)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cdn_url_allowed(url):
    try:
        host = urlparse(url).hostname or ""
        return any(host == d or host.endswith("." + d) for d in _ALLOWED_CDN)
    except Exception:
        return False


def _find_chrome():
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _set_cache(job_id, data):
    frappe.cache().set_value(f"story_dl_{job_id}", data, expires_in_sec=CACHE_TTL)


def _get_cache(job_id):
    return frappe.cache().get_value(f"story_dl_{job_id}")
