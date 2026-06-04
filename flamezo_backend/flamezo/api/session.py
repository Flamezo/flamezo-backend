# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Session lifecycle endpoints for the merchant dashboard SPA.

These power the client-side SessionGuard which keeps long-lived dashboard
sessions resilient:

  • get_csrf_token        — hand the SPA a fresh CSRF token so a stale
                            `window.csrf_token` (frozen at page load) can be
                            refreshed without a full reload. Self-heals the
                            403 / "Invalid Request" failures that otherwise
                            surface on write actions.

  • ping                  — cheap "am I still logged in?" probe for the
                            heartbeat. Returns the live user without throwing
                            so the client can decide how to react.

  • log_session_diagnostic — capture the exact state at the moment the SPA
                            detects a forced logout (cookies present, sid,
                            last request, response) so production tells us the
                            real trigger instead of us guessing.
"""

import json

import frappe
import frappe.sessions
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	"""Return the current session's CSRF token.

	Safe to call as a GET (no CSRF required for GET), which is exactly why the
	SPA can use it to recover from a stale token. For a Guest the token is
	empty — the client treats that as "session gone" and surfaces re-login.
	"""
	token = ""
	user = frappe.session.user if frappe.session else "Guest"

	if user and user != "Guest":
		# Generates-and-persists on first call, returns the existing one after.
		token = frappe.sessions.get_csrf_token()
		frappe.db.commit()

	return {
		"csrf_token": token,
		"user": user,
		"authenticated": bool(user and user != "Guest"),
	}


@frappe.whitelist(allow_guest=True)
def ping():
	"""Lightweight liveness probe for the heartbeat.

	Never throws on an expired session — returns ``authenticated: False`` so the
	client can drive the graceful re-login flow instead of eating an exception.
	"""
	user = frappe.session.user if frappe.session else "Guest"
	authenticated = bool(user and user != "Guest")

	# Read-only: never generate a token here (generation writes to the session
	# and needs a live session object). Echo the existing one if present so the
	# client can re-assert it after a silent rotation; otherwise empty.
	existing_token = ""
	if authenticated:
		try:
			existing_token = frappe.session.data.csrf_token or ""
		except (AttributeError, KeyError):
			existing_token = ""

	return {
		"authenticated": authenticated,
		"user": user if authenticated else None,
		"csrf_token": existing_token,
	}


@frappe.whitelist(allow_guest=True)
def log_session_diagnostic(context=None):
	"""Record the client-side state captured at a forced-logout event.

	The SPA posts a small JSON blob (last request, response status, whether a
	`sid` cookie was present, timestamp, url). We persist it to the Error Log so
	we can correlate real merchant logouts with server behaviour and pin the
	exact trigger. Best-effort: never raises back to the client.
	"""
	try:
		if isinstance(context, str):
			try:
				context = json.loads(context)
			except (ValueError, TypeError):
				context = {"raw": context}

		payload = {
			"reported_user": (frappe.session.user if frappe.session else None),
			"request_ip": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
			"user_agent": frappe.get_request_header("User-Agent"),
			"client": context or {},
		}

		frappe.log_error(
			title="SPA Session Diagnostic",
			message=frappe.as_json(payload, indent=2),
		)
	except Exception:
		# Diagnostics must never break the client's logout flow.
		pass

	return {"logged": True}
