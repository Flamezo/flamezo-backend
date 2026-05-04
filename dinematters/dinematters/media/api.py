# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

"""
Media upload and management APIs
"""

import frappe
from frappe import _
from .config import get_allowed_mime_types, get_max_upload_size
from .storage import generate_object_key, generate_signed_upload_url, verify_object_exists
from .utils import get_allowed_roles, get_actual_media_role, get_restaurant_from_owner
from dinematters.dinematters.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES
from dinematters.dinematters.utils.common import safe_log_error
import os


@frappe.whitelist()
def request_upload_session(owner_doctype, owner_name, media_role, filename, content_type, size_bytes):
	"""
	Request upload session for direct R2 upload
	
	Args:
		owner_doctype: DocType that will own this media (e.g., "Menu Product")
		owner_name: Name of the owner document
		media_role: Role of the media (e.g., "product_image")
		filename: Original filename
		content_type: MIME type
		size_bytes: File size in bytes
	
	Returns:
		dict with upload_id, object_key, upload_url, headers, expires_in
	"""
	# Validate authentication
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)
	
	# Validate owner document exists
	if not frappe.db.exists(owner_doctype, owner_name):
		frappe.throw(_(f"{owner_doctype} {owner_name} does not exist"))
	
	# Get restaurant from owner document
	restaurant = get_restaurant_from_owner(owner_doctype, owner_name)
	
	# Validate user has access to restaurant
	validate_restaurant_access(restaurant)
	
	# Validate media role for doctype
	validate_media_role_for_doctype(owner_doctype, media_role)
	
	# Determine media kind from content type
	media_kind = get_media_kind_from_mime(content_type)
	
	# Validate content type
	validate_content_type(content_type, media_kind)
	
	# Validate file size
	validate_file_size(size_bytes, media_kind)
	
	# Generate media_id
	import uuid
	media_id = f"med_{uuid.uuid4().hex[:12]}"
	
	# Sanitize filename
	safe_filename = sanitize_filename(filename)
	
	# Normalize role for storage and session record
	actual_role = get_actual_media_role(owner_doctype, media_role)
	
	# Generate object key
	object_key = generate_object_key(
		restaurant_id=restaurant,
		owner_doctype=owner_doctype,
		owner_name=owner_name,
		media_role=actual_role,
		media_id=media_id,
		filename=safe_filename
	)
	
	# Generate signed upload URL
	upload_data = generate_signed_upload_url(object_key, content_type)
	
	# Create upload session record (optional - for tracking)
	upload_session = frappe.get_doc({
		"doctype": "Media Upload Session",
		"upload_id": media_id,
		"restaurant": restaurant,
		"owner_doctype": owner_doctype,
		"owner_name": owner_name,
		"media_role": actual_role,
		"media_kind": media_kind,
		"object_key": object_key,
		"filename": safe_filename,
		"content_type": content_type,
		"size_bytes": size_bytes,
		"status": "pending"
	})
	
	try:
		upload_session.insert(ignore_permissions=True)
	except Exception as e:
		# Upload session is optional, log but don't fail
		safe_log_error("Upload Session Creation", str(e))
	
	return {
		"upload_id": media_id,
		"object_key": object_key,
		"upload_url": upload_data["upload_url"],
		"headers": upload_data["headers"],
		"expires_in": upload_data["expires_in"]
	}


