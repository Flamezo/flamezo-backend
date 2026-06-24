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

@frappe.whitelist()
def start_story_download(
    template_url, media_type,
    restaurant_name="",
    coupon_code=None, discount_type=None, discount_value=None,
    offer_description=None, valid_until=None,
):
    """
    Validate inputs, enqueue the generation job, return {job_id} immediately.
    The frontend polls get_story_download_status() until status == 'done'.
    """
    if not _cdn_url_allowed(template_url):
        frappe.throw("Media URL is not from an allowed CDN domain.", frappe.PermissionError)

    if media_type not in ("image", "video"):
        frappe.throw("Invalid media_type.")

    job_id = str(uuid.uuid4())
    _set_cache(job_id, {"status": "pending"})

    frappe.enqueue(
        "flamezo_backend.flamezo.api.story_generator._run_job",
        queue="long",
        timeout=300,
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

            # 1. Download source media from CDN (server-side — no CORS)
            src_ext  = "mp4" if media_type == "video" else "jpg"
            src_path = os.path.join(tmp, f"source.{src_ext}")
            r = _req.get(template_url, timeout=120, stream=True, headers=_CDN_HEADERS)
            r.raise_for_status()
            with open(src_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)

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

<!-- Top-left: Flamezo logo chip -->
<div style="position:absolute;top:{pad}px;left:{pad}px;display:inline-flex;align-items:center;
            justify-content:center;padding:{chip_py}px {chip_px}px;background:rgba(255,255,255,0.22);
            backdrop-filter:blur(14px) saturate(1.6);-webkit-backdrop-filter:blur(14px) saturate(1.6);
            border-radius:{chip_br}px;border:0.5px solid rgba(255,255,255,0.35);
            box-shadow:0 2px 10px rgba(0,0,0,0.25);">
  <img src="{logo_src}" style="width:{logo_w}px;height:auto;object-fit:contain;display:block;">
</div>

<!-- Top-right: QR + label -->
<div style="position:absolute;top:{pad}px;right:{pad}px;display:flex;flex-direction:column;
            align-items:center;gap:{qr_gap}px;">
  <div style="width:{qr_size}px;height:{qr_size}px;background:#fff;
              border-radius:{round(w*0.018)}px;padding:{qr_pad}px;box-shadow:0 2px 8px rgba(0,0,0,.45);">
    <img src="{qr_src}" style="width:100%;height:100%;display:block;object-fit:contain;">
  </div>
  <p style="color:rgba(255,255,255,0.7);font-size:{fz(0.024)}px;font-weight:500;text-align:center;
            line-height:1.25;text-shadow:0 1px 3px rgba(0,0,0,.8);margin:0;">Scan to join</p>
</div>

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
    """Pillow fallback overlay — no frosted glass, simpler but reliable."""
    from PIL import Image, ImageDraw, ImageFont
    import io, qrcode

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Bottom vignette gradient
    for y in range(h):
        t = max(0.0, (y / h - 0.25) / 0.75)  # 0 → 1 from 25% to 100%
        alpha = int(min(224, t * t * 224))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    # Logo chip
    if os.path.exists(LOGO_PATH):
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_w = round(w * 0.28)
        logo_h = round(logo.height * logo_w / logo.width)
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        pad = round(w * 0.038)
        chip_px = round(w * 0.020)
        chip_py = round(w * 0.014)
        chip_x, chip_y = pad, pad
        chip_w = logo_w + 2 * chip_px
        chip_h = logo_h + 2 * chip_py
        chip = Image.new("RGBA", (chip_w, chip_h), (255, 255, 255, 56))
        overlay.paste(chip, (chip_x, chip_y), chip)
        overlay.paste(logo, (chip_x + chip_px, chip_y + chip_py), logo)

    # QR code
    qr_img  = qrcode.make(WA_CHANNEL_URL).convert("RGBA")
    qr_size = round(w * 0.17)
    qr_img  = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    pad     = round(w * 0.038)
    qr_x    = w - pad - qr_size
    qr_y    = pad
    bg_qr   = Image.new("RGBA", (qr_size, qr_size), (255, 255, 255, 255))
    overlay.paste(bg_qr, (qr_x, qr_y))
    overlay.paste(qr_img, (qr_x, qr_y), qr_img)

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
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
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
