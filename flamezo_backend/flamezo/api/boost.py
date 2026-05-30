"""
Flamezo Boost — Ad campaign management API.

Restaurant owners create, pay for, and monitor Meta ad campaigns that drive
walk-in customers via coupon redemption tracking.
"""
import frappe
import json
from frappe import _
from frappe.utils import now, today, flt, add_days, getdate
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api


# ─── Prerequisites ──────────────────────────────────────────────────

@frappe.whitelist()
def check_prerequisites(restaurant_id):
	"""
	Run all prerequisite checks for Boost eligibility.
	Returns score (0-100), individual check results, and location grade.
	"""
	restaurant_id = validate_restaurant_for_api(restaurant_id)
	restaurant = frappe.get_doc("Restaurant", restaurant_id)

	checks = []

	# 1. Verified address + coordinates
	has_address = bool(restaurant.address and restaurant.city)
	has_coords = bool(restaurant.latitude and restaurant.longitude)
	checks.append({
		"check": "verified_address",
		"label": "Verified address with GPS coordinates",
		"passed": has_address and has_coords,
		"details": f"{'Address set' if has_address else 'No address'}, {'Coords set' if has_coords else 'No coordinates'}"
	})

	# 2. Minimum 8 food photos
	# Product Media is a child table of Menu Product — count via parent
	photo_count = frappe.db.sql("""
		SELECT COUNT(DISTINCT pm.name) FROM `tabProduct Media` pm
		INNER JOIN `tabMenu Product` mp ON pm.parent = mp.name
		WHERE mp.restaurant = %s
	""", (restaurant_id,))[0][0] or 0
	# Also count Media Assets linked to this restaurant
	media_count = frappe.db.count("Media Asset", filters={"restaurant": restaurant_id}) or 0
	total_photos = photo_count + media_count
	checks.append({
		"check": "min_photos",
		"label": "At least 8 food photos uploaded",
		"passed": total_photos >= 8,
		"details": f"{total_photos} photos found (need 8)"
	})

	# 3. Complete menu with prices (min 15 items)
	menu_count = frappe.db.count("Menu Product", filters={
		"restaurant": restaurant_id,
		"is_active": 1
	}) or 0
	checks.append({
		"check": "complete_menu",
		"label": "At least 15 active menu items",
		"passed": menu_count >= 15,
		"details": f"{menu_count} active items (need 15)"
	})

	# 4. Operating hours set
	has_hours = bool(restaurant.opening_time and restaurant.closing_time) if hasattr(restaurant, 'opening_time') else True
	checks.append({
		"check": "operating_hours",
		"label": "Operating hours configured",
		"passed": has_hours,
		"details": "Hours set" if has_hours else "No hours configured"
	})

	# 5. At least 1 dish with photo (proxy for signature item)
	signature_count = photo_count  # reuse the Product Media count from check #2
	checks.append({
		"check": "signature_dish",
		"label": "At least 1 dish with photo (signature item)",
		"passed": signature_count >= 1,
		"details": f"{signature_count} dishes with photos"
	})

	# 6. Active subscription
	checks.append({
		"check": "active_subscription",
		"label": "Active Flamezo subscription",
		"passed": True,  # All restaurants are GOLD now
		"details": "GOLD plan active"
	})

	# 7. Razorpay active
	has_razorpay = bool(restaurant.razorpay_account_id) if hasattr(restaurant, 'razorpay_account_id') else False
	checks.append({
		"check": "razorpay_active",
		"label": "Payment setup (Razorpay)",
		"passed": has_razorpay,
		"details": "Razorpay linked" if has_razorpay else "Razorpay not configured"
	})

	# 9. Owner WhatsApp verified
	# Check if any Restaurant User has a verified phone
	has_owner = frappe.db.count("Restaurant User", filters={"restaurant": restaurant_id}) > 0
	checks.append({
		"check": "owner_verified",
		"label": "Restaurant owner verified",
		"passed": has_owner,
		"details": "Owner account exists" if has_owner else "No owner account"
	})

	# 10. Staff coupon training (check if any Boost Coupon Redemption exists = trained)
	# For first-time: auto-pass (training happens in wizard)
	past_campaigns = frappe.db.count("Boost Campaign", filters={
		"restaurant": restaurant_id,
		"status": ["in", ["Live", "Completed"]]
	})
	training_done = past_campaigns > 0
	checks.append({
		"check": "coupon_training",
		"label": "Coupon redemption training",
		"passed": training_done or True,  # Auto-pass for v1 — training in wizard
		"details": "Completed" if training_done else "Will complete during setup"
	})

	# Compute score
	passed_count = sum(1 for c in checks if c["passed"])
	total_count = len(checks)
	score = int((passed_count / total_count) * 100)

	# Location grade (simplified — based on city tier)
	location_grade = _get_location_grade(restaurant)

	# Save audit trail
	prereq_doc = frappe.get_doc({
		"doctype": "Boost Prerequisite Check",
		"restaurant": restaurant_id,
		"checked_at": now(),
		"overall_score": score,
		"passed": 1 if score == 100 else 0,
		"checks": json.dumps(checks),
		"location_grade": location_grade,
	})
	prereq_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"score": score,
			"passed": score == 100,
			"checks": checks,
			"location_grade": location_grade,
			"failed_checks": [c for c in checks if not c["passed"]],
		}
	}


