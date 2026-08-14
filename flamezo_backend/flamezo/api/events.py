# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Events
outlet_id is optional — omit for consumer-level discovery (returns all active outlets' events).
"""

import frappe
from frappe import _
from frappe.utils import today, get_url, formatdate, format_time
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.media.utils import format_media_field


def _parse_media(raw):
	"""Parse the Event media_gallery JSON into a safe list of {type, url}."""
	try:
		items = frappe.parse_json(raw or "[]")
	except Exception:
		return []
	if not isinstance(items, list):
		return []
	out = []
	for m in items:
		if isinstance(m, dict) and m.get("url"):
			out.append({"type": m.get("type") or "image", "url": m.get("url")})
	return out


def _format_event(event, include_outlet=False, outlet_meta=None):
	"""Shared formatter for a single event row."""
	date_str = formatdate(event["date"], "yyyy-mm-dd") if event.get("date") else ""
	time_str = format_time(event["time"], "HH:mm:ss") if event.get("time") else ""

	event_data = {
		"id": str(event["id"]),
		"title": event["title"],
		"description": event.get("description", ""),
		"date": date_str,
		"time": time_str,
		"location": event.get("location", ""),
		"category": event.get("category", ""),
		"featured": bool(event.get("featured", False)),
		"status": event.get("status", "upcoming"),
		"image_src": event.get("image_src", ""),
		"google_maps_link": event.get("google_maps_link", ""),
		"registration_link": event.get("registration_link", ""),
		"media": _parse_media(event.get("media_gallery")),
	}

	if include_outlet and outlet_meta:
		event_data["outletId"] = outlet_meta.get("restaurant_id", "")
		event_data["outletName"] = outlet_meta.get("restaurant_name", "")
		event_data["outletCity"] = outlet_meta.get("city", "")

	if event.get("repeat_this_event"):
		event_data["recurring"] = {
			"repeatThisEvent": True,
			"repeatOn": event.get("repeat_on", ""),
			"repeatTill": formatdate(event["repeat_till"], "yyyy-mm-dd") if event.get("repeat_till") else None,
		}
		if event.get("repeat_on") == "Weekly":
			weekdays = [d for d in ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"] if event.get(d)]
			weekdays_display = [d.capitalize() for d in weekdays]
			if weekdays_display:
				event_data["recurring"]["weekdays"] = weekdays_display
	else:
		event_data["recurring"] = {"repeatThisEvent": False}

	format_media_field(event_data, "image_src", "Event", event.get("id"), "event_image", "imageSrc")
	if event.get("image_alt"):
		event_data["imageAlt"] = event["image_alt"]

	return event_data


_EVENT_FIELDS = [
	"name as id", "title", "image_src", "image_alt", "description",
	"date", "time", "location", "category", "featured", "status", "is_active",
	"repeat_this_event", "repeat_on", "repeat_till", "google_maps_link",
	"registration_link", "monday", "tuesday", "wednesday", "thursday",
	"friday", "saturday", "sunday", "restaurant", "media_gallery",
]


@frappe.whitelist(allow_guest=True)
def get_events(outlet_id=None, featured=None, category=None, upcoming_only=True):
	"""
	GET /api/method/flamezo_backend.flamezo.api.events.get_events

	outlet_id optional:
	  - provided  → events for that outlet only (existing behaviour)
	  - omitted   → all active-outlet events (consumer discovery page)
	"""
	try:
		consumer_mode = not outlet_id

		or_filters = None
		if consumer_mode:
			# Fetch all active outlets once for name/city lookup
			active_outlets = frappe.get_all(
				"Restaurant",
				filters={"is_active": 1},
				fields=["name", "restaurant_id", "restaurant_name", "city"],
			)
			outlet_map = {r["name"]: r for r in active_outlets}
			active_names = list(outlet_map.keys())

			# Global events feed: show events that belong to an active outlet OR
			# platform events with no merchant attached (restaurant unset).
			filters = {"is_active": 1}
			or_filters = [["restaurant", "is", "not set"]]
			if active_names:
				or_filters.append(["restaurant", "in", active_names])
		else:
			restaurant = validate_restaurant_for_api(outlet_id)
			filters = {"restaurant": restaurant, "is_active": 1}

		if featured is not None:
			filters["featured"] = 1 if featured else 0
		if category:
			filters["category"] = category
		if upcoming_only:
			filters["status"] = ["in", ["upcoming", "recurring"]]

		events = frappe.get_all("Event", fields=_EVENT_FIELDS, filters=filters,
								or_filters=or_filters,
								order_by="display_order asc, title asc")

		formatted_events = []
		for event in events:
			if consumer_mode:
				meta = outlet_map.get(event.get("restaurant"), {})
				formatted_events.append(_format_event(event, include_outlet=True, outlet_meta=meta))
			else:
				formatted_events.append(_format_event(event))

		return {"success": True, "data": {"events": formatted_events}}

	except Exception as e:
		frappe.log_error(f"Error in get_events: {str(e)}")
		return {"success": False, "error": {"code": "EVENT_FETCH_ERROR", "message": str(e)}}



@frappe.whitelist(allow_guest=True)
def join_event(event_id):
	"""An app user joins an event. Their details are pulled from their session
	and stored so the merchant sees who joined. Idempotent per (event, customer)."""
	from flamezo_backend.flamezo.utils.customer_helpers import get_customer_token, get_customer_from_token

	token = get_customer_token()
	if not token:
		return {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Please sign in to join."}}
	customer_id = get_customer_from_token(token)
	if not customer_id:
		return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Session expired. Sign in again."}}
	if not event_id or not frappe.db.exists("Event", event_id):
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Event not found."}}

	if frappe.db.exists("Event Registration", {"event": event_id, "customer": customer_id}):
		return {"success": True, "data": {"joined": True, "already_joined": True}}

	cust = frappe.db.get_value("Customer", customer_id, ["customer_name", "phone"], as_dict=True) or {}
	doc = frappe.get_doc({
		"doctype": "Event Registration",
		"event": event_id,
		"customer": customer_id,
		"customer_name": cust.get("customer_name") or "",
		"customer_phone": cust.get("phone") or "",
		"joined_at": frappe.utils.now_datetime(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"joined": True}}


@frappe.whitelist(allow_guest=True)
def leave_event(event_id):
	"""An app user cancels their event join."""
	from flamezo_backend.flamezo.utils.customer_helpers import get_customer_token, get_customer_from_token

	token = get_customer_token()
	customer_id = get_customer_from_token(token) if token else None
	if not customer_id:
		return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Please sign in."}}
	name = frappe.db.exists("Event Registration", {"event": event_id, "customer": customer_id})
	if name:
		frappe.delete_doc("Event Registration", name, ignore_permissions=True, force=True)
		frappe.db.commit()
	return {"success": True, "data": {"joined": False}}


def deactivate_past_events():
	"""Scheduled: auto-deactivate non-recurring events once their time is over —
	either the event date has passed, or it's today and the end time is done.
	Deactivated events (is_active=0, status='past') drop off the app feed and
	fall to the bottom of the dashboard list. Recurring events are left alone.
	"""
	try:
		frappe.db.sql(
			"""
			UPDATE `tabEvent`
			SET is_active = 0, status = 'past'
			WHERE is_active = 1
			  AND COALESCE(repeat_this_event, 0) = 0
			  AND date IS NOT NULL
			  AND (
			        date < CURDATE()
			     OR (date = CURDATE() AND end_time IS NOT NULL AND end_time < CURTIME())
			  )
			"""
		)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"deactivate_past_events failed: {e}", "Events Auto-Deactivate")


@frappe.whitelist()
def get_outlet_active_events(restaurant):
	"""Events an outlet is currently hosting — upcoming/ongoing (date >= today)
	or recurring. Non-recurring events drop out automatically once their date
	passes, so the merchant dashboard's Event tab disappears after the event.
	"""
	try:
		if not restaurant:
			return {"success": True, "data": {"events": []}}
		rows = frappe.get_all(
			"Event",
			filters={"restaurant": restaurant, "is_active": 1},
			or_filters=[["date", ">=", today()], ["repeat_this_event", "=", 1]],
			fields=_EVENT_FIELDS,
			order_by="date asc, title asc",
		)
		return {"success": True, "data": {"events": [_format_event(r) for r in rows]}}
	except Exception as e:
		frappe.log_error(f"Error in get_outlet_active_events: {str(e)}")
		return {"success": False, "error": {"code": "EVENT_FETCH_ERROR", "message": str(e)}}


@frappe.whitelist(allow_guest=True)
def get_event_detail(event_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.events.get_event_detail

	Returns full details for a single event by its ID.
	Consumer-facing — no outlet_id required.
	"""
	try:
		if not event_id:
			frappe.throw(_("event_id is required"))

		events = frappe.get_all("Event", fields=_EVENT_FIELDS + ["restaurant"],
								filters={"name": event_id, "is_active": 1}, limit=1)
		if not events:
			frappe.throw(_("Event not found"), frappe.DoesNotExistError)

		event = events[0]
		outlet_meta = {}
		if event.get("restaurant"):
			r = frappe.db.get_value(
				"Restaurant",
				event["restaurant"],
				["restaurant_id", "restaurant_name", "city"],
				as_dict=True,
			)
			if r:
				outlet_meta = r

		formatted = _format_event(event, include_outlet=True, outlet_meta=outlet_meta)
		return {"success": True, "data": {"event": formatted}}

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Event not found"}}
	except Exception as e:
		frappe.log_error(f"Error in get_event_detail: {str(e)}")
		return {"success": False, "error": {"code": "EVENT_FETCH_ERROR", "message": str(e)}}


@frappe.whitelist()
def save_event(outlet_id, event_data):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.save_event
	Create or update an event
	"""
	try:
		# Validate outlet and user access
		restaurant = validate_restaurant_for_api(outlet_id, user=frappe.session.user)
		
		# Parse event data (handles JSON string from frontend)
		if isinstance(event_data, str):
			import json
			event_data = json.loads(event_data)
		
		event_id = event_data.get("id")
		
		# Build doc data
		doc_data = {
			"doctype": "Event",
			"restaurant": restaurant,
			"title": event_data.get("title"),
			"description": event_data.get("description"),
			"date": event_data.get("date"),
			"time": event_data.get("time"),
			"location": event_data.get("location"),
			"google_maps_link": event_data.get("google_maps_link"),
			"registration_link": event_data.get("registration_link"),
			"category": event_data.get("category"),
			"featured": 1 if event_data.get("featured") else 0,
			"status": event_data.get("status", "upcoming"),
			"is_active": 1 if event_data.get("is_active", True) else 0,
			"image_src": event_data.get("image_src"),
			"image_alt": event_data.get("image_alt"),
			"display_order": event_data.get("display_order", 0)
		}
		
		# Recurring event data
		recurring = event_data.get("recurring", {})
		if recurring.get("repeatThisEvent"):
			doc_data["repeat_this_event"] = 1
			doc_data["repeat_on"] = recurring.get("repeatOn")
			doc_data["repeat_till"] = recurring.get("repeatTill")
			
			if recurring.get("repeatOn") == "Weekly":
				weekdays = recurring.get("weekdays", [])
				doc_data["monday"] = 1 if "Monday" in weekdays else 0
				doc_data["tuesday"] = 1 if "Tuesday" in weekdays else 0
				doc_data["wednesday"] = 1 if "Wednesday" in weekdays else 0
				doc_data["thursday"] = 1 if "Thursday" in weekdays else 0
				doc_data["friday"] = 1 if "Friday" in weekdays else 0
				doc_data["saturday"] = 1 if "Saturday" in weekdays else 0
				doc_data["sunday"] = 1 if "Sunday" in weekdays else 0
		else:
			doc_data["repeat_this_event"] = 0
		
		if event_id:
			# Update existing event
			doc = frappe.get_doc("Event", event_id)
			if doc.restaurant != restaurant:
				frappe.throw(_("You don't have access to this event"), exc=frappe.PermissionError)
			
			doc.update(doc_data)
			doc.save()
		else:
			# Create new event
			doc = frappe.get_doc(doc_data)
			doc.insert()
		
		return {
			"success": True,
			"data": {
				"event_id": doc.name
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in save_event: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "EVENT_SAVE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def delete_event(outlet_id, event_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.delete_event
	Delete an event
	"""
	try:
		# Validate outlet and user access
		restaurant = validate_restaurant_for_api(outlet_id, user=frappe.session.user)
		
		# Verify event belongs to outlet
		doc = frappe.get_doc("Event", event_id)
		if doc.restaurant != restaurant:
			frappe.throw(_("You don't have access to this event"), exc=frappe.PermissionError)
		
		# Delete event
		frappe.delete_doc("Event", event_id)
		
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error in delete_event: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "EVENT_DELETE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def toggle_event_status(outlet_id, event_id, field):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.toggle_event_status
	Toggle is_active or featured status
	"""
	try:
		if field not in ["is_active", "featured"]:
			frappe.throw(_("Invalid field"))
			
		# Validate outlet and user access
		restaurant = validate_restaurant_for_api(outlet_id, user=frappe.session.user)
		
		# Verify event belongs to outlet
		doc = frappe.get_doc("Event", event_id)
		if doc.restaurant != restaurant:
			frappe.throw(_("You don't have access to this event"), exc=frappe.PermissionError)
		
		# Toggle status
		current_val = doc.get(field)
		doc.set(field, 0 if current_val else 1)
		doc.save()
		
		return {
			"success": True,
			"data": {
				field: bool(doc.get(field))
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in toggle_event_status: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "EVENT_STATUS_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def generate_event_suggestions(outlet_id, user_prompt=None, poster_base64=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.generate_event_suggestions

	AI event creation (Gemini 2.5 Flash), two modes:
	  • user_prompt   — "Describe Event": merchant types the event in plain words
	  • poster_base64 — "Upload Poster": up to 3 images of the SAME event poster

	Returns Event-shaped dicts to pre-fill the merchant's event form (they always
	review before saving). Shares the AI monthly quota with coupon generation:
	free allowance first, then wallet coins.
	"""
	try:
		from flamezo_backend.flamezo.utils.feature_gate import require_plan
		from flamezo_backend.flamezo.services.ai.event_generator import generate_events
		from flamezo_backend.flamezo.services.ai.coupon_generator import (
			FREE_MONTHLY_QUOTA, _check_quota_status,
		)
		from flamezo_backend.flamezo.api.coin_billing import deduct_coins
		from frappe.utils import flt

		restaurant = validate_restaurant_for_api(outlet_id)
		require_plan(restaurant, ["GOLD"])

		COINS_PER_AI_EVENT = 2

		quota_status = _check_quota_status(restaurant)
		if not quota_status["free_remaining"]:
			balance = flt(frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0)
			if balance < COINS_PER_AI_EVENT:
				return {
					"success": False,
					"error_code": "INSUFFICIENT_BALANCE",
					"message": (
						f"Your {FREE_MONTHLY_QUOTA} free AI generations for this month are used up. "
						f"Each additional generation costs {COINS_PER_AI_EVENT} wallet coins. "
						f"Your current balance is ₹{balance:.0f}. Please recharge your wallet."
					),
					"quota": quota_status,
				}

		result = generate_events(
			outlet_id=restaurant,
			user_prompt=(user_prompt or None),
			poster_base64=(poster_base64 or None),
		)
		if not result.get("success"):
			return result

		if not quota_status["free_remaining"]:
			try:
				mode = "poster" if poster_base64 else "prompt"
				deduct_coins(
					restaurant=restaurant,
					amount=COINS_PER_AI_EVENT,
					type="AI Deduction",
					description=f"AI event creation ({mode})",
				)
				result["coins_deducted"] = COINS_PER_AI_EVENT
			except Exception as e:
				frappe.log_error(f"Coin deduction failed after AI event gen: {e}", "AI Event Billing")

		return {
			"success": True,
			"data": {
				"events": result["events"],
				"quota": result["quota"],
				"coins_deducted": result.get("coins_deducted", 0),
			},
		}

	except Exception as e:
		frappe.log_error(f"Error in generate_event_suggestions: {str(e)}")
		return {"success": False, "error": {"code": "AI_EVENT_ERROR", "message": str(e)}}
