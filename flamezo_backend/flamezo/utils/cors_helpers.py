# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
CORS Helper Functions for Flamezo Backend API
Provides comprehensive CORS header management for frontend access
"""

import frappe


# Allowed origins for CORS
ALLOWED_ORIGINS = [
	'https://app.flamezo_backend.com',
	'https://flamezo_backend.com',
	'https://www.flamezo_backend.com',
	'http://localhost:3000',
	'http://localhost:3001',
	'http://127.0.0.1:3000',
	'http://127.0.0.1:3001',
	'http://192.168.64.3:3000',
	'http://192.168.64.3:3001',
	'http://192.168.64.5:3000',
	'http://192.168.64.5:3001',
]

# Allowed HTTP methods
ALLOWED_METHODS = ['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS', 'PUT']

# Allowed headers
ALLOWED_HEADERS = [
	'Content-Type',
	'Authorization',
	'X-Requested-With',
	'X-Frappe-CSRF-Token',
	'Accept',
	'Origin',
]


def get_allowed_origins():
	"""
	Get allowed origins from site config or use defaults
	Returns list of allowed origins
	"""
	# Check if allow_cors is configured in site config
	if hasattr(frappe.conf, 'allow_cors') and frappe.conf.allow_cors:
		config_origins = frappe.conf.allow_cors
		if isinstance(config_origins, str):
			return [config_origins] if config_origins != '*' else ['*']
		elif isinstance(config_origins, list):
			return config_origins
	
	# Fallback to default allowed origins
	return ALLOWED_ORIGINS


def is_origin_allowed(origin):
	"""
	Check if the given origin is allowed for CORS
	Args:
		origin: The origin header value from the request
	Returns:
		bool: True if origin is allowed, False otherwise
	"""
	if not origin:
		return False
	
	allowed_origins = get_allowed_origins()
	
	# If wildcard is allowed
	if '*' in allowed_origins:
		return True
	
	# Check if origin is in allowed list
	return origin in allowed_origins


def add_cors_headers(response=None, request=None):
	"""
	Add CORS headers to all API responses
	This function is called in after_request hook with response and request parameters
	
	Args:
		response: The response object (passed by Frappe hook system)
		request: The request object (passed by Frappe hook system)
	"""
	# Get request from parameter or frappe.local
	if not request:
		request = getattr(frappe.local, 'request', None)
	
	if not request:
		return
	
	# Get origin from request
	origin = request.headers.get('Origin', '')
	
	# Check if origin is allowed
	if not is_origin_allowed(origin):
		return
	
	# Get response from parameter or frappe.local
	if not response:
		response = getattr(frappe.local, 'response', None)
	
	if not response:
		return
	
	# Add CORS headers
	if hasattr(response, 'headers') and response.headers is not None:
		# Werkzeug Response object
		response.headers['Access-Control-Allow-Origin'] = origin
		response.headers['Access-Control-Allow-Credentials'] = 'true'
		response.headers['Vary'] = 'Origin'
		
		if request.method == 'OPTIONS':
			response.headers['Access-Control-Allow-Methods'] = ', '.join(ALLOWED_METHODS)
			response.headers['Access-Control-Allow-Headers'] = ', '.join(ALLOWED_HEADERS)
			if not frappe.conf.developer_mode:
				response.headers['Access-Control-Max-Age'] = '86400'
		else:
			response.headers['Access-Control-Allow-Methods'] = ', '.join(ALLOWED_METHODS)
			response.headers['Access-Control-Allow-Headers'] = ', '.join(ALLOWED_HEADERS)
	elif isinstance(response, dict):
		# Frappe response dict
		# Note: Frappe's response dict doesn't have a standard 'headers' key for CORS,
		# but we can try to set it if needed. Usually, after_request is best for objects.
		# However, to be safe, we don't crash.
		pass


def handle_cors_preflight():
	"""
	Handle CORS preflight OPTIONS requests in before_request hook
	This ensures OPTIONS requests get proper CORS headers before Frappe's default handling
	"""
	if not hasattr(frappe.local, 'request') or not frappe.local.request:
		return
	
	request = frappe.local.request
	
	# Only handle OPTIONS requests
	if request.method != 'OPTIONS':
		return
	
	# Get origin from request
	origin = request.headers.get('Origin', '')
	
	# Check if origin is allowed
	if not is_origin_allowed(origin):
		return
	
	# Ensure response object exists (Frappe creates it for OPTIONS)
	if not hasattr(frappe.local, 'response'):
		from werkzeug.wrappers import Response
		frappe.local.response = Response()
	
	# Add CORS headers early for OPTIONS requests
	add_cors_headers(frappe.local.response, request)