@frappe.whitelist()
def confirm_upload(upload_id, owner_doctype, owner_name, media_role, alt_text=None, caption=None, display_order=0):
	"""
	Confirm upload and create Media Asset
	
	This endpoint is idempotent - calling it multiple times with same upload_id
	will not create duplicate media assets.
	
	Args:
		upload_id: Upload ID from request_upload_session
		owner_doctype: Owner DocType
		owner_name: Owner document name
		media_role: Media role
		alt_text: Optional alt text
		caption: Optional caption
		display_order: Display order
	
	Returns:
		dict with media_id, status, primary_url
	"""
	# Validate authentication
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)
	
	# Check if media asset already exists for this upload_id (idempotency)
	existing_asset = frappe.db.get_value("Media Asset", {"media_id": upload_id}, "name")
	
	if existing_asset:
		# Return existing asset
		asset_doc = frappe.get_doc("Media Asset", existing_asset)
		# Use primary_url if available, otherwise construct from raw_object_key
		url = asset_doc.primary_url
		if not url and asset_doc.raw_object_key:
			from dinematters.dinematters.media.storage import get_cdn_url
			url = get_cdn_url(asset_doc.raw_object_key)
		return {
			"media_id": asset_doc.media_id,
			"status": asset_doc.status,
			"primary_url": url,
			"message": "Media asset already exists"
		}
	
	# Get upload session
	upload_session = frappe.db.get_value(
		"Media Upload Session",
		{"upload_id": upload_id},
		["object_key", "restaurant", "media_kind", "filename", "content_type", "size_bytes"],
		as_dict=True
	)
	
	if not upload_session:
		frappe.throw(_("Upload session not found"))
	
	# Verify object exists in R2
	verification = verify_object_exists(upload_session.object_key)
	
	if not verification.get("exists"):
		frappe.throw(_("File not found in storage. Please retry upload."))
	
	# Get restaurant from owner
	restaurant = get_restaurant_from_owner(owner_doctype, owner_name)
	
	# Validate restaurant access
	validate_restaurant_access(restaurant)
	
	# Get file extension
	file_extension = os.path.splitext(upload_session.filename)[1].lstrip('.')
	
	# Construct CDN URL immediately — persisted into the record so it's
	# available to API queries without waiting for the async processing job.
	from dinematters.dinematters.media.storage import get_cdn_url
	cdn_url = get_cdn_url(upload_session.object_key)

	# Normalize role (ensure we save the canonical role to the Media Asset record)
	actual_role = get_actual_media_role(owner_doctype, media_role)
	
	# Create Media Asset with primary_url set from the start so that
	# get_media_assets_batch / get_media_asset_data can surface it immediately.
	media_asset = frappe.get_doc({
		"doctype": "Media Asset",
		"media_id": upload_id,
		"restaurant": restaurant,
		"owner_doctype": owner_doctype,
		"owner_name": owner_name,
		"media_role": actual_role,
		"media_kind": upload_session.media_kind,
		"source_filename": upload_session.filename,
		"source_extension": file_extension,
		"source_mime_type": upload_session.content_type,
		"source_size_bytes": verification.get("size") or upload_session.size_bytes,
		"storage_provider": "cloudflare_r2",
		"raw_object_key": upload_session.object_key,
		"primary_url": cdn_url,
		"status": "uploaded",
		"alt_text": alt_text,
		"caption": caption,
		"display_order": display_order or 0,
		"is_active": 1
	})
	
	media_asset.insert(ignore_permissions=True)
	frappe.db.commit()
	
	# Update upload session status
	frappe.db.set_value("Media Upload Session", {"upload_id": upload_id}, "status", "confirmed")
	frappe.db.commit()
	
	# Enqueue processing job — will generate variants, optimise image, and flip status to "ready"
	frappe.enqueue(
		"dinematters.dinematters.media.jobs.process_media_asset",
		media_asset_name=media_asset.name,
		queue="default",
		timeout=600,
		is_async=True,
		now=False
	)
	
	return {
		"name": media_asset.name,
		"media_id": media_asset.media_id,
		"status": media_asset.status,
		"primary_url": cdn_url,
		"raw_object_key": upload_session.object_key,
		"message": "Upload confirmed, processing started"
	}


