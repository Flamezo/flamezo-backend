"""
Service Appointment API — wellness, fitness, fashion, sports_venue merchants.

Customers request an appointment (date + time + service). Merchant confirms/rejects.
No payment at booking time — payment happens at the outlet.

Consumer endpoints (guest allowed):
  create_appointment(...)
  get_my_appointments(phone)
  cancel_appointment(appointment_id, phone, reason)

Merchant endpoints (auth required):
  get_appointment_requests(outlet_id, status, date, page, limit)
  confirm_appointment(appointment_id, outlet_id)
  reject_appointment(appointment_id, outlet_id, reason)
  mark_appointment_completed(appointment_id, outlet_id)
  mark_appointment_no_show(appointment_id, outlet_id)
  get_appointment_summary(outlet_id, date)
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today, now_datetime

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_restaurant(outlet_id):
	name = frappe.db.get_value("Restaurant", {"restaurant_id": outlet_id}, "name")
	return name or frappe.db.get_value("Restaurant", outlet_id, "name")


def _require_session(phone):
	"""Every endpoint here touches personal appointment data — a client-supplied
	phone alone is not identity. Without this, anyone who knows/guesses a phone
	number could create appointments as that person, or read/cancel their real
	ones (same class of bug found and fixed in crowd.py / table_booking_consumer.py)."""
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
	return phone


def _assert_restaurant_access(restaurant_name):
	if frappe.session.user in ("Administrator",):
		return
	has_access = frappe.db.exists(
		"Restaurant User",
		{"restaurant": restaurant_name, "user": frappe.session.user, "is_active": 1},
	)
	if not has_access:
		frappe.throw(_("Access denied to this outlet."), frappe.PermissionError)


def _assert_appointment_belongs_to_restaurant(appointment_name, restaurant_name):
	owner = frappe.db.get_value("Service Appointment", appointment_name, "restaurant")
	if owner != restaurant_name:
		frappe.throw(_("Appointment not found."), frappe.DoesNotExistError)


def _format_appointment(appt):
	return {
		"id": appt.name,
		"restaurant": appt.restaurant,
		"outlet_type": appt.outlet_type or "",
		"catalogue_item": appt.catalogue_item or "",
		"catalogue_item_name": appt.catalogue_item_name or "",
		"sub_item_name": appt.sub_item_name or "",
		"sub_item_price": flt(appt.sub_item_price) if appt.sub_item_price else None,
		"customer_name": appt.customer_name,
		"customer_phone": appt.customer_phone,
		"appointment_date": str(appt.appointment_date) if appt.appointment_date else "",
		"appointment_time": str(appt.appointment_time)[:5] if appt.appointment_time else "",
		"duration_minutes": cint(appt.duration_minutes) or 60,
		"notes": appt.notes or "",
		"status": appt.status,
		"cancelled_by": appt.cancelled_by or "",
		"cancellation_reason": appt.cancellation_reason or "",
		"confirmed_at": str(appt.confirmed_at) if appt.confirmed_at else None,
		"completed_at": str(appt.completed_at) if appt.completed_at else None,
	}


# ── Consumer: create appointment ──────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def create_appointment(
	outlet_id=None,
	customer_name=None,
	customer_phone=None,
	appointment_date=None,
	appointment_time=None,
	catalogue_item_id=None,
	sub_item_name=None,
	sub_item_price=None,
	duration_minutes=60,
	notes=None,
):
	"""
	POST /api/method/flamezo_backend.flamezo.api.appointments.create_appointment

	Creates a new service appointment request (status: Pending).
	No payment — merchant confirms manually.
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	if not customer_name or not customer_phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "customer_name and customer_phone are required"}}
	if not appointment_date or not appointment_time:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_date and appointment_time are required"}}

	_require_session(customer_phone)

	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		# Prevent past bookings
		appt_date = getdate(appointment_date)
		if appt_date < getdate(today()):
			return {"success": False, "error": {"code": "INVALID_DATE", "message": "Cannot book a past date"}}

		outlet_type = frappe.db.get_value("Restaurant", restaurant_name, "outlet_type") or ""

		doc = frappe.get_doc({
			"doctype": "Service Appointment",
			"restaurant": restaurant_name,
			"outlet_type": outlet_type,
			"catalogue_item": catalogue_item_id or None,
			"sub_item_name": sub_item_name or "",
			"sub_item_price": flt(sub_item_price) if sub_item_price else None,
			"customer_name": customer_name.strip(),
			"customer_phone": customer_phone.strip(),
			"appointment_date": appointment_date,
			"appointment_time": appointment_time,
			"duration_minutes": cint(duration_minutes) or 60,
			"notes": (notes or "").strip(),
			"status": "Pending",
		})
		doc.insert(ignore_permissions=True)

		return {
			"success": True,
			"data": {
				"appointment_id": doc.name,
				"status": "Pending",
				"message": "Appointment request submitted. The merchant will confirm shortly.",
			},
		}

	except Exception as e:
		frappe.log_error(f"appointments.create_appointment error: {e}")
		return {"success": False, "error": {"code": "CREATE_ERROR", "message": str(e)}}


