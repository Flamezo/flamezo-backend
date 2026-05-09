# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
Customer APIs for cross-restaurant analytics.
"""

import frappe
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api
from dinematters.dinematters.utils.permission_helpers import get_user_restaurant_ids
from dinematters.dinematters.utils.customer_helpers import (
	normalize_phone, 
	get_customer_token,
	validate_customer_session,
	mask_name,
	mask_phone
)
from dinematters.dinematters.api.coin_billing import deduct_coins
from dinematters.dinematters.utils.feature_gate import require_plan
from dinematters.dinematters.utils.roles import is_supervisor, is_global_admin

@frappe.whitelist(allow_guest=True)
@require_plan('GOLD')
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
		
		# If Guest, check customer token
		if not is_authorized:
			customer_token = get_customer_token()
			if validate_customer_session(normalized, customer_token):
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
			["name", "phone", "customer_name", "email", "verified_at", "date_of_birth"],
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
				"birthday": str(c.date_of_birth) if c.date_of_birth else None,
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
@require_plan('GOLD')
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
					"birthday": str(customer.date_of_birth) if customer.date_of_birth else None,
					"verifiedAt": str(customer.verified_at) if customer.verified_at else None
				},
				"restaurants": restaurants
			}
		}
	except Exception as e:
		frappe.log_error(f"get_customer_profile error: {e}", "Customer_API")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def get_restaurant_customers(restaurant_id, search=None, page=1, page_size=20):
	"""
	Restaurant: Get customers who have orders/bookings at this restaurant only. Supports search (name, phone), pagination.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		restaurant_ids = get_user_restaurant_ids(frappe.session.user)
		if not is_supervisor() and restaurant not in restaurant_ids:
			return {"success": False, "error": "Permission denied"}

		is_admin = is_supervisor() or "System Manager" in frappe.get_roles()

		page = max(1, int(page))
		page_size = max(1, min(100, int(page_size)))
		limit_start = (page - 1) * page_size
		
		# Collect all distinct customers for this restaurant from two sources:
		# 1. Activity-based: customers who have orders/bookings at this restaurant
		# 2. Import-based: customers explicitly imported for this restaurant
		customer_ids = set()
		for doctype in ["Order", "Table Booking", "Banquet Booking", "Restaurant Loyalty Entry"]:
			filters = {"restaurant": restaurant}
			if doctype == "Restaurant Loyalty Entry":
				filters["customer"] = ["is", "set"]
				pluck_field = "customer"
			else:
				filters["platform_customer"] = ["is", "set"]
				pluck_field = "platform_customer"

			rows = frappe.get_all(
				doctype,
				filters=filters,
				pluck=pluck_field
			)
			customer_ids.update(row for row in rows if row)

		# Also include customers imported for this restaurant (no orders yet)
		if frappe.db.has_column("Customer", "imported_restaurants"):
			imported = frappe.db.sql("""
				SELECT name FROM `tabCustomer`
				WHERE imported_restaurants LIKE %s
				  AND (imported_restaurants = %s
				       OR imported_restaurants LIKE %s
				       OR imported_restaurants LIKE %s
				       OR imported_restaurants LIKE %s)
			""", (
				f"%{restaurant}%",
				restaurant,
				f"{restaurant},%",
				f"%,{restaurant}",
				f"%,{restaurant},%",
			), as_dict=True)
			customer_ids.update(r.name for r in imported)

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
			fields=["name", "phone", "customer_name", "verified_at", "date_of_birth", "imported_restaurants"]
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
			
			# Check if imported for this restaurant
			imported_restaurants = c.get("imported_restaurants") or ""
			is_imported = restaurant in {r.strip() for r in imported_restaurants.split(",") if r.strip()}

			enriched_customers.append({
				**c,
				"last_visited": last_visited,
				"is_imported": is_imported
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

			# Check unlock status for this specific customer
			# GOLD plan has full access, others need to unlock or be admin
			plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type")
			is_gold = plan_type == "GOLD"
			is_unlocked = is_gold or frappe.db.exists("Customer Data Unlock", {"restaurant": restaurant, "customer": cid})
			
			# Mask phone and data if not unlocked
			display_phone = phone if is_unlocked else mask_phone(phone)

			final_customers.append({
				"id": cid,
				"phone": display_phone,
				"customerName": c.get("customer_name") if is_unlocked else mask_name(c.get("customer_name")),
				"email": c.get("email") if is_unlocked else "********",
				"verifiedAt": str(c.get("verified_at")) if c.get("verified_at") else None,
				"birthday": str(c.get("date_of_birth")) if c.get("date_of_birth") else None,
				"lastVisited": str(c.get("last_visited")) if c.get("last_visited") else None,
				"isImported": c.get("is_imported"),
				"orders": orders if is_unlocked else [],
				"tableBookings": table_bookings if is_unlocked else [],
				"banquetBookings": banquet_bookings if is_unlocked else [],
				"is_unlocked": is_unlocked
			})


		
		return {"success": True, "data": {"customers": final_customers, "isAdmin": is_admin, "totalCount": total_count}}
	except Exception as e:
		frappe.log_error(f"get_restaurant_customers error: {e}", f"Customer_API_{restaurant_id}")
		return {"success": False, "error": str(e)}


def _link_customer_to_restaurant(customer_id: str, restaurant: str, updates: dict):
	"""
	Ensure `restaurant` is recorded in the Customer's `imported_restaurants` field.
	Mutates `updates` dict in-place so the caller can batch it into a single set_value call.
	"""
	if not frappe.db.has_column("Customer", "imported_restaurants"):
		return
	current = frappe.db.get_value("Customer", customer_id, "imported_restaurants") or ""
	existing = {r.strip() for r in current.split(",") if r.strip()}
	if restaurant not in existing:
		existing.add(restaurant)
		updates["imported_restaurants"] = ",".join(sorted(existing))


@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def import_customers(restaurant_id, rows):
	"""
	Bulk import customers for a restaurant.

	Accepts a JSON list of row dicts, each with keys:
	  phone (required), name, email, birthday (YYYY-MM-DD)

	For every row:
	  - Phone is normalized via normalize_phone().
	  - If a Customer with that phone already exists → update name/email (birthday only
	    if not already set).
	  - Otherwise → create a new Customer record.

	Returns per-row results plus aggregate counts so the UI can show a summary
	and a downloadable error list.

	Permissions: supervisor or user with access to restaurant_id. GOLD plan required.
	"""
	import json
	import re

	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		restaurant_ids = get_user_restaurant_ids(frappe.session.user)
		if not is_supervisor() and restaurant not in restaurant_ids:
			return {"success": False, "error": "Permission denied"}

		# rows may arrive as a JSON string (form_dict) or already a list
		if isinstance(rows, str):
			try:
				rows = json.loads(rows)
			except Exception:
				return {"success": False, "error": "Invalid rows format — expected a JSON array"}

		if not isinstance(rows, list):
			return {"success": False, "error": "rows must be a list"}

		if len(rows) > 5000:
			return {"success": False, "error": "Maximum 5000 rows per import"}

		from dinematters.dinematters.utils.customer_helpers import (
			normalize_phone,
			get_or_create_customer,
		)

		def _sanitize_raw_phone(raw: str) -> str:
			"""
			Undo Excel corruption before normalize_phone() sees the value:
			  - Scientific notation: '9.19877E+11' → '919877000000'
			  - Float suffix: '9876543210.0' → '9876543210'
			Both are caused by Excel treating phone columns as numbers.
			"""
			import math
			s = raw.strip()
			# Detect scientific notation (e.g. 9.19877E+11 or 9.19877e+11)
			if re.match(r'^[+\-]?\d+\.?\d*[eE][+\-]?\d+$', s):
				try:
					n = float(s)
					if not math.isnan(n) and math.isfinite(n) and n > 0:
						s = str(int(round(n)))
				except (ValueError, OverflowError):
					pass
			# Strip trailing .0 / .00 (float suffix)
			s = re.sub(r'\.0+$', '', s)
			return s

		results = []      # per-row outcome for the UI
		imported = 0      # net-new customers created
		updated  = 0      # existing customers updated
		skipped  = 0      # rows we could not process

		# Track phones we've already processed in THIS batch to skip within-file dupes
		seen_phones: set = set()

		for idx, row in enumerate(rows):
			row_num = idx + 1  # 1-based for human display

			# ── 1. Extract & validate phone ──────────────────────────────────────
			raw_phone = _sanitize_raw_phone(str(row.get("phone") or ""))
			if not raw_phone:
				results.append({"row": row_num, "status": "skipped", "reason": "Phone number is missing"})
				skipped += 1
				continue

			normalized = normalize_phone(raw_phone)
			if not normalized or len(normalized) != 10:
				results.append({"row": row_num, "phone": raw_phone, "status": "skipped",
								"reason": f"Invalid phone number: '{raw_phone}'"})
				skipped += 1
				continue

			if normalized in seen_phones:
				results.append({"row": row_num, "phone": normalized, "status": "skipped",
								"reason": "Duplicate phone number in file — already processed"})
				skipped += 1
				continue

			seen_phones.add(normalized)

			# ── 2. Extract optional fields ────────────────────────────────────────
			raw_name  = str(row.get("name") or "").strip()[:100] or None
			raw_email = str(row.get("email") or "").strip() or None
			raw_dob   = str(row.get("birthday") or "").strip() or None

			# Validate birthday format if provided
			dob_value = None
			if raw_dob:
				if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_dob):
					dob_value = raw_dob
				else:
					# best-effort: skip birthday but don't fail the row
					raw_dob = None

			# ── 3. Upsert customer ────────────────────────────────────────────────
			try:
				existing_id = frappe.db.get_value("Customer", {"phone": normalized}, "name")
				if not existing_id:
					# Try phone variants in case it was saved in a non-normalized form
					for variant in [f"0{normalized}", f"+91{normalized}", f"91{normalized}"]:
						existing_id = frappe.db.get_value("Customer", {"phone": variant}, "name")
						if existing_id:
							break

				if existing_id:
					# ── UPDATE existing customer ──────────────────────────────
					updates = {"phone": normalized}  # always normalize stored phone

					if raw_name:
						updates["customer_name"] = raw_name

					if raw_email is not None:
						updates["email"] = raw_email

					if dob_value:
						current_dob = frappe.db.get_value("Customer", existing_id, "date_of_birth")
						if not current_dob:
							updates["date_of_birth"] = dob_value
						# if already set, silently skip (per product policy)

					# Track which restaurants have imported this customer
					_link_customer_to_restaurant(existing_id, restaurant, updates)

					frappe.db.set_value("Customer", existing_id, updates)
					updated += 1
					results.append({"row": row_num, "phone": normalized,
									"name": raw_name, "status": "updated"})
				else:
					# ── CREATE new customer ───────────────────────────────────
					customer_doc = get_or_create_customer(normalized, raw_name, raw_email)
					if customer_doc:
						new_updates = {}
						if dob_value:
							new_updates["date_of_birth"] = dob_value
						_link_customer_to_restaurant(customer_doc.name, restaurant, new_updates)
						if new_updates:
							frappe.db.set_value("Customer", customer_doc.name, new_updates)
					imported += 1
					results.append({"row": row_num, "phone": normalized,
									"name": raw_name, "status": "imported"})

			except Exception as row_err:
				frappe.log_error(f"import_customers row {row_num} error: {row_err}", "Customer_Import")
				results.append({"row": row_num, "phone": normalized,
								"status": "skipped", "reason": f"Internal error: {str(row_err)[:120]}"})
				skipped += 1

		# Single commit after all rows
		frappe.db.commit()

		return {
			"success": True,
			"data": {
				"imported": imported,
				"updated":  updated,
				"skipped":  skipped,
				"total":    len(rows),
				"results":  results,
			}
		}

	except Exception as e:
		frappe.log_error(f"import_customers error: {e}", "Customer_Import")
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
			
		normalized = normalize_phone(phone)
		if not normalized:
			return {"success": False, "error": "Invalid phone number"}

		# Validate session
		customer_token = get_customer_token()
		if not validate_customer_session(normalized, customer_token):
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
			# "Date of birth can only be inserted once and can not be updated"
			current_dob = frappe.db.get_value("Customer", customer_id, "date_of_birth")
			
			if current_dob:
				# If already set, we ignore the update unless it's the same value
				# User specifically asked to "make sure it can not be updated"
				if date_of_birth and str(date_of_birth) != str(current_dob):
					return {"success": False, "error": "Birthday is already set and cannot be changed."}
			else:
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

@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def unlock_customer_data(restaurant_id, customer_id):
	"""
	Unlocks a customer's profile and phone number for a restaurant.
	Costs 3 coins for SILVER restaurants.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# 1. Check if already unlocked
		if frappe.db.exists("Customer Data Unlock", {"restaurant": restaurant, "customer": customer_id}):
			return {"success": True, "message": "Customer already unlocked."}
			
		# 2. Check Plan - Gold users get it for free
		plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type")
		if plan_type == "GOLD":
			return {"success": True, "message": "Customer data accessible (GOLD Plan)."}

		# 3. Deduct 5 coins
		amount_to_deduct = 5

		deduct_coins(
			restaurant=restaurant,
			amount=amount_to_deduct,
			type="Lead Unlock",
			description=f"Unlocked Customer Profile: {customer_id}",
			ref_doctype="Customer",
			ref_name=customer_id
		)
		
		# 4. Record the unlock
		unlock = frappe.get_doc({
			"doctype": "Customer Data Unlock",
			"restaurant": restaurant,
			"customer": customer_id,
			"unlocked_at": frappe.utils.now_datetime()
		})
		unlock.insert(ignore_permissions=True)
		frappe.db.commit()
		
		return {"success": True, "message": "Profile successfully unlocked for 3 Coins."}
		
	except frappe.ValidationError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(f"[Customer Unlock] Error: {e}", "Customers API")
		return {"success": False, "error": "Internal error occurred during unlock."}
