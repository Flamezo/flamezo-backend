import frappe
import requests
import json
import base64
import os
import uuid
import random
from PIL import Image, ImageFilter, ImageOps
from flamezo_backend.flamezo.media.storage import upload_object, get_cdn_url, generate_object_key

MENU_THEME_COINS = 30
MENU_THEME_OUTPUT_SIZE = (1080, 1920)


def _get_restaurant_config_name(restaurant):
    config_name = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "name")
    if config_name:
        return config_name

    restaurant_name = frappe.db.get_value("Restaurant", restaurant, "restaurant_name") or restaurant
    config_doc = frappe.get_doc({
        "doctype": "Restaurant Config",
        "restaurant": restaurant,
        "restaurant_name": restaurant_name,
        "primary_color": "#DB782F",
        "default_theme": "light",
        "currency": frappe.db.get_value("Restaurant", restaurant, "currency") or "INR",
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
    config_doc = frappe.get_doc("Restaurant Config", config_name)
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

def _build_theme_generation_prompt(restaurant_name, items=None, color_theme=None):
    # Determine the color instruction based on the theme
    if color_theme and color_theme != "Multi-color" and color_theme != "None":
        color_instruction = f"COLOR THEME: Use vibrant, rich colors with a {color_theme} dominant tone that strictly matches the aesthetic of the original artwork."
    elif color_theme == "Multi-color":
        color_instruction = "COLOR THEME: Use a vibrant, rich multi-color palette that harmonizes with the original menu visuals."
    else:
        color_instruction = "COLOR THEME: EXACT COLOR MATCH. Do not change the colors. Use the exact same color palette, saturation, and tones from the original menu image."

    identify_instruction = (
        f"You are designing a premium, high-fidelity modern wallpaper based on {restaurant_name}'s actual menu visuals. "
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


def generate_menu_theme_background_gemini(image_paths, restaurant_name, items=None, color_theme=None):
    gemini_key = frappe.conf.get("gemini_api_key")
    if not gemini_key:
        frappe.throw("Gemini API key required for generation")

    prompt = _build_theme_generation_prompt(restaurant_name, items=items, color_theme=color_theme)
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

    response = requests.post(url, json=payload)
    response.raise_for_status()
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
    balance = frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0.0
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


def generate_image_gemini(image_path, dish_name, dish_description, dish_category=None, include_branding=False, restaurant_name=None):
    """Uses Gemini 2.5 Flash Image for native image-to-image enhancement."""
    gemini_key = frappe.conf.get("gemini_api_key")
    if not gemini_key:
        frappe.throw("Gemini API key required for generation")
    
    # Load input image
    with open(image_path, "rb") as f:
        img_data = f.read()
    
    # Load random local reference image
    ref_path = get_random_reference_image()
    
    with open(ref_path, "rb") as f:
        ref_data = f.read()

    description_text = f"Dish Details: {dish_description}" if dish_description else ""
    category_text = f"Category: {dish_category}" if dish_category else ""
    
    branding_text = ""
    if include_branding and restaurant_name:
        branding_text = (
            f"\nBRANDING INSTRUCTIONS: Incorporate the restaurant name '{restaurant_name}' in a minimalistic, professional way like in photography or pinterest level"
            f"It could be on the plating utensils (like a subtle engraving on a spoon or fork), "
            f"on a napkin, or discretely in the background (like eg on wooden table). "
            f"Keep it elegant and integrated into the scene."
        )

    prompt = (
        f"Disclaimer: Don't generate whole new image as per you, generated image should be aligned with first image."
        f"Convert (first image) which is {dish_name} image into professional food photography, restaurant menu photography, "
        f"magazine quality Pinterest-Style Images editorial food photography highly detailed. \n"
        f"{category_text}\n"
        f"{description_text}\n"
        f"{branding_text}\n"
        f"Note: I HAVE ALSO ATTACHED REFERENCE IMAGE (second image) FOR THE VISUALS I AM EXPECTING IN IMAGE, AND MAKE SURE THE BACKGROUND IS HAVING INGREDIENTS OR SIDES OR GARNISHES OR SERVING STYLE RELATED TO DISH"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={gemini_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img_data).decode('utf-8')}},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref_data).decode('utf-8')}}
            ]
        }]
    }
    
    response = requests.post(url, json=payload)
    response.raise_for_status()
    res_json = response.json()
    
    # Extract image from response
    if 'candidates' in res_json and res_json['candidates']:
        for part in res_json['candidates'][0]['content']['parts']:
            if 'inlineData' in part:
                # Save to a temporary file and return the path
                temp_output = f"/tmp/{uuid.uuid4().hex}.png"
                with open(temp_output, "wb") as f:
                    f.write(base64.b64decode(part['inlineData']['data']))
                return temp_output
                
    frappe.throw("Gemini failed to generate an image in the response.")


