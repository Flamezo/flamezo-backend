"""
Centralized Media Asset Utilities
Provides helper functions for fetching and formatting Media Asset data across all APIs
"""

import frappe
from frappe.utils import get_url


def normalize_variant_name(variant_name):
	"""Map legacy short variant names to canonical API keys."""
	variant_map = {
		"thumb": "thumbnail",
		"sm": "small",
		"md": "medium",
		"lg": "large",
	}
	return variant_map.get(variant_name, variant_name)


def get_allowed_roles():
	"""Centralized mapping of owner doctypes to their allowed media roles"""
	return {
		"Menu Product": ["product_image", "product_video", "product_video_poster"],
		"Menu Category": ["category_image"],
		"Home Feature": ["home_feature_image"],
		"Restaurant": ["restaurant_logo", "restaurant_hero_video", "restaurant_banner", "restaurant_gallery_image", "event_image", "offer_image"],
		"Restaurant Config": ["restaurant_config_logo", "restaurant_config_hero_video", "apple_touch_icon"],
		"Menu Image Extractor": ["category_image"],
		"Event": ["event_image"],
		"Offer": ["offer_image"],
		"Legacy Content": ["legacy_hero_media", "legacy_hero_fallback", "legacy_footer_media", "legacy_member_image", "legacy_testimonial_avatar", "legacy_testimonial_dish_image", "legacy_gallery_image"],
		"Legacy Member": ["legacy_member_image"],
		"Legacy Testimonial": ["legacy_testimonial_avatar", "legacy_testimonial_dish_image"],
		"Legacy Gallery Image": ["legacy_gallery_image"],
		"Legacy Testimonial Image": ["legacy_testimonial_dish_image"]
	}


def get_actual_media_role(owner_doctype, media_role):
	"""
	Map prefixed media roles (e.g. "menu_category_category_image") 
	to base roles (e.g. "category_image").
	"""
	if not owner_doctype or not media_role:
		return media_role
		
	# Check if it's already a base role
	allowed_roles = get_allowed_roles()
	if owner_doctype in allowed_roles and media_role in allowed_roles[owner_doctype]:
		return media_role
		
	# Check if it has a doctype prefix
	prefix = owner_doctype.lower().replace(' ', '_') + "_"
	if media_role.startswith(prefix):
		actual_role = media_role[len(prefix):]
		# Only return the stripped version if it's actually allowed for this doctype
		if owner_doctype in allowed_roles and actual_role in allowed_roles[owner_doctype]:
			return actual_role
			
	return media_role


def get_media_asset_data(owner_doctype, owner_name, media_role, fallback_url=None):
	"""
	Centralized function to get Media Asset data for any DocType field
	
	Args:
		owner_doctype: Owner DocType (e.g., "Event", "Offer")
		owner_name: Owner document name
		media_role: Media role (e.g., "event_image", "offer_image")
		fallback_url: Fallback URL if no Media Asset exists (legacy /files/ path)
	
	Returns:
		dict: {
			"url": CDN URL or fallback (primary/medium variant),
			"blur_placeholder": Base64 blur placeholder (if image),
			"media_id": Media Asset name,
			"variants": {
				"thumbnail": {"url": str, "width": int, "height": int},
				"small": {...},
				"medium": {...},
				"large": {...}
			},
			"srcset": "url1 width1w, url2 width2w, ..." (for responsive images)
		}
	"""
	if not owner_name:
		return {
			"url": fallback_url or "",
			"blur_placeholder": None,
			"media_id": None,
			"variants": {},
			"srcset": None
		}
	
	# Normalize role (strip doctype prefix if present)
	actual_role = get_actual_media_role(owner_doctype, media_role)
	
	# Try to get Media Asset — prefer 'ready' (processed variants) over 'uploaded',
	# and newest record first so stale/orphaned assets don't shadow the current one.
	candidates = frappe.get_all(
		"Media Asset",
		filters={
			"owner_doctype": owner_doctype,
			"owner_name": owner_name,
			"media_role": actual_role,
			"status": ["in", ["uploaded", "ready"]]
		},
		fields=["name", "primary_url", "blur_placeholder", "media_kind", "status"],
		order_by="modified desc",
		limit=10
	)
	# Prefer 'ready' assets over 'uploaded' ones
	media_asset = next((a for a in candidates if a.get("status") == "ready"), None) or \
				  (candidates[0] if candidates else None)
	
	if media_asset and media_asset.get("primary_url"):
		result = {
			"url": media_asset["primary_url"],
			"blur_placeholder": media_asset.get("blur_placeholder"),
			"media_id": media_asset["name"],
			"variants": {},
			"srcset": None
		}
		
		# Get variants if image
		if media_asset.get("media_kind") == "image":
			variants = frappe.get_all(
				"Media Variant",
				filters={"parent": media_asset["name"]},
				fields=["variant_name", "file_url as url", "width", "height"],
				order_by="width asc"
			)
			
			# Format variants as dictionary for easy frontend access
			variants_dict = {}
			srcset_parts = []
			
			for v in variants:
				variant_name = v.get("variant_name", "")
				canonical_name = normalize_variant_name(variant_name)
				variant_payload = {
					"url": v["url"],
					"width": v.get("width"),
					"height": v.get("height")
				}
				variants_dict[canonical_name] = variant_payload
				if variant_name and variant_name != canonical_name:
					variants_dict[variant_name] = variant_payload
				
				# Build srcset string for responsive images
				if v.get("width"):
					srcset_parts.append(f"{v['url']} {v['width']}w")
			
			result["variants"] = variants_dict
			
			# Set srcset for responsive images
			if srcset_parts:
				result["srcset"] = ", ".join(srcset_parts)
		
		return result
	
	# Fallback to legacy URL
	url = fallback_url or ""
	
	return {
		"url": url,
		"blur_placeholder": None,
		"media_id": None,
		"variants": {},
		"srcset": None
	}