# ── Consumer: get my appointments ─────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_appointments(phone=None, page=1, limit=20):
	"""
	GET /api/method/flamezo_backend.flamezo.api.appointments.get_my_appointments

	Returns all appointments for a customer phone (across all restaurants).
	Sorted by appointment_date desc.
	"""
	if not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "phone is required"}}
	_require_session(phone)
	try:
		page = cint(page) or 1
		limit = min(cint(limit) or 20, 50)
		offset = (page - 1) * limit

		appointments = frappe.get_all(
			"Service Appointment",
			filters={"customer_phone": phone.strip()},
			fields=[
				"name", "restaurant", "outlet_type",
				"catalogue_item", "catalogue_item_name",
				"sub_item_name", "sub_item_price",
				"customer_name", "customer_phone",
				"appointment_date", "appointment_time", "duration_minutes",
				"notes", "status", "cancelled_by", "cancellation_reason",
				"confirmed_at", "completed_at",
			],
			order_by="appointment_date desc, appointment_time desc",
			limit=limit,
			start=offset,
		)

		total = frappe.db.count("Service Appointment", filters={"customer_phone": phone.strip()})

		return {
			"success": True,
			"data": {
				"appointments": [_format_appointment(a) for a in appointments],
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

	except Exception as e:
		frappe.log_error(f"appointments.get_my_appointments error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: cancel appointment ──────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def cancel_appointment(appointment_id=None, phone=None, reason=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.appointments.cancel_appointment

	Allows a customer to cancel their own appointment.
	Only Pending or Confirmed appointments can be cancelled.
	"""
	if not appointment_id or not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_id and phone are required"}}
	_require_session(phone)
	try:
		doc = frappe.get_doc("Service Appointment", appointment_id)

		if doc.customer_phone != phone.strip():
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "You are not authorized to cancel this appointment"}}

		if doc.status in ("Cancelled", "Completed", "No Show"):
			return {"success": False, "error": {"code": "INVALID_STATUS", "message": f"Cannot cancel appointment with status '{doc.status}'"}}

		doc.status = "Cancelled"
		doc.cancelled_by = "customer"
		doc.cancellation_reason = (reason or "").strip()
		doc.save(ignore_permissions=True)

		return {"success": True, "data": {"appointment_id": doc.name, "status": "Cancelled"}}

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Appointment not found"}}
	except Exception as e:
		frappe.log_error(f"appointments.cancel_appointment error: {e}")
		return {"success": False, "error": {"code": "CANCEL_ERROR", "message": str(e)}}


# ── Merchant: list appointments ───────────────────────────────────────────────

@frappe.whitelist()
def get_appointment_requests(
	outlet_id=None,
	status=None,
	date=None,
	page=1,
	limit=20,
):
	"""
	GET /api/method/flamezo_backend.flamezo.api.appointments.get_appointment_requests

	Merchant view — list all appointments for a restaurant.
	Filterable by status and date.
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		page = cint(page) or 1
		limit = min(cint(limit) or 20, 100)
		offset = (page - 1) * limit

		filters = {"restaurant": restaurant_name}
		if status:
			filters["status"] = status
		if date:
			filters["appointment_date"] = date

		appointments = frappe.get_all(
			"Service Appointment",
			filters=filters,
			fields=[
				"name", "restaurant", "outlet_type",
				"catalogue_item", "catalogue_item_name",
				"sub_item_name", "sub_item_price",
				"customer_name", "customer_phone",
				"appointment_date", "appointment_time", "duration_minutes",
				"notes", "status", "cancelled_by", "cancellation_reason",
				"confirmed_at", "completed_at",
			],
			order_by="appointment_date asc, appointment_time asc",
			limit=limit,
			start=offset,
		)

		total = frappe.db.count("Service Appointment", filters=filters)

		return {
			"success": True,
			"data": {
				"appointments": [_format_appointment(a) for a in appointments],
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

	except Exception as e:
		frappe.log_error(f"appointments.get_appointment_requests error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Merchant: status transitions ──────────────────────────────────────────────

def _merchant_status_change(appointment_id, outlet_id, new_status, extra_fields=None):
	restaurant_name = _resolve_restaurant(outlet_id)
	if not restaurant_name:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
	_assert_restaurant_access(restaurant_name)

	doc = frappe.get_doc("Service Appointment", appointment_id)
	_assert_appointment_belongs_to_restaurant(appointment_id, restaurant_name)

	doc.status = new_status
	if extra_fields:
		for k, v in extra_fields.items():
			setattr(doc, k, v)
	doc.save(ignore_permissions=True)
	return {"success": True, "data": {"appointment_id": doc.name, "status": new_status}}


@frappe.whitelist()
def confirm_appointment(appointment_id=None, outlet_id=None):
	"""Confirm a pending appointment."""
	if not appointment_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_id and outlet_id are required"}}
	try:
		return _merchant_status_change(appointment_id, outlet_id, "Confirmed",
			{"confirmed_at": now_datetime()})
	except Exception as e:
		frappe.log_error(f"appointments.confirm_appointment error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def reject_appointment(appointment_id=None, outlet_id=None, reason=None):
	"""Cancel a pending appointment from merchant side."""
	if not appointment_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_id and outlet_id are required"}}
	try:
		return _merchant_status_change(appointment_id, outlet_id, "Cancelled",
			{"cancelled_by": "merchant", "cancellation_reason": reason or ""})
	except Exception as e:
		frappe.log_error(f"appointments.reject_appointment error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def mark_appointment_completed(appointment_id=None, outlet_id=None):
	"""Mark a confirmed appointment as completed."""
	if not appointment_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_id and outlet_id are required"}}
	try:
		return _merchant_status_change(appointment_id, outlet_id, "Completed",
			{"completed_at": now_datetime()})
	except Exception as e:
		frappe.log_error(f"appointments.mark_appointment_completed error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def mark_appointment_no_show(appointment_id=None, outlet_id=None):
	"""Mark a confirmed appointment as no-show."""
	if not appointment_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "appointment_id and outlet_id are required"}}
	try:
		return _merchant_status_change(appointment_id, outlet_id, "No Show")
	except Exception as e:
		frappe.log_error(f"appointments.mark_appointment_no_show error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


# ── Merchant: daily summary ───────────────────────────────────────────────────

@frappe.whitelist()
def get_appointment_summary(outlet_id=None, date=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.appointments.get_appointment_summary

	Returns appointment counts by status for a given date (default: today).
	Used for the merchant dashboard day-view header.
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		target_date = date or today()

		rows = frappe.get_all(
			"Service Appointment",
			filters={"restaurant": restaurant_name, "appointment_date": target_date},
			fields=["status"],
		)

		summary = {"Pending": 0, "Confirmed": 0, "Cancelled": 0, "Completed": 0, "No Show": 0}
		for row in rows:
			if row.status in summary:
				summary[row.status] += 1

		return {
			"success": True,
			"data": {
				"date": target_date,
				"total": len(rows),
				"by_status": summary,
			},
		}

	except Exception as e:
		frappe.log_error(f"appointments.get_appointment_summary error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}
