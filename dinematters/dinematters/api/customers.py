# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
Customer APIs for cross-restaurant analytics.
"""

import frappe
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api
from dinematters.dinematters.utils.permission_helpers import get_user_restaurant_ids
from dinematters.dinematters.utils.customer_helpers import normalize_phone
from dinematters.dinematters.utils.feature_gate import require_plan
from dinematters.dinematters.utils.roles import is_supervisor, is_global_admin

@frappe.whitelist(allow_guest=True)
@require_plan('DIAMOND')
def get_customer_by_phone(phone, restaurant_id):
	"""
	Fetch customer details by phone and restaurant.
	Returns customer info (id, phone, name, email, verified, lastVisited at this restaurant).
	Secure access: 
	- Admin/Staff with restaurant access
	- Customers with valid X-Customer-Token matching the phone number
	"""
	try:
		restaurant = restaurant_id
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "Invalid phone number"}

		# 1. Authorization Check
		is_authorized = False
		
		# Check if User is a System User (Admin/Staff)
		if frappe.session.user != "Guest":
			restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
			restaurant_ids = get_user_restaurant_ids(frappe.session.user)
			if is_supervisor() or restaurant in restaurant_ids:
				is_authorized = True
		
		# If Guest, check X-Customer-Token
		if not is_authorized:
			customer_token = frappe.get_request_header("X-Customer-Token")
			if customer_token:
				from dinematters.dinematters.api.otp import check_session
				session_res = check_session(customer_token)
				if session_res.get("success") and normalize_phone(session_res.get("phone")) == normalized:
					is_authorized = True

		if not is_authorized:
			return {"success": False, "error": "Permission denied. Valid session required."}

		# Find customer by phone (try normalized and common variants)
		customer_id = frappe.db.get_value("Customer", {"phone": normalized}, "name")
		if not customer_id:
			for variant in [f"0{normalized}", f"+91{normalized}", f"+91 {normalized}", f"91{normalized}"]:
				customer_id = frappe.db.get_value("Customer", {"phone": variant}, "name")
				if customer_id:
					break
		if not customer_id:
			return {"success": True, "data": None}

		c = frappe.db.get_value(
			"Customer",
			customer_id,
			["name", "phone", "customer_name", "email", "verified_at"],
			as_dict=True
		)
		if not c:
			return {"success": True, "data": None}

		ph = c.phone
		order_fields = ["name", "order_number", "total", "status", "creation", "customer_phone"]
		if frappe.db.has_column("Order", "customer_rating"):
			order_fields.extend(["customer_rating", "customer_feedback"])
		orders = frappe.get_all(
			"Order",
			filters={"restaurant": restaurant, "platform_customer": customer_id},
			fields=order_fields
		)
		table_bookings = frappe.get_all(
			"Table Booking",
			filters={"restaurant": restaurant, "platform_customer": customer_id},
			fields=["name", "booking_number", "date", "time_slot", "status", "creation", "customer_phone"]
		)
		banquet_bookings = frappe.get_all(
			"Banquet Booking",
			filters={"restaurant": restaurant, "platform_customer": customer_id},
			fields=["name", "booking_number", "date", "event_type", "status", "creation", "customer_phone"]
		)
		if not ph and orders:
			ph = orders[0].get("customer_phone")
		if not ph and table_bookings:
			ph = table_bookings[0].get("customer_phone")
		if not ph and banquet_bookings:
			ph = banquet_bookings[0].get("customer_phone")

		last_dates = []
		for o in orders:
			if o.get("creation"):
				last_dates.append(o["creation"])
		for b in table_bookings + banquet_bookings:
			if b.get("creation"):
				last_dates.append(b["creation"])
		last_visited = max(last_dates) if last_dates else None

		return {
			"success": True,
			"data": {
				"id": c.name,
				"phone": ph,
				"customerName": c.customer_name,
				"email": c.email,
				"verifiedAt": str(c.verified_at) if c.verified_at else None,
				"lastVisited": str(last_visited) if last_visited else None,
				"orders": orders,
				"tableBookings": table_bookings,
				"banquetBookings": banquet_bookings
			}
		}
	except Exception as e:
		frappe.log_error(f"get_customer_by_phone error: {e}", "Customer_API")
		return {"success": False, "error": str(e)}


def update_customer_last_visited(doc, event=None):
	"""Update Customer.last_visited when Order/Table Booking/Banquet Booking is submitted."""
	customer_id = getattr(doc, "platform_customer", None)
	if not customer_id or not frappe.db.exists("Customer", customer_id):
		return
	if not frappe.db.has_column("Customer", "last_visited"):
		return
	ts = doc.creation or doc.modified
	frappe.db.set_value("Customer", customer_id, "last_visited", ts)
	frappe.db.commit()


def normalize_customer_phone_on_save(doc, event=None):
	"""
	Hook to ensure customer phone is always stored in a normalized 10-digit format.
	This prevents duplicates caused by +91, 0, spaces, etc.
	"""
	if doc.phone:
		doc.phone = normalize_phone(doc.phone)


def normalize_order_phone_on_save(doc, event=None):
	"""
	Hook to ensure Order.customer_phone is always stored in a normalized 10-digit format.
	This ensures the customer dashboard remains clean.
	"""
	if doc.customer_phone:
		doc.customer_phone = normalize_phone(doc.customer_phone)


@frappe.whitelist()
@require_plan('DIAMOND')
def get_customer_profile(customer_id, restaurant_id=None):
	"""
	Admin: Get customer profile. If restaurant_id is provided, limit to that restaurant.
	System Manager or Supervisor only.
	"""
	if not is_supervisor():
		return {"success": False, "error": "Permission denied"}

	try:
		if not frappe.db.exists("Customer", customer_id):
			return {"success": False, "error": "Customer not found"}

		customer = frappe.get_doc("Customer", customer_id)
		restaurants = []

		# Orders (include feedback)
		order_fields = ["name", "restaurant", "order_number", "total", "status", "creation"]
		if frappe.db.has_column("Order", "customer_rating"):
			order_fields.extend(["customer_rating", "customer_feedback"])
            
		order_filters = {"platform_customer": customer_id}
		if restaurant_id:
			order_filters["restaurant"] = restaurant_id
            
		orders = frappe.get_all(
			"Order",
			filters=order_filters,
			fields=order_fields
		)
		order_by_rest = {}
		for o in orders:
			rest = o.restaurant
			if rest not in order_by_rest:
				order_by_rest[rest] = []
			order_by_rest[rest].append(o)

		# Table bookings
		tb_filters = {"platform_customer": customer_id}
		if restaurant_id:
			tb_filters["restaurant"] = restaurant_id
            
		table_bookings = frappe.get_all(
			"Table Booking",
			filters=tb_filters,
			fields=["name", "restaurant", "booking_number", "date", "time_slot", "status", "creation"]
		)
		tb_by_rest = {}
		for b in table_bookings:
			rest = b.restaurant
			if rest not in tb_by_rest:
				tb_by_rest[rest] = []
			tb_by_rest[rest].append(b)

		# Banquet bookings
		bb_filters = {"platform_customer": customer_id}
		if restaurant_id:
			bb_filters["restaurant"] = restaurant_id
            
		banquet_bookings = frappe.get_all(
			"Banquet Booking",
			filters=bb_filters,
			fields=["name", "restaurant", "booking_number", "date", "event_type", "status", "creation"]
		)
		bb_by_rest = {}
		for b in banquet_bookings:
			rest = b.restaurant
			if rest not in bb_by_rest:
				bb_by_rest[rest] = []
			bb_by_rest[rest].append(b)

		all_rests = set(order_by_rest.keys()) | set(tb_by_rest.keys()) | set(bb_by_rest.keys())
		for rest_id in all_rests:
			rest_name = frappe.db.get_value("Restaurant", rest_id, "restaurant_name") or rest_id
			restaurants.append({
				"restaurant_id": rest_id,
				"restaurant_name": rest_name,
				"orders": order_by_rest.get(rest_id, []),
				"tableBookings": tb_by_rest.get(rest_id, []),
				"banquetBookings": bb_by_rest.get(rest_id, [])
			})

		return {
			"success": True,
			"data": {
				"customer": {
					"id": customer.name,
					"phone": customer.phone,
					"customerName": customer.customer_name,
					"email": customer.email,
					"verifiedAt": str(customer.verified_at) if customer.verified_at else None
				},
				"restaurants": restaurants
			}
		}
	except Exception as e:
		frappe.log_error(f"get_customer_profile error: {e}", "Customer_API")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
@require_plan('DIAMOND')
def get_restaurant_customers(restaurant_id, search=None, page=1, page_size=20):
	"""
	Restaurant: Get customers who have orders/bookings at this restaurant only. Supports search (name, phone), pagination.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		restaurant_ids = get_user_restaurant_ids(frappe.session.user)
		if not is_supervisor() and restaurant not in restaurant_ids:
			return {"success": False, "error": "Permission denied"}

		page = max(1, int(page))
		page_size = max(1, min(100, int(page_size)))
		limit_start = (page - 1) * page_size
		
		# Collect all distinct platform customers with activity at this restaurant
		# Using frappe.get_all is the most robust and compatible way.
		customer_ids = set()
		for doctype in ["Order", "Table Booking", "Banquet Booking"]:
			rows = frappe.get_all(
				doctype,
				filters={"restaurant": restaurant, "platform_customer": ["!=", ""]},
				pluck="platform_customer"
			)
			customer_ids.update(row for row in rows if row)

		if not customer_ids:
			return {"success": True, "data": {"customers": [], "isAdmin": "System Manager" in frappe.get_roles(), "totalCount": 0}}

		# Filter customers by search if provided
		customer_filters = {"name": ["in", list(customer_ids)]}
		customer_or_filters = []
		
		if search:
			customer_or_filters = [
				["customer_name", "like", f"%{search}%"],
				["phone", "like", f"%{search}%"]
			]

		# Fetch customer details with their last visited date.
		customer_records = frappe.get_all(
			"Customer",
			filters=customer_filters,
			or_filters=customer_or_filters if customer_or_filters else None,
			fields=["name", "phone", "customer_name", "verified_at"]
		)

		# Get last visited date for each customer efficiently using bulk queries
		activity_map = {}
		for doctype_name in ["Order", "Table Booking", "Banquet Booking"]:
			# Using backticks with DocType name is standard in Frappe DB
			table_name = f"tab{doctype_name}"
			# We use a simple SQL to get max creation date per platform_customer
			activity = frappe.db.sql(f"""
				SELECT platform_customer, MAX(creation) as max_date
				FROM `{table_name}`
				WHERE restaurant = %s AND platform_customer IN ({', '.join(['%s'] * len(customer_ids))})
				GROUP BY platform_customer
			""", [restaurant] + list(customer_ids), as_dict=True)
			
			for row in activity:
				cid = row.platform_customer
				mdate = str(row.max_date) if row.max_date else ""
				if cid not in activity_map or mdate > activity_map[cid]:
					activity_map[cid] = mdate

		# Enrich with last_visited and sort
		enriched_customers = []
		for c in customer_records:
			cid = c.get("name")
			last_visited = activity_map.get(cid)
			
			enriched_customers.append({
				**c,
				"last_visited": last_visited
			})

		# Sort by last_visited
		enriched_customers.sort(key=lambda x: (x.get("last_visited") or "", x.get("customer_name") or ""), reverse=True)
		
		total_count = len(enriched_customers)
		
		# Paginate memory-sorted list
		paginated_customers = enriched_customers[limit_start : limit_start + page_size]

		final_customers = []
		for c in paginated_customers:
			cid = c.get("name")
			
			# Fetch child records ONLY for paginated customers
			order_fields = ["name", "order_number", "total", "status", "creation", "customer_phone"]
			if frappe.db.has_column("Order", "customer_rating"):
				order_fields.extend(["customer_rating", "customer_feedback"])
			if frappe.db.has_column("Order", "food_rating"):
				order_fields.extend(["food_rating", "service_rating"])
				
			orders = frappe.get_all(
				"Order",
				filters={"restaurant": restaurant, "platform_customer": cid},
				fields=order_fields,
				order_by="creation desc"
			)
			table_bookings = frappe.get_all(
				"Table Booking",
				filters={"restaurant": restaurant, "platform_customer": cid},
				fields=["name", "booking_number", "date", "time_slot", "status", "creation", "customer_phone"],
				order_by="creation desc"
			)
			banquet_bookings = frappe.get_all(
				"Banquet Booking",
				filters={"restaurant": restaurant, "platform_customer": cid},
				fields=["name", "booking_number", "date", "event_type", "status", "creation", "customer_phone"],
				order_by="creation desc"
			)

			phone = c.get("phone")
			if not phone and orders:
				phone = orders[0].get("customer_phone")
			if not phone and table_bookings:
				phone = table_bookings[0].get("customer_phone")
			if not phone and banquet_bookings:
				phone = banquet_bookings[0].get("customer_phone")

			final_customers.append({
				"id": cid,
				"phone": phone,
				"customerName": c.get("customer_name"),
				"verifiedAt": str(c.get("verified_at")) if c.get("verified_at") else None,
				"lastVisited": str(c.get("last_visited")) if c.get("last_visited") else None,
				"orders": orders,
				"tableBookings": table_bookings,
				"banquetBookings": banquet_bookings
			})

		is_admin = is_supervisor()
		
		return {"success": True, "data": {"customers": final_customers, "isAdmin": is_admin, "totalCount": total_count}}
	except Exception as e:
		frappe.log_error(f"get_restaurant_customers error: {e}", f"Customer_API_{restaurant_id}")
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def update_customer_profile(**kwargs):
	"""
	Called from ONO Menu Profile page. Lets a verified customer update their
	own name, email and date_of_birth (for birthday marketing triggers).
	Auth: X-Customer-Token session header must match the phone number.
	"""
	# Get parameters from kwargs or form_dict
	phone = kwargs.get("phone") or frappe.form_dict.get("phone")
	customer_name = kwargs.get("customer_name") or frappe.form_dict.get("customer_name")
	email = kwargs.get("email") or frappe.form_dict.get("email")
	date_of_birth = kwargs.get("date_of_birth") or frappe.form_dict.get("date_of_birth")

	try:
		if not phone:
			return {"success": False, "error": "Phone number is required"}
			
		from dinematters.dinematters.utils.customer_helpers import normalize_phone
		normalized = normalize_phone(phone)
		if not normalized:
			return {"success": False, "error": "Invalid phone number"}

		# Validate session
		customer_token = frappe.get_request_header("X-Customer-Token")
		if not customer_token and frappe.request:
			customer_token = frappe.request.headers.get("X-Customer-Token")
			if not customer_token:
				# Try lowercase just in case
				customer_token = frappe.request.headers.get("x-customer-token")
			
		if not customer_token:
			# Log headers for debugging if auth fails
			headers_dump = {}
			if frappe.request:
				headers_dump = dict(frappe.request.headers)
			
			# Truncate headers dump to avoid CharacterLengthExceededError
			dump_str = str(headers_dump)[:2000]
			frappe.log_error("Auth Error", f"Auth failed for {phone}. Headers: {dump_str}"[:5000])
			return {"success": False, "error": "Authentication required"}

		from dinematters.dinematters.api.otp import check_session
		session_res = check_session(customer_token)
		if not session_res.get("success") or normalize_phone(session_res.get("phone")) != normalized:
			return {"success": False, "error": "Session invalid or phone mismatch"}

		# Find customer
		customer_id = frappe.db.get_value("Customer", {"phone": normalized}, "name")
		if not customer_id:
			# Try variants
			for variant in [f"+91{normalized}", f"0{normalized}"]:
				customer_id = frappe.db.get_value("Customer", {"phone": variant}, "name")
				if customer_id:
					break
		if not customer_id:
			return {"success": False, "error": "Customer not found. Please verify your phone first."}

		# Build update dict (only update fields provided)
		updates = {}
		if customer_name is not None:
			updates["customer_name"] = str(customer_name)[:100].strip()
		if email is not None:
			updates["email"] = str(email).strip() or None
		if date_of_birth is not None:
			# Accept YYYY-MM-DD or empty string (clear)
			import re
			dob = str(date_of_birth).strip()
			if dob == "":
				updates["date_of_birth"] = None
			elif re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
				updates["date_of_birth"] = dob
			else:
				return {"success": False, "error": "date_of_birth must be YYYY-MM-DD format"}

		if not updates:
			return {"success": True, "message": "Nothing to update"}

		frappe.db.set_value("Customer", customer_id, updates)
		frappe.db.commit()

		# Return updated fields
		c = frappe.db.get_value("Customer", customer_id,
			["customer_name", "email", "date_of_birth"], as_dict=True)
		return {
			"success": True,
			"data": {
				"customer_name": c.customer_name,
				"email": c.email,
				"date_of_birth": str(c.date_of_birth) if c.date_of_birth else None
			}
		}
	except Exception as e:
		msg = str(e)[:1000]
		frappe.log_error("Customer API Error", f"update_customer_profile error: {msg}"[:5000])
		return {"success": False, "error": "Internal server error"}