def format_media_field(data_dict, field_name, owner_doctype, owner_name, media_role, output_key=None):
	"""
	Helper to format a media field in API response data with CDN URLs, blur placeholders, and responsive variants
	
	Args:
		data_dict: Dictionary to update (API response data)
		field_name: Source field name in data (e.g., "image_src")
		owner_doctype: Owner DocType
		owner_name: Owner document name
		media_role: Media role
		output_key: Output key in response (defaults to camelCase of field_name)
	
	Example:
		format_media_field(event_data, "image_src", "Event", event_name, "event_image")
		# Adds: 
		#   event_data["imageSrc"] - Primary CDN URL
		#   event_data["imageSrcBlurPlaceholder"] - Base64 blur placeholder
		#   event_data["imageSrcVariants"] - Dict of variant sizes
		#   event_data["imageSrcSrcset"] - Srcset string for <img srcset>
	"""
	if output_key is None:
		# Convert snake_case to camelCase
		parts = field_name.split('_')
		output_key = parts[0] + ''.join(word.capitalize() for word in parts[1:])
	
	fallback_url = data_dict.get(field_name, "")
	media_data = get_media_asset_data(owner_doctype, owner_name, media_role, fallback_url)
	
	# Primary URL
	data_dict[output_key] = media_data["url"]
	
	# Blur placeholder for progressive loading
	if media_data.get("blur_placeholder"):
		data_dict[f"{output_key}BlurPlaceholder"] = media_data["blur_placeholder"]
	
	# Media Asset ID
	if media_data.get("media_id"):
		data_dict["mediaId"] = media_data["media_id"]
	
	# Variants dictionary for manual selection
	if media_data.get("variants"):
		data_dict[f"{output_key}Variants"] = media_data["variants"]
	
	# Srcset for responsive images
	if media_data.get("srcset"):
		data_dict[f"{output_key}Srcset"] = media_data["srcset"]