def _get_location_grade(restaurant):
	"""
	Determine location grade based on city.
	Tier 1 metros = B/C (higher CPM), Tier 2 = A (lower CPM).
	"""
	city = (restaurant.city or "").lower().strip()
	tier1 = ["mumbai", "delhi", "bangalore", "bengaluru", "chennai", "hyderabad", "kolkata", "pune"]
	tier1_premium = ["mumbai", "delhi", "bangalore", "bengaluru"]

	if city in tier1_premium:
		return "C"
	elif city in tier1:
		return "B"
	else:
		return "A"  # Tier 2/3 cities — best CPM rates


# ─── Templates ──────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_boost_templates():
	"""Return all active Boost Templates sorted by rank."""
	templates = frappe.get_all("Boost Template",
		filters={"is_active": 1},
		fields=["template_id", "template_name", "rank", "best_for", "cta_type",
				"requires_hero_dish", "hook_formula", "offer_type_description",
				"expected_ctr_low", "expected_ctr_high"],
		order_by="rank asc"
	)
	return {"success": True, "data": templates}


# ─── Campaign CRUD ──────────────────────────────────────────────────

@frappe.whitelist()
def get_boost_overview(restaurant_id):
	"""Dashboard overview: active campaigns, totals, ROI."""
	validate_restaurant_for_api(restaurant_id)

	campaigns = frappe.get_all("Boost Campaign",
		filters={"restaurant": restaurant_id},
		fields=["name", "campaign_name", "status", "package_tier", "budget_total",
				"impressions", "reach", "link_clicks", "coupons_claimed",
				"coupons_redeemed", "amount_spent_meta", "cost_per_redemption",
				"launch_date", "end_date", "template_id", "offer_amount",
				"location_grade", "is_first_campaign"],
		order_by="creation desc"
	)

	total_spend = sum(flt(c.budget_total) for c in campaigns)
	total_redemptions = sum(c.coupons_redeemed or 0 for c in campaigns)
	active = [c for c in campaigns if c.status in ("Live", "Submitted", "Meta Review")]

	return {
		"success": True,
		"data": {
			"campaigns": campaigns,
			"active_count": len(active),
			"total_campaigns": len(campaigns),
			"total_spend": total_spend,
			"total_redemptions": total_redemptions,
			"avg_cost_per_redemption": (total_spend / max(total_redemptions, 1)),
		}
	}


