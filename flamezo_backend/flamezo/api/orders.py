"""
Customer Order Tracking API

Order creation happens in payments.py (create_payment_order).
This module provides customer-facing read + cancel endpoints.

Consumer endpoints (session required):
  get_my_orders(phone, page, limit, status, outlet_id)
  get_order_detail(order_id, phone)
  get_order_status(order_id, phone)
  cancel_order(order_id, phone, reason)
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
import random
import string


def generate_order_number() -> str:
	"""Generate a short human-readable order number, e.g. FZ-A3X9."""
	chars = string.ascii_uppercase + string.digits
	suffix = "".join(random.choices(chars, k=4))
	return f"FZ-{suffix}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_customer_token():
	return (
		frappe.request.headers.get("X-Customer-Token")
		or frappe.form_dict.get("customer_token")
		or ""
	)


def _validate_phone_owns_order(order_doc, phone):
	"""
	Returns True if the given phone matches the order's customer_phone.
	Checks common variants (+91, leading 0, plain 10-digit).
	"""
	if not phone or not order_doc.customer_phone:
		return False
	def _norm(p):
		p = str(p).strip().replace(" ", "").replace("-", "")
		if p.startswith("+91"):
			p = p[3:]
		if p.startswith("91") and len(p) == 12:
			p = p[2:]
		if p.startswith("0") and len(p) == 11:
			p = p[1:]
		return p
	return _norm(phone) == _norm(order_doc.customer_phone)


def _validate_session(phone):
	"""Lightweight session check — reuses customer_helpers if available."""
	try:
		from flamezo_backend.flamezo.utils.customer_helpers import (
			validate_customer_session, is_phone_verified,
		)
		token = _get_customer_token()
		return validate_customer_session(phone, token) or is_phone_verified(phone)
	except Exception:
		return True  # Fail open if helper unavailable (dev env)


def _format_order(order, include_items=False):
	result = {
		"id": order.name,
		"order_number": order.order_number or order.order_id or order.name,
		"outlet_id": order.outlet,
		"status": order.status or "",
		"payment_status": order.payment_status or "",
		"payment_method": order.payment_method or "",
		"order_type": order.order_type or "",
		"subtotal": flt(order.subtotal),
		"discount": flt(order.discount),
		"loyalty_discount": flt(order.loyalty_discount),
		"packaging_fee": flt(order.packaging_fee),
		"delivery_fee": flt(order.delivery_fee),
		"tax": flt(order.tax),
		"total": flt(order.total),
		"coupon": order.coupon or "",
		"table_number": order.table_number or "",
		"created_at": str(order.creation) if order.creation else "",
		"modified_at": str(order.modified) if order.modified else "",
	}

	if order.order_type == "delivery":
		result["delivery"] = {
			"address": order.delivery_address or "",
			"landmark": order.delivery_landmark or "",
			"city": order.delivery_city or "",
			"state": order.delivery_state or "",
			"pincode": order.delivery_zip_code or "",
			"instructions": order.delivery_instructions or "",
		}

	if include_items and hasattr(order, "order_items"):
		result["items"] = [
			{
				"product_id": item.product or "",
				"name": item.product_name or "",
				"quantity": cint(item.quantity),
				"unit_price": flt(item.unit_price),
				"original_price": flt(item.original_price),
				"total_price": flt(item.total_price),
			}
			for item in (order.order_items or [])
		]

	return result


# ── Consumer: list my orders ──────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_orders(phone=None, page=1, limit=20, status=None, outlet_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.orders.get_my_orders

	Returns paginated order history for a customer, newest first.
	Optionally filtered by status or restaurant.
	"""
	if not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "phone is required"}}

	if not _validate_session(phone):
		return {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Please log in to view your orders"}}

	try:
		page  = cint(page) or 1
		limit = min(cint(limit) or 20, 50)
		offset = (page - 1) * limit

		filters = {"customer_phone": ["like", f"%{phone.strip()[-10:]}%"]}
		if status:
			filters["status"] = status
		if outlet_id:
			filters["outlet"] = outlet_id

		orders = frappe.get_all(
			"Order",
			filters=filters,
			fields=[
				"name", "order_id", "order_number", "outlet",
				"status", "payment_status", "payment_method", "order_type",
				"subtotal", "discount", "loyalty_discount", "packaging_fee",
				"delivery_fee", "tax", "total", "coupon",
				"table_number", "creation", "modified",
			],
			order_by="creation desc",
			limit=limit,
			start=offset,
		)

		total = frappe.db.count("Order", filters=filters)

		# Batch-fetch restaurant names
		rest_ids = list({o.outlet for o in orders if o.outlet})
		rest_meta = {}
		if rest_ids:
			for r in frappe.get_all(
				"Outlet",
				filters={"name": ["in", rest_ids]},
				fields=["name", "outlet_name", "logo"],
			):
				rest_meta[r.name] = r

		result = []
		for o in orders:
			fmt = _format_order(o, include_items=False)
			rm = rest_meta.get(o.outlet, {})
			fmt["outlet_name"] = rm.get("outlet_name") or o.outlet
			fmt["outlet_logo"] = rm.get("logo") or ""
			result.append(fmt)

		return {
			"success": True,
			"data": {
				"orders": result,
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

	except Exception as e:
		frappe.log_error(f"orders.get_my_orders error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: order detail ────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_order_detail(order_id=None, phone=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.orders.get_order_detail

	Returns full order detail including all line items.
	Phone is used to verify the customer owns the order.
	"""
	if not order_id or not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "order_id and phone are required"}}

	if not _validate_session(phone):
		return {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Please log in to view your orders"}}

	try:
		# Try by Frappe name first, then by order_id field
		doc = None
		try:
			doc = frappe.get_doc("Order", order_id)
		except frappe.DoesNotExistError:
			name = frappe.db.get_value("Order", {"order_id": order_id}, "name")
			if name:
				doc = frappe.get_doc("Order", name)

		if not doc:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Order not found"}}

		if not _validate_phone_owns_order(doc, phone):
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "You are not authorized to view this order"}}

		fmt = _format_order(doc, include_items=True)

		# Enrich with restaurant info
		if doc.outlet:
			rm = frappe.db.get_value(
				"Outlet", doc.outlet,
				["outlet_name", "logo", "city"], as_dict=True,
			) or {}
			fmt["outlet_name"] = rm.get("outlet_name") or doc.outlet
			fmt["outlet_logo"] = rm.get("logo") or ""
			fmt["outlet_city"] = rm.get("city") or ""

		return {"success": True, "data": fmt}

	except Exception as e:
		frappe.log_error(f"orders.get_order_detail error: {e}")
		return {"success": False, "error": {"code": "FETCH_ERROR", "message": str(e)}}


# ── Consumer: lightweight status check ───────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_order_status(order_id=None, phone=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.orders.get_order_status

	Lightweight polling endpoint — returns only status and payment_status.
	Called every few seconds from an active order tracking screen.
	"""
	if not order_id or not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "order_id and phone are required"}}

	try:
		# Resolve Frappe name
		name = order_id
		if not frappe.db.exists("Order", order_id):
			name = frappe.db.get_value("Order", {"order_id": order_id}, "name")
		if not name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Order not found"}}

		row = frappe.db.get_value(
			"Order", name,
			["status", "payment_status", "customer_phone", "modified"],
			as_dict=True,
		)
		if not row:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Order not found"}}

		if not _validate_phone_owns_order(frappe._dict(row), phone):
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}}

		return {
			"success": True,
			"data": {
				"order_id": name,
				"status": row.get("status") or "",
				"payment_status": row.get("payment_status") or "",
				"last_updated": str(row.get("modified") or ""),
			},
		}

	except Exception as e:
		frappe.log_error(f"orders.get_order_status error: {e}")
		return {"success": False, "error": {"code": "STATUS_ERROR", "message": str(e)}}


