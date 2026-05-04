# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from dinematters.dinematters.media.utils import get_allowed_roles, get_actual_media_role, get_restaurant_from_owner
import hashlib


class MediaAsset(Document):
	def before_insert(self):
		"""Generate media_id before insert"""
		if not self.media_id:
			self.media_id = self.generate_media_id()
	
	def validate(self):
		"""Validate media asset"""
		self.validate_owner_exists()
		self.validate_media_role_for_doctype()
		self.validate_restaurant_ownership()
	
	def generate_media_id(self):
		"""Generate unique media_id"""
		import uuid
		return f"med_{uuid.uuid4().hex[:12]}"
	
	def validate_owner_exists(self):
		"""Validate that owner document exists"""
		if self.owner_doctype and self.owner_name:
			if not frappe.db.exists(self.owner_doctype, self.owner_name):
				frappe.throw(f"{self.owner_doctype} {self.owner_name} does not exist")
	
	def validate_media_role_for_doctype(self):
		"""Validate that media_role is allowed for owner_doctype"""
		allowed_roles = get_allowed_roles()
		
		if self.owner_doctype in allowed_roles:
			actual_role = get_actual_media_role(self.owner_doctype, self.media_role)
			if actual_role not in allowed_roles[self.owner_doctype]:
				frappe.throw(
					f"Media role '{self.media_role}' is not allowed for {self.owner_doctype}. "
					f"Allowed roles: {', '.join(allowed_roles[self.owner_doctype])}"
				)
	
	def validate_restaurant_ownership(self):
		"""Validate that owner document belongs to the same restaurant"""
		if not self.owner_doctype or not self.owner_name or not self.restaurant:
			return
		
		# Get restaurant from owner document
		owner_restaurant = get_restaurant_from_owner(self.owner_doctype, self.owner_name)
		
		if owner_restaurant and owner_restaurant != self.restaurant:
			frappe.throw(
				f"Restaurant mismatch: Media Asset restaurant '{self.restaurant}' "
				f"does not match owner document restaurant '{owner_restaurant}'"
			)
	
	def mark_as_uploaded(self):
		"""Mark media as uploaded"""
		self.status = "uploaded"
		self.save(ignore_permissions=True)
	
	def mark_as_processing(self):
		"""Mark media as processing"""
		self.status = "processing"
		self.processing_attempts = (self.processing_attempts or 0) + 1
		self.save(ignore_permissions=True)
	
	def mark_as_ready(self):
		"""Mark media as ready"""
		self.status = "ready"
		self.processed_at = now_datetime()
		self.last_error = None
		self.save(ignore_permissions=True)
	
	def mark_as_failed(self, error_message):
		"""Mark media as failed"""
		self.status = "failed"
		self.last_error = error_message
		self.save(ignore_permissions=True)
	
	def soft_delete(self):
		"""Soft delete media asset"""
		self.is_deleted = 1
		self.is_active = 0
		self.status = "deleted"
		self.save(ignore_permissions=True)
	
	def get_variant_url(self, variant_name):
		"""Get URL for a specific variant"""
		for variant in self.media_variants:
			if variant.variant_name == variant_name:
				return variant.file_url
		return None
	
	def get_primary_variant_url(self):
		"""Get primary variant URL"""
		for variant in self.media_variants:
			if variant.is_primary:
				return variant.file_url
		return self.primary_url