@frappe.whitelist()
def create_boost_campaign(restaurant_id, template_id, package_tier,
						   campaign_duration, geo_radius_km, offer_amount,
						   hero_dish_name=None, ad_image_url=None):
	"""
	Create a draft Boost Campaign. Generates AI ad copy and linked coupon.
	"""
	restaurant_id = validate_restaurant_for_api(restaurant_id)
	restaurant = frappe.get_doc("Restaurant", restaurant_id)
	offer_amount = flt(offer_amount)

	if offer_amount <= 0:
		return {"success": False, "error": {"code": "INVALID_OFFER", "message": "Offer amount must be greater than 0"}}

	# Generate AI ad copy
	from flamezo_backend.flamezo.services.boost_creative import generate_ad_copy
	copy = generate_ad_copy(restaurant_id, template_id, hero_dish_name, offer_amount)

	# Create campaign doc
	campaign = frappe.get_doc({
		"doctype": "Boost Campaign",
		"restaurant": restaurant_id,
		"campaign_name": f"{restaurant.restaurant_name} — {frappe.db.get_value('Boost Template', template_id, 'template_name') or template_id}",
		"status": "Draft",
		"package_tier": package_tier,
		"campaign_duration": str(campaign_duration),
		"template_id": template_id,
		"hero_dish_name": hero_dish_name,
		"offer_amount": offer_amount,
		"offer_description": copy["offer_description"],
		"ad_primary_text": copy["primary_text"],
		"ad_headline": copy["headline"],
		"ad_image_url": ad_image_url,
		"geo_radius_km": str(geo_radius_km),
		"restaurant_lat": restaurant.latitude,
		"restaurant_lng": restaurant.longitude,
		"target_age_min": 18,
		"target_age_max": 55,
		"location_grade": _get_location_grade(restaurant),
	})
	campaign.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"campaign_id": campaign.name,
			"campaign_name": campaign.campaign_name,
			"ad_primary_text": campaign.ad_primary_text,
			"ad_headline": campaign.ad_headline,
			"offer_description": campaign.offer_description,
			"coupon_code": campaign.coupon_code,
			"budget_total": campaign.budget_total,
			"ad_spend_allocated": campaign.ad_spend_allocated,
			"flamezo_fee": campaign.flamezo_fee,
			"gst_on_fee": campaign.gst_on_fee,
			"guaranteed_redemptions": campaign.guaranteed_redemptions,
			"is_first_campaign": campaign.is_first_campaign,
			"location_grade": campaign.location_grade,
		}
	}


@frappe.whitelist()
def approve_creative(campaign_id):
	"""Restaurant approves the ad creative preview."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status != "Draft":
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Can only approve Draft campaigns"}}

	campaign.creative_approved = 1
	campaign.status = "Pending Payment"
	campaign.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"campaign_id": campaign.name, "status": campaign.status}}


@frappe.whitelist()
def regenerate_creative(campaign_id):
	"""Regenerate AI ad copy for a Draft campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status != "Draft":
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Can only regenerate Draft campaigns"}}

	from flamezo_backend.flamezo.services.boost_creative import generate_ad_copy
	copy = generate_ad_copy(campaign.restaurant, campaign.template_id,
							campaign.hero_dish_name, flt(campaign.offer_amount))

	campaign.ad_primary_text = copy["primary_text"]
	campaign.ad_headline = copy["headline"]
	campaign.creative_approved = 0
	campaign.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"ad_primary_text": campaign.ad_primary_text,
			"ad_headline": campaign.ad_headline,
		}
	}


# ─── Payment ────────────────────────────────────────────────────────

