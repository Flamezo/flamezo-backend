#!/usr/bin/env python3
"""
Configure CORS for Cloudflare R2 Bucket

This script configures CORS rules for the R2 bucket to allow direct uploads from the browser.
Run this once after setting up the R2 bucket.

Usage:
    bench --site [site-name] execute flamezo_backend.flamezo.media.configure_r2_cors.configure_cors
"""

import frappe
import requests
import json


def configure_cors():
	"""Configure CORS rules for R2 bucket"""
	from .config import get_media_config
	
	config = get_media_config()
	
	# Get Cloudflare API credentials from site config
	cf_api_token = frappe.conf.get("cloudflare_api_token")
	if not cf_api_token:
		frappe.throw("Cloudflare API token not found in site_config.json. Add 'cloudflare_api_token' to proceed.")
	
	account_id = config["r2_account_id"]
	bucket_name = config["r2_bucket_name"]
	
	# CORS configuration
	cors_rules = [
		{
			"AllowedOrigins": [
				"http://localhost:8000",
				"http://localhost:3000",
				"https://*.flamezo_backend.com",
				frappe.utils.get_url()
			],
			"AllowedMethods": [
				"GET",
				"PUT",
				"POST",
				"DELETE",
				"HEAD"
			],
			"AllowedHeaders": [
				"*"
			],
			"ExposeHeaders": [
				"ETag",
				"Content-Length",
				"Content-Type"
			],
			"MaxAgeSeconds": 3600
		}
	]
	
	# Cloudflare R2 CORS API endpoint
	url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/{bucket_name}/cors"
	
	headers = {
		"Authorization": f"Bearer {cf_api_token}",
		"Content-Type": "application/json"
	}
	
	try:
		# Set CORS configuration
		response = requests.put(url, headers=headers, json=cors_rules)
		response.raise_for_status()
		
		frappe.msgprint(f"✅ CORS configured successfully for bucket: {bucket_name}")
		print(f"✅ CORS configured successfully for bucket: {bucket_name}")
		print(json.dumps(cors_rules, indent=2))
		
		return {
			"success": True,
			"message": "CORS configured successfully",
			"bucket": bucket_name,
			"rules": cors_rules
		}
		
	except requests.exceptions.RequestException as e:
		error_msg = f"Failed to configure CORS: {str(e)}"
		if hasattr(e.response, 'text'):
			error_msg += f"\nResponse: {e.response.text}"
		
		frappe.log_error(error_msg, "R2 CORS Configuration Error")
		frappe.throw(error_msg)


def get_cors_configuration():
	"""Get current CORS configuration for R2 bucket"""
	from .config import get_media_config
	
	config = get_media_config()
	cf_api_token = frappe.conf.get("cloudflare_api_token")
	
	if not cf_api_token:
		frappe.throw("Cloudflare API token not found in site_config.json")
	
	account_id = config["r2_account_id"]
	bucket_name = config["r2_bucket_name"]
	
	url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/{bucket_name}/cors"
	
	headers = {
		"Authorization": f"Bearer {cf_api_token}",
		"Content-Type": "application/json"
	}
	
	try:
		response = requests.get(url, headers=headers)
		response.raise_for_status()
		
		cors_config = response.json()
		print(json.dumps(cors_config, indent=2))
		
		return cors_config
		
	except requests.exceptions.RequestException as e:
		error_msg = f"Failed to get CORS configuration: {str(e)}"
		if hasattr(e.response, 'text'):
			error_msg += f"\nResponse: {e.response.text}"
		
		frappe.log_error(error_msg, "R2 CORS Get Error")
		frappe.throw(error_msg)
