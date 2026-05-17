# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Table and Banquet Bookings
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime_str, getdate, today
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import (
	require_verified_phone, 
	get_or_create_customer,
	get_customer_token,
	validate_customer_session
)
from flamezo_backend.flamezo.utils.feature_gate import require_plan
from flamezo_backend.flamezo.utils.roles import is_supervisor, is_global_admin
import json


# ========== TABLE BOOKING APIs ==========

@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')
def create_table_booking(restaurant_id, number_of_diners, date, time_slot, customer_info=None, session_id=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.create_table_booking
	Create a new table reservation
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Parse customer_info if string
		if isinstance(customer_info, str):
			customer_info = json.loads(customer_info) if customer_info else {}
		customer_info = customer_info or {}
		
		# Production Auth Gate: require valid session token when verify_my_user is on
		phone = customer_info.get("phone")
		if phone:
			config = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "verify_my_user")
			if config:
				session_token = get_customer_token()
				if not validate_customer_session(phone, session_token):
					return {
						"success": False,
						"error": {"code": "SECURE_SESSION_INVALID", "message": "Please log in to complete your booking"}
					}
		
		# Get platform customer for linking
		platform_customer = None
		if phone:
			cust = get_or_create_customer(phone, customer_info.get("fullName"), customer_info.get("email"))
			platform_customer = cust.name if cust else None
		
		# Get user
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		# Create table booking
		booking_doc = frappe.get_doc({
			"doctype": "Table Booking",
			"restaurant": restaurant,
			"user": user,
			"session_id": session_id,
			"number_of_diners": int(number_of_diners),
			"date": date,
			"time_slot": time_slot,
			"status": "pending",
			"customer_name": customer_info.get("fullName"),
			"customer_phone": customer_info.get("phone"),
			"customer_email": customer_info.get("email"),
			"platform_customer": platform_customer,
			"notes": customer_info.get("notes")
		})
		booking_doc.insert(ignore_permissions=True)
		
		# Format response
		booking_data = {
			"id": str(booking_doc.name),
			"bookingNumber": booking_doc.booking_number,
			"numberOfDiners": booking_doc.number_of_diners,
			"date": str(booking_doc.date),
			"timeSlot": booking_doc.time_slot,
			"status": booking_doc.status,
			"createdAt": get_datetime_str(booking_doc.creation)
		}
		
		if booking_doc.customer_name:
			booking_data["customerInfo"] = {
				"fullName": booking_doc.customer_name,
				"phone": booking_doc.customer_phone,
				"email": booking_doc.customer_email,
				"notes": booking_doc.notes
			}
		
		return {
			"success": True,
			"data": {
				"booking": booking_data
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in create_table_booking: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "BOOKING_CREATE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')
def get_table_bookings(restaurant_id, status=None, date_from=None, date_to=None, page=1, limit=20, session_id=None, admin_mode=False):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_table_bookings
	Get user's table bookings or all bookings in admin mode
	"""
	try:
		# Validate restaurant (allow guest access for public bookings)
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user if admin_mode else None)
		
		# Security: If admin_mode is requested, verify user has restaurant access
		if admin_mode:
			from flamezo_backend.flamezo.utils.permissions import validate_restaurant_access
			if not validate_restaurant_access(frappe.session.user, restaurant):
				return {"success": False, "error": {"code": "PERMISSION_DENIED", "message": "Admin access required"}}
		
		# Get user
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		# Build filters
		filters = {"restaurant": restaurant}
		
		# In admin mode, don't filter by user - get all bookings
		if not admin_mode:
			if user:
				filters["user"] = user
			elif session_id:
				filters["session_id"] = session_id
		
		if status:
			filters["status"] = status
		
		# Handle date filtering properly
		if date_from and date_to:
			filters["date"] = ["between", date_from, date_to]
		elif date_from:
			filters["date"] = [">=", date_from]
		elif date_to:
			filters["date"] = ["<=", date_to]
		
		# Pagination
		page = int(page) or 1
		limit = int(limit) or 20
		start = (page - 1) * limit
		
		# Get bookings
		fields = [
			"name as id",
			"booking_number",
			"number_of_diners",
			"date",
			"time_slot",
			"status",
			"creation"
		]
		
		# Add customer fields in admin mode
		if admin_mode:
			fields.extend([
				"customer_name",
				"customer_phone", 
				"customer_email",
				"notes",
				"confirmed_at",
				"rejected_at",
				"rejection_reason"
			])
		
		bookings = frappe.get_all(
			"Table Booking",
			fields=fields,
			filters=filters,
			limit_start=start,
			limit_page_length=limit,
			order_by="date desc, creation desc"
		)
		
		# Format bookings
		formatted_bookings = []
		for booking in bookings:
			booking_data = {
				"id": str(booking["id"]),
				"bookingNumber": booking["booking_number"],
				"numberOfDiners": booking["number_of_diners"],
				"date": str(booking["date"]),
				"timeSlot": booking["time_slot"],
				"status": booking["status"],
				"createdAt": get_datetime_str(booking["creation"])
			}
			
			# Add customer fields in admin mode
			if admin_mode:
				booking_data.update({
					"customerName": booking.get("customer_name"),
					"customerPhone": booking.get("customer_phone"),
					"customerEmail": booking.get("customer_email"),
					"notes": booking.get("notes"),
					"confirmedAt": get_datetime_str(booking.get("confirmed_at")) if booking.get("confirmed_at") else None,
					"rejectedAt": get_datetime_str(booking.get("rejected_at")) if booking.get("rejected_at") else None,
					"rejectionReason": booking.get("rejection_reason")
				})
			
			formatted_bookings.append(booking_data)
		
		# Get total count
		total = frappe.db.count("Table Booking", filters=filters)
		total_pages = (total + limit - 1) // limit if limit > 0 else 1
		
		return {
			"success": True,
			"data": {
				"bookings": formatted_bookings,
				"pagination": {
					"page": page,
					"limit": limit,
					"total": total,
					"totalPages": total_pages
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_table_bookings: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "BOOKING_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')
def get_available_time_slots(restaurant_id, date, number_of_diners=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_available_time_slots
	Get available time slots for table booking on a specific date
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Default time slots (can be configured per restaurant)
		all_slots = [
			"11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM", "1:00 PM", "1:30 PM",
			"2:00 PM", "2:30 PM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM",
			"8:00 PM", "8:15 PM", "8:30 PM", "9:00 PM", "9:30 PM", "10:00 PM", "10:30 PM"
		]
		
		# Get booked slots for this date
		booked_slots = frappe.get_all(
			"Table Booking",
			filters={
				"restaurant": restaurant,
				"date": date,
				"status": ["!=", "cancelled"]
			},
			pluck="time_slot"
		)
		
		available_slots = [slot for slot in all_slots if slot not in booked_slots]
		unavailable_slots = booked_slots
		
		return {
			"success": True,
			"data": {
				"date": date,
				"availableSlots": available_slots,
				"unavailableSlots": unavailable_slots
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_available_time_slots: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "SLOT_FETCH_ERROR",
				"message": str(e)
			}
		}


# ========== BANQUET BOOKING APIs ==========

@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')
def create_banquet_booking(restaurant_id, number_of_guests, event_type, date, time_slot, customer_info=None, session_id=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.create_banquet_booking
	Create a new banquet/event booking
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Parse customer_info if string
		if isinstance(customer_info, str):
			customer_info = json.loads(customer_info) if customer_info else {}
		customer_info = customer_info or {}
		
		# Production Auth Gate: require valid session token when verify_my_user is on
		phone = customer_info.get("phone")
		if phone:
			config = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "verify_my_user")
			if config:
				session_token = get_customer_token()
				if not validate_customer_session(phone, session_token):
					return {
						"success": False,
						"error": {"code": "SECURE_SESSION_INVALID", "message": "Please log in to complete your booking"}
					}
		
		# Get platform customer for linking
		platform_customer = None
		if phone:
			cust = get_or_create_customer(phone, customer_info.get("fullName"), customer_info.get("email"))
			platform_customer = cust.name if cust else None
		
		# Get user
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		# Create banquet booking
		booking_doc = frappe.get_doc({
			"doctype": "Banquet Booking",
			"restaurant": restaurant,
			"user": user,
			"session_id": session_id,
			"number_of_guests": int(number_of_guests),
			"event_type": event_type,
			"date": date,
			"time_slot": time_slot,
			"status": "pending",
			"customer_name": customer_info.get("fullName"),
			"customer_phone": customer_info.get("phone"),
			"customer_email": customer_info.get("email"),
			"platform_customer": platform_customer,
			"notes": customer_info.get("notes")
		})
		booking_doc.insert(ignore_permissions=True)
		
		# Format response
		booking_data = {
			"id": str(booking_doc.name),
			"bookingNumber": booking_doc.booking_number,
			"numberOfGuests": booking_doc.number_of_guests,
			"eventType": booking_doc.event_type,
			"date": str(booking_doc.date),
			"timeSlot": booking_doc.time_slot,
			"status": booking_doc.status,
			"createdAt": get_datetime_str(booking_doc.creation)
		}
		
		if booking_doc.customer_name:
			booking_data["customerInfo"] = {
				"fullName": booking_doc.customer_name,
				"phone": booking_doc.customer_phone,
				"email": booking_doc.customer_email,
				"notes": booking_doc.notes
			}
		
		return {
			"success": True,
			"data": {
				"booking": booking_data
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in create_banquet_booking: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "BOOKING_CREATE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')  # This is for public/client checking their own banquet bookings
def get_banquet_bookings(restaurant_id, status=None, event_type=None, date_from=None, date_to=None, page=1, limit=20, session_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_banquet_bookings
	Get user's banquet bookings
	"""
	try:
		# Validate restaurant (allow guest access for public bookings)
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get user
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		# Build filters
		filters = {"restaurant": restaurant}
		if user:
			filters["user"] = user
		elif session_id:
			filters["session_id"] = session_id
		
		if status:
			filters["status"] = status
		
		if event_type:
			filters["event_type"] = event_type
		
		if date_from:
			filters["date"] = [">=", date_from]
		if date_to:
			if "date" in filters and isinstance(filters["date"], list):
				filters["date"].append(["<=", date_to])
			else:
				filters["date"] = ["<=", date_to]
		
		# Pagination
		page = int(page) or 1
		limit = int(limit) or 20
		start = (page - 1) * limit
		
		# Get bookings
		bookings = frappe.get_all(
			"Banquet Booking",
			fields=[
				"name as id",
				"booking_number",
				"number_of_guests",
				"event_type",
				"date",
				"time_slot",
				"status",
				"creation"
			],
			filters=filters,
			limit_start=start,
			limit_page_length=limit,
			order_by="date desc, creation desc"
		)
		
		# Format bookings
		formatted_bookings = []
		for booking in bookings:
			formatted_bookings.append({
				"id": str(booking["id"]),
				"bookingNumber": booking["booking_number"],
				"numberOfGuests": booking["number_of_guests"],
				"eventType": booking["event_type"],
				"date": str(booking["date"]),
				"timeSlot": booking["time_slot"],
				"status": booking["status"],
				"createdAt": get_datetime_str(booking["creation"])
			})
		
		# Get total count
		total = frappe.db.count("Banquet Booking", filters=filters)
		total_pages = (total + limit - 1) // limit if limit > 0 else 1
		
		return {
			"success": True,
			"data": {
				"bookings": formatted_bookings,
				"pagination": {
					"page": page,
					"limit": limit,
					"total": total,
					"totalPages": total_pages
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_banquet_bookings: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "BOOKING_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_banquet_available_time_slots(restaurant_id, date, number_of_guests=None, event_type=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_banquet_available_time_slots
	Get available time slots for banquet booking on a specific date
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Default time slots for banquets (typically fewer slots)
		all_slots = [
			"11:00 AM", "12:00 PM", "2:00 PM", "6:00 PM", "8:00 PM"
		]
		
		# Get booked slots for this date
		booked_slots = frappe.get_all(
			"Banquet Booking",
			filters={
				"restaurant": restaurant,
				"date": date,
				"status": ["!=", "cancelled"]
			},
			pluck="time_slot"
		)
		
		available_slots = [slot for slot in all_slots if slot not in booked_slots]
		unavailable_slots = booked_slots
		
		return {
			"success": True,
			"data": {
				"date": date,
				"availableSlots": available_slots,
				"unavailableSlots": unavailable_slots
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_banquet_available_time_slots: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "SLOT_FETCH_ERROR",
				"message": str(e)
			}
		}


# ========== STAFF MANAGEMENT APIs ==========

@frappe.whitelist()
@require_plan('GOLD')
def confirm_booking(booking_id, restaurant_id, assigned_table=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.confirm_booking
	Confirm a pending booking (staff only)
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get booking
		booking = frappe.get_doc("Table Booking", booking_id)
		
		# Verify booking belongs to this restaurant
		if booking.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_BOOKING", "message": "Booking does not belong to this restaurant"}
			}
		
		# Check if already confirmed
		if booking.status == "confirmed":
			return {
				"success": False,
				"error": {"code": "ALREADY_CONFIRMED", "message": "Booking is already confirmed"}
			}
		
		# Update status
		booking.status = "confirmed"
		
		# Assign table if provided
		if assigned_table:
			booking.assigned_table = assigned_table
			booking.table_assignment_method = "manual"
		
		booking.save(ignore_permissions=True)
		
		return {
			"success": True,
			"data": {
				"booking": {
					"id": booking.name,
					"status": booking.status,
					"assignedTable": booking.assigned_table,
					"confirmedAt": get_datetime_str(booking.confirmed_at) if booking.confirmed_at else None
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in confirm_booking: {str(e)}")
		return {
			"success": False,
			"error": {"code": "CONFIRM_ERROR", "message": str(e)}
		}


@frappe.whitelist()
@require_plan('GOLD')
def reject_booking(booking_id, restaurant_id, reason=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.reject_booking
	Reject a pending booking (staff only)
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get booking
		booking = frappe.get_doc("Table Booking", booking_id)
		
		# Verify booking belongs to this restaurant
		if booking.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_BOOKING", "message": "Booking does not belong to this restaurant"}
			}
		
		# Update status
		booking.status = "rejected"
		if reason:
			booking.rejection_reason = reason
		
		booking.save(ignore_permissions=True)
		
		return {
			"success": True,
			"data": {
				"booking": {
					"id": booking.name,
					"status": booking.status,
					"rejectedAt": get_datetime_str(booking.rejected_at) if booking.rejected_at else None,
					"rejectionReason": booking.rejection_reason
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in reject_booking: {str(e)}")
		return {
			"success": False,
			"error": {"code": "REJECT_ERROR", "message": str(e)}
		}


@frappe.whitelist()
def reassign_table(booking_id, restaurant_id, new_table_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.reassign_table
	Reassign a booking to a different table (staff only)
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get booking
		booking = frappe.get_doc("Table Booking", booking_id)
		
		# Verify booking belongs to this restaurant
		if booking.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_BOOKING", "message": "Booking does not belong to this restaurant"}
			}
		
		# Verify new table belongs to restaurant
		table = frappe.get_doc("Restaurant Table", new_table_id)
		if table.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_TABLE", "message": "Table does not belong to this restaurant"}
			}
		
		# Update table assignment
		booking.assigned_table = new_table_id
		booking.table_assignment_method = "manual"
		booking.save(ignore_permissions=True)
		
		return {
			"success": True,
			"data": {
				"booking": {
					"id": booking.name,
					"assignedTable": booking.assigned_table,
					"tableNumber": table.table_number,
					"tableCapacity": table.capacity
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in reassign_table: {str(e)}")
		return {
			"success": False,
			"error": {"code": "REASSIGN_ERROR", "message": str(e)}
		}


@frappe.whitelist()
def mark_no_show(booking_id, restaurant_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.mark_no_show
	Mark a booking as no-show (staff only)
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get booking
		booking = frappe.get_doc("Table Booking", booking_id)
		
		# Verify booking belongs to this restaurant
		if booking.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_BOOKING", "message": "Booking does not belong to this restaurant"}
			}
		
		# Update status
		booking.status = "no-show"
		booking.save(ignore_permissions=True)
		
		return {
			"success": True,
			"data": {
				"booking": {
					"id": booking.name,
					"status": booking.status,
					"noShowAt": get_datetime_str(booking.no_show_at) if booking.no_show_at else None
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in mark_no_show: {str(e)}")
		return {
			"success": False,
			"error": {"code": "NO_SHOW_ERROR", "message": str(e)}
		}


@frappe.whitelist()
def mark_completed(booking_id, restaurant_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.bookings.mark_completed
	Mark a booking as completed (staff only)
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get booking
		booking = frappe.get_doc("Table Booking", booking_id)
		
		# Verify booking belongs to this restaurant
		if booking.restaurant != restaurant:
			return {
				"success": False,
				"error": {"code": "INVALID_BOOKING", "message": "Booking does not belong to this restaurant"}
			}
		
		# Update status
		booking.status = "completed"
		booking.save(ignore_permissions=True)
		
		return {
			"success": True,
			"data": {
				"booking": {
					"id": booking.name,
					"status": booking.status,
					"completedAt": get_datetime_str(booking.completed_at) if booking.completed_at else None
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in mark_completed: {str(e)}")
		return {
			"success": False,
			"error": {"code": "COMPLETE_ERROR", "message": str(e)}
		}


@frappe.whitelist()
@require_plan('GOLD')
def get_admin_bookings(restaurant_id, date_from=None, date_to=None, status=None, page=1, limit=50, search_query=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_admin_bookings
	Get all bookings for restaurant admin dashboard
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Build filters
		filters = {"restaurant": restaurant}
		
		if status:
			filters["status"] = status
		
		if date_from and date_to:
			filters["date"] = ["between", [date_from, date_to]]
		elif date_from:
			filters["date"] = [">=", date_from]
		elif date_to:
			filters["date"] = ["<=", date_to]

		if search_query:
			filters["or"] = {
				"customer_name": ["like", f"%{search_query}%"],
				"customer_phone": ["like", f"%{search_query}%"],
				"booking_number": ["like", f"%{search_query}%"]
			}
		
		# Pagination
		page = int(page) or 1
		limit = int(limit) or 50
		start = (page - 1) * limit

		booking_meta = frappe.get_meta("Table Booking")
		has_assigned_table = booking_meta.has_field("assigned_table")
		
		# Get bookings with table info
		booking_fields = [
			"name as id",
			"booking_number",
			"number_of_diners",
			"date",
			"time_slot",
			"status",
			"customer_name",
			"customer_phone",
			"customer_email",
			"notes",
			"creation",
			"confirmed_at",
			"rejected_at",
			"rejection_reason"
		]
		if has_assigned_table:
			booking_fields.append("assigned_table")

		bookings = frappe.get_all(
			"Table Booking",
			fields=booking_fields,
			filters=filters,
			limit_start=start,
			limit_page_length=limit,
			order_by="date desc, time_slot desc"
		)
		
		# Enrich with table details
		formatted_bookings = []
		for booking in bookings:
			booking_data = {
				"id": str(booking["id"]),
				"bookingNumber": booking["booking_number"],
				"numberOfDiners": booking["number_of_diners"],
				"date": str(booking["date"]),
				"timeSlot": booking["time_slot"],
				"status": booking["status"],
				"customerName": booking["customer_name"],
				"customerPhone": booking["customer_phone"],
				"customerEmail": booking["customer_email"],
				"notes": booking["notes"],
				"createdAt": get_datetime_str(booking["creation"]),
				"confirmedAt": get_datetime_str(booking["confirmed_at"]) if booking.get("confirmed_at") else None,
				"rejectedAt": get_datetime_str(booking["rejected_at"]) if booking.get("rejected_at") else None,
				"rejectionReason": booking.get("rejection_reason")
			}
			
			# Add table info if assigned
			if booking.get("assigned_table"):
				try:
					table = frappe.get_doc("Restaurant Table", booking["assigned_table"])
					booking_data["assignedTable"] = {
						"id": table.name,
						"tableNumber": table.table_number,
						"capacity": table.capacity,
						"location": table.location
					}
				except:
					booking_data["assignedTable"] = None
			else:
				booking_data["assignedTable"] = None
			
			formatted_bookings.append(booking_data)
		
		# Get total count
		total = frappe.db.count("Table Booking", filters=filters)
		total_pages = (total + limit - 1) // limit if limit > 0 else 1
		
		return {
			"success": True,
			"data": {
				"bookings": formatted_bookings,
				"pagination": {
					"page": page,
					"limit": limit,
					"total": total,
					"totalPages": total_pages
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_admin_bookings: {str(e)}")
		return {
			"success": False,
			"error": {"code": "FETCH_ERROR", "message": str(e)}
		}


@frappe.whitelist()
def get_restaurant_tables(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.bookings.get_restaurant_tables
	Get all tables for a restaurant
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get all tables
		tables = frappe.get_all(
			"Restaurant Table",
			filters={"restaurant": restaurant},
			fields=[
				"name as id",
				"table_number",
				"table_name",
				"capacity",
				"status",
				"location",
				"floor",
				"priority"
			],
			order_by="table_number asc"
		)
		
		formatted_tables = []
		for table in tables:
			formatted_tables.append({
				"id": table["id"],
				"tableNumber": table["table_number"],
				"tableName": table["table_name"],
				"capacity": table["capacity"],
				"status": table["status"],
				"location": table["location"],
				"floor": table["floor"],
				"priority": table["priority"]
			})
		
		return {
			"success": True,
			"data": {
				"tables": formatted_tables
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_tables: {str(e)}")
		return {
			"success": False,
			"error": {"code": "FETCH_ERROR", "message": str(e)}
		}