def get_media_assets_batch(owner_doctype, owner_names, media_roles):
	"""
	Batch fetch Media Assets and their Variants for multiple owners/roles.
	Reduces DB roundtrips significantly for lists.
	
	Args:
		owner_doctype: str
		owner_names: list of str
		media_roles: list of str
		
	Returns:
		dict: Mapping of (owner_name, media_role) -> media_data_dict
	"""
	if not owner_names or not media_roles:
		return {}
	
	# Normalize roles
	actual_roles = [get_actual_media_role(owner_doctype, r) for r in media_roles]
	
	# 1. Fetch all matching Media Assets in one query
	# Accept both 'uploaded' (processing in queue) and 'ready' so freshly-uploaded
	# assets are returned immediately rather than waiting for the worker to finish.
	# Order by modified desc so newest assets come first (used for deduplication below).
	assets = frappe.get_all(
		"Media Asset",
		filters={
			"owner_doctype": owner_doctype,
			"owner_name": ["in", owner_names],
			"media_role": ["in", actual_roles],
			"status": ["in", ["uploaded", "ready"]]
		},
		fields=["name", "owner_name", "media_role", "primary_url", "blur_placeholder", "media_kind", "status"],
		order_by="modified desc"
	)
	
	if not assets:
		return {}
	
	asset_names = [a["name"] for a in assets]
	
	# 2. Fetch all Variants for these assets in one query
	variants = frappe.get_all(
		"Media Variant",
		filters={"parent": ["in", asset_names]},
		fields=["parent", "variant_name", "file_url as url", "width", "height"],
		order_by="width asc"
	)
	
	# Group variants by asset name
	variants_by_asset = {}
	for v in variants:
		parent = v.pop("parent")
		if parent not in variants_by_asset:
			variants_by_asset[parent] = []
		variants_by_asset[parent].append(v)
	
	# 3. Process and format results
	# Track which keys already have a 'ready' asset so we don't overwrite with 'uploaded'.
	results = {}
	results_status = {}
	for asset in assets:
		asset_name = asset["name"]
		# Map back to the original role requested by the caller
		original_role = next((r for r in media_roles if get_actual_media_role(owner_doctype, r) == asset["media_role"]), asset["media_role"])
		key = (asset["owner_name"], original_role)

		# Skip if we already have a 'ready' asset for this key (assets ordered newest first)
		if key in results_status and results_status[key] == "ready" and asset.get("status") != "ready":
			continue
		# Skip if key already has same status and we already recorded one (newest wins via order_by)
		if key in results and results_status.get(key) == asset.get("status"):
			continue

		media_data = {
			"url": asset["primary_url"],
			"blur_placeholder": asset.get("blur_placeholder"),
			"media_id": asset["name"],
			"variants": {},
			"srcset": None
		}
		
		# Process variants if image
		if asset.get("media_kind") == "image" and asset_name in variants_by_asset:
			asset_variants = variants_by_asset[asset_name]
			variants_dict = {}
			srcset_parts = []
			
			for v in asset_variants:
				v_name = v.get("variant_name", "")
				canonical_name = normalize_variant_name(v_name)
				variant_payload = {
					"url": v["url"],
					"width": v.get("width"),
					"height": v.get("height")
				}
				variants_dict[canonical_name] = variant_payload
				if v_name and v_name != canonical_name:
					variants_dict[v_name] = variant_payload
				
				if v.get("width"):
					srcset_parts.append(f"{v['url']} {v['width']}w")
			
			media_data["variants"] = variants_dict
			if srcset_parts:
				media_data["srcset"] = ", ".join(srcset_parts)
		
		results[key] = media_data
		results_status[key] = asset.get("status")

	return results


def get_restaurant_from_owner(owner_doctype, owner_name):
	"""Get restaurant from owner document"""
	if owner_doctype == "Menu Product":
		return frappe.db.get_value("Menu Product", owner_name, "restaurant")
	elif owner_doctype == "Menu Category":
		return frappe.db.get_value("Menu Category", owner_name, "restaurant")
	elif owner_doctype == "Home Feature":
		return frappe.db.get_value("Home Feature", owner_name, "restaurant")
	elif owner_doctype == "Restaurant":
		return owner_name
	elif owner_doctype == "Restaurant Config":
		return frappe.db.get_value("Restaurant Config", owner_name, "restaurant")
	elif owner_doctype == "Menu Image Extractor":
		return frappe.db.get_value("Menu Image Extractor", owner_name, "restaurant")
	elif owner_doctype == "Event":
		return frappe.db.get_value("Event", owner_name, "restaurant")
	elif owner_doctype == "Offer":
		return frappe.db.get_value("Offer", owner_name, "restaurant")
	elif owner_doctype == "Legacy Content":
		return frappe.db.get_value("Legacy Content", owner_name, "restaurant")
	elif owner_doctype == "Legacy Member":
		# Legacy Member is a child table, get restaurant from parent
		parent = frappe.db.get_value("Legacy Member", owner_name, "parent")
		if parent:
			return frappe.db.get_value("Legacy Content", parent, "restaurant")
	elif owner_doctype == "Legacy Testimonial":
		# Legacy Testimonial is a child table, get restaurant from parent
		parent = frappe.db.get_value("Legacy Testimonial", owner_name, "parent")
		if parent:
			return frappe.db.get_value("Legacy Content", parent, "restaurant")
	elif owner_doctype == "Legacy Gallery Image":
		# Legacy Gallery Image is a child table, get restaurant from parent
		parent = frappe.db.get_value("Legacy Gallery Image", owner_name, "parent")
		if parent:
			return frappe.db.get_value("Legacy Content", parent, "restaurant")
	elif owner_doctype == "Legacy Testimonial Image":
		# Legacy Testimonial Image is a child table, get restaurant from parent
		parent = frappe.db.get_value("Legacy Testimonial Image", owner_name, "parent")
		if parent:
			parent_testimonial = frappe.db.get_value("Legacy Testimonial", parent, "parent")
			if parent_testimonial:
				return frappe.db.get_value("Legacy Content", parent_testimonial, "restaurant")
	else:
		from frappe import _
		frappe.throw(_(f"Unsupported owner doctype: {owner_doctype}"))
