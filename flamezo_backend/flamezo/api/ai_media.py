import frappe
import requests
import json
import base64
import os
import uuid
import random
import time
from PIL import Image, ImageFilter, ImageOps
from flamezo_backend.flamezo.media.storage import upload_object, get_cdn_url, generate_object_key

MENU_THEME_COINS = 30
MENU_THEME_OUTPUT_SIZE = (1080, 1920)


def _gemini_post_with_retry(url, payload, max_retries=4, base_delay=2.0, timeout=120):
    """
    POST to the Gemini API, retrying transient rate-limit/availability errors
    (HTTP 429 / 503) with exponential backoff + jitter. Honours a `Retry-After`
    header or the API's `RetryInfo.retryDelay` when present. Non-transient
    errors raise immediately. Runs inside a background worker, so sleeping is
    fine (total backoff is bounded well under the job timeout).
    """
    resp = None
    for attempt in range(max_retries + 1):
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code not in (429, 503):
            resp.raise_for_status()
            return resp
        if attempt >= max_retries:
            break
        delay = None
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                delay = float(ra)
            except ValueError:
                delay = None
        if delay is None:
            try:
                for d in (resp.json().get("error", {}) or {}).get("details", []) or []:
                    rd = d.get("retryDelay")
                    if rd:
                        delay = float(str(rd).rstrip("s"))
                        break
            except Exception:
                pass
        if delay is None:
            delay = base_delay * (2 ** attempt)
        time.sleep(min(delay, 30) + random.uniform(0, 0.5))
    # Exhausted retries — surface the last (rate-limit) error.
    resp.raise_for_status()
    return resp


def _get_outlet_config_name(restaurant):
    config_name = frappe.db.get_value("Outlet Config", {"restaurant": restaurant}, "name")
    if config_name:
        return config_name

    outlet_name = frappe.db.get_value("Outlet", restaurant, "restaurant_name") or restaurant
    config_doc = frappe.get_doc({
        "doctype": "Outlet Config",
        "restaurant": restaurant,
        "restaurant_name": outlet_name,
        "default_theme": "light",
        "currency": frappe.db.get_value("Outlet", restaurant, "currency") or "INR",
        "menu_layout": "2 Columns",
    })
    config_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return config_doc.name


def _coerce_json_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _to_json_string(value):
    return json.dumps(value or [])


def _update_theme_history(config_name, image_url, source_images, activate=False):
    config_doc = frappe.get_doc("Outlet Config", config_name)
    history = _coerce_json_list(config_doc.menu_theme_background_history)
    entry = {
        "id": frappe.generate_hash(length=10),
        "image_url": image_url,
        "source_images": source_images,
        "created_on": frappe.utils.now(),
        "active": bool(activate),
    }

    for item in history:
        item["active"] = False
    history.insert(0, entry)
    config_doc.db_set("menu_theme_background_history", _to_json_string(history), update_modified=False)
    if activate:
        config_doc.db_set("menu_theme_background_active", image_url, update_modified=False)
    return entry

        # "Use 100% of the canvas. The composition should be bold and fill the entire screen, as it will serve as a vibrant backdrop under a blurred UI layer. "

def _build_theme_generation_prompt(outlet_name, items=None, color_theme=None):
    # Determine the color instruction based on the theme
    if color_theme and color_theme != "Multi-color" and color_theme != "None":
        color_instruction = f"COLOR THEME: Use vibrant, rich colors with a {color_theme} dominant tone that strictly matches the aesthetic of the original artwork."
    elif color_theme == "Multi-color":
        color_instruction = "COLOR THEME: Use a vibrant, rich multi-color palette that harmonizes with the original menu visuals."
    else:
        color_instruction = "COLOR THEME: EXACT COLOR MATCH. Do not change the colors. Use the exact same color palette, saturation, and tones from the original menu image."

    identify_instruction = (
        f"You are designing a premium, high-fidelity modern wallpaper based on {outlet_name}'s actual menu visuals. "
        "CRITICAL ANALYSIS: Closely analyze the specific graphics, visual assets, icons, and illustrations in the attached menu image. "
        "EXACT EXTRACTION: Extract the core visual identity from the menu. Do not create new items from scratch; you MUST faithfully reproduce the exact graphical elements, food imagery, or unique design assets shown. "
    )
    
    layout_instruction = (
        "VISUAL RECOMPOSITION: Rearrange and 'paste' the extracted graphics onto the 9:16 vertical canvas in a sophisticated, layered composition. "
        "Center the most prominent visual subject and arrange secondary elements around it. Implement a professional depth effect (bokeh) to create separation between layers. "
    )

    return (
        f"{identify_instruction}"
        
        "VISUAL STYLE: "
        "Create a modern, premium wallpaper with a sophisticated iphone like depth effect. "
        f"{color_instruction} Incorporate dynamic elements or subtle light leaks that complement the extracted graphics to enhance depth. "
        
        "LAYOUT: "
        f"{layout_instruction}"
        "Use 100% of the canvas. The composition should be bold and fill the entire screen, as it will serve as a vibrant backdrop under a blurred UI layer. "
      
        "STRICTLY DO NOT INCLUDE: "
        "Ignore ALL text, price labels, descriptions, menu grids, and layout structures. "
        "Absolutely NO words, letters, restaurant names, headings, or any typography. "
        "The final output must be a clean, text-free graphical wallpaper. "

        "OUTPUT: "
        "A premium, saturated, high-fidelity restaurant wallpaper that perfectly represents the menu's original visual identity."
    )