@frappe.whitelist()
def get_media_asset(media_id):
	"""Get media asset by media_id"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)
	
	asset = frappe.db.get_value(
		"Media Asset",
		{"media_id": media_id, "is_deleted": 0},
		["name", "media_id", "status", "primary_url", "poster_url", "width", "height", 
		 "duration_seconds", "alt_text", "caption", "display_order", "media_kind"],
		as_dict=True
	)
	
	if not asset:
		frappe.throw(_("Media asset not found"))
	
	# Get variants
	variants = frappe.get_all(
		"Media Variant",
		filters={"parent": asset.name},
		fields=["variant_name", "file_url", "width", "height", "size_bytes", "format", "is_primary"]
	)
	
	asset["variants"] = variants
	
	return asset


@frappe.whitelist()
def delete_media_asset(media_id):
	"""Soft delete media asset"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)
	
	asset_name = frappe.db.get_value("Media Asset", {"media_id": media_id}, "name")
	
	if not asset_name:
		frappe.throw(_("Media asset not found"))
	
	asset_doc = frappe.get_doc("Media Asset", asset_name)
	
	# Validate restaurant access
	validate_restaurant_access(asset_doc.restaurant)
	
	# Soft delete
	asset_doc.soft_delete()
	
	# Enqueue cleanup job
	frappe.enqueue(
		"dinematters.dinematters.media.jobs.cleanup_deleted_media",
		media_asset_name=asset_name,
		queue="long",
		timeout=300
	)
	
	return {"message": "Media asset deleted"}


# Helper functions



def validate_restaurant_access(restaurant):
	"""Validate that current user has access to restaurant"""
	user_roles = frappe.get_roles()
	# System Manager, Administrator, and Supervisors have access to all
	if any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles):
		return True
	
	# Check if user is restaurant manager or has restaurant user role
	user_restaurants = frappe.get_all(
		"Restaurant User",
		filters={"user": frappe.session.user},
		fields=["restaurant"]
	)
	
	user_restaurant_list = [r.restaurant for r in user_restaurants]
	
	if restaurant not in user_restaurant_list:
		frappe.throw(_("You do not have access to this restaurant"), frappe.PermissionError)
	
	return True


def validate_media_role_for_doctype(owner_doctype, media_role):
	"""Validate media role is allowed for owner doctype"""
	allowed_roles = get_allowed_roles()
	
	if owner_doctype not in allowed_roles:
		frappe.throw(_(f"Media upload not supported for {owner_doctype}"))
	
	actual_role = get_actual_media_role(owner_doctype, media_role)
	
	if actual_role not in allowed_roles[owner_doctype]:
		frappe.throw(
			_(f"Media role '{media_role}' not allowed for {owner_doctype}. Allowed: {', '.join(allowed_roles[owner_doctype])}")
		)


def get_media_kind_from_mime(content_type):
	"""Determine media kind from MIME type"""
	if content_type.startswith("image/"):
		return "image"
	elif content_type.startswith("video/"):
		return "video"
	else:
		frappe.throw(_(f"Unsupported content type: {content_type}"))


def validate_content_type(content_type, media_kind):
	"""Validate content type matches media kind"""
	# Accept all image/* and video/* types
	if media_kind == 'image' and not content_type.startswith('image/'):
		frappe.throw(
			_(f"Content type '{content_type}' is not an image type. Expected image/*")
		)
	
	if media_kind == 'video' and not content_type.startswith('video/'):
		frappe.throw(
			_(f"Content type '{content_type}' is not a video type. Expected video/*")
		)


def validate_file_size(size_bytes, media_kind):
	"""Validate file size is within limits"""
	max_sizes = get_max_upload_size()
	max_size = max_sizes.get(media_kind, 5 * 1024 * 1024)
	
	if size_bytes > max_size:
		max_mb = max_size / (1024 * 1024)
		frappe.throw(_(f"File size exceeds maximum allowed size of {max_mb}MB"))


def sanitize_filename(filename):
	"""Sanitize filename for safe storage"""
	import re
	# Remove path components
	filename = os.path.basename(filename)
	# Replace spaces and special chars
	filename = re.sub(r'[^\w\s.-]', '', filename)
	filename = re.sub(r'[-\s]+', '-', filename)
	return filename.lower()