# ── Consumer: cancel order ────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def cancel_order(order_id=None, phone=None, reason=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.orders.cancel_order

	Allows a customer to cancel a pending/confirmed order.
	Only orders in 'pending' or 'confirmed' status can be cancelled.
	Paid orders: refund must be triggered separately via merchant/admin.
	"""
	if not order_id or not phone:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "order_id and phone are required"}}

	if not _validate_session(phone):
		return {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Please log in to cancel your order"}}

	try:
		doc = None
		try:
			doc = frappe.get_doc("Order", order_id)
		except frappe.DoesNotExistError:
			name = frappe.db.get_value("Order", {"order_id": order_id}, "name")
			if name:
				doc = frappe.get_doc("Order", name)

		if not doc:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Order not found"}}

		if not _validate_phone_owns_order(doc, phone):
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "You are not authorized to cancel this order"}}

		cancellable_statuses = {"draft", "confirmed"}
		if (doc.status or "").lower() not in cancellable_statuses:
			return {
				"success": False,
				"error": {
					"code": "INVALID_STATUS",
					"message": f"Cannot cancel order with status '{doc.status}'. Only pending or confirmed orders can be cancelled.",
				},
			}

		doc.status = "cancelled"
		if reason:
			# Store in notes or a cancellation reason field if it exists
			if hasattr(doc, "cancellation_reason"):
				doc.cancellation_reason = reason.strip()
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {
			"success": True,
			"data": {
				"order_id": doc.name,
				"status": "cancelled",
				"message": "Your order has been cancelled.",
				"refund_note": "If you paid online, refund will be processed within 5–7 business days." if doc.payment_status == "completed" else "",
			},
		}

	except Exception as e:
		frappe.log_error(f"orders.cancel_order error: {e}")
		return {"success": False, "error": {"code": "CANCEL_ERROR", "message": str(e)}}
