# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
API endpoints for Legacy/Place Content
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
import json
from frappe.utils import get_url
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api
from dinematters.dinematters.media.utils import get_media_asset_data
import json


@frappe.whitelist(allow_guest=True)
def get_legacy_content(restaurant_id):
	"""
	GET /api/method/dinematters.dinematters.api.legacy.get_legacy_content
	Get all content for "The Place & Its Legacy" page
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get restaurant name
		restaurant_name = frappe.db.get_value("Restaurant", restaurant, "restaurant_name")
		
		# Get or create legacy content
		legacy_name = frappe.db.get_value("Legacy Content", {"restaurant": restaurant}, "name")
		
		if not legacy_name:
			# Return default structure if not exists
			return {
				"success": True,
				"data": get_default_legacy_content(restaurant_name)
			}
		
		legacy_doc = frappe.get_doc("Legacy Content", legacy_name)
		
		# Format hero section
		hero_media_src = legacy_doc.hero_media_src
		if hero_media_src and hero_media_src.startswith("/files/"):
			hero_media_src = get_url(hero_media_src)
		
		hero_fallback = legacy_doc.hero_fallback_image
		if hero_fallback and hero_fallback.startswith("/files/"):
			hero_fallback = get_url(hero_fallback)
		
		hero_title = legacy_doc.hero_title or f"Discover the Culinary Heritage of {restaurant_name}"
		
		hero = {
			"mediaType": legacy_doc.hero_media_type or "video",
			"mediaSrc": hero_media_src or "",
			"fallbackImage": hero_fallback or "",
			"title": hero_title,
			"ctaButtons": [
				{"text": "Explore Our Menu", "route": "/main-menu"},
				{"text": "Book a Table", "route": "/book-table"}
			]
		}
		
		# Format content
		content = {
			"openingText": legacy_doc.opening_text or "",
			"paragraph1": legacy_doc.paragraph_1 or "",
			"paragraph2": legacy_doc.paragraph_2 or ""
		}
		
		# Format signature dishes - return array of dish IDs for frontend compatibility
		signature_dishes = []
		sorted_dishes = sorted(legacy_doc.signature_dishes, key=lambda x: x.display_order or 0)
		for dish in sorted_dishes:
			signature_dishes.append(dish.dish)
		
		# Format testimonials
		testimonials = []
		for testimonial in legacy_doc.testimonials:
			dish_images = []
			# Handle dish images (new table structure) with Media Asset data
			if hasattr(testimonial, 'dish_images') and testimonial.dish_images:
				for img_row in testimonial.dish_images:
					# Get dish image from Media Asset or fallback
					dish_media = get_media_asset_data(
						"Legacy Testimonial Image",
						img_row.name,
						"legacy_testimonial_dish_image",
						img_row.image
					)
					if dish_media["url"]:
						dish_images.append(dish_media["url"])
			# Fallback: handle old JSON format for backward compatibility
			elif hasattr(testimonial, 'dish_images') and isinstance(testimonial.dish_images, str):
				try:
					dish_images = json.loads(testimonial.dish_images)
					dish_images = [get_url(img) if img.startswith("/files/") else img for img in dish_images]
				except:
					pass
			
			# Get avatar from Media Asset or fallback
			avatar_media = get_media_asset_data(
				"Legacy Testimonial",
				testimonial.name,
				"legacy_testimonial_avatar",
				testimonial.avatar
			)
			avatar_url = avatar_media["url"]
			
			testimonials.append({
				"id": int(testimonial.idx) if hasattr(testimonial, 'idx') else len(testimonials) + 1,
				"name": testimonial.name,
				"location": testimonial.location or "",
				"rating": int(testimonial.rating) if testimonial.rating else 5,
				"text": testimonial.text,
				"dishImages": dish_images,
				"avatar": avatar_url or testimonial.name[:2].upper()
			})
		
		# Format members with Media Asset data
		members = []
		for member in legacy_doc.members:
			# Get member image from Media Asset or fallback
			member_media = get_media_asset_data(
				"Legacy Member",
				member.name,
				"legacy_member_image",
				member.image
			)
			
			members.append({
				"id": int(member.idx) if hasattr(member, 'idx') else len(members) + 1,
				"name": member.name,
				"image": member_media["url"],
				"imageBlurPlaceholder": member_media.get("blur_placeholder"),
				"role": member.role or "",
				"displayOrder": member.display_order
			})
		
		# Format gallery - merge items from Restaurant Gallery and Legacy Content
		gallery_images = []
		seen_urls = set()

		# 1. Fetch selected items from the new Restaurant Gallery Dashboard (Primary Source)
		selected_gallery_items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={"restaurant": restaurant, "is_selected": 1},
			fields=["url", "title", "media_type", "sort_order"],
			order_by="sort_order asc",
			limit=25
		)
		
		for item in selected_gallery_items:
			url = item.url
			if url and url not in seen_urls:
				gallery_images.append({
					"src": url,
					"title": item.title or "",
					"type": item.media_type or "Image"
				})
				seen_urls.add(url)

		# 2. Add images from Legacy Content (backward compatibility / additional curated images)
		if hasattr(legacy_doc, 'gallery_featured_images') and legacy_doc.gallery_featured_images:
			for img_row in legacy_doc.gallery_featured_images:
				# Get gallery image from Media Asset or fallback
				gallery_media = get_media_asset_data(
					"Legacy Gallery Image",
					img_row.name,
					"legacy_gallery_image",
					img_row.image
				)
				if gallery_media["url"] and gallery_media["url"] not in seen_urls:
					gallery_images.append({
						"src": gallery_media["url"],
						"blurPlaceholder": gallery_media.get("blur_placeholder"),
						"title": img_row.title or ""
					})
					seen_urls.add(gallery_media["url"])
		# Fallback: handle old JSON format for backward compatibility
		elif hasattr(legacy_doc, 'gallery_featured_images') and isinstance(legacy_doc.gallery_featured_images, str):
			try:
				img_list = json.loads(legacy_doc.gallery_featured_images)
				for img in img_list:
					url = get_url(img) if img.startswith("/files/") else img
					if url and url not in seen_urls:
						gallery_images.append({"src": url, "title": ""})
						seen_urls.add(url)
			except:
				pass
		
		gallery = {
			"featuredImages": gallery_images
		}
		
		# Format Instagram reels
		instagram_reels = []
		for reel in legacy_doc.instagram_reels:
			instagram_reels.append({
				"id": str(reel.idx) if hasattr(reel, 'idx') else str(len(instagram_reels) + 1),
				"reelLink": reel.reel_link,
				"title": reel.title or ""
			})
		
		# Format footer
		footer_media = legacy_doc.footer_media_src
		if footer_media and footer_media.startswith("/files/"):
			footer_media = get_url(footer_media)
		
		footer = {
			"mediaSrc": footer_media or "",
			"title": legacy_doc.footer_title or "Ready for Your Next Culinary Adventure?",
			"description": legacy_doc.footer_description or "Start exploring our menu today and discover the hidden gems of our culinary legacy with just a few clicks.",
			"ctaButton": {
				"text": legacy_doc.footer_cta_text or "Explore Our Menu",
				"route": legacy_doc.footer_cta_route or "/main-menu"
			}
		}
		
		return {
			"success": True,
			"data": {
				"hero": hero,
				"content": content,
				"signatureDishes": signature_dishes,
				"testimonials": testimonials,
				"members": members,
				"gallery": gallery,
				"instagramReels": instagram_reels,
				"footer": footer
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_legacy_content: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "LEGACY_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def update_legacy_content(restaurant_id, hero=None, content=None, signature_dishes=None, testimonials=None, members=None, gallery=None, instagram_reels=None, footer=None):
	"""
	POST /api/method/dinematters.dinematters.api.legacy.update_legacy_content
	Update content for "The Place & Its Legacy" page (Admin only)
	"""
	try:
		# Validate restaurant access
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Parse JSON strings if needed
		if isinstance(hero, str):
			hero = json.loads(hero) if hero else {}
		if isinstance(content, str):
			content = json.loads(content) if content else {}
		if isinstance(signature_dishes, str):
			signature_dishes = json.loads(signature_dishes) if signature_dishes else []
		if isinstance(testimonials, str):
			testimonials = json.loads(testimonials) if testimonials else []
		if isinstance(members, str):
			members = json.loads(members) if members else []
		if isinstance(gallery, str):
			gallery = json.loads(gallery) if gallery else {}
		if isinstance(instagram_reels, str):
			instagram_reels = json.loads(instagram_reels) if instagram_reels else []
		if isinstance(footer, str):
			footer = json.loads(footer) if footer else {}
		
		# Get or create legacy content
		legacy_name = frappe.db.get_value("Legacy Content", {"restaurant": restaurant}, "name")
		
		if legacy_name:
			legacy_doc = frappe.get_doc("Legacy Content", legacy_name)
		else:
			legacy_doc = frappe.get_doc({
				"doctype": "Legacy Content",
				"restaurant": restaurant
			})
		
		# Update hero
		if hero:
			if "mediaType" in hero:
				legacy_doc.hero_media_type = hero["mediaType"]
			if "mediaSrc" in hero:
				legacy_doc.hero_media_src = hero["mediaSrc"]
			if "fallbackImage" in hero:
				legacy_doc.hero_fallback_image = hero["fallbackImage"]
			if "title" in hero:
				legacy_doc.hero_title = hero["title"]
		
		# Update content
		if content:
			if "openingText" in content:
				legacy_doc.opening_text = content["openingText"]
			if "paragraph1" in content:
				legacy_doc.paragraph_1 = content["paragraph1"]
			if "paragraph2" in content:
				legacy_doc.paragraph_2 = content["paragraph2"]
		
		# Update signature dishes
		if signature_dishes:
			legacy_doc.signature_dishes = []
			for dish_data in signature_dishes:
				legacy_doc.append("signature_dishes", {
					"dish": dish_data.get("dishId"),
					"display_order": dish_data.get("displayOrder", 0)
				})
		
		# Update testimonials
		if testimonials:
			legacy_doc.testimonials = []
			for test_data in testimonials:
				testimonial_row = legacy_doc.append("testimonials", {
					"name": test_data.get("name"),
					"location": test_data.get("location", ""),
					"rating": test_data.get("rating", 5),
					"text": test_data.get("text"),
					"avatar": test_data.get("avatar", test_data.get("name", "")[:2].upper()),
					"display_order": test_data.get("displayOrder", 0)
				})
				
				# Handle dish images (new table structure)
				dish_images = test_data.get("dishImages", [])
				if dish_images:
					for img_url in dish_images:
						testimonial_row.append("dish_images", {
							"image": img_url,
							"display_order": len(testimonial_row.dish_images) + 1
						})
		
		# Update members
		if members:
			legacy_doc.members = []
			for member_data in members:
				member_image = member_data.get("image", "")
				# Extract file path if full URL provided
				if member_image and "://" in member_image:
					# Extract path from URL (e.g., "http://domain/files/image.jpg" -> "/files/image.jpg")
					import re
					match = re.search(r'/files/[^/]+', member_image)
					if match:
						member_image = match.group(0)
				
				legacy_doc.append("members", {
					"name": member_data.get("name"),
					"image": member_image,
					"role": member_data.get("role", ""),
					"display_order": member_data.get("displayOrder", 0)
				})
		
		# Update gallery
		if gallery and "featuredImages" in gallery:
			legacy_doc.gallery_featured_images = []
			for img_data in gallery["featuredImages"]:
				# Handle both new format (object with src/title) and old format (string URL)
				if isinstance(img_data, dict):
					img_url = img_data.get("src", "")
					img_title = img_data.get("title", "")
				else:
					img_url = img_data
					img_title = ""
				
				if img_url:
					legacy_doc.append("gallery_featured_images", {
						"image": img_url,
						"title": img_title,
						"display_order": len(legacy_doc.gallery_featured_images) + 1
					})
		
		# Update Instagram reels
		if instagram_reels:
			legacy_doc.instagram_reels = []
			for reel_data in instagram_reels:
				legacy_doc.append("instagram_reels", {
					"reel_link": reel_data.get("reelLink"),
					"title": reel_data.get("title", ""),
					"display_order": reel_data.get("displayOrder", 0)
				})
		
		# Update footer
		if footer:
			if "mediaSrc" in footer:
				legacy_doc.footer_media_src = footer["mediaSrc"]
			if "title" in footer:
				legacy_doc.footer_title = footer["title"]
			if "description" in footer:
				legacy_doc.footer_description = footer["description"]
			if "ctaButton" in footer:
				cta = footer["ctaButton"]
				if "text" in cta:
					legacy_doc.footer_cta_text = cta["text"]
				if "route" in cta:
					legacy_doc.footer_cta_route = cta["route"]
		
		# Save
		if legacy_name:
			legacy_doc.save(ignore_permissions=True)
		else:
			legacy_doc.insert(ignore_permissions=True)
		
		return {
			"success": True,
			"message": "Legacy content updated successfully"
		}
	except Exception as e:
		frappe.log_error(f"Error in update_legacy_content: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "LEGACY_UPDATE_ERROR",
				"message": str(e)
			}
		}


def get_default_legacy_content(restaurant_name):
	"""Get default legacy content structure"""
	return {
		"hero": {
			"mediaType": "video",
			"mediaSrc": "",
			"fallbackImage": "",
			"title": f"Discover the Culinary Heritage of {restaurant_name}",
			"ctaButtons": [
				{"text": "Explore Our Menu", "route": "/main-menu"},
				{"text": "Book a Table", "route": "/book-table"}
			]
		},
		"content": {
			"openingText": "",
			"paragraph1": "",
			"paragraph2": ""
		},
		"signatureDishes": [],
		"testimonials": [],
		"members": [],
		"gallery": {
			"featuredImages": []
		},
		"instagramReels": [],
		"footer": {
			"mediaSrc": "",
			"title": "Ready for Your Next Culinary Adventure?",
			"description": "Start exploring our menu today and discover the hidden gems of our culinary legacy with just a few clicks.",
			"ctaButton": {
				"text": "Explore Our Menu",
				"route": "/main-menu"
			}
		}
	}


