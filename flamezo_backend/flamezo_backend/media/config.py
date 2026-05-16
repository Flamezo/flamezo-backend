# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

"""
Media configuration management for Cloudflare R2 and CDN
"""

import frappe
from frappe import _


def get_media_config():
	"""Get media configuration from site config"""
	config = frappe.conf.get("media_config", {})
	
	required_keys = [
		"r2_account_id",
		"r2_access_key_id",
		"r2_secret_access_key",
		"r2_bucket_name",
		"cdn_base_url"
	]
	
	missing_keys = [key for key in required_keys if not config.get(key)]
	
	if missing_keys:
		frappe.throw(
			_("Media configuration incomplete. Missing keys: {0}").format(", ".join(missing_keys)),
			title=_("Media Configuration Error")
		)
	
	return config


def get_r2_config():
	"""Get R2 storage configuration"""
	config = get_media_config()
	
	return {
		"account_id": config["r2_account_id"],
		"access_key_id": config["r2_access_key_id"],
		"secret_access_key": config["r2_secret_access_key"],
		"bucket_name": config["r2_bucket_name"],
		"region": config.get("r2_region", "auto"),
		"endpoint_url": f"https://{config['r2_account_id']}.r2.cloudflarestorage.com"
	}


def get_cdn_config():
	"""Get CDN configuration"""
	config = get_media_config()
	
	return {
		"base_url": config["cdn_base_url"],
		"cache_control": config.get("cdn_cache_control", "public, max-age=31536000, immutable")
	}


def get_environment():
	"""Get current environment (dev, staging, prod)"""
	return frappe.conf.get("media_environment", "dev")


def get_allowed_mime_types():
	"""Get allowed MIME types for uploads"""
	return {
		"image": [
			"image/jpeg",
			"image/png",
			"image/webp"
		],
		"video": [
			"video/mp4",
			"video/quicktime"
		]
	}


def get_max_upload_size():
	"""Get max upload size in bytes"""
	return {
		"image": 5 * 1024 * 1024,  # 5MB
		"video": 100 * 1024 * 1024  # 100MB
	}


def validate_media_config():
	"""Validate that media configuration is complete"""
	try:
		get_media_config()
		return True
	except Exception as e:
		frappe.log_error(f"Media configuration validation failed: {str(e)}", "Media Config Validation")
		return False
