# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import re


class MenuProduct(Document):
	def validate(self):
		"""Validate Product Media constraints and per-restaurant uniqueness"""
		# Ensure product_id is set
		if not self.product_id and self.product_name:
			self.product_id = self.generate_slug_from_name(self.product_name)
		
		# Ensure seo_slug is set
		if not self.seo_slug and self.product_name:
			self.seo_slug = self.generate_slug_from_name(self.product_name)
		
		# Auto-resolve duplicates for product_id and seo_slug
		if self.restaurant:
			self.resolve_duplicate_slugs()

	def resolve_duplicate_slugs(self):
		# check product_id
		if self.product_id:
			original_pid = self.product_id
			counter = 1
			while frappe.db.exists("Menu Product", {"product_id": self.product_id, "restaurant": self.restaurant, "name": ["!=", self.name]}):
				self.product_id = f"{original_pid}-{counter}"
				counter += 1

		# check seo_slug
		if self.seo_slug:
			original_slug = self.seo_slug
			counter = 1
			while frappe.db.exists("Menu Product", {"seo_slug": self.seo_slug, "restaurant": self.restaurant, "name": ["!=", self.name]}):
				self.seo_slug = f"{original_slug}-{counter}"
				counter += 1
		
		self.validate_product_media()
		
		# Compute has_no_media based on presence of product media
		self.has_no_media = 1
		if self.product_media:
			for media_item in self.product_media:
				if media_item.media_url:
					self.has_no_media = 0
					break
	
	def after_save(self):
		"""Clear top picks cache for the restaurant"""
		if self.get('restaurant'):
			frappe.cache().delete_value(f"top_picks:{self.restaurant}")
	
	def on_trash(self):
		"""Cleanup associated assets and references on deletion"""
		# 1. Clear top picks cache
		if self.get('restaurant'):
			frappe.cache().delete_value(f"top_picks:{self.restaurant}")
		
		# 2. Delete associated Media Assets
		media_assets = frappe.get_all("Media Asset", filters={"owner_doctype": "Menu Product", "owner_name": self.name}, fields=["name"])
		for asset in media_assets:
			frappe.delete_doc("Media Asset", asset.name, ignore_permissions=True)
		
		# 3. Cleanup non-transactional references
		# Delete cart entries for this product
		frappe.db.delete("Cart Entry", {"product": self.name})
		
		# Delete recommendations for this product
		frappe.db.delete("Menu Recommendation", {"source_product": self.name})
		frappe.db.delete("Menu Recommendation", {"recommended_product": self.name})
		
		# Delete legacy signature dish entries
		frappe.db.delete("Legacy Signature Dish", {"dish": self.name})

		# 5. Deactivate combo coupons that required this product
		self._deactivate_dependent_combo_coupons()

	def _deactivate_dependent_combo_coupons(self):
		"""
		When a Menu Product is deleted, find all active combo coupons that list
		this product in required_items and deactivate them so they don't silently
		fail at checkout.
		"""
		import json
		combo_coupons = frappe.get_all(
			"Coupon",
			filters={"restaurant": self.restaurant, "offer_type": "combo", "is_active": 1},
			fields=["name", "code", "required_items"],
		)
		deactivated = []
		for coupon in combo_coupons:
			if not coupon.required_items:
				continue
			try:
				required = json.loads(coupon.required_items) if isinstance(coupon.required_items, str) else coupon.required_items
				if self.name in (required or []):
					frappe.db.set_value("Coupon", coupon.name, "is_active", 0)
					deactivated.append(coupon.code)
			except Exception:
				pass
		if deactivated:
			frappe.db.commit()
			frappe.logger().warning(
				f"[menu_product] Deactivated combo coupons {deactivated} because product '{self.name}' was deleted."
			)
	
	def generate_slug_from_name(self, name):
		"""Generate a slug-like string from name"""
		if not name:
			return None
		
		# Convert to lowercase
		slug = name.lower()
		
		# Replace spaces and special characters with hyphens
		slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
		slug = re.sub(r'[-\s]+', '-', slug)  # Replace spaces and multiple hyphens with single hyphen
		slug = slug.strip('-')  # Remove leading/trailing hyphens
		
		# Limit length to 140 characters (Frappe name field limit)
		if len(slug) > 140:
			slug = slug[:140].rstrip('-')
		
		return slug
	
	def validate_product_media(self):
		"""Validate Product Media:
		- Maximum 3 media items per product
		- Maximum 1 video per product
		- File type must match media_type
		"""
		if not self.product_media:
			return
		
		media_count = len(self.product_media)
		video_count = 0
		
		# Define valid file extensions
		image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']
		video_extensions = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv']
		
		# Validate each media item
		for idx, media_item in enumerate(self.product_media, start=1):
			# Count videos
			if media_item.media_type == 'video':
				video_count += 1
			
			# Validate file type matches media_type
			if media_item.media_url and media_item.media_type:
				# Get file extension
				file_url = media_item.media_url
				file_extension = ''
				
				# Extract extension from file path
				if '.' in file_url:
					file_extension = file_url.split('.')[-1].lower()
				
				# Validate image files
				if media_item.media_type == 'image':
					if file_extension and file_extension not in image_extensions:
						frappe.throw(
							_('Row {0}: Image media type requires an image file (jpg, png, gif, etc.). File "{1}" is not a valid image file.').format(
								idx, file_url
							),
							title=_('Invalid File Type')
						)
				
				# Validate video files
				elif media_item.media_type == 'video':
					if file_extension and file_extension not in video_extensions:
						frappe.throw(
							_('Row {0}: Video media type requires a video file (mp4, webm, mov, etc.). File "{1}" is not a valid video file.').format(
								idx, file_url
							),
							title=_('Invalid File Type')
						)
		
		# Validate maximum 3 media items
		if media_count > 3:
			frappe.throw(
				_('Maximum 3 media items allowed per product. Currently {0} items found.').format(media_count),
				title=_('Maximum Media Items Exceeded')
			)
		
		# Validate maximum 1 video
		if video_count > 1:
			frappe.throw(
				_('Maximum 1 video allowed per product. Currently {0} videos found.').format(video_count),
				title=_('Maximum Videos Exceeded')
			)