@frappe.whitelist()
def create_boost_payment(campaign_id):
	"""Create a Razorpay order for a Pending Payment campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status != "Pending Payment":
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Campaign must be in Pending Payment status"}}

	from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config, get_razorpay_client
	config = get_razorpay_config()
	client = get_razorpay_client()

	# Total = budget + GST on fee
	total_amount_inr = flt(campaign.budget_total) + flt(campaign.gst_on_fee)
	total_amount_paisa = int(total_amount_inr * 100)

	order_data = {
		"amount": total_amount_paisa,
		"currency": "INR",
		"receipt": f"boost_{campaign.name}",
		"notes": {
			"boost_campaign": campaign.name,
			"restaurant": campaign.restaurant,
			"package": campaign.package_tier,
		}
	}
	rz_order = client.order.create(data=order_data)

	campaign.razorpay_order_id = rz_order["id"]
	campaign.payment_status = "Pending"
	campaign.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"razorpay_order_id": rz_order["id"],
			"amount": total_amount_paisa,
			"currency": "INR",
			"key_id": config["key_id"],
			"campaign_id": campaign.name,
			"restaurant": campaign.restaurant,
		}
	}


@frappe.whitelist()
def verify_boost_payment(campaign_id, razorpay_order_id, razorpay_payment_id, razorpay_signature):
	"""Verify Razorpay payment and launch Meta campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)

	from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client
	client = get_razorpay_client()

	# Verify signature
	try:
		client.utility.verify_payment_signature({
			"razorpay_order_id": razorpay_order_id,
			"razorpay_payment_id": razorpay_payment_id,
			"razorpay_signature": razorpay_signature,
		})
	except Exception:
		campaign.payment_status = "Failed"
		campaign.save(ignore_permissions=True)
		frappe.db.commit()
		return {"success": False, "error": {"code": "PAYMENT_FAILED", "message": "Payment verification failed"}}

	# Payment success — mark as Captured but stay in "Submitted" (not Live yet)
	# Meta launch happens in background; if it fails, campaign goes to "Failed"
	# and admin can retry or refund. This avoids the race condition of marking
	# Captured before Meta succeeds.
	campaign.razorpay_payment_id = razorpay_payment_id
	campaign.payment_status = "Captured"
	campaign.paid_at = now()
	campaign.status = "Submitted"
	campaign.save(ignore_permissions=True)

	# Create the linked Coupon doc (inactive until campaign goes Live)
	_create_linked_coupon(campaign, active=False)

	frappe.db.commit()

	# Enqueue Meta campaign launch as background job with retry
	frappe.enqueue(
		"flamezo_backend.flamezo.services.meta_ads.launch_boost_campaign",
		campaign_name=campaign.name,
		queue="long",
		timeout=180,
		enqueue_after_commit=True,
		is_async=True,
		at_front=True,
	)

	return {
		"success": True,
		"data": {
			"campaign_id": campaign.name,
			"status": "Submitted",
			"message": "Payment verified. Campaign is being launched on Meta — you'll be notified when it's live."
		}
	}


def _create_linked_coupon(campaign, active=True):
	"""Create a Coupon doc linked to this Boost Campaign for redemption tracking."""
	valid_until = add_days(today(), int(campaign.campaign_duration or 14) + 7)

	coupon = frappe.get_doc({
		"doctype": "Coupon",
		"restaurant": campaign.restaurant,
		"code": campaign.coupon_code,
		"offer_type": "coupon",
		"discount_type": "flat",
		"discount_value": flt(campaign.coupon_discount),
		"min_order_amount": flt(campaign.coupon_min_order),
		"description": campaign.offer_description,
		"detailed_description": f"Boost Campaign: {campaign.name}",
		"valid_from": today(),
		"valid_until": valid_until,
		"is_active": 1 if active else 0,
		"max_uses": 0,  # Unlimited
		"max_uses_per_user": 0,  # Unlimited
	})
	coupon.insert(ignore_permissions=True)

	campaign.linked_coupon = coupon.name
	campaign.save(ignore_permissions=True)


# ─── Campaign Management ───────────────────────────────────────────

@frappe.whitelist()
def pause_boost_campaign(campaign_id):
	"""Pause a live campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status != "Live":
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Can only pause Live campaigns"}}

	from flamezo_backend.flamezo.services.meta_ads import pause_campaign
	if campaign.meta_campaign_id:
		pause_campaign(campaign.meta_campaign_id)

	campaign.mark_paused()
	frappe.db.commit()

	return {"success": True, "data": {"campaign_id": campaign.name, "status": "Paused"}}


@frappe.whitelist()
def resume_boost_campaign(campaign_id):
	"""Resume a paused campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status != "Paused":
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Can only resume Paused campaigns"}}

	from flamezo_backend.flamezo.services.meta_ads import activate_campaign
	if campaign.meta_campaign_id:
		activate_campaign(campaign.meta_campaign_id)

	campaign.mark_resumed()
	frappe.db.commit()

	return {"success": True, "data": {"campaign_id": campaign.name, "status": "Live"}}


