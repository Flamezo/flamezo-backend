"""
Court Booking API — sports_court merchants.

Customers browse courts, check slot availability, book and pay the consumer fee
via Razorpay. After payment confirmation the booking is locked.

Consumer endpoints (guest allowed):
  get_courts(outlet_id)
  get_court_availability(outlet_id, court_id, date)
  create_court_booking(...)        → returns Razorpay order for consumer_fee
  verify_court_payment(...)        → confirms booking after payment
  get_my_court_bookings(phone)
  cancel_court_booking(booking_id, phone, reason)

Merchant endpoints (auth required):
  get_court_bookings(outlet_id, date, court_id, status, page, limit)
  get_court_booking_summary(outlet_id, date)
  mark_court_completed(booking_id, outlet_id)
  mark_court_no_show(booking_id, outlet_id)
  save_court(outlet_id, ...)
  delete_court(outlet_id, court_id)
"""

import json
import hmac
import hashlib
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today, now_datetime, add_days
from datetime import datetime, timedelta, date as date_type
import razorpay

from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client as _shared_get_razorpay_client, get_razorpay_config


DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_restaurant(outlet_id):
	name = frappe.db.get_value("Restaurant", {"restaurant_id": outlet_id}, "name")
	return name or frappe.db.get_value("Restaurant", outlet_id, "name")


def _assert_restaurant_access(restaurant_name):
	if frappe.session.user in ("Administrator",):
		return
	has_access = frappe.db.exists(
		"Restaurant User",
		{"restaurant": restaurant_name, "user": frappe.session.user, "is_active": 1},
	)
	if not has_access:
		frappe.throw(_("Access denied to this outlet."), frappe.PermissionError)


def _get_razorpay_client():
	return _shared_get_razorpay_client()


def _time_str_to_minutes(t):
	"""Convert 'HH:MM:SS' or 'HH:MM' to minutes since midnight."""
	parts = str(t).split(":")
	return cint(parts[0]) * 60 + cint(parts[1])


def _minutes_to_time_str(m):
	"""Convert minutes since midnight to 'HH:MM'."""
	return f"{m // 60:02d}:{m % 60:02d}"


def _is_court_open_on_date(court, check_date):
	"""Check if court operates on the given date's day of week."""
	day_abbr = DAY_ABBR[check_date.weekday()]
	available = [d.strip() for d in (court.available_days or "").split(",")]
	return day_abbr in available


def _generate_slots(court, check_date):
	"""
	Generate all time slots for a court on a given date.
	Returns list of {"start": "09:00", "end": "10:00"} dicts.
	"""
	if not _is_court_open_on_date(court, check_date):
		return []

	open_min  = _time_str_to_minutes(court.opening_time)
	close_min = _time_str_to_minutes(court.closing_time)
	duration  = cint(court.slot_duration_minutes) or 60

	slots = []
	cur = open_min
	while cur + duration <= close_min:
		slots.append({
			"start": _minutes_to_time_str(cur),
			"end":   _minutes_to_time_str(cur + duration),
		})
		cur += duration
	return slots


def _get_booked_slots(court_name, check_date):
	"""Return set of start times already booked (non-cancelled) for a court on a date."""
	bookings = frappe.get_all(
		"Court Booking",
		filters={
			"court": court_name,
			"booking_date": check_date,
			"status": ["not in", ["Cancelled"]],
		},
		fields=["start_time"],
	)
	return {_minutes_to_time_str(_time_str_to_minutes(str(b.start_time))) for b in bookings}


def _format_booking(b):
	return {
		"id": b.name,
		"restaurant": b.restaurant,
		"court": b.court,
		"court_name": b.court_name or "",
		"sport_type": b.sport_type or "",
		"booking_date": str(b.booking_date) if b.booking_date else "",
		"start_time": _minutes_to_time_str(_time_str_to_minutes(str(b.start_time))) if b.start_time else "",
		"end_time":   _minutes_to_time_str(_time_str_to_minutes(str(b.end_time))) if b.end_time else "",
		"customer_name": b.customer_name,
		"customer_phone": b.customer_phone,
		"notes": b.notes or "",
		"slot_price": flt(b.slot_price),
		"consumer_fee": flt(b.consumer_fee),
		"payment_status": b.payment_status,
		"status": b.status,
		"razorpay_order_id": b.razorpay_order_id or "",
		"cancelled_by": b.cancelled_by or "",
		"cancellation_reason": b.cancellation_reason or "",
		"completed_at": str(b.completed_at) if b.completed_at else None,
	}


