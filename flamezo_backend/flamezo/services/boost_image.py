"""
Flamezo Boost — Ad creative image refinement.

Turns a raw food photo into a Meta-ready ad creative WITHOUT regenerating the
photo itself. The dish pixels are never re-drawn by AI; we only:

  1. ANALYZE the photo (Gemini vision) to understand what's already on it
     (food vs. not, address/branding/offer text already present) and where the
     overlays should sit (cleanest corner for the logo, best band for the offer,
     light/dark tone for legibility). Returns a structured dict + a refinement
     prompt. Falls back to safe defaults when the API key/response is missing.

  2. COMPOSE the creative with Pillow (deterministic, testable):
       • Full-bleed photo in the best feed aspect (4:5 / 1:1), lightly graded
         and vignetted for a magazine-quality pop — the dish is never redrawn.
       • One frosted-glass offer card: orange label pill + "FLAT ₹X OFF" hero +
         restaurant·locality line + coupon chip + a circular CTA arrow.
       • A discreet Flamezo wordmark in the opposite corner.
     Consolidating into a single card keeps the text footprint low (better Meta
     reach) and looks premium.

The two stages are independent: `compose_ad_overlays()` is a pure function with
no `frappe`/network dependency so it can be unit-tested offline. `frappe` is
imported lazily only inside the orchestration / job helpers.
"""
import os
import json
import base64
import uuid

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageEnhance


# ─── Constants & palette ────────────────────────────────────────────

# Meta feed canvases. Portrait 4:5 (1080×1350) is the highest-performing feed
# format (most screen real-estate); square 1:1 is used for landscape sources so
# we don't crop them aggressively.
SQUARE = (1080, 1080)
PORTRAIT = (1080, 1350)
BRAND_NAME = "Flamezo"

# Brand orange gradient (matches the web UI from-orange-500 to-amber-600)
ORANGE_FROM = (249, 115, 22)        # #F97316
ORANGE_TO = (217, 119, 47)          # #D9782F  (amber-600-ish)
WHITE = (255, 255, 255)
INK = (17, 17, 17)

