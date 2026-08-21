import frappe

def create_default_coupons(restaurant_name):
	"""
	Automatically creates highly profitable default "calm" offers for a restaurant.
	These offers run automatically (Curated for You) and cap at ~8% max discount.
	"""
	default_coupons = [
		{
			"code": "SAVE50",
			"offer_type": "auto",
			"discount_type": "flat",
			"discount_value": 50,
			"min_order_amount": 600,
			"description": "Get ₹50 off on small orders",
			"priority": 1,
			"can_stack": 0,
			"is_active": 1,
			"category": "Discounts"
		},
		{
			"code": "SAVE100",
			"offer_type": "auto",
			"discount_type": "flat",
			"discount_value": 100,
			"min_order_amount": 1200,
			"description": "Get ₹100 off on medium orders",
			"priority": 2,
			"can_stack": 0,
			"is_active": 1,
			"category": "Discounts"
		},
		{
			"code": "SAVE200",
			"offer_type": "auto",
			"discount_type": "flat",
			"discount_value": 200,
			"min_order_amount": 2500,
			"description": "Get ₹200 off on large orders",
			"priority": 3,
			"can_stack": 0,
			"is_active": 1,
			"category": "Discounts"
		},
		{
			"code": "GOOGLEREVIEW",
			"offer_type": "google_review",
			"review_reward_type": "cashback",
			"discount_type": "flat",
			"discount_value": 50,
			"min_order_amount": 350,
			# Works out of the box as ₹50 cashback; the merchant can switch to a
			# Free Dish (and type its name) in the merchant Coupons form.
			"description": "Leave us a 5-Star Google Review & get ₹50 off your bill!",
			"priority": 4,
			"can_stack": 0,
			"is_active": 1,
			"category": "Reviews"
		}
	]

	created_count = 0
	for coupon_data in default_coupons:
		# Check if coupon code already exists for this restaurant
		if frappe.db.exists("Coupon", {"outlet": restaurant_name, "code": coupon_data["code"]}):
			continue

		try:
			doc = frappe.get_doc({
				"doctype": "Coupon",
				"outlet": restaurant_name,
				**coupon_data
			})
			doc.insert(ignore_permissions=True)
			created_count += 1
		except Exception as e:
			frappe.log_error(f"Failed to create default coupon {coupon_data['code']} for restaurant {restaurant_name}: {str(e)}", "Default Coupon Creation")

	if created_count > 0:
		frappe.db.commit()
	
	return created_count
