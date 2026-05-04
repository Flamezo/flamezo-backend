# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

"""
R2 storage utilities for media management
"""

import frappe
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from .config import get_r2_config, get_cdn_config, get_environment
from dinematters.dinematters.utils.common import safe_log_error
import hashlib
import os


def get_r2_client():
	"""Get boto3 S3 client configured for Cloudflare R2"""
	config = get_r2_config()
	
	# Enhanced retry logic for R2 (S3-compatible)
	# InternalError (500) from R2 should be retried more aggressively
	retry_config = Config(
		retries={
			'max_attempts': 10,
			'mode': 'standard'
		},
		connect_timeout=5,
		read_timeout=60,
		signature_version='s3v4',
		s3={
			'expect_100_continue': False,
			'addressing_style': 'path'
		}
	)
	
	return boto3.client(
		's3',
		endpoint_url=config["endpoint_url"],
		aws_access_key_id=config["access_key_id"],
		aws_secret_access_key=config["secret_access_key"],
		region_name=config["region"],
		config=retry_config
	)


def generate_object_key(restaurant_id, owner_doctype, owner_name, media_role, media_id, filename, variant=None):
	"""
	Generate object key for R2 storage
	
	Optimized format (removed bucket name and env prefix):
	  restaurants/{restaurant_id}/menu_product/{product_id}/{media_id}/{variant}.webp
	  restaurants/{restaurant_id}/menu_product/{product_id}/{media_id}/raw.{ext}
	
	Old format (too long):
	  dinematters-prod/prod/restaurants/{restaurant_id}/menu_product/{owner_name}/{media_role}/{media_id}/variants/{variant}
	"""
	# Map doctypes to folder names
	doctype_map = {
		'Menu Product': 'menu_product',
		'Restaurant': 'restaurant',
		'Restaurant Config': 'restaurant_config'
	}
	
	doctype_folder = doctype_map.get(owner_doctype, 'other')
	
	# Sanitize IDs (remove special chars, keep alphanumeric and hyphens)
	import re
	restaurant_safe = re.sub(r'[^a-z0-9-]', '', restaurant_id.lower())
	owner_safe = re.sub(r'[^a-z0-9-]', '', owner_name.lower())
	
	# Build path: restaurants/{restaurant}/{doctype}/{owner}/{media_id}/{variant}
	ext = filename.split('.')[-1] if '.' in filename else 'jpg'
	if variant:
		# Use .jpg for variants to match user preference and avoid mismatch mapping
		return f"restaurants/{restaurant_safe}/{doctype_folder}/{owner_safe}/{media_id}/{variant}.{ext}"
	else:
		# Raw: restaurants/unvind/menu_product/burger/med_abc123/raw.jpg
		return f"restaurants/{restaurant_safe}/{doctype_folder}/{owner_safe}/{media_id}/raw.{ext}"


def generate_signed_upload_url(object_key, content_type, expiration=600):
	"""
	Generate presigned URL for direct upload to R2
	
	Args:
		object_key: S3 object key
		content_type: MIME type
		expiration: URL expiration in seconds (default 10 minutes)
	
	Returns:
		dict with upload_url and required headers
	"""
	try:
		client = get_r2_client()
		config = get_r2_config()
		
		# Generate presigned URL
		url = client.generate_presigned_url(
			'put_object',
			Params={
				'Bucket': config["bucket_name"],
				'Key': object_key,
				'ContentType': content_type
			},
			ExpiresIn=expiration,
			HttpMethod='PUT'
		)
		
		return {
			"upload_url": url,
			"headers": {
				"Content-Type": content_type
			},
			"expires_in": expiration
		}
	except ClientError as e:
		safe_log_error("R2 Upload URL Generation", str(e))
		frappe.throw(f"Failed to generate upload URL: {str(e)}")


def verify_object_exists(object_key):
	"""Verify that object exists in R2"""
	try:
		client = get_r2_client()
		config = get_r2_config()
		
		response = client.head_object(
			Bucket=config["bucket_name"],
			Key=object_key
		)
		
		return {
			"exists": True,
			"size": response.get("ContentLength"),
			"content_type": response.get("ContentType"),
			"etag": response.get("ETag", "").strip('"')
		}
	except ClientError as e:
		if e.response['Error']['Code'] == '404':
			return {"exists": False}
		else:
			safe_log_error("R2 Object Verification", str(e))
			frappe.throw(f"Failed to verify object: {str(e)}")


def download_object(object_key, local_path):
	"""Download object from R2 to local path"""
	try:
		client = get_r2_client()
		config = get_r2_config()
		
		# Ensure directory exists
		os.makedirs(os.path.dirname(local_path), exist_ok=True)
		
		client.download_file(
			config["bucket_name"],
			object_key,
			local_path
		)
		
		return local_path
	except ClientError as e:
		safe_log_error("R2 Object Download", str(e))
		frappe.throw(f"Failed to download object: {str(e)}")


def upload_object(local_path, object_key, content_type=None, metadata=None):
	"""Upload object from local path to R2"""
	try:
		client = get_r2_client()
		config = get_r2_config()
		
		extra_args = {}
		
		if content_type:
			extra_args['ContentType'] = content_type
		
		if metadata:
			extra_args['Metadata'] = metadata
		
		# Set cache control for public CDN delivery
		cdn_config = get_cdn_config()
		extra_args['CacheControl'] = cdn_config["cache_control"]
		
		# Use put_object instead of upload_file for more direct R2 interaction
		# This avoids managed multipart transfers which can sometimes cause InternalError on R2
		with open(local_path, 'rb') as f:
			client.put_object(
				Bucket=config["bucket_name"],
				Key=object_key,
				Body=f,
				**extra_args
			)
		
		return get_cdn_url(object_key)
	except ClientError as e:
		error_msg = f"Error uploading object: {str(e)}"
		safe_log_error("R2 Object Upload", error_msg)
		frappe.throw(error_msg)


def delete_object(object_key):
	"""Delete object from R2"""
	try:
		client = get_r2_client()
		config = get_r2_config()
		
		client.delete_object(
			Bucket=config["bucket_name"],
			Key=object_key
		)
		
		return True
	except ClientError as e:
		safe_log_error("R2 Object Deletion", str(e))
		return False


def get_cdn_url(object_key):
	"""Get CDN URL for object key"""
	cdn_config = get_cdn_config()
	base_url = cdn_config["base_url"].rstrip('/')
	
	return f"{base_url}/{object_key}"


def calculate_file_hash(file_path):
	"""Calculate SHA256 hash of file"""
	sha256_hash = hashlib.sha256()
	
	with open(file_path, "rb") as f:
		for byte_block in iter(lambda: f.read(4096), b""):
			sha256_hash.update(byte_block)
	
	return sha256_hash.hexdigest()