# ── Consumer: list courts ─────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_courts(outlet_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.courts.get_courts

	Returns all active courts for a sports_court merchant.
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		courts = frappe.get_all(
			"Court",
			filters={"restaurant": restaurant_name, "is_active": 1},
			fields=[
				"name", "court_name", "sport_type",
				"slot_duration_minutes", "price_per_slot", "consumer_fee",
				"opening_time", "closing_time", "available_days",
				"advance_booking_days", "sort_order",
			],
			order_by="sort_order asc, court_name asc",
		)

		return {
			"success": True,
			"data": [
				{
					"id": c.name,
					"name": c.court_name,
					"sport_type": c.sport_type,
					"slot_duration_minutes": cint(c.slot_duration_minutes),
					"price_per_slot": flt(c.price_per_slot),
					"consumer_fee": flt(c.consumer_fee),
					"opening_time": str(c.opening_time)[:5] if c.opening_time else "",
					"closing_time": str(c.closing_time)[:5] if c.closing_time else "",
					"available_days": c.available_days or "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
					"advance_booking_days": cint(c.advance_booking_days) or 7,
				}
				for c in courts
			],
		}

	except Exception as e:
		frappe.log_error(f"courts.get_courts error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: check availability ──────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_court_availability(outlet_id=None, court_id=None, date=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.courts.get_court_availability

	Returns all slots for a court on a given date, with is_available flag.
	Past slots are always marked unavailable.

	Response:
	  {
	    slots: [
	      { start: "09:00", end: "10:00", is_available: true },
	      { start: "10:00", end: "11:00", is_available: false },
	      ...
	    ]
	  }
	"""
	if not outlet_id or not court_id or not date:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id, court_id and date are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		court = frappe.get_doc("Court", court_id)
		if court.restaurant != restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Court not found"}}
		if not court.is_active:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Court is not available"}}

		check_date = getdate(date)

		# Enforce advance booking window
		max_date = getdate(add_days(today(), cint(court.advance_booking_days) or 7))
		if check_date > max_date:
			return {"success": False, "error": {"code": "INVALID_DATE", "message": f"Cannot book more than {court.advance_booking_days} days in advance"}}
		if check_date < getdate(today()):
			return {"success": False, "error": {"code": "INVALID_DATE", "message": "Cannot check availability for past dates"}}

		all_slots    = _generate_slots(court, check_date)
		booked_starts = _get_booked_slots(court_id, check_date)

		# Current time for same-day filtering
		now = datetime.now()
		is_today = (check_date == getdate(today()))

		result_slots = []
		for slot in all_slots:
			is_booked = slot["start"] in booked_starts

			# Block past slots for today
			is_past = False
			if is_today:
				h, m = slot["start"].split(":")
				slot_dt = now.replace(hour=cint(h), minute=cint(m), second=0, microsecond=0)
				is_past = slot_dt <= now

			result_slots.append({
				"start": slot["start"],
				"end": slot["end"],
				"is_available": not is_booked and not is_past,
			})

		return {
			"success": True,
			"data": {
				"court_id": court_id,
				"date": str(check_date),
				"is_open": _is_court_open_on_date(court, check_date),
				"price_per_slot": flt(court.price_per_slot),
				"consumer_fee": flt(court.consumer_fee),
				"slots": result_slots,
			},
		}

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Court not found"}}
	except Exception as e:
		frappe.log_error(f"courts.get_court_availability error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: create booking + Razorpay order ─────────────────────────────────

@frappe.whitelist(allow_guest=True)
def create_court_booking(
	outlet_id=None,
	court_id=None,
	booking_date=None,
	start_time=None,
	customer_name=None,
	customer_phone=None,
	notes=None,
):
	"""
	POST /api/method/flamezo_backend.flamezo.api.courts.create_court_booking

	Reserves a slot and creates a Razorpay order for the consumer_fee.
	Booking stays in 'Pending Payment' until verify_court_payment is called.

	Response:
	  {
	    booking_id,
	    razorpay_order_id,
	    razorpay_key_id,
	    consumer_fee,
	    slot_price,
	    currency: "INR"
	  }
	"""
	if not all([outlet_id, court_id, booking_date, start_time, customer_name, customer_phone]):
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id, court_id, booking_date, start_time, customer_name, customer_phone are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		court = frappe.get_doc("Court", court_id)
		if court.restaurant != restaurant_name or not court.is_active:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Court not found"}}

		check_date = getdate(booking_date)
		if check_date < getdate(today()):
			return {"success": False, "error": {"code": "INVALID_DATE", "message": "Cannot book a past date"}}

		# Validate slot exists in court schedule
		all_slots = _generate_slots(court, check_date)
		valid_starts = {s["start"] for s in all_slots}
		slot_start = str(start_time)[:5]
		if slot_start not in valid_starts:
			return {"success": False, "error": {"code": "INVALID_SLOT", "message": "Invalid time slot for this court"}}

		# Check slot is not already taken
		booked = _get_booked_slots(court_id, check_date)
		if slot_start in booked:
			return {"success": False, "error": {"code": "SLOT_TAKEN", "message": "This slot is already booked"}}

		# Compute end time
		slot_end = next(s["end"] for s in all_slots if s["start"] == slot_start)

		consumer_fee = flt(court.consumer_fee)
		slot_price   = flt(court.price_per_slot)

		# Create Court Booking doc (Pending Payment)
		doc = frappe.get_doc({
			"doctype": "Court Booking",
			"restaurant": restaurant_name,
			"court": court_id,
			"court_name": court.court_name,
			"sport_type": court.sport_type,
			"booking_date": booking_date,
			"start_time": slot_start,
			"end_time": slot_end,
			"customer_name": customer_name.strip(),
			"customer_phone": customer_phone.strip(),
			"notes": (notes or "").strip(),
			"slot_price": slot_price,
			"consumer_fee": consumer_fee,
			"payment_status": "Pending",
			"status": "Pending Payment",
		})
		doc.insert(ignore_permissions=True)

		# Create Razorpay order for consumer_fee only
		client = _get_razorpay_client()
		order_data = client.order.create({
			"amount": cint(consumer_fee * 100),  # paise
			"currency": "INR",
			"receipt": doc.name,
			"notes": {
				"booking_id": doc.name,
				"court": court.court_name,
				"date": str(booking_date),
				"slot": f"{slot_start} – {slot_end}",
				"customer": customer_name,
			},
		})

		# Persist Razorpay order ID
		frappe.db.set_value("Court Booking", doc.name, "razorpay_order_id", order_data["id"], update_modified=False)

		return {
			"success": True,
			"data": {
				"booking_id": doc.name,
				"razorpay_order_id": order_data["id"],
				"razorpay_key_id": get_razorpay_config()["key_id"],
				"consumer_fee": consumer_fee,
				"slot_price": slot_price,
				"currency": "INR",
				"court_name": court.court_name,
				"booking_date": str(booking_date),
				"start_time": slot_start,
				"end_time": slot_end,
			},
		}

	except Exception as e:
		frappe.log_error(f"courts.create_court_booking error: {e}")
		return {"success": False, "error": {"code": "BOOKING_ERROR", "message": str(e)}}


# ── Consumer: verify payment and confirm booking ──────────────────────────────

@frappe.whitelist(allow_guest=True)
def verify_court_payment(
	booking_id=None,
	razorpay_order_id=None,
	razorpay_payment_id=None,
	razorpay_signature=None,
):
	"""
	POST /api/method/flamezo_backend.flamezo.api.courts.verify_court_payment

	Verifies Razorpay payment signature and confirms the court booking.
	Called client-side after the Razorpay checkout completes.
	"""
	if not all([booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature are required"}}
	try:
		doc = frappe.get_doc("Court Booking", booking_id)

		if doc.razorpay_order_id != razorpay_order_id:
			return {"success": False, "error": {"code": "ORDER_MISMATCH", "message": "Order ID mismatch"}}

		if doc.status != "Pending Payment":
			return {"success": False, "error": {"code": "INVALID_STATUS", "message": f"Booking is already in status '{doc.status}'"}}

		# Verify HMAC-SHA256 signature
		expected = hmac.new(
			get_razorpay_config()["key_secret"].encode(),
			f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
			hashlib.sha256,
		).hexdigest()

		if not hmac.compare_digest(expected, razorpay_signature):
			return {"success": False, "error": {"code": "SIGNATURE_INVALID", "message": "Payment signature verification failed"}}

		# Slot double-check — guard against race condition
		booked = frappe.get_all(
			"Court Booking",
			filters={
				"court": doc.court,
				"booking_date": doc.booking_date,
				"start_time": doc.start_time,
				"status": ["not in", ["Cancelled", "Pending Payment"]],
				"name": ["!=", booking_id],
			},
			fields=["name"],
			limit=1,
		)
		if booked:
			# Refund the payment
			try:
				client = _get_razorpay_client()
				client.payment.refund(razorpay_payment_id, {"amount": cint(flt(doc.consumer_fee) * 100)})
			except Exception:
				pass
			doc.payment_status = "Refunded"
			doc.status = "Cancelled"
			doc.cancelled_by = "merchant"
			doc.cancellation_reason = "Slot was taken by another booking"
			doc.save(ignore_permissions=True)
			return {"success": False, "error": {"code": "SLOT_TAKEN", "message": "This slot was just booked by someone else. Your payment will be refunded."}}

		doc.razorpay_payment_id = razorpay_payment_id
		doc.payment_status = "Paid"
		doc.status = "Confirmed"
		doc.save(ignore_permissions=True)

		return {
			"success": True,
			"data": {
				"booking_id": doc.name,
				"status": "Confirmed",
				"message": "Booking confirmed! See you on the court.",
			},
		}

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Booking not found"}}
	except Exception as e:
		frappe.log_error(f"courts.verify_court_payment error: {e}")
		return {"success": False, "error": {"code": "VERIFY_ERROR", "message": str(e)}}


# ── Consumer: my bookings ─────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_court_bookings(phone=None, page=1, limit=20):
	"""
	GET /api/method/flamezo_backend.flamezo.api.courts.get_my_court_bookings

	Returns all court bookings for a customer phone (across all restaurants).
	"""
	if not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "phone is required"}}
	try:
		page  = cint(page) or 1
		limit = min(cint(limit) or 20, 50)
		offset = (page - 1) * limit

		bookings = frappe.get_all(
			"Court Booking",
			filters={"customer_phone": phone.strip()},
			fields=[
				"name", "restaurant", "court", "court_name", "sport_type",
				"booking_date", "start_time", "end_time",
				"customer_name", "customer_phone", "notes",
				"slot_price", "consumer_fee",
				"razorpay_order_id", "payment_status", "status",
				"cancelled_by", "cancellation_reason", "completed_at",
			],
			order_by="booking_date desc, start_time desc",
			limit=limit,
			start=offset,
		)

		total = frappe.db.count("Court Booking", filters={"customer_phone": phone.strip()})

		return {
			"success": True,
			"data": {
				"bookings": [_format_booking(b) for b in bookings],
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

	except Exception as e:
		frappe.log_error(f"courts.get_my_court_bookings error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: cancel booking ──────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def cancel_court_booking(booking_id=None, phone=None, reason=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.courts.cancel_court_booking

	Cancel a court booking. If payment was made, triggers Razorpay refund.
	Only Confirmed bookings can be cancelled by the customer.
	"""
	if not booking_id or not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "booking_id and phone are required"}}
	try:
		doc = frappe.get_doc("Court Booking", booking_id)

		if doc.customer_phone != phone.strip():
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "You are not authorized to cancel this booking"}}

		if doc.status in ("Cancelled", "Completed", "No Show"):
			return {"success": False, "error": {"code": "INVALID_STATUS", "message": f"Cannot cancel a booking with status '{doc.status}'"}}

		# Refund consumer_fee if paid
		refunded = False
		if doc.payment_status == "Paid" and doc.razorpay_payment_id:
			try:
				client = _get_razorpay_client()
				client.payment.refund(doc.razorpay_payment_id, {"amount": cint(flt(doc.consumer_fee) * 100)})
				refunded = True
			except Exception as re:
				frappe.log_error(f"courts.cancel_court_booking refund error: {re}")

		doc.status = "Cancelled"
		doc.cancelled_by = "customer"
		doc.cancellation_reason = (reason or "").strip()
		if refunded:
			doc.payment_status = "Refunded"
		doc.save(ignore_permissions=True)

		return {
			"success": True,
			"data": {
				"booking_id": doc.name,
				"status": "Cancelled",
				"refunded": refunded,
			},
		}

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Booking not found"}}
	except Exception as e:
		frappe.log_error(f"courts.cancel_court_booking error: {e}")
		return {"success": False, "error": {"code": "CANCEL_ERROR", "message": str(e)}}