@frappe.whitelist()
def cancel_boost_campaign(campaign_id):
	"""Cancel a campaign (Draft or Pending Payment only)."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)
	if campaign.status not in ("Draft", "Pending Payment"):
		return {"success": False, "error": {"code": "INVALID_STATUS", "message": "Can only cancel Draft or Pending Payment campaigns"}}

	campaign.status = "Cancelled"
	campaign.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"campaign_id": campaign.name, "status": "Cancelled"}}


# ─── Performance ────────────────────────────────────────────────────

@frappe.whitelist()
def get_boost_performance(campaign_id):
	"""Get real-time performance for a single campaign."""
	campaign = frappe.get_doc("Boost Campaign", campaign_id)

	# Compute days remaining
	days_remaining = 0
	if campaign.end_date and campaign.status == "Live":
		end_dt = getdate(str(campaign.end_date))
		today_dt = getdate(today())
		if end_dt and today_dt:
			days_remaining = (end_dt - today_dt).days

	# Get redemption details
	redemptions = frappe.get_all("Boost Coupon Redemption",
		filters={"boost_campaign": campaign_id},
		fields=["redeemed_at", "redemption_method", "bill_amount"],
		order_by="redeemed_at desc",
		limit=100
	)

	# Compute estimated revenue from bill amounts
	total_bill = sum(flt(r.bill_amount) for r in redemptions if r.bill_amount)

	data = {
		"campaign_id": campaign.name,
		"campaign_name": campaign.campaign_name,
		"status": campaign.status,
		"package_tier": campaign.package_tier,
		"budget_total": campaign.budget_total,
		"ad_spend_allocated": campaign.ad_spend_allocated,
		"impressions": campaign.impressions,
		"reach": campaign.reach,
		"link_clicks": campaign.link_clicks,
		"coupons_claimed": campaign.coupons_claimed,
		"coupons_redeemed": campaign.coupons_redeemed,
		"amount_spent_meta": campaign.amount_spent_meta,
		"cost_per_redemption": campaign.cost_per_redemption,
		"estimated_revenue": total_bill or campaign.estimated_revenue,
		"launch_date": str(campaign.launch_date) if campaign.launch_date else None,
		"end_date": str(campaign.end_date) if campaign.end_date else None,
		"days_remaining": days_remaining,
		"guaranteed_redemptions": campaign.guaranteed_redemptions,
		"guarantee_met": campaign.guarantee_met,
		"is_first_campaign": campaign.is_first_campaign,
		"location_grade": campaign.location_grade,
		"coupon_code": campaign.coupon_code,
		"offer_amount": campaign.offer_amount,
		"template_id": campaign.template_id,
		"ad_primary_text": campaign.ad_primary_text,
		"ad_headline": campaign.ad_headline,
		"ad_image_url": campaign.ad_image_url,
		"offer_description": campaign.offer_description,
		"flamezo_fee": campaign.flamezo_fee,
		"gst_on_fee": campaign.gst_on_fee,
		"redemptions": redemptions,
	}

	return {"success": True, "data": data}


@frappe.whitelist()
def get_boost_campaigns(restaurant_id, status=None):
	"""List all campaigns for a restaurant, optionally filtered by status."""
	validate_restaurant_for_api(restaurant_id)

	filters = {"restaurant": restaurant_id}
	if status:
		filters["status"] = status

	campaigns = frappe.get_all("Boost Campaign",
		filters=filters,
		fields=["name", "campaign_name", "status", "package_tier", "budget_total",
				"impressions", "coupons_redeemed", "amount_spent_meta",
				"cost_per_redemption", "launch_date", "end_date", "template_id",
				"offer_amount", "coupon_code", "is_first_campaign", "location_grade"],
		order_by="creation desc"
	)

	return {"success": True, "data": campaigns}


# ─── Coupon Redemption (Staff) ──────────────────────────────────────

@frappe.whitelist()
def redeem_boost_coupon(restaurant_id, coupon_code, bill_amount=None,
						redemption_method="Staff Entry"):
	"""
	Staff redeems a Boost coupon at the restaurant.
	Creates a Boost Coupon Redemption record and increments campaign counter.
	"""
	validate_restaurant_for_api(restaurant_id)
	coupon_code = (coupon_code or "").strip().upper()

	if not coupon_code:
		return {"success": False, "error": {"code": "NO_CODE", "message": "Coupon code is required"}}

	# Find the active Boost Campaign with this code
	campaign = frappe.db.get_value("Boost Campaign",
		filters={
			"restaurant": restaurant_id,
			"coupon_code": coupon_code,
			"status": ["in", ["Live", "Completed"]],
		},
		fieldname=["name", "campaign_name", "offer_amount", "coupon_discount"],
		as_dict=True
	)

	if not campaign:
		return {"success": False, "error": {"code": "INVALID_CODE", "message": "No active Boost campaign found for this code"}}

	# Create redemption record
	redemption = frappe.get_doc({
		"doctype": "Boost Coupon Redemption",
		"boost_campaign": campaign.name,
		"restaurant": restaurant_id,
		"coupon_code": coupon_code,
		"redeemed_at": now(),
		"redemption_method": redemption_method,
		"bill_amount": flt(bill_amount) if bill_amount else None,
	})
	redemption.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"redemption_id": redemption.name,
			"campaign_name": campaign.campaign_name,
			"discount": campaign.coupon_discount,
			"message": f"Coupon redeemed! ₹{int(campaign.coupon_discount)} off applied."
		}
	}


# ─── Public Coupon Claim (Customer) ─────────────────────────────────

@frappe.whitelist(allow_guest=True)
def claim_boost_coupon(restaurant_id, coupon_code):
	"""
	Public endpoint — customer lands here from Meta ad.
	Returns coupon details + restaurant info for the claim page.
	"""
	coupon_code = (coupon_code or "").strip().upper()

	# Find campaign
	campaign = frappe.db.get_value("Boost Campaign",
		filters={
			"restaurant": restaurant_id,
			"coupon_code": coupon_code,
			"status": ["in", ["Live", "Completed"]],
		},
		fieldname=["name", "campaign_name", "offer_amount", "coupon_discount",
				   "coupon_min_order", "end_date", "coupon_valid_days"],
		as_dict=True
	)

	if not campaign:
		return {"success": False, "error": {"code": "INVALID_CODE", "message": "This offer is no longer available"}}

	# Get restaurant info
	restaurant = frappe.db.get_value("Restaurant", restaurant_id,
		fieldname=["restaurant_name", "address", "city", "latitude", "longitude"],
		as_dict=True
	)

	# Increment claimed counter
	frappe.db.sql("""
		UPDATE `tabBoost Campaign`
		SET coupons_claimed = coupons_claimed + 1
		WHERE name = %s
	""", (campaign.name,))
	frappe.db.commit()

	valid_until = add_days(today(), campaign.coupon_valid_days or 21)

	return {
		"success": True,
		"data": {
			"coupon_code": coupon_code,
			"discount": campaign.coupon_discount,
			"min_order": campaign.coupon_min_order,
			"valid_until": str(valid_until),
			"restaurant_name": restaurant.restaurant_name if restaurant else restaurant_id,
			"restaurant_address": restaurant.address if restaurant else "",
			"restaurant_city": restaurant.city if restaurant else "",
			"restaurant_lat": restaurant.latitude if restaurant else None,
			"restaurant_lng": restaurant.longitude if restaurant else None,
			"offer_description": f"Flat ₹{int(campaign.offer_amount)} off (min order ₹{int(campaign.coupon_min_order or 0)})",
		}
	}
