# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


ALLOWED_FEATURE_IDS = {"menu", "book-table", "legacy", "offers-events", "dine-play"}


class HomeFeature(Document):
	def validate(self):
		"""Business rules for Home Feature

		- Mandatory features cannot be disabled
		- One row per (restaurant, feature_id)
		- Feature IDs are restricted to the known set for new records
		"""

		# Ensure mandatory features cannot be disabled
		if self.is_mandatory and not self.is_enabled:
			frappe.throw(_("Mandatory features cannot be disabled"))

		# Restrict feature_id choices for new records so we don't create
		# arbitrary extra feature types beyond the core five.
		if self.is_new() and self.feature_id not in ALLOWED_FEATURE_IDS:
			frappe.throw(
				_("Invalid Feature ID: {0}. Allowed values: {1}").format(
					self.feature_id, ", ".join(sorted(ALLOWED_FEATURE_IDS))
				)
			)

		# Enforce uniqueness: only one document per restaurant + feature_id
		if self.restaurant and self.feature_id:
			existing = frappe.db.exists(
				"Home Feature",
				{
					"restaurant": self.restaurant,
					"feature_id": self.feature_id,
					"name": ["!=", self.name],
				},
			)
			if existing:
				frappe.throw(
					_(
						"Home Feature {0} is already configured for restaurant {1}. "
						"Edit the existing record instead of creating a duplicate."
					).format(self.feature_id, self.restaurant)
				)

	def on_update(self):
		"""Handle image updates and media asset synchronization"""
		# Always try to update media assets if there's an image
		if self.image_src:
			self.update_media_assets()
			
		# Log the update for debugging
		import frappe
		frappe.logger().info(f"Home Feature {self.name} updated with image_src: {self.image_src}")

	def update_media_assets(self):
		"""Update Media Assets to point to the latest image"""
		if not self.image_src:
			return

		# Get Media Assets linked to this Home Feature — newest and ready first
		media_assets = frappe.get_all(
			"Media Asset",
			filters={
				"owner_doctype": "Home Feature",
				"owner_name": self.name,
				"media_role": "home_feature_image",
				"status": ["in", ["uploaded", "ready"]],
			},
			fields=["name", "primary_url", "status"],
			order_by="modified desc"
		)

		# Prefer the most recent 'ready' asset; fall back to newest 'uploaded'
		target_asset = next((a for a in media_assets if a.status == "ready"), None) or \
					   (media_assets[0] if media_assets else None)

		if target_asset and target_asset.primary_url != self.image_src:
			frappe.db.set_value("Media Asset", target_asset.name, "primary_url", self.image_src)
			frappe.db.commit()

		# If no Media Assets exist, create one for the new image
		if not media_assets:
			try:
				# Create a new Media Asset record
				media_asset = frappe.get_doc({
					"doctype": "Media Asset",
					"restaurant": self.restaurant,
					"owner_doctype": "Home Feature",
					"owner_name": self.name,
					"media_role": "home_feature_image",
					"primary_url": self.image_src,
					"status": "ready",
					"is_active": 1
				})
				media_asset.insert(ignore_permissions=True)
				frappe.db.commit()
			except Exception as e:
				# Log error but don't fail the update
				frappe.log_error(
					f"Failed to create Media Asset for Home Feature {self.name}: {str(e)}",
					"Media Asset Creation"
				)


def update_home_feature_from_file(doc, method):
	"""Update Home Feature when a new file is uploaded"""
	if doc.attached_to_doctype == "Home Feature" and doc.attached_to_name:
		try:
			# Get the Home Feature document
			home_feature = frappe.get_doc("Home Feature", doc.attached_to_name)
			
			# Update the image_src to point to the new file
			if doc.file_url != home_feature.image_src:
				home_feature.image_src = doc.file_url
				home_feature.save(ignore_permissions=True)
				frappe.db.commit()
				
				# Also update Media Assets
				home_feature.update_media_assets()
				
				frappe.logger().info(f"Updated Home Feature {doc.attached_to_name} with new image: {doc.file_url}")
		except Exception as e:
			frappe.log_error(
				f"Failed to update Home Feature from file: {str(e)}",
				"Home Feature File Update"
			)


@frappe.whitelist()
def update_media_assets_from_ui(home_feature_name, image_src):
	"""Update Media Assets from UI upload"""
	try:
		home_feature = frappe.get_doc("Home Feature", home_feature_name)
		
		# Update the image_src if different
		if image_src != home_feature.image_src:
			home_feature.image_src = image_src
			home_feature.save(ignore_permissions=True)
			frappe.db.commit()
		
		# Update Media Assets
		home_feature.update_media_assets()
		
		return {"success": True, "message": "Media Assets updated successfully"}
	except Exception as e:
		frappe.log_error(
			f"Failed to update Media Assets from UI: {str(e)}",
			"Media Asset UI Update"
		)
		return {"success": False, "message": str(e)}