# Real Flamezo wordmark (white version) — composited by code for pixel-perfect,
# consistent branding instead of relying on the AI to draw it.
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "public",
                          "flamezo_backend", "images", "main-logo-dark.png")

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "media", "fonts")
# System fallbacks so rendering still works if bundled fonts go missing.
_SYS_FONTS = {
    "ExtraBold": ["/Library/Fonts/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "Bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "SemiBold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "Medium": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "Regular": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}

_FONT_CACHE = {}


def _font(weight, size):
    """Load a bundled Poppins weight, falling back to a system font."""
    key = (weight, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    candidates = [os.path.join(_FONT_DIR, f"Poppins-{weight}.ttf")] + _SYS_FONTS.get(weight, [])
    for path in candidates:
        try:
            if os.path.exists(path):
                f = ImageFont.truetype(path, size)
                _FONT_CACHE[key] = f
                return f
        except Exception:
            continue

    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _has_glyph(font, ch):
    try:
        return font.getmask(ch).getbbox() is not None
    except Exception:
        return False


def _rupee(font, amount):
    """'₹100' when the font has the glyph, else 'Rs 100'."""
    n = int(round(float(amount)))
    return f"₹{n}" if _has_glyph(font, "₹") else f"Rs {n}"


# ─── Low-level drawing helpers ──────────────────────────────────────

def _text_size(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return r - l, b - t


def _fit_font(weight, text, max_width, start_size, min_size=14):
    """Largest font of `weight` that renders `text` within `max_width`."""
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    size = start_size
    while size > min_size:
        f = _font(weight, size)
        if _text_size(scratch, text, f)[0] <= max_width:
            return f
        size -= 2
    return _font(weight, min_size)


def _truncate(draw, text, font, max_width):
    if _text_size(draw, text, font)[0] <= max_width:
        return text
    ell = "…"
    while text and _text_size(draw, text + ell, font)[0] > max_width:
        text = text[:-1]
    return (text + ell) if text else ell


def _diagonal_brand_gradient(size):
    """Orange→amber diagonal gradient used for the offer ribbon."""
    w, h = size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    denom = max(w + h - 2, 1)
    for y in range(h):
        for x in range(w):
            t = (x + y) / denom
            px[x, y] = tuple(
                int(ORANGE_FROM[i] + (ORANGE_TO[i] - ORANGE_FROM[i]) * t) for i in range(3)
            )
    return grad


def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def _drop_shadow(layer_rgba, blur=18, offset=(0, 10), opacity=120):
    """Return an RGBA shadow image sized to fit layer + blur padding."""
    pad = blur * 3
    w, h = layer_rgba.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    alpha = layer_rgba.split()[3].point(lambda a: min(a, opacity))
    shadow = Image.new("RGBA", layer_rgba.size, (0, 0, 0, 0))
    shadow.putalpha(alpha)
    black = Image.new("RGBA", layer_rgba.size, (0, 0, 0, 255))
    black.putalpha(alpha)
    canvas.paste(black, (pad + offset[0], pad + offset[1]), black)
    return canvas.filter(ImageFilter.GaussianBlur(blur)), pad


def _paste_with_shadow(canvas, layer_rgba, xy, blur=18, offset=(0, 10), opacity=120):
    shadow, pad = _drop_shadow(layer_rgba, blur, offset, opacity)
    canvas.alpha_composite(shadow, (xy[0] - pad, xy[1] - pad))
    canvas.alpha_composite(layer_rgba, xy)


# ─── Text helpers (letter-spacing, glyphs) ──────────────────────────

def _tracked_width(draw, text, font, tracking):
    w = 0
    for ch in text:
        w += _text_size(draw, ch, font)[0] + tracking
    return max(0, w - tracking)


def _draw_tracked_text(draw, xy, text, font, fill, tracking):
    """Draw letter-spaced text (Pillow has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += _text_size(draw, ch, font)[0] + tracking


def _draw_pin(draw, xy, size, fill=WHITE, accent=ORANGE_FROM):
    """A small map-pin (teardrop) glyph."""
    x, y = xy
    draw.ellipse([x, y, x + size, y + size], fill=fill)
    draw.polygon([(x + size * 0.18, y + size * 0.68),
                  (x + size * 0.82, y + size * 0.68),
                  (x + size * 0.5, y + size + size * 0.28)], fill=fill)
    r = size * 0.18
    cx, cy = x + size / 2, y + size * 0.46
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)


def _draw_arrow(draw, center, size, fill=WHITE, width=None):
    """A clean right-pointing chevron arrow (CTA cue)."""
    cx, cy = center
    w = width or max(4, int(size * 0.26))
    draw.line([(cx - size * 0.85, cy), (cx + size * 0.55, cy)], fill=fill, width=w)
    draw.line([(cx + size * 0.02, cy - size * 0.6), (cx + size * 0.62, cy)], fill=fill, width=w)
    draw.line([(cx + size * 0.02, cy + size * 0.6), (cx + size * 0.62, cy)], fill=fill, width=w)


# ─── Photo treatment (full-bleed, graded, vignetted) ────────────────

def _color_grade(img):
    """Subtle magazine-grade pop — never enough to alter the dish."""
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Brightness(img).enhance(1.015)
    img = ImageEnhance.Sharpness(img).enhance(1.18)
    return img


def _vignette(canvas, strength=88):
    """Gently darken the edges to focus the eye on the dish."""
    w, h = canvas.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse(
        [int(-w * 0.22), int(-h * 0.22), int(w * 1.22), int(h * 1.22)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(int(w * 0.16)))
    edges = ImageOps.invert(mask).point(lambda a: int(a / 255 * strength))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    dark.putalpha(edges)
    canvas.alpha_composite(dark)


def _build_base(img):
    """
    Full-bleed Meta creative: cover-crop into the best feed aspect (4:5 for
    portrait sources, 1:1 for square/landscape), then grade + vignette.
    No blurred letterbox bars — the dish fills the whole frame.
    """
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    target = PORTRAIT if (w / h) < 0.9 else SQUARE
    base = ImageOps.fit(img, target, method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
    base = _color_grade(base)
    canvas = base.convert("RGBA")
    _vignette(canvas)
    return canvas


def _frosted_panel(canvas, box, radius):
    """A frosted-glass panel sampled from the image region under `box`."""
    region = canvas.crop(box).convert("RGB").filter(ImageFilter.GaussianBlur(20))
    panel = region.convert("RGBA")
    panel.alpha_composite(Image.new("RGBA", panel.size, (12, 12, 16, 162)))
    ImageDraw.Draw(panel).rounded_rectangle(
        [1, 1, panel.size[0] - 2, panel.size[1] - 2], radius=radius - 1,
        outline=(255, 255, 255, 46), width=2)
    return panel, _rounded_mask(panel.size, radius)


def _paste_rounded_with_shadow(canvas, panel, mask, xy, blur=26, offset=(0, 16), opacity=120):
    panel = panel.copy()
    panel.putalpha(mask)
    pad = blur * 3
    sh = Image.new("RGBA", (panel.width + pad * 2, panel.height + pad * 2), (0, 0, 0, 0))
    alpha = mask.point(lambda a: int(a * opacity / 255))
    black = Image.new("RGBA", panel.size, (0, 0, 0, 255))
    black.putalpha(alpha)
    sh.paste(black, (pad + offset[0], pad + offset[1]), black)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (xy[0] - pad, xy[1] - pad))
    canvas.alpha_composite(panel, xy)


def _resolve_logo_corner(analysis, offer_position, has_offer):
    """
    The offer card spans the full width of its band, so the wordmark goes to the
    opposite band. Honour the analysis' left/right preference for the corner.
    """
    requested = analysis.get("logo_corner", "top-right") or "top-right"
    side = "left" if requested.endswith("left") else "right"
    if has_offer and offer_position == "bottom":
        return f"top-{side}"
    if has_offer and offer_position == "top":
        return f"bottom-{side}"
    return requested


LIGHT_ORANGE = (253, 186, 116)      # #FDBA74 — warm accent on dark glass


def _coupon_chip(coupon_code):
    """Translucent glass chip: 'CODE · XXXX' — fits the frosted card."""
    if not coupon_code:
        return None, 0, 0
    label_font = _font("SemiBold", 22)
    code_font = _font("Bold", 28)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    label, code = "CODE", coupon_code.upper()
    pad_x, pad_y, gap = 22, 13, 13
    lw, lh = _text_size(scratch, label, label_font)
    cw, ch = _text_size(scratch, code, code_font)
    h = max(lh, ch) + pad_y * 2
    w = pad_x + lw + gap + 2 + gap + cw + pad_x

    chip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = _rounded_mask((w, h), h // 2)
    chip.paste(Image.new("RGBA", (w, h), (255, 255, 255, 30)), (0, 0), mask)
    d = ImageDraw.Draw(chip)
    d.rounded_rectangle([1, 1, w - 2, h - 2], radius=h // 2 - 1, outline=(255, 255, 255, 150), width=2)
    d.text((pad_x, (h - lh) // 2), label, font=label_font, fill=(255, 255, 255, 165))
    dx = pad_x + lw + gap
    d.line([(dx, pad_y), (dx, h - pad_y)], fill=(255, 255, 255, 90), width=2)
    d.text((dx + gap + 2, (h - ch) // 2), code, font=code_font, fill=LIGHT_ORANGE)
    return chip, w, h


def _draw_offer_card(canvas, *, offer_headline, offer_detail=None, coupon_code=None,
                     restaurant_name=None, location=None, position="bottom"):
    """
    One elegant frosted-glass card holding the whole offer: a small orange label
    pill, the big dynamic offer headline (e.g. 'FLAT ₹100 OFF', 'BUY 1 GET 1
    FREE'), the restaurant + locality line, the coupon chip, and a circular CTA
    arrow. Consolidating into a single card keeps the text footprint low and
    looks premium.
    """
    W, H = canvas.size
    margin = 44
    card_w = W - margin * 2
    pad = 46
    cta_r = 44
    inner_w = card_w - pad * 2
    text_w = inner_w - (cta_r * 2 + 26)

    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # Content & fonts
    label = "LIMITED-TIME OFFER"
    label_font = _font("Bold", 22)
    hero_font = _font("ExtraBold", 90)
    sub_font = _font("Medium", 30)
    detail_font = _font("Medium", 26)
    tracking = 3

    hero = (offer_headline or "").strip()
    if _text_size(scratch, hero, hero_font)[0] > text_w:
        hero_font = _fit_font("ExtraBold", hero, text_w, 90, 42)
    hero_w, hero_h = _text_size(scratch, hero, hero_font)

    detail = _truncate(scratch, offer_detail, detail_font, text_w) if offer_detail else None
    detail_h = _text_size(scratch, detail, detail_font)[1] if detail else 0

    loc_bits = [b for b in [restaurant_name, location] if b]
    sub = "  ·  ".join(loc_bits)
    pin_w = 24
    sub = _truncate(scratch, sub, sub_font, text_w - (pin_w + 12))
    sub_w, sub_h = _text_size(scratch, sub, sub_font)

    lpad_x, lpad_y = 16, 9
    label_w = _tracked_width(scratch, label, label_font, tracking)
    label_h = _text_size(scratch, "Ag", label_font)[1]
    pill_w, pill_h = label_w + lpad_x * 2, label_h + lpad_y * 2

    chip, chip_w, chip_h = _coupon_chip(coupon_code)

    g1, gd, g2, g3 = 20, 8, 16, 22
    block_h = (pill_h + g1 + hero_h + (gd + detail_h if detail else 0)
               + g2 + sub_h + (g3 + chip_h if chip else 0))
    card_h = max(block_h, cta_r * 2) + pad * 2

    y0 = margin if position == "top" else H - margin - card_h
    box = (margin, y0, margin + card_w, y0 + card_h)
    panel, mask = _frosted_panel(canvas, box, radius=42)
    _paste_rounded_with_shadow(canvas, panel, mask, (margin, y0))

    d = ImageDraw.Draw(canvas)
    cx = margin + pad
    cy = y0 + (card_h - block_h) // 2

    # Label pill (the colour pop)
    d.rounded_rectangle([cx, cy, cx + pill_w, cy + pill_h], radius=pill_h // 2, fill=ORANGE_FROM)
    _draw_tracked_text(d, (cx + lpad_x, cy + lpad_y), label, label_font, WHITE, tracking)
    cy += pill_h + g1

    # Hero offer (dynamic — flat ₹, BOGO, % off, free item …)
    d.text((cx, cy), hero, font=hero_font, fill=WHITE)
    cy += hero_h
    if detail:
        cy += gd
        d.text((cx, cy), detail, font=detail_font, fill=LIGHT_ORANGE)
        cy += detail_h
    cy += g2

    # Restaurant · locality with a pin
    if sub:
        _draw_pin(d, (cx, cy + (sub_h - pin_w) // 2), pin_w)
        d.text((cx + pin_w + 12, cy), sub, font=sub_font, fill=(255, 255, 255, 235))
    cy += sub_h

    # Coupon chip
    if chip:
        cy += g3
        canvas.alpha_composite(chip, (cx, cy))

    # Circular CTA arrow, vertically centred
    ccx = margin + card_w - pad - cta_r
    ccy = y0 + card_h // 2
    _paste_with_shadow(canvas, _orange_disc(cta_r), (ccx - cta_r, ccy - cta_r), blur=14, offset=(0, 6), opacity=110)
    _draw_arrow(d, (ccx, ccy), cta_r * 0.42, fill=WHITE, width=max(4, int(cta_r * 0.16)))


def _orange_disc(r):
    """An orange-gradient filled circle (CTA button)."""
    size = (r * 2, r * 2)
    disc = _diagonal_brand_gradient(size).convert("RGBA")
    disc.putalpha(_circle_mask(size))
    ImageDraw.Draw(disc).ellipse([2, 2, size[0] - 3, size[1] - 3], outline=(255, 255, 255, 90), width=2)
    return disc


def _circle_mask(size):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, size[0] - 1, size[1] - 1], fill=255)
    return m


def _draw_wordmark(canvas, corner="top-right"):
    """Discreet Flamezo lozenge: orange bolt + 'Flamezo' on a translucent pill."""
    W, H = canvas.size
    name_font = _font("SemiBold", 26)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    name_w, name_h = _text_size(scratch, BRAND_NAME, name_font)

    pad_x, pad_y, bolt_w, gap = 18, 10, 18, 10
    w = pad_x + bolt_w + gap + name_w + pad_x
    h = name_h + pad_y * 2

    pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pill.paste(Image.new("RGBA", (w, h), (0, 0, 0, 125)), (0, 0), _rounded_mask((w, h), h // 2))
    d = ImageDraw.Draw(pill)

    bx, by, bh = pad_x, pad_y, name_h
    bolt = [
        (bx + bolt_w * 0.55, by),
        (bx + bolt_w * 0.05, by + bh * 0.58),
        (bx + bolt_w * 0.45, by + bh * 0.58),
        (bx + bolt_w * 0.30, by + bh),
        (bx + bolt_w * 0.95, by + bh * 0.40),
        (bx + bolt_w * 0.50, by + bh * 0.40),
    ]
    d.polygon(bolt, fill=ORANGE_FROM)
    d.text((pad_x + bolt_w + gap, pad_y), BRAND_NAME, font=name_font, fill=(255, 255, 255, 235))

    m = 30
    pos = {
        "bottom-right": (W - w - m, H - h - m),
        "bottom-left": (m, H - h - m),
        "top-right": (W - w - m, m),
        "top-left": (m, m),
    }.get(corner, (W - w - m, m))
    canvas.alpha_composite(pill, pos)
    return pos, (w, h)


# ─── Public: deterministic compositor (no frappe / network) ─────────

def _short_location(text):
    """Reduce a full address to a short, ad-friendly locality (e.g. 'Surat')."""
    import re
    if not text:
        return None
    parts = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
    parts = [p for p in parts if not re.search(r"\d{4,}", p) and p.lower() != "india"]
    return parts[-1] if parts else None


def compose_ad_overlays(
    image_path,
    *,
    offer_amount=0,
    offer_headline=None,
    offer_detail=None,
    coupon_code=None,
    restaurant_name=None,
    address=None,
    area=None,
    analysis=None,
    add_offer=True,
    add_branding=True,
    add_address=True,
    output_path=None,
):
    """
    Composite a premium ad creative onto a food photo.

    The dish is never regenerated — the photo is full-bleed, lightly graded and
    vignetted, then a single frosted-glass offer card + a discreet Flamezo
    wordmark are drawn on top. `area`/`address` only set the small locality line
    inside the card (kept short for legibility and Meta reach).

    Returns the path to the written JPEG.
    """
    analysis = analysis or {}
    offer_position = analysis.get("offer_position", "bottom")
    if analysis.get("has_offer_text"):
        add_offer = False
    if analysis.get("has_branding_text"):
        add_branding = False
    if analysis.get("has_address_text"):
        add_address = False

    headline = offer_headline or (_default_offer_headline(offer_amount) if offer_amount else None)
    show_offer = bool(add_offer and headline)
    location = area or (_short_location(address) if add_address else None)

    with Image.open(image_path) as im:
        canvas = _build_base(im)

    if show_offer:
        _draw_offer_card(
            canvas,
            offer_headline=headline,
            offer_detail=offer_detail,
            coupon_code=coupon_code,
            restaurant_name=restaurant_name,
            location=location,
            position=offer_position,
        )

    if add_branding:
        corner = _resolve_logo_corner(analysis, offer_position, show_offer)
        _draw_wordmark(canvas, corner=corner)

    out = output_path or f"/tmp/{uuid.uuid4().hex}.jpg"
    canvas.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out


# ─── Gemini vision analysis ─────────────────────────────────────────

_ANALYSIS_DEFAULTS = {
    "is_food": True,
    "has_address_text": False,
    "has_branding_text": False,
    "has_offer_text": False,
    "logo_corner": "top-right",
    "offer_position": "bottom",
    "tone": "dark",
    "description": "",
    "refinement_prompt": "",
}


def _analysis_prompt(restaurant_name):
    return (
        "You are a senior ad-creative director reviewing a restaurant photo that will become a "
        "Meta (Instagram/Facebook) ad. Inspect the image and return ONLY strict JSON, no prose, "
        "with exactly these keys:\n"
        '{\n'
        '  "is_food": bool,                      // is the main subject food/drink/restaurant\n'
        '  "has_address_text": bool,             // is a street address already printed on the image\n'
        '  "has_branding_text": bool,            // is a restaurant name/logo already printed on the image\n'
        '  "has_offer_text": bool,               // is a discount/offer already printed on the image\n'
        '  "logo_corner": "top-left|top-right|bottom-left|bottom-right",  // cleanest, least-busy corner for a small logo\n'
        '  "offer_position": "top|bottom",       // emptier band to place a bold offer graphic without hiding the dish\n'
        '  "tone": "light|dark",                 // overall brightness where overlays will go\n'
        '  "description": string,                // <=18 words describing the dish/scene\n'
        '  "refinement_prompt": string           // <=40 words: how to lightly enhance lighting/colour/clarity WITHOUT changing the dish or adding text\n'
        '}\n'
        f"Restaurant: {restaurant_name or 'a restaurant'}."
    )


def analyze_ad_image(image_path, restaurant_name=None, gemini_key=None):
    """
    Gemini vision analysis of the photo. Returns a dict (see _ANALYSIS_DEFAULTS).
    Never raises — falls back to safe defaults on any failure.
    """
    result = dict(_ANALYSIS_DEFAULTS)
    if not gemini_key:
        return result
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"

        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.5-flash:generateContent?key={gemini_key}")
        payload = {
            "contents": [{"parts": [
                {"text": _analysis_prompt(restaurant_name)},
                {"inline_data": {"mime_type": mime, "data": img_b64}},
            ]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }
        resp = requests.post(url, json=payload, timeout=45)
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        parsed = json.loads(text)
        for k in result:
            if k in parsed and parsed[k] is not None:
                result[k] = parsed[k]
    except Exception:
        pass  # caller logs; defaults are good enough to still produce a creative
    return result


# ─── Full AI generation (gemini-2.5-flash-image / "nano-banana") ─────

def _default_offer_headline(offer_amount):
    """Fallback hero text when no explicit offer headline is supplied."""
    n = int(round(float(offer_amount or 0)))
    return f"FLAT ₹{n} OFF" if n else "SPECIAL OFFER"


def _ai_creative_prompt(offer_headline, offer_detail, coupon_code, restaurant_name, area,
                        *, has_offer=False, has_address=False, position="bottom",
                        clean_corner="top-right"):
    """
    Build the nano-banana prompt DYNAMICALLY from what's already on the photo
    (detected by vision/OCR): only ask for the elements that are missing. The
    offer text is verbatim (any offer type), numbers preserved exactly, and the
    Flamezo logo is NOT requested — we stamp the real logo by code afterwards,
    so the `clean_corner` is kept empty.
    """
    loc = f"{restaurant_name}" + (f" · {area}" if area else "") if restaurant_name else (area or "")
    include_offer = not has_offer
    include_loc = bool(loc) and not has_address

    lines = []
    if include_offer:
        lines.append('   - A small uppercase pill label: "LIMITED-TIME OFFER"')
        lines.append(f'   - A large bold headline, the hero of the design, written EXACTLY: "{offer_headline}"')
        if offer_detail:
            lines.append(f'   - A small supporting line written EXACTLY: "{offer_detail}"')
    if include_loc:
        lines.append(f'   - A location line: "{loc}" with a small map-pin icon')
    if coupon_code:
        lines.append(f'   - A coupon-code chip written EXACTLY, character for character: "CODE: {coupon_code}"')
    lines.append('   - A circular call-to-action button with a right-arrow (→).')
    card_text = "\n".join(lines)

    exact_tokens = []
    if include_offer:
        exact_tokens += [offer_headline, offer_detail]
    if coupon_code:
        exact_tokens.append(f"CODE: {coupon_code}")
    exact_block = "; ".join(f'"{t}"' for t in exact_tokens if t)

    already = []
    if has_offer:
        already.append("an offer/discount")
    if has_address:
        already.append("an address/location")
    already_note = (
        f"NOTE: the photo ALREADY shows {' and '.join(already)} — do NOT add a duplicate of that; "
        f"only add the elements listed below.\n" if already else ""
    )

    return (
        f'You are a senior social-media advertising designer. The attached photograph is a real dish from the '
        f'restaurant "{restaurant_name or "this restaurant"}". Turn it into a polished, scroll-stopping '
        f'Instagram/Facebook (Meta) ad creative.\n\n'
        f'⚠️ TEXT ACCURACY — HIGHEST PRIORITY:\n'
        f'Reproduce all on-image text EXACTLY as given. Every DIGIT, the ₹ currency symbol, and every letter of the '
        f'coupon code must appear character-for-character identical. Do NOT change, round, translate, reformat, add '
        f'or remove ANY number, symbol or character. In particular the discount number must stay exactly the same. '
        f'These strings must appear verbatim: {exact_block}. '
        f'If a character is hard to render, make the text smaller but keep it 100% correct rather than altering it.\n'
        f'Do NOT add ANY other words, captions, labels, taglines or invented text anywhere on the image — '
        f'render ONLY the exact strings specified below and nothing else.\n\n'
        f'{already_note}'
        f'NON-NEGOTIABLE RULES:\n'
        f'1. PRESERVE THE FOOD EXACTLY as in the original photo — same dish, plating, garnish and colours. '
        f'Do NOT replace, redraw or restyle the food itself. You may only subtly improve lighting, clarity and '
        f'vibrancy, and add graphic overlays ON TOP of the photo.\n'
        f'2. Fill the entire frame with the photo — absolutely no borders, bars or padding.\n'
        f'3. Add ONE premium, modern offer graphic — a sleek frosted-glass / rounded card placed along the '
        f'{position.upper()} of the image, NOT covering the main dish. Inside the card render, crisp and legible:\n'
        f'{card_text}\n'
        f'4. Brand colour is vibrant orange (#F97316) — use it for the label pill, the CTA button and accents. '
        f'Keep all text high-contrast and easy to read on a phone.\n'
        f'5. Do NOT add any logo, watermark, brand name or app name anywhere. Keep the {clean_corner.upper()} '
        f'corner completely clean and empty (branding is added separately).\n'
        f'6. Style: editorial, magazine-quality, appetising, premium food advertising. Clean typography, tasteful '
        f'shadows, balanced composition.\n'
        f'OUTPUT: a single finished ad image in 4:5 portrait aspect ratio.'
    )


def generate_creative_gemini(image_path, *, offer_headline, offer_detail=None, coupon_code=None,
                             restaurant_name=None, area=None, gemini_key=None, aspect="4:5",
                             has_offer=False, has_address=False, position="bottom",
                             clean_corner="top-right"):
    """
    Generate the FULL ad creative with gemini-2.5-flash-image (text + graphics
    layered onto the dish by the model). Returns a tmp PNG path. Raises on failure.
    """
    if not gemini_key:
        raise RuntimeError("Gemini API key required for AI creative generation")

    with open(image_path, "rb") as f:
        img_data = f.read()
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"

    prompt = _ai_creative_prompt(
        offer_headline, offer_detail, coupon_code, restaurant_name, area,
        has_offer=has_offer, has_address=has_address, position=position, clean_corner=clean_corner)
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash-image:generateContent?key={gemini_key}")
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_data).decode("utf-8")}},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    res_json = resp.json()

    candidates = res_json.get("candidates") or []
    if candidates:
        for part in candidates[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                out = f"/tmp/{uuid.uuid4().hex}.png"
                with open(out, "wb") as f:
                    f.write(base64.b64decode(part["inlineData"]["data"]))
                return out
    raise RuntimeError("Gemini returned no image for the ad creative")


def _overlay_logo(canvas, corner="top-right", width_frac=0.23, logo_path=None):
    """Composite the real Flamezo wordmark into a corner (code, not AI)."""
    path = logo_path or _LOGO_PATH
    if not os.path.exists(path):
        return
    W, H = canvas.size
    logo = Image.open(path).convert("RGBA")
    tw = int(W * width_frac)
    th = max(1, int(logo.height * tw / logo.width))
    logo = logo.resize((tw, th), Image.Resampling.LANCZOS)

    m = int(W * 0.04)
    pos = {
        "top-left": (m, m),
        "top-right": (W - tw - m, m),
        "bottom-left": (m, H - th - m),
        "bottom-right": (W - tw - m, H - th - m),
    }.get(corner, (W - tw - m, m))
    # Soft dark glow so the white wordmark stays legible on bright photos.
    _paste_with_shadow(canvas, logo, pos, blur=12, offset=(0, 2), opacity=95)


def _finalize_ai_creative(src_path, corner="top-right", output_path=None, target=PORTRAIT):
    """Standardise an AI-generated creative to feed size and stamp the real logo."""
    out = output_path or f"/tmp/{uuid.uuid4().hex}.jpg"
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = ImageOps.fit(im, target, method=Image.Resampling.LANCZOS)
        canvas = im.convert("RGBA")
    _overlay_logo(canvas, corner=corner)
    canvas.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out


# ─── Orchestration (frappe-bound, imported lazily) ──────────────────

def _download_to_tmp(url):
    """Download any image URL (or local /files path) to a tmp file."""
    from flamezo_backend.flamezo.api.ai_media import download_image
    return download_image(url)


def refine_ad_image(
    source,
    *,
    restaurant_id=None,
    restaurant_name=None,
    address=None,
    area=None,
    offer_amount=0,
    offer_headline=None,
    offer_detail=None,
    coupon_code=None,
    mode="ai",
    do_analysis=True,
    gemini_key=None,
    output_path=None,
):
    """
    End-to-end: load any-format image (URL/path) → produce the ad creative.

    The offer text is dynamic: pass `offer_headline` (e.g. "FLAT ₹100 OFF",
    "BUY 1 GET 1 FREE", "30% OFF", "FREE DESSERT") and optional `offer_detail`
    (e.g. "Min order ₹200"). If no headline is given, one is built from
    `offer_amount`. Numbers/code are rendered verbatim.

    mode="ai"      → gemini-2.5-flash-image generates the whole creative (text +
                     graphics layered onto the dish). Falls back to the overlay
                     renderer if the AI call fails, so a creative is always produced.
    mode="overlay" → deterministic Pillow compositor (pixel-perfect text).

    Returns (output_path, meta_dict).
    """
    headline = offer_headline or _default_offer_headline(offer_amount)
    tmp_in = None
    tmp_ai = None
    try:
        if os.path.exists(source):
            image_path = source
        else:
            tmp_in = _download_to_tmp(source)
            image_path = tmp_in

        # 1) Full AI generation (preferred)
        if mode == "ai" and gemini_key:
            try:
                # OCR/vision pass: see what's already printed on the photo so the
                # prompt only asks the AI to add what's missing.
                analysis = analyze_ad_image(image_path, restaurant_name, gemini_key) \
                    if do_analysis else dict(_ANALYSIS_DEFAULTS)
                position = analysis.get("offer_position", "bottom")
                logo_corner = _resolve_logo_corner(analysis, position, True)

                tmp_ai = generate_creative_gemini(
                    image_path, offer_headline=headline, offer_detail=offer_detail,
                    coupon_code=coupon_code, restaurant_name=restaurant_name,
                    area=area, gemini_key=gemini_key,
                    has_offer=bool(analysis.get("has_offer_text")),
                    has_address=bool(analysis.get("has_address_text")),
                    position=position, clean_corner=logo_corner)
                # Stamp the REAL Flamezo logo by code (not AI) for consistency.
                out = _finalize_ai_creative(tmp_ai, corner=logo_corner, output_path=output_path)
                return out, {"mode": "ai", "offer_headline": headline, "analysis": analysis}
            except Exception as e:
                try:
                    import frappe
                    frappe.log_error(f"AI creative gen failed, using overlay: {e}"[:140], "Boost Creative Image")
                except Exception:
                    pass
                # fall through to deterministic overlay

        # 2) Deterministic overlay (fallback, or mode="overlay")
        analysis = analyze_ad_image(image_path, restaurant_name, gemini_key) if do_analysis \
            else dict(_ANALYSIS_DEFAULTS)
        out = compose_ad_overlays(
            image_path,
            offer_headline=headline,
            offer_detail=offer_detail,
            offer_amount=offer_amount,
            coupon_code=coupon_code,
            restaurant_name=restaurant_name,
            address=address,
            area=area,
            analysis=analysis,
            output_path=output_path,
        )
        analysis["mode"] = "overlay"
        return out, analysis
    finally:
        for p in (tmp_in, tmp_ai):
            if p and p != source and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


# ─── Background job + status (used by the Boost API) ────────────────

def _status_key(campaign_name):
    return f"boost_creative_status:{campaign_name}"


def set_creative_status(campaign_name, status, error=None):
    import frappe
    frappe.cache().set_value(
        _status_key(campaign_name),
        json.dumps({"status": status, "error": error}),
        expires_in_sec=3600,
    )


def get_creative_status(campaign_name):
    import frappe
    raw = frappe.cache().get_value(_status_key(campaign_name))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return None


def _campaign_offer_text(campaign):
    """
    Derive a dynamic on-image offer headline + detail from a Boost Campaign.
    Numbers come straight from the campaign and are rendered verbatim.

    - Flat ₹ discount  → "FLAT ₹100 OFF"  + "Min order ₹200"
    - Any other offer  → falls back to the campaign's generated ad_headline
      (e.g. BOGO / % off), so all offer types are covered.
    """
    amt = int(round(float(campaign.offer_amount or 0)))
    min_order = int(round(float(getattr(campaign, "coupon_min_order", 0) or 0)))
    if amt:
        headline = f"FLAT ₹{amt} OFF"
        detail = f"Min order ₹{min_order}" if min_order else None
    else:
        headline = (campaign.ad_headline or campaign.offer_description or "SPECIAL OFFER").strip()
        detail = campaign.offer_description if campaign.offer_description and campaign.offer_description != headline else None
    return headline, detail


def process_boost_creative(campaign_name, source_image_url):
    """Background job: refine the chosen photo and store it on the campaign."""
    import frappe
    from flamezo_backend.flamezo.media.storage import upload_object, generate_object_key

    out_path = None
    try:
        set_creative_status(campaign_name, "Processing")
        campaign = frappe.get_doc("Boost Campaign", campaign_name)
        restaurant = frappe.get_doc("Restaurant", campaign.restaurant)

        # Keep the on-image locality short (city, or the cleanest address part).
        area = restaurant.city or _short_location(restaurant.address)

        # Dynamic offer text straight from the campaign — covers any offer type.
        offer_headline, offer_detail = _campaign_offer_text(campaign)

        out_path, analysis = refine_ad_image(
            source_image_url,
            restaurant_id=campaign.restaurant,
            restaurant_name=restaurant.restaurant_name,
            area=area,
            offer_amount=campaign.offer_amount,
            offer_headline=offer_headline,
            offer_detail=offer_detail,
            coupon_code=campaign.coupon_code,
            mode="ai",
            gemini_key=frappe.conf.get("gemini_api_key"),
        )

        uid = frappe.generate_hash(length=8)
        object_key = generate_object_key(
            restaurant_id=campaign.restaurant,
            owner_doctype="Restaurant",
            owner_name=campaign.restaurant,
            media_role="boost_ad_creative",
            media_id=uid,
            filename="creative.jpg",
            variant="lg",
        )
        cdn_url = upload_object(out_path, object_key, content_type="image/jpeg")

        # Persist: keep the chosen source AND the processed creative.
        frappe.db.set_value("Boost Campaign", campaign_name, {
            "ad_image_url": source_image_url,
            "ad_image_with_overlay": cdn_url,
        })
        frappe.db.commit()
        set_creative_status(campaign_name, "Ready")
    except Exception as e:
        set_creative_status(campaign_name, "Failed", error=str(e))
        frappe.log_error(f"Boost creative failed for {campaign_name}: {e}"[:140], "Boost Creative Image")
        raise
    finally:
        if out_path and os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