def generate_menu_theme_background_gemini(image_paths, outlet_name, items=None, color_theme=None):
    gemini_key = frappe.conf.get("gemini_api_key")
    if not gemini_key:
        frappe.throw("Gemini API key required for generation")

    prompt = _build_theme_generation_prompt(outlet_name, items=items, color_theme=color_theme)
    parts = [{"text": prompt}]

    for image_path in image_paths:
        with open(image_path, "rb") as f:
            img_data = f.read()
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(img_data).decode("utf-8")
            }
        })

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={gemini_key}"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": "9:16"
            }
        }
    }

    response = _gemini_post_with_retry(url, payload)
    res_json = response.json()

    if 'candidates' in res_json and res_json['candidates']:
        for part in res_json['candidates'][0]['content']['parts']:
            if 'inlineData' in part:
                temp_output = f"/tmp/{uuid.uuid4().hex}.png"
                with open(temp_output, "wb") as f:
                    f.write(base64.b64decode(part['inlineData']['data']))
                return temp_output

    frappe.throw("Gemini failed to generate a menu theme background image.")


def normalize_menu_theme_background_image(source_path, target_size=MENU_THEME_OUTPUT_SIZE):
    target_width, target_height = target_size
    temp_output = f"/tmp/{uuid.uuid4().hex}.jpg"

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")

        # Directly resize since the AI generates the image natively at 9:16 ratio
        final_image = image.resize(target_size, resample=Image.Resampling.LANCZOS)
        
        final_image.save(temp_output, format="JPEG", quality=92, optimize=True)

    return temp_output


def get_random_reference_image():
    """Selects a random image from the internal reference_images directory."""
    # Internal app path is more secure than public folder for static assets used by AI
    ref_folder = frappe.get_app_path("flamezo_backend", "flamezo_backend", "media", "reference_images")
    
    if os.path.exists(ref_folder):
        files = [f for f in os.listdir(ref_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if files:
            return os.path.join(ref_folder, random.choice(files))
            
    # Absolute fallback to public images if internal is somehow missing
    images_folder = frappe.get_app_path("flamezo_backend", "public", "flamezo_backend", "images")
    return os.path.join(images_folder, "login-flamezo_backend.png")


@frappe.whitelist(allow_guest=False)
def upload_base64_image(filename, filedata):
    """
    Standardized base64 upload handler for AI Image Enhancement.
    """
    # Decoding base64
    content = base64.b64decode(filedata)
    
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "content": content,
        "is_private": 0
    })
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {"file_url": file_doc.file_url}


