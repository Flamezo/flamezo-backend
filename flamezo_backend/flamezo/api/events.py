# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Events
restaurant_id is optional — omit for consumer-level discovery (returns all active restaurants' events).
"""

import frappe
from frappe import _
from frappe.utils import today, get_url, formatdate, format_time
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.media.utils import format_media_field


def _format_event(event, include_restaurant=False, restaurant_meta=None):
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
	}

	if include_restaurant and restaurant_meta:
		event_data["restaurantId"] = restaurant_meta.get("restaurant_id", "")
		event_data["restaurantName"] = restaurant_meta.get("restaurant_name", "")
		event_data["restaurantCity"] = restaurant_meta.get("city", "")

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
	"friday", "saturday", "sunday", "restaurant",
]


@frappe.whitelist(allow_guest=True)
def get_events(restaurant_id=None, featured=None, category=None, upcoming_only=True):
	"""
	GET /api/method/flamezo_backend.flamezo.api.events.get_events

	restaurant_id optional:
	  - provided  → events for that restaurant only (existing behaviour)
	  - omitted   → all active-restaurant events (consumer discovery page)
	"""
	try:
		consumer_mode = not restaurant_id

		if consumer_mode:
			# Fetch all active restaurants once for name/city lookup
			active_restaurants = frappe.get_all(
				"Restaurant",
				filters={"is_active": 1},
				fields=["name", "restaurant_id", "restaurant_name", "city"],
			)
			restaurant_map = {r["name"]: r for r in active_restaurants}
			active_names = list(restaurant_map.keys())

			filters = {"restaurant": ["in", active_names], "is_active": 1}
		else:
			restaurant = validate_restaurant_for_api(restaurant_id)
			filters = {"restaurant": restaurant, "is_active": 1}

		if featured is not None:
			filters["featured"] = 1 if featured else 0
		if category:
			filters["category"] = category
		if upcoming_only:
			filters["status"] = ["in", ["upcoming", "recurring"]]

		events = frappe.get_all("Event", fields=_EVENT_FIELDS, filters=filters,
								order_by="display_order asc, title asc")

		formatted_events = []
		for event in events:
			if consumer_mode:
				meta = restaurant_map.get(event.get("restaurant"), {})
				formatted_events.append(_format_event(event, include_restaurant=True, restaurant_meta=meta))
			else:
				formatted_events.append(_format_event(event))

		return {"success": True, "data": {"events": formatted_events}}

	except Exception as e:
		frappe.log_error(f"Error in get_events: {str(e)}")
		return {"success": False, "error": {"code": "EVENT_FETCH_ERROR", "message": str(e)}}



@frappe.whitelist()
def save_event(restaurant_id, event_data):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.save_event
	Create or update an event
	"""
	try:
		# Validate restaurant and user access
		restaurant = validate_restaurant_for_api(restaurant_id, user=frappe.session.user)
		
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
def delete_event(restaurant_id, event_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.delete_event
	Delete an event
	"""
	try:
		# Validate restaurant and user access
		restaurant = validate_restaurant_for_api(restaurant_id, user=frappe.session.user)
		
		# Verify event belongs to restaurant
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
def toggle_event_status(restaurant_id, event_id, field):
	"""
	POST /api/method/flamezo_backend.flamezo.api.events.toggle_event_status
	Toggle is_active or featured status
	"""
	try:
		if field not in ["is_active", "featured"]:
			frappe.throw(_("Invalid field"))
			
		# Validate restaurant and user access
		restaurant = validate_restaurant_for_api(restaurant_id, user=frappe.session.user)
		
		# Verify event belongs to restaurant
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
