# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
import urllib.request
import os
import tempfile
import time
import random
from io import BytesIO
from functools import wraps


# MySQL error codes that mean "transient, retry me":
#   1213 = Deadlock found when trying to get lock; try restarting transaction
#   1205 = Lock wait timeout exceeded; try restarting transaction
_MYSQL_TRANSIENT_ERROR_CODES = (1213, 1205)


def _is_transient_db_error(exc):
	"""Return True if the exception is a retryable MySQL deadlock / lock-wait."""
	args = getattr(exc, "args", None)
	if args and isinstance(args, tuple) and len(args) > 0:
		code = args[0]
		if isinstance(code, int) and code in _MYSQL_TRANSIENT_ERROR_CODES:
			return True
	# Fall back to message sniffing for wrapped exceptions
	msg = str(exc).lower()
	return "deadlock" in msg or "lock wait timeout" in msg


def retry_on_deadlock(max_attempts=6, base_delay=0.1, max_delay=4.0):
	"""
	Decorator: retry a function on MySQL deadlocks / lock-wait timeouts with
	exponential backoff + jitter. Rolls back the transaction before each retry.

	Use on any function that performs database writes which might contend with
	concurrent jobs (e.g. media variant inserts, child-table replacements).
	Non-transient exceptions are re-raised immediately. Returns the function's
	value on the first successful attempt.
	"""

	def decorator(fn):
		@wraps(fn)
		def wrapper(*args, **kwargs):
			last_exc = None
			for attempt in range(max_attempts):
				try:
					return fn(*args, **kwargs)
				except Exception as e:
					last_exc = e
					if not _is_transient_db_error(e):
						raise
					try:
						frappe.db.rollback()
					except Exception:
						pass
					if attempt >= max_attempts - 1:
						break
					delay = min(max_delay, base_delay * (2 ** attempt))
					time.sleep(delay + random.random() * base_delay)
			# All retries exhausted - re-raise the last transient error.
			raise last_exc  # type: ignore[misc]

		return wrapper

	return decorator

def safe_log_error(title, message=None, reference_doctype=None, reference_name=None):
	"""
	Unified safe logging that prevents CharacterLengthExceededError on the Title field.
	Automatically handles single-argument calls and ensures title length compliance.
	"""
	if message is None:
		# If only one argument provided, treat it as message and use a default title
		message = title
		title = "Flamezo Error"
	
	# Frappe log_error(title, message)
	# Ensure title is within 140 chars
	safe_title = str(title)[:140]
	# Ensure message is truncated to a reasonable size if needed
	safe_message = str(message)
	
	return frappe.log_error(title=safe_title, message=safe_message, 
						   reference_doctype=reference_doctype, 
						   reference_name=reference_name)

def safe_fetch_url(url, timeout=10, user_agent=None):
	"""
	Fetch URL with a proper User-Agent and timeout to avoid WAF/Cloudflare blocks.
	"""
	if not user_agent:
		user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
		
	req = urllib.request.Request(
		url, 
		headers={'User-Agent': user_agent}
	)
	return urllib.request.urlopen(req, timeout=timeout)

def resolve_and_fetch_media(url, timeout=10):
	"""
	Unified helper to fetch media:
	1. Try direct R2 download if it is an internal CDN URL
	2. Fallback to safe HTTP request with User-Agent
	"""
	from flamezo_backend.flamezo.media.storage import download_object
	from flamezo_backend.flamezo.media.config import get_cdn_config
	
	cdn_config = get_cdn_config()
	cdn_base = cdn_config.get("base_url", "").rstrip('/')
	
	is_internal = False
	if cdn_base and url.startswith(cdn_base):
		is_internal = True
	elif "cdn.flamezo_backend.com" in url or "dev-cdn.flamezo_backend.com" in url:
		is_internal = True
		
	if is_internal:
		# Try R2 first
		current_base = cdn_base if (cdn_base and url.startswith(cdn_base)) else ""
		if not current_base:
			if "cdn.flamezo_backend.com" in url: current_base = "https://cdn.flamezo_backend.com"
			elif "dev-cdn.flamezo_backend.com" in url: current_base = "https://dev-cdn.flamezo_backend.com"
			
		if current_base:
			object_key = url[len(current_base):].lstrip('/')
			# Use a temp file for download
			with tempfile.NamedTemporaryFile(delete=False) as tf:
				temp_path = tf.name
			try:
				download_object(object_key, temp_path)
				with open(temp_path, 'rb') as f:
					return f.read()
			except Exception as e:
				# Log error using our safe helper
				safe_log_error("R2 Fallback Error", f"Failed to download {object_key} from R2: {e}")
			finally:
				if os.path.exists(tf.name):
					os.remove(tf.name)

	# Fallback to HTTP
	try:
		with safe_fetch_url(url, timeout=timeout) as response:
			return response.read()
	except Exception as e:
		safe_log_error("Media Fetch Error", f"Failed to fetch {url} via HTTP: {e}")
		raise