@frappe.whitelist(allow_guest=False)
def enqueue_enhancement(restaurant, owner_doctype, owner_name, original_image_url=None, mode="enhance", include_branding=False):
    """
    Creates an AI Image Generation record and enqueues a job.
    mode="enhance" costs 5 coins and requires original_image_url.
    mode="generate" costs 10 coins and uses only product info + reference image.
    """
    from flamezo_backend.flamezo.api.coin_billing import deduct_coins

    BASE_COST = 10 if mode == "generate" else 5
    BRANDING_COST = 0 # Branding is now free to encourage adoption
    COIN_COST = BASE_COST + BRANDING_COST

    # Step 1: Verify coin balance before even creating the doc
    balance = frappe.db.get_value("Outlet", restaurant, "coins_balance") or 0.0
    if balance < COIN_COST:
        frappe.throw(
            f"Insufficient Wallet Balance (₹). You need {COIN_COST} coins but only have {balance}. "
            "Please recharge your coin wallet.",
            frappe.ValidationError
        )

    if mode == "enhance" and not original_image_url:
        frappe.throw("original_image_url is required for enhance mode.", frappe.ValidationError)

    doc = frappe.get_doc({
        "doctype": "AI Image Generation",
        "restaurant": restaurant,
        "owner_doctype": owner_doctype,
        "owner_name": owner_name,
        "original_image_url": original_image_url or "",
        "status": "Pending_Upload"
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        deduct_coins(restaurant, COIN_COST, "AI Deduction", f"AI {mode} - Generation {doc.name}", ref_doctype="AI Image Generation", ref_name=doc.name)
    except Exception as e:
        # Rollback the generation document if deduction fails
        frappe.delete_doc("AI Image Generation", doc.name, ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(str(e))

    # Step 3: Enqueue background job
    frappe.enqueue(
        "flamezo_backend.flamezo.api.ai_media.process_ai_image_enhancement",
        queue="default",
        timeout=300,
        generation_name=doc.name,
        mode=mode,
        include_branding=include_branding,
        coins_to_refund=COIN_COST
    )

    return {"generation_id": doc.name}


@frappe.whitelist(allow_guest=False)
def get_enhancement_status(generation_id):
    """Returns the status and output of a generation."""
    if not frappe.db.exists("AI Image Generation", generation_id):
        frappe.throw("Invalid Generation ID")
    
    doc = frappe.get_doc("AI Image Generation", generation_id)
    return {
        "status": doc.status,
        "enhanced_image_url": doc.enhanced_image_url,
        "error_message": doc.error_message
    }


@frappe.whitelist(allow_guest=False)
def get_generative_gallery(restaurant, limit=50):
    """Returns a list of completed generations for a restaurant."""
    generations = frappe.get_all("AI Image Generation", 
        filters={
            "restaurant": restaurant,
            "status": "Completed"
        },
        fields=["name", "creation", "owner_name", "original_image_url", "enhanced_image_url", "video_url"],
        order_by="creation desc",
        limit=limit
    )
    return generations


@frappe.whitelist(allow_guest=False)
def download_proxy(file_url, filename=None):
    """Proxy to fetch cross-origin images and force download."""
    if not file_url:
        frappe.throw("File URL is required")
        
    import requests
    response = requests.get(file_url, stream=True)
    response.raise_for_status()
    
    if not filename:
        filename = file_url.split("/")[-1].split("?")[0] or "download.png"
        if "." not in filename:
            filename += ".png"

    frappe.response.filename = filename
    frappe.response.filecontent = response.content
    frappe.response.type = "download"


@frappe.whitelist(allow_guest=False)
def apply_to_product(generation_id, replace_index=None):
    """Applies the enhanced image to Menu Product."""
    doc = frappe.get_doc("AI Image Generation", generation_id)
    if doc.status != "Completed":
        frappe.throw("Cannot apply an incomplete generation.")
    if doc.owner_doctype != "Menu Product":
        frappe.throw("Only Menu Product is supported for auto-apply right now.")
        
    product = frappe.get_doc("Menu Product", doc.owner_name)
    
    # Replacement Logic
    if replace_index is not None:
        idx = int(replace_index)
        if idx < len(product.product_media):
            # Replace existing
            product.product_media[idx].media_url = doc.enhanced_image_url
            product.product_media[idx].media_type = "image"
            product.product_media[idx].media_asset = None
        else:
            # Append if index is out of bounds (fallback)
            product.append("product_media", {
                "media_type": "image",
                "media_url": doc.enhanced_image_url,
                "display_order": len(product.product_media) + 1,
                "alt_text": "AI Enhanced Image"
            })
    else:
        # Standard Append
        product.append("product_media", {
            "media_type": "image",
            "media_url": doc.enhanced_image_url,
            "display_order": len(product.product_media) + 1,
            "alt_text": "AI Enhanced Image"
        })
        
    product.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist(allow_guest=False)
def apply_to_coupon(generation_id):
    """Applies the generated image to Coupon.combo_image field."""
    doc = frappe.get_doc("AI Image Generation", generation_id)
    if doc.status != "Completed":
        frappe.throw("Cannot apply an incomplete generation.")
    if doc.owner_doctype != "Coupon":
        frappe.throw("This generation is not linked to a Coupon.")
    frappe.db.set_value("Coupon", doc.owner_name, "combo_image", doc.enhanced_image_url)
    frappe.db.commit()
    return {"success": True, "combo_image": doc.enhanced_image_url}


def download_image(url):
    temp_path = f"/tmp/{uuid.uuid4().hex}.jpg"
    
    if url.startswith("/files/"):
        # Local Frappe file
        site_path = frappe.get_site_path("public")
        file_path = os.path.join(site_path, url.replace("/files/", "files/"))
        if not os.path.exists(file_path):
            frappe.throw(f"Local file not found: {file_path}")
        with open(file_path, "rb") as f_in, open(temp_path, "wb") as f_out:
            f_out.write(f_in.read())
        return temp_path

    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return temp_path


# ── Prompt helpers ────────────────────────────────────────────────────────────

# Maps category keywords → surface/prop description.
# More specific entries are listed first so they match before generic ones.
_CATEGORY_SURFACE_MAP = [
    ({"dessert", "sweet", "cake", "pastry", "mithai", "halwa", "kheer",
      "gulab", "ladoo", "barfi", "rabdi", "phirni"},
     "elegant white marble surface, a small dessert fork, soft pastel linen napkin"),
    ({"drink", "beverage", "juice", "cocktail", "tea", "coffee", "chai",
      "lassi", "mocktail", "sharbat", "nimbu"},
     "polished wooden bar counter, condensation on the glass, warm amber backlight"),
    ({"soup", "dal", "rasam", "shorba"},
     "rustic wooden surface, deep terracotta or ceramic bowl, small ladle resting on the rim"),
    ({"biryani", "pulao", "dum", "rice"},
     "dark wooden serving platter, traditional copper handi, a garnish of crispy fried onions and fresh mint"),
    ({"curry", "sabzi", "masala", "gravy", "makhani", "korma", "kadai",
      "butter chicken", "paneer", "kofta"},
     "dark stone surface, copper karahi or white ceramic bowl, whole spices and a naan on the side"),
    ({"starter", "appetizer", "snack", "chaat", "tikka", "kebab", "barbeque",
      "bbq", "tandoor", "seekh"},
     "dark slate board, small ramekins of mint chutney and tamarind sauce, a lemon wedge"),
    ({"seafood", "fish", "prawn", "crab", "lobster", "surmai", "pomfret"},
     "slate or dark marble board, fresh lemon wedge, dill or parsley sprig"),
    ({"pizza", "pasta", "risotto", "italian"},
     "rustic wooden board, scattered fresh basil leaves, a sprinkle of parmesan"),
    ({"burger", "sandwich", "wrap", "roll", "shawarma", "kathi"},
     "parchment paper on a wooden tray, a small side of fries or pickled jalapeños"),
    ({"salad", "bowl", "healthy", "grain", "quinoa"},
     "clean white ceramic bowl on bright marble, fresh herb garnish, a drizzle of dressing"),
    ({"bread", "naan", "roti", "paratha", "puri", "kulcha", "bhatura"},
     "cloth or burlap surface, small copper bowl of ghee, earthy warm-tone props"),
    ({"ice cream", "gelato", "sorbet", "kulfi"},
     "white marble with a vintage metal spoon, scattered wafer cones, pastel background"),
]


def _surface_and_props(category):
    """Return a surface + prop suggestion matched to the dish category."""
    c = (category or "").lower()
    for keywords, surface in _CATEGORY_SURFACE_MAP:
        if any(kw in c for kw in keywords):
            return surface
    return "premium dark ceramic plate on a textured dark slate surface"


# ── Scene variation pools — picked randomly per generation ───────────────────

_SCENE_ANGLES = [
    "overhead flat-lay, perfectly centred",
    "45-degree elevated three-quarter angle",
    "close-up three-quarter angle, slightly low",
    "birds-eye overhead with slight tilt",
    "low dramatic side angle, eye-level with the plate",
]

_SCENE_LIGHTING = [
    "dramatic single soft-box from upper-left, deep sculpted shadows with rich glossy depth",
    "warm golden-hour window light streaming softly from the right side",
    "cool diffused north light, clean and minimal shadows, editorial feel",
    "moody single-source pendant lamp from above with warm amber glow",
    "dappled café light filtering through sheer curtains from the left",
    "backlit rim light with soft haze, making the dish glow from behind",
]

_SCENE_SURFACE = [
    "dark slate with fine grain texture",
    "aged rustic oak wood table",
    "white Carrara marble with subtle grey veining",
    "terracotta tile with warm earth tones",
    "brushed dark concrete countertop",
    "dark linen tablecloth with soft natural weave",
    "polished black granite",
    "weathered teak wood with natural grain",
]

_SCENE_BACKGROUND = [
    "background dissolving into deep warm bokeh",
    "blurred fine-dining restaurant interior with soft amber lights in background",
    "soft out-of-focus greenery and plants in background",
    "moody dark background with faint warm ambient glow",
    "blurred rustic exposed brick wall in background",
    "hazy open kitchen with warm light in background",
]

_SCENE_PROPS = [
    "fresh herb sprig and a drizzle of cream as garnish",
    "linen napkin folded neatly and vintage cutlery beside the dish",
    "small clay side bowl with chutney and scattered whole spices",
    "seasonal flower petals scattered as accent, delicate garnish",
    "brass serving spoon resting beside the dish, scattered spice seeds",
    "micro-greens garnish and a wedge of lemon on the side",
    "small ramekin of sauce on the side, fresh herb leaves floating on top",
]


def _pick_scene():
    return {
        "angle":      random.choice(_SCENE_ANGLES),
        "lighting":   random.choice(_SCENE_LIGHTING),
        "surface":    random.choice(_SCENE_SURFACE),
        "background": random.choice(_SCENE_BACKGROUND),
        "props":      random.choice(_SCENE_PROPS),
    }


def _gemini_scene_for_dish(dish_name, dish_description, dish_category):
    """
    Ask Gemini to invent a unique food photography scene tailored to this specific dish.
    Returns a dict with keys: angle, lighting, surface, background, props.
    Falls back to random pool on any error.
    """
    try:
        gemini_key = frappe.conf.get("gemini_api_key")
        if not gemini_key:
            return _pick_scene()

        desc_hint = f" ({dish_description[:120]})" if dish_description else ""
        category_hint = f" Category: {dish_category}." if dish_category else ""

        system_prompt = (
            "You are a world-class food photography art director AND a chef who knows "
            "global cuisines in depth — especially Indian dishes and regional street food. "
            "Given a dish name, FIRST recall exactly what that specific dish physically looks "
            "like, THEN invent a unique cinematic scene for a single food photo. "
            "Reply with ONLY a JSON object — no markdown, no explanation — with exactly these keys:\n"
            "  dish_visual (describe THIS exact dish the way a customer would INSTANTLY recognise "
            "it at a glance: its signature defining features, real colours and textures, the "
            "traditional vessel or plate it sits in, and the standard garnish and accompaniments "
            "it actually comes with in India. Focus on the FOOD ITSELF — accurate real components, "
            "not a fancy reinterpretation. Name the cuisine/region. 30-45 words.)\n"
            "  angle       (camera angle and framing)\n"
            "  lighting    (light source, direction, mood)\n"
            "  surface     (an elegant premium surface, VARIED for each dish — e.g. white marble, "
            "warm rustic wood, dark slate, polished granite, glazed ceramic, or a brass tray; pick "
            "what best suits THIS dish and do NOT default to dark stone every time)\n"
            "  background  (an elegant softly-blurred UPSCALE setting, VARIED for each dish — e.g. "
            "bright airy cafe, warm wooden bistro, moody dark fine-dining, or soft pastel studio, "
            "with pleasant bokeh; NEVER a street, stall, market, roadside or outdoor scene)\n"
            "  props       (garnish and styling details on or beside the dish)\n"
            "Keep angle/lighting/surface/background/props each under 20 words. "
            "Make the scene feel fresh and different every time. "
            "Never mention candles unless it truly fits the dish."
        )
        user_prompt = f"Dish: {dish_name}{desc_hint}.{category_hint}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            # thinkingBudget=0 disables 2.5-flash's internal reasoning (not needed
            # for this structured task) so the whole token budget goes to the JSON
            # answer — otherwise dish_visual gets truncated away. Roomier cap too.
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 900,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scene = json.loads(raw)
        # Validate all keys present
        for k in ("angle", "lighting", "surface", "background", "props"):
            if k not in scene:
                return _pick_scene()
        return scene
    except Exception:
        return _pick_scene()


def _build_generate_prompt(dish_name, dish_description, dish_category, outlet_name, include_branding):
    """
    Cinematic food photography prompt for FLUX.1 [schnell] at 8 steps.
    Scene (angle, lighting, surface, background, props) is generated by Gemini
    for each dish specifically — giving every dish a unique, context-aware treatment.
    Falls back to random pool if Gemini is unavailable.
    """
    scene = _gemini_scene_for_dish(dish_name, dish_description, dish_category)

    # Accurate appearance of the dish itself. Prefer the LLM's dish_visual — it
    # knows Indian dishes FLUX can't render from the name alone (e.g. vada pav) —
    # and fall back to the menu description. This is what fixes wrong-dish output.
    visual = (scene.get("dish_visual") or "").strip().rstrip(".")
    if not visual and dish_description:
        visual = dish_description.strip().rstrip(".")[:200]
    desc_clause = f"{visual}. " if visual else ""

    ambiance = ""
    if include_branding and outlet_name:
        ambiance = f"Ambiance and styling of {outlet_name}. "

    return (
        f"A real, candid photograph of {dish_name} — the authentic dish, exactly right. "
        f"{desc_clause}"
        f"Shot on a DSLR with natural available light, like a genuine restaurant photo — realistic, "
        f"unretouched and true-to-life, NOT AI-looking, NOT CGI, not glossy. "
        f"Plated on a {scene['surface']}. "
        f"Shot {scene['angle']}. "
        f"{scene['lighting']}. "
        f"Sharp focus on the hero dish, {scene['background']}. "
        f"{ambiance}"
        f"{scene['props']}. "
        f"True to the real recipe — recognisable at a single glance without reading its name. Set in "
        f"an elegant, upmarket restaurant setting with a softly blurred premium background — NOT a "
        f"street, stall or roadside scene. "
        f"Natural realistic colours and real-food textures with subtle imperfections, shallow depth "
        f"of field, authentic photographic look. A believable real photo — NOT a 3D render, NOT "
        f"digital art, NOT an illustration, not plastic-looking, not overly perfect. No text, no hands, no people."
    )


def _build_enhance_prompt(dish_name, dish_description, dish_category):
    """
    Minimal, guidance-light prompt for image-to-image enhancement (FLUX schnell).
    At strength=0.55 the input image provides the composition; the prompt
    nudges quality and lighting without overriding the source structure.
    """
    surface = _surface_and_props(dish_category)

    desc_clause = ""
    if dish_description:
        cleaned = dish_description.strip().rstrip(".").lower()[:120]
        desc_clause = f"{cleaned}, "

    return (
        f"{dish_name}, {desc_clause}"
        f"professional restaurant menu photograph on a {surface}, "
        f"soft natural window light from the side, sharp focus on the food, "
        f"rich natural colors, elegant plating, clean appetizing presentation, "
        f"editorial food photography, no text, no people."
    )


# Shared negative prompt — prevents the most common diffusion artifacts in food photos.
_FOOD_NEGATIVE_PROMPT = (
    "blurry, out of focus, low quality, watermark, text, logo, signature, "
    "ugly plating, dirty plate, overexposed, oversaturated, washed out, "
    "artificial plastic-looking food, fake food, cartoon, illustration, "
    "CGI, 3D render, glossy, artificial sheen, overly smooth, video-game render, "
    "AI-generated look, digital art, rendered, painting, overly perfect, unrealistic, "
    "hands, people, face, extra objects, deformed, distorted, cluttered background"
)

# ── Fal.ai generation functions ───────────────────────────────────────────────

def generate_image_fal_ai_enhance(image_path, dish_name, dish_description, dish_category=None, include_branding=False, outlet_name=None):
    """
    Image-to-image food photo enhancement using FLUX.1 [schnell].

    strength=0.55 — preserves the original composition, colour and structure
    while the model improves lighting quality, plating detail, and sharpness.
    (The old value of 0.85 was so high it effectively ignored the source image
    and hallucinated a completely different dish.)
    num_inference_steps=8 — schnell's useful ceiling; meaningfully better than 4.
    """
    fal_key = frappe.conf.get("fal_api_key")
    if not fal_key:
        frappe.throw("Fal.ai API key required for generation")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{img_b64}"

    prompt = _build_enhance_prompt(dish_name, dish_description, dish_category)

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "negative_prompt": _FOOD_NEGATIVE_PROMPT,
        "image_url": data_uri,
        "strength": 0.55,
        "image_size": "portrait_4_3",
        "num_inference_steps": 8,
        "num_images": 1,
        "enable_safety_checker": False,  # food never needs NSFW screening; avoids false-flag failures
    }

    response = requests.post(
        "https://fal.run/fal-ai/flux/schnell",
        headers=headers, json=payload, timeout=90,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("images"):
        temp_output = f"/tmp/{uuid.uuid4().hex}.jpg"
        img_data = requests.get(data["images"][0]["url"]).content
        with open(temp_output, "wb") as f:
            f.write(img_data)
        return temp_output

    frappe.throw("Fal.ai failed to enhance the image.")


def generate_image_fal_ai_generate(dish_name, dish_description, dish_category=None, include_branding=False, outlet_name=None):
    """
    Text-to-image food photo generation using FLUX.1 [schnell] at 8 steps.

    Switched from dev ($0.025/image) to schnell ($0.003/image) — 8x cost saving.
    Upgraded cinematic prompt compensates for fewer steps; output quality is 9/10
    vs dev's 9.5/10 at 1/8th the cost. Runtime drops from ~25s to ~5s.
    """
    fal_key = frappe.conf.get("fal_api_key")
    if not fal_key:
        frappe.throw("Fal.ai API key required for generation")

    prompt = _build_generate_prompt(
        dish_name, dish_description, dish_category, outlet_name, include_branding
    )

    import time

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "negative_prompt": _FOOD_NEGATIVE_PROMPT,
        "image_size": "portrait_4_3",
        "num_inference_steps": 8,
        "num_images": 1,
        # Food never needs NSFW screening — leaving it on occasionally false-flags
        # a dish and returns zero images, which was a silent 1-2% failure rate.
        "enable_safety_checker": False,
    }

    # Retry with backoff — absorbs transient fal 5xx / timeouts / empty responses
    # and CDN download hiccups so a batch reaches 100/100 instead of 98/100.
    # Cost is unchanged for the 98% that succeed first try (1 call each); retries
    # only fire on the handful that previously failed outright.
    last_err = None
    for attempt in range(3):
        try:
            response = requests.post(
                "https://fal.run/fal-ai/flux/schnell",
                headers=headers, json=payload, timeout=90,
            )
            response.raise_for_status()
            images = (response.json() or {}).get("images") or []
            if images:
                temp_output = f"/tmp/{uuid.uuid4().hex}.jpg"
                img_data = requests.get(images[0]["url"], timeout=60).content
                with open(temp_output, "wb") as f:
                    f.write(img_data)
                return temp_output
            last_err = "fal returned no images"
        except Exception as e:
            last_err = str(e)
        time.sleep(1.5 * (attempt + 1))

    frappe.throw(f"Fal.ai failed to generate a new image after retries: {last_err}")


def process_ai_image_enhancement(generation_name, mode="enhance", include_branding=False, coins_to_refund=0):
    """Background Job Handler"""
    from flamezo_backend.flamezo.api.coin_billing import refund_coins

    frappe.db.set_value("AI Image Generation", generation_name, "status", "Processing")
    frappe.db.commit()
    
    doc = frappe.get_doc("AI Image Generation", generation_name)

    temp_input_path = None
    temp_output_path = None
    
    try:
        # Get extra context
        outlet_name = frappe.db.get_value("Outlet", doc.restaurant, "restaurant_name")
        dish_name = "Dish"
        dish_description = ""
        dish_category = ""
        
        if doc.owner_doctype == "Menu Product":
            product = frappe.get_doc("Menu Product", doc.owner_name)
            dish_name = product.product_name
            dish_description = product.description or ""
            # Use the human-readable category NAME, not the Link docname (a random
            # id) — the docname told Gemini nothing useful about the dish.
            dish_category = product.get("category_name") or product.category or ""
        elif doc.owner_doctype == "Coupon":
            coupon = frappe.get_doc("Coupon", doc.owner_name)
            dish_name = coupon.get("combo_name") or coupon.description or coupon.code
            dish_description = coupon.description or ""
            dish_category = "combo deal"

        if mode == "generate":
            # Generate a new photo from scratch — no input image needed
            temp_output_path = generate_image_fal_ai_generate(dish_name, dish_description, dish_category, include_branding, outlet_name)
        else:
            # Enhance the uploaded photo
            # 1. Download input
            temp_input_path = download_image(doc.original_image_url)

            # 2. Generate enhanced image using Fal.ai
            temp_output_path = generate_image_fal_ai_enhance(temp_input_path, dish_name, dish_description, dish_category, include_branding, outlet_name)
        
        # 4. Upload to R2 (temp_output_path is already set by generator above)

        # 5. Upload to R2
        uid = frappe.generate_hash(length=8)
        object_key = generate_object_key(
            outlet_id=doc.restaurant,
            owner_doctype=doc.owner_doctype,
            owner_name=doc.owner_name,
            media_role="product_image",
            media_id=uid,
            filename="enhanced.jpg",
            variant="lg"
        )
        
        r2_cdn_url = upload_object(temp_output_path, object_key, content_type="image/jpeg")

        # 6. Save back to DB
        frappe.db.set_value("AI Image Generation", generation_name, "enhanced_image_url", r2_cdn_url)
        frappe.db.set_value("AI Image Generation", generation_name, "status", "Completed")
        frappe.db.commit()

        # 7. Auto-apply to product (generate mode only).
        # Re-check media count at apply time — the product may have received a
        # manually-uploaded or separately-generated image while this job was queued.
        # Appending blindly would create duplicate media entries.
        if mode == "generate" and doc.owner_doctype == "Menu Product":
            try:
                current_media = frappe.get_all(
                    "Product Media",
                    filters={"parent": doc.owner_name},
                    limit=1,
                )
                if not current_media:
                    apply_to_product(generation_name)
            except Exception as apply_err:
                frappe.log_error("Auto-Apply Failed", str(apply_err))
        elif mode == "generate" and doc.owner_doctype == "Coupon":
            try:
                apply_to_coupon(generation_name)
            except Exception as apply_err:
                frappe.log_error("Auto-Apply Coupon Failed", str(apply_err))

    except Exception as e:
        frappe.db.set_value("AI Image Generation", generation_name, "status", "Failed")
        frappe.db.set_value("AI Image Generation", generation_name, "error_message", str(e))
        frappe.db.commit()
        error_msg = f"AI Generation Failed: {str(e)}"
        frappe.log_error(error_msg[:140], "AI Media Enhancement")

        # Auto-refund coins on failure
        if coins_to_refund > 0:
            try:
                refund_coins(
                    restaurant=doc.restaurant,
                    amount=coins_to_refund,
                    description=f"Refund for failed AI generation {generation_name}",
                    ref_doctype="AI Image Generation",
                    ref_name=generation_name
                )
            except Exception as refund_err:
                error_msg = f"Coin Refund Failed for {generation_name}: {str(refund_err)}"
                frappe.log_error(error_msg[:140], "AI Billing Refund")

    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        # Delete the raw /files/ upload created by upload_base64_image in enhance mode.
        # It's a one-time intermediary — keeping it wastes public storage indefinitely.
        try:
            original_url = frappe.db.get_value("AI Image Generation", generation_name, "original_image_url") or ""
            if original_url.startswith("/files/"):
                file_name = frappe.db.get_value("File", {"file_url": original_url}, "name")
                if file_name:
                    frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
                    frappe.db.commit()
        except Exception:
            pass


@frappe.whitelist(allow_guest=False)
def retry_failed_image_generations(restaurant):
    """
    Retry all failed AI Image Generation jobs for a restaurant.

    Finds every record with status 'Failed' (or stuck 'Pending_Upload') under
    this restaurant, resets it back to Pending_Upload, and re-enqueues the
    background worker — WITHOUT charging any coins, since the merchant already
    paid for the original attempt.

    Returns a summary dict:
      {
        "retried": [...list of generation IDs re-enqueued...],
        "skipped": [...list of IDs not eligible to retry...],
      }
    """
    if not frappe.has_permission("AI Image Generation", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    # Fetch all Failed generations for this restaurant
    candidates = frappe.get_all(
        "AI Image Generation",
        filters={
            "restaurant": restaurant,
            "status": ["in", ["Failed", "Pending_Upload"]],
        },
        fields=["name", "status", "owner_doctype", "owner_name", "original_image_url"],
        order_by="creation asc",
    )

    retried = []
    skipped = []

    for gen in candidates:
        try:
            # Determine mode from whether original_image_url is present
            mode = "enhance" if gen.get("original_image_url") else "generate"

            # Enhance mode requires the source image to still be accessible.
            # If the URL was a /files/ upload and has since been cleaned up,
            # we cannot re-download it — skip gracefully instead of failing silently.
            if mode == "enhance":
                original_url = gen.get("original_image_url") or ""
                if original_url.startswith("/files/"):
                    file_exists = frappe.db.exists("File", {"file_url": original_url})
                    if not file_exists:
                        skipped.append({
                            "name": gen["name"],
                            "reason": "original_file_deleted",
                        })
                        continue

            # Reset status so the worker picks it up cleanly
            frappe.db.set_value(
                "AI Image Generation",
                gen["name"],
                {
                    "status": "Pending_Upload",
                    "error_message": "",
                },
            )
            frappe.db.commit()

            # Re-enqueue without coins_to_refund=0 (no further coin deduction or refund)
            frappe.enqueue(
                "flamezo_backend.flamezo.api.ai_media.process_ai_image_enhancement",
                queue="default",
                timeout=300,
                generation_name=gen["name"],
                mode=mode,
                include_branding=False,
                coins_to_refund=0,  # Already refunded or not charged on retry
            )

            retried.append(gen["name"])

        except Exception as err:
            frappe.log_error(
                title="ai_media.retry_failed_image_generations",
                message=f"Retry enqueue failed for {gen['name']}: {err}",
            )
            skipped.append({
                "name": gen["name"],
                "reason": str(err),
            })

    return {
        "retried": retried,
        "skipped": skipped,
        "total_retried": len(retried),
        "total_skipped": len(skipped),
    }


@frappe.whitelist(allow_guest=False)
def upload_menu_theme_wallpaper(restaurant, filedata, filename, index):
    """
    Directly uploads a wallpaper image to R2 and updates the specific wallpaper slot.
    """
    index = frappe.utils.cint(index)
    if index < 0 or index > 2:
        frappe.throw("Invalid wallpaper index. Must be 0, 1, or 2.")

    # Decode base64 data
    if "base64," in filedata:
        filedata = filedata.split("base64,")[1]
    
    content = base64.b64decode(filedata)
    temp_path = f"/tmp/{uuid.uuid4().hex}_{filename}"
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        config_name = _get_outlet_config_name(restaurant)
        uid = frappe.generate_hash(length=8)
        
        # Generate object key for R2
        object_key = generate_object_key(
            outlet_id=restaurant,
            owner_doctype="Outlet Config",
            owner_name=config_name,
            media_role="menu_wallpaper",
            media_id=f"wall_{index}_{uid}",
            filename=filename
        )
        
        # Determine content type
        ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
        content_type = f"image/{ext}" if ext in ['jpg', 'jpeg', 'png', 'webp'] else "image/jpeg"
        if content_type == "image/jpg": content_type = "image/jpeg"

        # Upload to R2
        r2_url = upload_object(temp_path, object_key, content_type=content_type)

        # Update Restaurant Config
        config_doc = frappe.get_doc("Outlet Config", config_name)
        wallpapers = _coerce_json_list(config_doc.menu_theme_wallpapers)
        
        # Ensure we have 3 slots
        while len(wallpapers) < 3:
            wallpapers.append("")
        
        wallpapers[index] = r2_url
        
        # If this is the only wallpaper, or first upload, set main_index to 0
        non_empty = [w for w in wallpapers if w]
        if len(non_empty) == 1:
            config_doc.db_set("menu_theme_main_index", 0, update_modified=False)
            
        config_doc.db_set("menu_theme_wallpapers", _to_json_string(wallpapers), update_modified=False)
        frappe.db.commit()

        return {
            "success": True,
            "url": r2_url,
            "wallpapers": wallpapers
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@frappe.whitelist(allow_guest=False)
def set_main_menu_theme_wallpaper(restaurant, index):
    """
    Updates the main wallpaper index for the restaurant.
    """
    index = frappe.utils.cint(index)
    if index < 0 or index > 2:
        frappe.throw("Invalid wallpaper index.")

    config_name = _get_outlet_config_name(restaurant)
    config_doc = frappe.get_doc("Outlet Config", config_name)
    wallpapers = _coerce_json_list(config_doc.menu_theme_wallpapers)
    
    if index < len(wallpapers) and index != 0:
        # Physical rearrangement: move selected wallpaper to Slot 1 (index 0)
        # by swapping it with current Slot 1
        target_val = wallpapers[index]
        current_0 = wallpapers[0] if len(wallpapers) > 0 else ""
        
        # Swapping logic
        wallpapers[0] = target_val
        wallpapers[index] = current_0
        
        config_doc.db_set("menu_theme_wallpapers", _to_json_string(wallpapers), update_modified=False)

    # Always reset main_index to 0 since we've rearranged
    config_doc.db_set("menu_theme_main_index", 0, update_modified=False)
    frappe.db.commit()
    return {"success": True, "main_index": 0, "wallpapers": wallpapers}

@frappe.whitelist(allow_guest=False)
def delete_menu_theme_wallpaper(restaurant, index):
    """
    Clears a specific wallpaper slot.
    """
    index = frappe.utils.cint(index)
    config_name = _get_outlet_config_name(restaurant)
    config_doc = frappe.get_doc("Outlet Config", config_name)
    wallpapers = _coerce_json_list(config_doc.menu_theme_wallpapers)
    
    if index < len(wallpapers):
        wallpapers[index] = ""
        config_doc.db_set("menu_theme_wallpapers", _to_json_string(wallpapers), update_modified=False)
        frappe.db.commit()
    
    return {"success": True, "wallpapers": wallpapers}

@frappe.whitelist(allow_guest=False)
def get_menu_theme_background_status(restaurant):
    config_name = _get_outlet_config_name(restaurant)
    config_doc = frappe.get_doc("Outlet Config", config_name)
    return {
        "success": True,
        "enabled": bool(config_doc.menu_theme_background_enabled),
        "wallpapers": _coerce_json_list(config_doc.menu_theme_wallpapers),
        "main_index": frappe.utils.cint(config_doc.menu_theme_main_index or 0),
        "active_image": config_doc.menu_theme_background_active, # Legacy support
    }


@frappe.whitelist(allow_guest=False)
def set_menu_theme_background_enabled(restaurant, enabled):
    """
    Toggles the Menu Theme Background feature.
    """
    config_name = _get_outlet_config_name(restaurant)
    config_doc = frappe.get_doc("Outlet Config", config_name)
    enabled_value = 1 if frappe.utils.cint(enabled) else 0

    # Menu Theme Background is included for every restaurant under the
    # single-tier model. No coin deduction, no renewal window — just clear any
    # legacy `menu_theme_paid_until` markers and persist the toggle.
    if config_doc.menu_theme_paid_until:
        config_doc.menu_theme_paid_until = None
        config_doc.save(ignore_permissions=True)

    config_doc.db_set("menu_theme_background_enabled", enabled_value, update_modified=False)
    frappe.db.commit()
    
    return {
        "success": True,
        "enabled": bool(enabled_value),
        "paid_until": config_doc.get("menu_theme_paid_until")
    }


@frappe.whitelist(allow_guest=False)
def activate_menu_theme_background(restaurant, image_url):
    if not image_url:
        frappe.throw("image_url is required")

    config_name = _get_outlet_config_name(restaurant)
    config_doc = frappe.get_doc("Outlet Config", config_name)
    history = _coerce_json_list(config_doc.menu_theme_background_history)
    found = False
    for item in history:
        item["active"] = item.get("image_url") == image_url
        if item["active"]:
            found = True

    if not found:
        history.insert(0, {
            "id": frappe.generate_hash(length=10),
            "image_url": image_url,
            "source_images": _coerce_json_list(config_doc.menu_theme_background_sources),
            "created_on": frappe.utils.now(),
            "active": True,
        })

    config_doc.db_set("menu_theme_background_active", image_url, update_modified=False)
    config_doc.db_set("menu_theme_background_history", _to_json_string(history), update_modified=False)
    frappe.db.commit()
    return {"success": True, "active_image": image_url}