def generate_image_gemini_from_product(dish_name, dish_description, dish_category=None, include_branding=False, restaurant_name=None):
    """Generates a NEW food photo from scratch using only product info + reference image."""
    gemini_key = frappe.conf.get("gemini_api_key")
    if not gemini_key:
        frappe.throw("Gemini API key required for generation")

    # Load random local reference image
    ref_path = get_random_reference_image()

    with open(ref_path, "rb") as f:
        ref_data = f.read()

    description_text = f"Dish Details: {dish_description}" if dish_description else ""
    category_text = f"Category: {dish_category}" if dish_category else ""

    branding_text = ""
    if include_branding and restaurant_name:
        branding_text = (
            f"\nBRANDING INSTRUCTIONS: Incorporate the restaurant name '{restaurant_name}' in a minimalistic, professional way like in photography or pinterest level"
            f"It could be on the plating utensils (like a subtle engraving on a spoon or fork), "
            f"on a napkin, or discretely in the background (like eg on wooden table). "
            f"Keep it elegant and integrated into the scene."
        )

    prompt = (
        f"Generate a brand-new, original, professional food photography image of '{dish_name}'. "
        f"Style: restaurant menu photography, magazine-quality, Pinterest-style, editorial food photography, highly detailed. "
        f"The dish should be beautifully plated, with relevant garnishes, ingredients, or sides visible in the background. "
        f"{category_text}\n"
        f"{description_text}\n"
        f"{branding_text}\n"
        f"IMPORTANT: Use the attached REFERENCE IMAGE only for the visual style, lighting, and composition you should aim for — NOT as the dish itself. "
        f"Generate an entirely new image of '{dish_name}'. Do NOT copy or reproduce the reference dish."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={gemini_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref_data).decode('utf-8')}}
            ]
        }]
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()
    res_json = response.json()

    if 'candidates' in res_json and res_json['candidates']:
        for part in res_json['candidates'][0]['content']['parts']:
            if 'inlineData' in part:
                temp_output = f"/tmp/{uuid.uuid4().hex}.png"
                with open(temp_output, "wb") as f:
                    f.write(base64.b64decode(part['inlineData']['data']))
                return temp_output

    frappe.throw("Gemini failed to generate a new image from product details.")


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
        restaurant_name = frappe.db.get_value("Restaurant", doc.restaurant, "restaurant_name")
        dish_name = "Dish"
        dish_description = ""
        dish_category = ""
        
        if doc.owner_doctype == "Menu Product":
            product = frappe.get_doc("Menu Product", doc.owner_name)
            dish_name = product.product_name
            dish_description = product.description or ""
            dish_category = product.category or ""

        if mode == "generate":
            # Generate a new photo from scratch — no input image needed
            temp_output_path = generate_image_gemini_from_product(dish_name, dish_description, dish_category, include_branding, restaurant_name)
        else:
            # Enhance the uploaded photo
            # 1. Download input
            temp_input_path = download_image(doc.original_image_url)

            # 2. Generate enhanced image using Gemini
            temp_output_path = generate_image_gemini(temp_input_path, dish_name, dish_description, dish_category, include_branding, restaurant_name)
        
        # 4. Upload to R2 (temp_output_path is already set by generator above)

        # 5. Upload to R2
        uid = frappe.generate_hash(length=8)
        object_key = generate_object_key(
            restaurant_id=doc.restaurant,
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
        # Cleanup
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)


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
        config_name = _get_restaurant_config_name(restaurant)
        uid = frappe.generate_hash(length=8)
        
        # Generate object key for R2
        object_key = generate_object_key(
            restaurant_id=restaurant,
            owner_doctype="Restaurant Config",
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
        config_doc = frappe.get_doc("Restaurant Config", config_name)
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

    config_name = _get_restaurant_config_name(restaurant)
    config_doc = frappe.get_doc("Restaurant Config", config_name)
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
    config_name = _get_restaurant_config_name(restaurant)
    config_doc = frappe.get_doc("Restaurant Config", config_name)
    wallpapers = _coerce_json_list(config_doc.menu_theme_wallpapers)
    
    if index < len(wallpapers):
        wallpapers[index] = ""
        config_doc.db_set("menu_theme_wallpapers", _to_json_string(wallpapers), update_modified=False)
        frappe.db.commit()
    
    return {"success": True, "wallpapers": wallpapers}

@frappe.whitelist(allow_guest=False)
def get_menu_theme_background_status(restaurant):
    config_name = _get_restaurant_config_name(restaurant)
    config_doc = frappe.get_doc("Restaurant Config", config_name)
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
    - GOLD: Free.
    - SILVER: 100 coins / 30 days.
    """
    config_name = _get_restaurant_config_name(restaurant)
    config_doc = frappe.get_doc("Restaurant Config", config_name)
    enabled_value = 1 if frappe.utils.cint(enabled) else 0

    # Monetization Logic: Only when enabling
    if enabled_value:
        plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
        
        # GOLD has this feature included for free.
        # Only SILVER restaurants pay the activation/renewal fee.
        if plan_type == "SILVER":
            from flamezo_backend.flamezo.api.coin_billing import deduct_coins
            from frappe.utils import getdate, add_days, today
            
            paid_until = getdate(config_doc.menu_theme_paid_until) if config_doc.menu_theme_paid_until else None
            if not paid_until or paid_until < getdate(today()):
                # AI Deduction (100 coins = ₹100): Throws if insufficient coins
                deduct_coins(restaurant, 100, "AI Deduction", "Menu Theme Background activation fee (30 days)")
                # Extends for 30 days
                config_doc.menu_theme_paid_until = add_days(today(), 30)
                config_doc.save(ignore_permissions=True)
        else:
            # For GOLD, ensure paid_until is cleared to avoid unnecessary renewal checks
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

    config_name = _get_restaurant_config_name(restaurant)
    config_doc = frappe.get_doc("Restaurant Config", config_name)
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
