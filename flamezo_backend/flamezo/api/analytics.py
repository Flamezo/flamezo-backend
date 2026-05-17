# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Analytics API for Offer System
Provides insights into coupon usage, offer performance, and revenue impact
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_days
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
import json


# Production-grade analytics engine with tiered feature gating
@frappe.whitelist()
def get_offer_analytics(restaurant_id, start_date=None, end_date=None):
	"""
	Get comprehensive analytics for offers and coupons
	
	Returns:
	- Total offers created
	- Active vs inactive offers
	- Coupon usage statistics
	- Revenue impact (discount given vs revenue generated)
	- Top performing offers
	- Offer type breakdown
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Default date range: last 30 days
		if not end_date:
			end_date = today()
		if not start_date:
			start_date = add_days(end_date, -30)
		
		# Get all offers for restaurant
		offers = frappe.get_all(
			"Coupon",
			filters={"restaurant": restaurant},
			fields=["name", "code", "offer_type", "is_active", "usage_count", "max_uses"]
		)
		
		# Offer breakdown
		total_offers = len(offers)
		active_offers = len([o for o in offers if o.is_active])
		inactive_offers = total_offers - active_offers
		
		# Offer type breakdown
		offer_types = {}
		for offer in offers:
			offer_type = offer.offer_type or "coupon"
			offer_types[offer_type] = offer_types.get(offer_type, 0) + 1
		
		# Get coupon usage data
		usage_data = frappe.db.sql("""
			SELECT 
				cu.coupon,
				c.code,
				c.offer_type,
				COUNT(*) as usage_count,
				SUM(cu.discount_amount) as total_discount,
				c.discount_value,
				c.discount_type
			FROM `tabCoupon Usage` cu
			JOIN `tabCoupon` c ON cu.coupon = c.name
			WHERE cu.restaurant = %s
			AND cu.usage_date BETWEEN %s AND %s
			GROUP BY cu.coupon
			ORDER BY usage_count DESC
			LIMIT 10
		""", (restaurant, start_date, end_date), as_dict=True)
		
		# Calculate total discount given
		total_discount_given = sum([flt(u.total_discount) for u in usage_data])
		total_redemptions = sum([u.usage_count for u in usage_data])
		
		# Get revenue impact (orders with coupons vs without)
		revenue_data = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_orders,
				SUM(subtotal) as total_subtotal,
				SUM(discount) as total_discount,
				SUM(total) as total_revenue
			FROM `tabOrder`
			WHERE restaurant = %s
			AND creation BETWEEN %s AND %s
			AND coupon IS NOT NULL
		""", (restaurant, start_date, end_date), as_dict=True)
		
		orders_with_coupons = revenue_data[0] if revenue_data else {
			"total_orders": 0,
			"total_subtotal": 0,
			"total_discount": 0,
			"total_revenue": 0
		}
		
		# Get orders without coupons for comparison
		revenue_no_coupon = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_orders,
				SUM(total) as total_revenue
			FROM `tabOrder`
			WHERE restaurant = %s
			AND creation BETWEEN %s AND %s
			AND (coupon IS NULL OR coupon = '')
		""", (restaurant, start_date, end_date), as_dict=True)
		
		orders_without_coupons = revenue_no_coupon[0] if revenue_no_coupon else {
			"total_orders": 0,
			"total_revenue": 0
		}
		
		# Calculate average order value
		avg_order_with_coupon = (
			flt(orders_with_coupons["total_revenue"]) / orders_with_coupons["total_orders"]
			if orders_with_coupons["total_orders"] > 0 else 0
		)
		
		avg_order_without_coupon = (
			flt(orders_without_coupons["total_revenue"]) / orders_without_coupons["total_orders"]
			if orders_without_coupons["total_orders"] > 0 else 0
		)
		
		# Top performing offers
		top_offers = []
		for usage in usage_data[:5]:
			top_offers.append({
				"code": usage.code,
				"offerType": usage.offer_type or "coupon",
				"usageCount": usage.usage_count,
				"totalDiscount": flt(usage.total_discount),
				"avgDiscount": flt(usage.total_discount) / usage.usage_count if usage.usage_count > 0 else 0
			})
		
		return {
			"success": True,
			"data": {
				"dateRange": {
					"startDate": start_date,
					"endDate": end_date
				},
				"offerSummary": {
					"totalOffers": total_offers,
					"activeOffers": active_offers,
					"inactiveOffers": inactive_offers,
					"offerTypeBreakdown": offer_types
				},
				"usageStatistics": {
					"totalRedemptions": total_redemptions,
					"totalDiscountGiven": total_discount_given,
					"avgDiscountPerRedemption": total_discount_given / total_redemptions if total_redemptions > 0 else 0
				},
				"revenueImpact": {
					"ordersWithCoupons": orders_with_coupons["total_orders"],
					"ordersWithoutCoupons": orders_without_coupons["total_orders"],
					"revenueWithCoupons": flt(orders_with_coupons["total_revenue"]),
					"revenueWithoutCoupons": flt(orders_without_coupons["total_revenue"]),
					"avgOrderValueWithCoupon": avg_order_with_coupon,
					"avgOrderValueWithoutCoupon": avg_order_without_coupon,
					"totalSubtotal": flt(orders_with_coupons["total_subtotal"]),
					"totalDiscount": flt(orders_with_coupons["total_discount"])
				},
				"topPerformingOffers": top_offers
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_offer_analytics: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "ANALYTICS_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def get_coupon_performance(restaurant_id, coupon_id):
	"""
	Get detailed performance metrics for a specific coupon
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get coupon details
		coupon = frappe.get_doc("Coupon", coupon_id)
		
		if coupon.restaurant != restaurant:
			return {
				"success": False,
				"error": {
					"code": "UNAUTHORIZED",
					"message": "Coupon does not belong to this restaurant"
				}
			}
		
		# Get usage history
		usage_history = frappe.get_all(
			"Coupon Usage",
			filters={"coupon": coupon_id},
			fields=["usage_date", "discount_amount", "customer", "order"],
			order_by="usage_date desc",
			limit=100
		)
		
		# Get unique customers
		unique_customers = len(set([u.customer for u in usage_history]))
		
		# Calculate daily usage trend
		daily_usage = {}
		for usage in usage_history:
			date_key = str(getdate(usage.usage_date))
			if date_key not in daily_usage:
				daily_usage[date_key] = {"count": 0, "discount": 0}
			daily_usage[date_key]["count"] += 1
			daily_usage[date_key]["discount"] += flt(usage.discount_amount)
		
		return {
			"success": True,
			"data": {
				"coupon": {
					"code": coupon.code,
					"offerType": coupon.offer_type or "coupon",
					"discountType": coupon.discount_type,
					"discountValue": flt(coupon.discount_value),
					"usageCount": coupon.usage_count or 0,
					"maxUses": coupon.max_uses,
					"isActive": coupon.is_active
				},
				"performance": {
					"totalRedemptions": len(usage_history),
					"uniqueCustomers": unique_customers,
					"avgRedemptionsPerCustomer": len(usage_history) / unique_customers if unique_customers > 0 else 0,
					"totalDiscountGiven": sum([flt(u.discount_amount) for u in usage_history]),
					"avgDiscountPerRedemption": sum([flt(u.discount_amount) for u in usage_history]) / len(usage_history) if usage_history else 0
				},
				"dailyTrend": [
					{
						"date": date,
						"count": data["count"],
						"discount": data["discount"]
					}
					for date, data in sorted(daily_usage.items())
				],
				"recentUsage": [
					{
						"date": str(u.usage_date),
						"discount": flt(u.discount_amount),
						"customer": u.customer,
						"order": u.order
					}
					for u in usage_history[:20]
				]
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_coupon_performance: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "PERFORMANCE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def log_event(restaurant_id, event_type, event_value=None, session_id=None, platform="web"):
	"""
	Logs a guest interaction event. Whitelisted for guests.
	"""
	try:
		# Ensure restaurant_id is lowercase slugs
		restaurant_id = restaurant_id.lower() if restaurant_id else restaurant_id
		
		if not restaurant_id or not event_type:
			return {"success": False, "message": "Missing required fields"}

		# Validate restaurant exists
		if not frappe.db.exists("Restaurant", restaurant_id):
			return {"success": False, "message": "Invalid restaurant"}

		doc = frappe.get_doc({
			"doctype": "Analytics Event",
			"restaurant": restaurant_id,
			"event_type": event_type,
			"event_value": event_value,
			"session_id": session_id or "anonymous",
			"platform": platform
		})
		doc.insert(ignore_permissions=True)

		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error in log_event: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_dashboard_summary(restaurant_id):
	"""
	Returns a tiered summary of analytics for the merchant dashboard.
	ALL values are computed from real data – no mocks, no Math.random().
	"""
	try:
		cache_key = f"dashboard_summary:{restaurant_id}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)
		# Ensure restaurant_id is lowercase (DocNames in Flamezo are lowercase slugs)
		restaurant_id = restaurant_id.lower() if restaurant_id else restaurant_id
		
		# Validate restaurant & check subscription tier
		restaurant = frappe.get_doc("Restaurant", restaurant_id)
		from flamezo_backend.flamezo.utils.feature_gate import get_restaurant_plan
		plan = get_restaurant_plan(restaurant_id)  # 'SILVER' or 'GOLD'

		end_date = add_days(today(), 1)
		start_date_7d = add_days(today(), -7)

		# ── 1. Traffic Stats (all tiers) ─────────────────────────────────────
		traffic_stats = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_views,
				COUNT(DISTINCT session_id) as unique_visitors
			FROM `tabAnalytics Event`
			WHERE restaurant = %s 
			AND event_type = 'menu_view'
			AND creation BETWEEN %s AND %s
		""", (restaurant_id, start_date_7d, end_date), as_dict=True)[0]

		# Growth vs previous 7d
		start_date_prev = add_days(start_date_7d, -7)
		prev_traffic = frappe.db.sql("""
			SELECT COUNT(*) as total_views
			FROM `tabAnalytics Event`
			WHERE restaurant = %s 
			AND event_type = 'menu_view'
			AND creation BETWEEN %s AND %s
		""", (restaurant_id, start_date_prev, start_date_7d), as_dict=True)[0]

		growth = 0
		if prev_traffic.total_views > 0:
			growth = ((traffic_stats.total_views - prev_traffic.total_views) / prev_traffic.total_views) * 100

		lifetime_scans = frappe.db.count("Analytics Event", {
			"restaurant": restaurant_id,
			"event_type": "menu_view"
		})

		summary = {
			"success": True,
			"tier": plan,
			"traffic": {
				"totalViews": traffic_stats.total_views,
				"uniqueVisitors": traffic_stats.unique_visitors,
				"growth": round(growth, 1),
				"lifetimeScans": lifetime_scans
			}
		}

		# ── 1.1 Peak Hour (real, from Analytics Events) ──────────────────────
		peak_hour_data = frappe.db.sql("""
			SELECT HOUR(creation) as hour, COUNT(*) as count
			FROM `tabAnalytics Event`
			WHERE restaurant = %s AND event_type = 'menu_view'
			AND creation BETWEEN %s AND %s
			GROUP BY hour ORDER BY count DESC LIMIT 1
		""", (restaurant_id, start_date_7d, end_date), as_dict=True)
		
		if peak_hour_data:
			h = peak_hour_data[0].hour
			am_pm = "AM" if h < 12 else "PM"
			display_h = h % 12 or 12
			summary["traffic"]["peakHour"] = f"{display_h} {am_pm}"
			summary["traffic"]["peakHourLabel"] = "Most busy time"

		# ── 1.2 Peak Day (real, from Order data — 7 days) ────────────────────
		# DAYNAME() returns 'Monday', 'Tuesday' etc. — real, not hardcoded.
		peak_day_data = frappe.db.sql("""
			SELECT DAYNAME(creation) as day_name, COUNT(*) as order_count
			FROM `tabOrder`
			WHERE restaurant = %s
			AND creation BETWEEN %s AND %s
			AND status NOT IN ('cancelled', 'pending_verification')
			GROUP BY DAYOFWEEK(creation), day_name
			ORDER BY order_count DESC
			LIMIT 1
		""", (restaurant_id, start_date_7d, end_date), as_dict=True)

		summary["traffic"]["peakDay"] = peak_day_data[0].day_name if peak_day_data else None
		summary["traffic"]["peakDayOrders"] = peak_day_data[0].order_count if peak_day_data else 0

		# ── 1.3 Top Category by Scans ─────────────────────────────────────────
		summary["traffic"]["topCategory"] = frappe.db.sql("""
			SELECT event_value, COUNT(*) as count
			FROM `tabAnalytics Event`
			WHERE restaurant = %s AND event_type = 'category_view'
			GROUP BY event_value ORDER BY count DESC LIMIT 1
		""", (restaurant_id,), as_dict=True)

		# ── 2. GOLD Features ──────────────────────────────────────────
		if plan == 'GOLD':
			# Order revenue stats
			order_stats = frappe.db.sql("""
				SELECT 
					COUNT(*) as total_orders,
					SUM(total) as revenue
				FROM `tabOrder`
				WHERE restaurant = %s
				AND creation BETWEEN %s AND %s
				AND status NOT IN ('cancelled', 'pending_verification')
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)[0]

			total_orders = order_stats.total_orders or 0
			revenue = flt(order_stats.revenue or 0)
			scans = traffic_stats.total_views or 1

			summary["enhanced"] = {
				"totalOrders": total_orders,
				"revenue": revenue,
				"conversionRate": round((total_orders / scans * 100), 2) if scans > 0 else 0,
				"avgOrderValue": round(revenue / total_orders, 2) if total_orders > 0 else 0,
			}

			# ── 2.1 Top Products — real order item counts (NOT Math.random) ──
			# Joins Order Items → Menu Product to get product_name and count sold.
			top_products_raw = frappe.db.sql("""
				SELECT 
					oi.product_name as item_name,
					COUNT(*) as order_count,
					SUM(oi.quantity) as total_qty,
					SUM(oi.total_price) as total_revenue
				FROM `tabOrder Item` oi
				INNER JOIN `tabOrder` o ON o.name = oi.parent
				WHERE o.restaurant = %s
				AND o.creation BETWEEN %s AND %s
				AND o.status NOT IN ('cancelled', 'pending_verification')
				GROUP BY oi.product_name
				ORDER BY order_count DESC
				LIMIT 8
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)

			# Fallback: if product_name is empty, use product (slug) as display name.
			# NOTE: oi.item_name does NOT exist in tabOrder Item — use only product_name or product.
			if not top_products_raw:
				top_products_raw = frappe.db.sql("""
					SELECT 
						COALESCE(oi.product_name, oi.product) as item_name,
						COUNT(*) as order_count,
						SUM(oi.quantity) as total_qty,
						SUM(oi.total_price) as total_revenue
					FROM `tabOrder Item` oi
					INNER JOIN `tabOrder` o ON o.name = oi.parent
					WHERE o.restaurant = %s
					AND o.creation BETWEEN %s AND %s
					GROUP BY item_name
					ORDER BY order_count DESC
					LIMIT 8
				""", (restaurant_id, start_date_7d, end_date), as_dict=True)

			summary["topPerformers"] = [
				{
					"item_name": row.item_name or "Unknown Item",
					"views": row.order_count,
					"order_count": row.order_count,
					"total_qty": row.total_qty,
					"total_revenue": flt(row.total_revenue),
				}
				for row in top_products_raw
			]

			# ── 2.2 Item Views — fallback if no order data available ─────────
			item_view_performers = frappe.db.sql("""
				SELECT 
					event_value as item_name,
					COUNT(*) as views
				FROM `tabAnalytics Event`
				WHERE restaurant = %s AND event_type = 'item_view'
				AND creation BETWEEN %s AND %s
				GROUP BY event_value
				ORDER BY views DESC
				LIMIT 8
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)

			# Prefer order-based; fall back to view-based if no orders yet
			if not summary["topPerformers"] and item_view_performers:
				summary["topPerformers"] = [
					{"item_name": r.item_name, "views": r.views, "order_count": 0,
					 "total_qty": 0, "total_revenue": 0.0}
					for r in item_view_performers
				]

			# ── 2.3 Churn Risk — real computation (prev 7d vs current 7d) ────
			prev_customers_raw = frappe.db.sql("""
				SELECT COUNT(DISTINCT COALESCE(platform_customer, customer_phone)) as cnt
				FROM `tabOrder`
				WHERE restaurant = %s
				AND creation BETWEEN %s AND %s
				AND status NOT IN ('cancelled', 'pending_verification')
			""", (restaurant_id, start_date_prev, start_date_7d), as_dict=True)

			curr_customers_raw = frappe.db.sql("""
				SELECT COUNT(DISTINCT COALESCE(platform_customer, customer_phone)) as cnt
				FROM `tabOrder`
				WHERE restaurant = %s
				AND creation BETWEEN %s AND %s
				AND status NOT IN ('cancelled', 'pending_verification')
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)

			prev_count = (prev_customers_raw[0].cnt or 0) if prev_customers_raw else 0
			curr_count = (curr_customers_raw[0].cnt or 0) if curr_customers_raw else 0

			if prev_count > 0:
				churn_rate = max(0, round((prev_count - curr_count) / prev_count * 100, 1))
			else:
				churn_rate = 0

			if churn_rate < 20:
				churn_label, churn_color = "Low", "emerald"
			elif churn_rate < 50:
				churn_label, churn_color = "Medium", "amber"
			else:
				churn_label, churn_color = "High", "rose"

			summary["enhanced"]["churnRate"] = churn_rate
			summary["enhanced"]["churnRiskLabel"] = churn_label
			summary["enhanced"]["churnRiskColor"] = churn_color

			# ── 2.4 Scan Efficiency (real conversion rate bucketed) ───────────
			conv = summary["enhanced"]["conversionRate"]
			if conv >= 10:
				scan_efficiency = "High"
			elif conv >= 3:
				scan_efficiency = "Medium"
			else:
				scan_efficiency = "Low"
			summary["enhanced"]["scanEfficiency"] = scan_efficiency

			# ── 2.5 Menu Heatmap (Views vs Orders) ───────────────────────────
			heatmap_raw = frappe.db.sql("""
				SELECT 
					v.item_name,
					v.views,
					COALESCE(o.orders, 0) as orders
				FROM (
					SELECT event_value as item_name, COUNT(*) as views
					FROM `tabAnalytics Event`
					WHERE restaurant = %s AND event_type = 'item_view'
					AND creation BETWEEN %s AND %s
					GROUP BY event_value
				) v
				LEFT JOIN (
					SELECT oi.product_name as item_name, COUNT(*) as orders
					FROM `tabOrder Item` oi
					INNER JOIN `tabOrder` ord ON ord.name = oi.parent
					WHERE ord.restaurant = %s
					AND ord.creation BETWEEN %s AND %s
					AND ord.status NOT IN ('cancelled', 'pending_verification')
					GROUP BY oi.product_name
				) o ON v.item_name = o.item_name
				ORDER BY v.views DESC
				LIMIT 10
			""", (restaurant_id, start_date_7d, end_date, restaurant_id, start_date_7d, end_date), as_dict=True)

			summary["menuHeatmap"] = []
			for row in heatmap_raw:
				views = row.views or 0
				orders = row.orders or 0
				item_conv = round((orders / views * 100), 1) if views > 0 else 0
				
				status = "Optimal"
				if views > 10 and item_conv < 5:
					status = "Check Price"
				elif views > 5 and item_conv == 0:
					status = "High Friction"

				summary["menuHeatmap"].append({
					"item_name": row.item_name,
					"views": views,
					"orders": orders,
					"conversion": item_conv,
					"status": status
				})

			# ── 2.6 QR ROAS (Revenue per Source) ─────────────────────────────
			qr_revenue_raw = frappe.db.sql("""
				SELECT 
					CASE 
						WHEN table_number IS NOT NULL AND table_number > 0 THEN 'Table QR'
						WHEN order_type = 'takeaway' THEN 'Takeaway QR'
						WHEN order_type = 'delivery' THEN 'Delivery QR'
						ELSE 'Entrance/General'
					END as source,
					SUM(total) as revenue,
					COUNT(*) as order_count
				FROM `tabOrder`
				WHERE restaurant = %s
				AND creation BETWEEN %s AND %s
				AND status NOT IN ('cancelled', 'pending_verification')
				GROUP BY source
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)
			
			social_revenue_raw = frappe.db.sql("""
				SELECT SUM(total) as revenue, COUNT(*) as orders
				FROM `tabOrder`
				WHERE restaurant = %s
				AND referral_link IS NOT NULL AND referral_link != ''
				AND creation BETWEEN %s AND %s
				AND status NOT IN ('cancelled', 'pending_verification')
			""", (restaurant_id, start_date_7d, end_date), as_dict=True)[0]
			
			summary["qrRoas"] = [
				{
					"source": r.source,
					"revenue": flt(r.revenue),
					"orders": r.order_count
				}
				for r in qr_revenue_raw
			]
			
			if social_revenue_raw.revenue:
				summary["qrRoas"].append({
					"source": "Social Media",
					"revenue": flt(social_revenue_raw.revenue),
					"orders": social_revenue_raw.orders
				})

		frappe.cache().set_value(cache_key, json.dumps(summary), expires_in_sec=300)
		return summary
	except Exception as e:
		frappe.log_error(f"Error in get_dashboard_summary: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_top_products(restaurant_id, days=7, limit=8):
	"""
	Standalone endpoint: top products by order count over the last N days.
	Returns real data from Order Items — no mocked values.
	"""
	try:
		restaurant_id = restaurant_id.lower() if restaurant_id else restaurant_id
		days = int(days) if days else 7
		limit = int(limit) if limit else 8

		end_date = add_days(today(), 1)
		start_date = add_days(today(), -days)

		# Primary: use product_name (human-readable, set by EC-17 migration)
		rows = frappe.db.sql("""
			SELECT 
				COALESCE(oi.product_name, oi.product) as item_name,
				COUNT(*) as order_count,
				SUM(oi.quantity) as total_qty,
				SUM(oi.total_price) as total_revenue
			FROM `tabOrder Item` oi
			INNER JOIN `tabOrder` o ON o.name = oi.parent
			WHERE o.restaurant = %s
			AND o.creation BETWEEN %s AND %s
			AND o.status NOT IN ('cancelled', 'pending_verification')
			GROUP BY item_name
			ORDER BY order_count DESC
			LIMIT %s
		""", (restaurant_id, start_date, end_date, limit), as_dict=True)

		return {
			"success": True,
			"data": [
				{
					"name": r.item_name or "Unknown",
					"count": r.order_count,
					"total": flt(r.total_revenue),
				}
				for r in rows
			]
		}
	except Exception as e:
		frappe.log_error(f"Error in get_top_products: {str(e)}")
		return {"success": False, "error": str(e)}