# ── Merchant: list bookings ───────────────────────────────────────────────────

@frappe.whitelist()
def get_court_bookings(
	outlet_id=None,
	date=None,
	court_id=None,
	status=None,
	page=1,
	limit=20,
):
	"""
	GET /api/method/flamezo_backend.flamezo.api.courts.get_court_bookings

	Merchant view — list court bookings with optional filters.
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		page  = cint(page) or 1
		limit = min(cint(limit) or 20, 100)
		offset = (page - 1) * limit

		filters = {"restaurant": restaurant_name}
		if date:
			filters["booking_date"] = date
		if court_id:
			filters["court"] = court_id
		if status:
			filters["status"] = status

		bookings = frappe.get_all(
			"Court Booking",
			filters=filters,
			fields=[
				"name", "restaurant", "court", "court_name", "sport_type",
				"booking_date", "start_time", "end_time",
				"customer_name", "customer_phone", "notes",
				"slot_price", "consumer_fee",
				"razorpay_order_id", "payment_status", "status",
				"cancelled_by", "cancellation_reason", "completed_at",
			],
			order_by="booking_date asc, start_time asc",
			limit=limit,
			start=offset,
		)

		total = frappe.db.count("Court Booking", filters=filters)

		return {
			"success": True,
			"data": {
				"bookings": [_format_booking(b) for b in bookings],
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

	except Exception as e:
		frappe.log_error(f"courts.get_court_bookings error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Merchant: daily summary ───────────────────────────────────────────────────

@frappe.whitelist()
def get_court_booking_summary(outlet_id=None, date=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.courts.get_court_booking_summary

	Returns booking counts and revenue summary for a given date.
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
			"Court Booking",
			filters={"restaurant": restaurant_name, "booking_date": target_date},
			fields=["status", "payment_status", "slot_price", "consumer_fee"],
		)

		by_status = {"Pending Payment": 0, "Confirmed": 0, "Cancelled": 0, "Completed": 0, "No Show": 0}
		total_slot_revenue = 0.0
		total_consumer_fees = 0.0

		for row in rows:
			if row.status in by_status:
				by_status[row.status] += 1
			if row.payment_status == "Paid":
				total_slot_revenue   += flt(row.slot_price)
				total_consumer_fees  += flt(row.consumer_fee)

		return {
			"success": True,
			"data": {
				"date": target_date,
				"total": len(rows),
				"by_status": by_status,
				"total_slot_revenue": total_slot_revenue,
				"total_consumer_fees_collected": total_consumer_fees,
			},
		}

	except Exception as e:
		frappe.log_error(f"courts.get_court_booking_summary error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


# ── Merchant: status transitions ──────────────────────────────────────────────

@frappe.whitelist()
def mark_court_completed(booking_id=None, outlet_id=None):
	"""Mark a confirmed court booking as completed."""
	if not booking_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "booking_id and outlet_id are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		_assert_restaurant_access(restaurant_name)

		doc = frappe.get_doc("Court Booking", booking_id)
		if doc.restaurant != restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Booking not found"}}

		doc.status = "Completed"
		doc.completed_at = now_datetime()
		doc.save(ignore_permissions=True)
		return {"success": True, "data": {"booking_id": doc.name, "status": "Completed"}}

	except Exception as e:
		frappe.log_error(f"courts.mark_court_completed error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def mark_court_no_show(booking_id=None, outlet_id=None):
	"""Mark a confirmed court booking as no-show."""
	if not booking_id or not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "booking_id and outlet_id are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		_assert_restaurant_access(restaurant_name)

		doc = frappe.get_doc("Court Booking", booking_id)
		if doc.restaurant != restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Booking not found"}}

		doc.status = "No Show"
		doc.save(ignore_permissions=True)
		return {"success": True, "data": {"booking_id": doc.name, "status": "No Show"}}

	except Exception as e:
		frappe.log_error(f"courts.mark_court_no_show error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


# ── Merchant: court CRUD ──────────────────────────────────────────────────────

@frappe.whitelist()
def save_court(outlet_id=None, court_id=None, court_data=None):
	"""
	Create or update a court configuration.

	court_data (JSON string or dict):
	  {
	    court_name, sport_type, slot_duration_minutes, price_per_slot,
	    consumer_fee, opening_time, closing_time,
	    available_days, advance_booking_days, is_active, sort_order
	  }
	"""
	if not outlet_id or not court_data:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and court_data are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		if isinstance(court_data, str):
			court_data = json.loads(court_data)

		required = ["court_name", "sport_type", "slot_duration_minutes", "price_per_slot",
					"consumer_fee", "opening_time", "closing_time", "available_days"]
		for field in required:
			if not court_data.get(field):
				return {"success": False, "error": {"code": "MISSING_PARAM", "message": f"{field} is required"}}

		if court_id:
			doc = frappe.get_doc("Court", court_id)
			if doc.restaurant != restaurant_name:
				frappe.throw(_("Access denied."), frappe.PermissionError)
			doc.court_name            = court_data["court_name"]
			doc.sport_type            = court_data["sport_type"]
			doc.slot_duration_minutes = cint(court_data["slot_duration_minutes"])
			doc.price_per_slot        = flt(court_data["price_per_slot"])
			doc.consumer_fee          = flt(court_data["consumer_fee"])
			doc.opening_time          = court_data["opening_time"]
			doc.closing_time          = court_data["closing_time"]
			doc.available_days        = court_data["available_days"]
			doc.advance_booking_days  = cint(court_data.get("advance_booking_days", 7))
			doc.is_active             = cint(court_data.get("is_active", 1))
			doc.sort_order            = cint(court_data.get("sort_order", 0))
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({
				"doctype": "Court",
				"restaurant": restaurant_name,
				"court_name": court_data["court_name"],
				"sport_type": court_data["sport_type"],
				"slot_duration_minutes": cint(court_data["slot_duration_minutes"]),
				"price_per_slot": flt(court_data["price_per_slot"]),
				"consumer_fee": flt(court_data["consumer_fee"]),
				"opening_time": court_data["opening_time"],
				"closing_time": court_data["closing_time"],
				"available_days": court_data["available_days"],
				"advance_booking_days": cint(court_data.get("advance_booking_days", 7)),
				"is_active": cint(court_data.get("is_active", 1)),
				"sort_order": cint(court_data.get("sort_order", 0)),
			})
			doc.insert(ignore_permissions=True)

		return {"success": True, "data": {"court_id": doc.name, "court_name": doc.court_name}}

	except Exception as e:
		frappe.log_error(f"courts.save_court error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def delete_court(outlet_id=None, court_id=None):
	"""Delete a court (only if it has no active/future bookings)."""
	if not outlet_id or not court_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and court_id are required"}}
	try:
		restaurant_name = _resolve_restaurant(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		doc = frappe.get_doc("Court", court_id)
		if doc.restaurant != restaurant_name:
			frappe.throw(_("Access denied."), frappe.PermissionError)

		# Block deletion if active future bookings exist
		future_bookings = frappe.db.count("Court Booking", {
			"court": court_id,
			"booking_date": [">=", today()],
			"status": ["in", ["Pending Payment", "Confirmed"]],
		})
		if future_bookings:
			return {"success": False, "error": {"code": "HAS_BOOKINGS", "message": f"Cannot delete court with {future_bookings} active upcoming booking(s)"}}

		frappe.delete_doc("Court", court_id, ignore_permissions=True)
		return {"success": True}

	except Exception as e:
		frappe.log_error(f"courts.delete_court error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}
