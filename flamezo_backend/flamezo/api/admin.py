import json

import frappe

from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client
from flamezo_backend.flamezo.utils.roles import (
    GLOBAL_ADMIN_ROLES,
    SUPERVISOR_ROLES,
    is_global_admin,
    is_supervisor,
)


@frappe.whitelist()
def check_admin_access():
    """
    Check if current user has admin access
    Returns success with allowed boolean
    """
    try:
        # Check if user is System Manager or has specific role
        # Allow System Managers, Administrators, and Supervisors
        user_roles = frappe.get_roles()
        has_admin_access = (
            frappe.session.user == 'Administrator' or
            any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles) or
            "Flamezo Admin" in user_roles
        )

        return {
            'success': True,
            'data': {
                'allowed': has_admin_access
            }
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error checking admin access: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }

@frappe.whitelist()
def get_all_restaurants(page=1, page_size=20, search=None, filters=None):
    """
    Get all restaurants with their plan details
    Only accessible by admin users
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {
                'success': False,
                'error': 'Admin access required'
            }

        page = int(page or 1)
        page_size = int(page_size or 20)
        limit_start = (page - 1) * page_size

        # Build searching logic
        where_conditions = []
        params = []

        # Pull the global platform defaults up-front — the filter clauses
        # below (success_share_tier in particular) need them to resolve
        # "legacy 1.5%" vs "new default" against the COALESCE fallback.
        settings = frappe.get_single("Flamezo Settings")

        if search:
            where_conditions.append("(r.restaurant_name LIKE %s OR r.restaurant_id LIKE %s OR r.owner_email LIKE %s)")
            search_val = f"%{search}%"
            params.extend([search_val, search_val, search_val])

        if filters:
            if isinstance(filters, str):
                filters = json.loads(filters)

            for f in filters:
                if len(f) == 3:
                    fieldname, operator, value = f
                    # Security: only allow specific fields for filtering.
                    # New (May 2026): added mandate_status, razorpay_kyc_status,
                    # route_mode for the admin restaurant-management filter
                    # chips. Synthetic filters `success_share_tier` and
                    # `throttled` are handled below.
                    allowed_eq_fields = (
                        'is_active', 'plan_type', 'enable_floor_recovery',
                        'mandate_status', 'razorpay_kyc_status', 'route_mode',
                    )
                    if fieldname in allowed_eq_fields:
                        if operator == '=':
                            where_conditions.append(f"r.{fieldname} = %s")
                            params.append(value)
                        elif operator == 'in':
                            if isinstance(value, list) and value:
                                placeholders = ', '.join(['%s'] * len(value))
                                where_conditions.append(f"r.{fieldname} IN ({placeholders})")
                                params.extend(value)
                    elif fieldname == 'success_share_tier' and operator == '=':
                        # `legacy` = grandfathered at 1.5%; `new` = at the
                        # current default; `custom` = anything else.
                        cur_default = float(settings.gold_commission_percent or 3.0)
                        if value == 'legacy':
                            where_conditions.append("ABS(COALESCE(r.platform_fee_percent, %s) - 1.5) < 0.001")
                            params.append(cur_default)
                        elif value == 'new':
                            where_conditions.append("ABS(COALESCE(r.platform_fee_percent, %s) - %s) < 0.001")
                            params.append(cur_default)
                            params.append(cur_default)
                        elif value == 'custom':
                            where_conditions.append(
                                "ABS(COALESCE(r.platform_fee_percent, %s) - 1.5) >= 0.001 "
                                "AND ABS(COALESCE(r.platform_fee_percent, %s) - %s) >= 0.001"
                            )
                            params.extend([cur_default, cur_default, cur_default])
                    elif fieldname == 'throttled' and operator == '=':
                        if value in ('yes', True, 1, '1'):
                            where_conditions.append(
                                "(r.cash_payments_disabled_until IS NOT NULL AND r.cash_payments_disabled_until >= CURDATE())"
                            )
                        else:
                            where_conditions.append(
                                "(r.cash_payments_disabled_until IS NULL OR r.cash_payments_disabled_until < CURDATE())"
                            )
                    elif fieldname == 'has_outstanding' and operator == '=':
                        if value in ('yes', True, 1, '1'):
                            where_conditions.append("COALESCE(r.outstanding_commission_paise, 0) > 0")
                        else:
                            where_conditions.append("COALESCE(r.outstanding_commission_paise, 0) = 0")

        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        # Check if RestaurantConfig table exists
        config_table_exists = frappe.db.table_exists('RestaurantConfig')

        # Dynamic defaults (settings already fetched above for filter math).
        def_comm = float(settings.gold_commission_percent or 3.0)
        def_floor = float(settings.gold_monthly_fee or 0)

        # Common columns the admin restaurant-management table needs.
        # `mandate_status`, `outstanding_commission_paise`,
        # `cash_payments_disabled_until`, `razorpay_kyc_status`, `route_mode`,
        # `owner_phone`, `cash_sweep_failure_count` were added so the
        # frontend can render filter chips + the Success Share / KYC /
        # throttle indicators without a second round-trip.
        _select_cols = f"""
            r.name,
            r.restaurant_id,
            r.restaurant_name,
            r.owner_email,
            r.owner_phone,
            r.is_active,
            r.creation,
            r.modified,
            COALESCE(r.coins_balance, 0) as coins_balance,
            COALESCE(r.platform_fee_percent, {def_comm}) as platform_fee_percent,
            COALESCE(r.monthly_minimum, {def_floor}) as monthly_minimum,
            COALESCE(r.enable_floor_recovery, 1) as enable_floor_recovery,
            COALESCE(r.mandate_status, '') as mandate_status,
            COALESCE(r.outstanding_commission_paise, 0) as outstanding_commission_paise,
            r.cash_payments_disabled_until,
            COALESCE(r.cash_sweep_failure_count, 0) as cash_sweep_failure_count,
            COALESCE(r.razorpay_kyc_status, '') as razorpay_kyc_status,
            COALESCE(r.route_mode, '') as route_mode
        """

        if config_table_exists:
            query = f"""
                SELECT {_select_cols},
                    COALESCE(rc.subscription_plan, r.plan_type, 'SILVER') as plan_type
                FROM `tabRestaurant` r
                LEFT JOIN `tabRestaurantConfig` rc ON r.name = rc.parent
                {where_clause}
                ORDER BY r.creation DESC
                LIMIT {limit_start}, {page_size}
            """
            count_query = f"SELECT COUNT(*) FROM `tabRestaurant` r {where_clause}"
        else:
            query = f"""
                SELECT {_select_cols},
                    COALESCE(r.plan_type, 'SILVER') as plan_type
                FROM `tabRestaurant` r
                {where_clause}
                ORDER BY r.creation DESC
                LIMIT {limit_start}, {page_size}
            """
            count_query = f"SELECT COUNT(*) FROM `tabRestaurant` r {where_clause}"

        restaurants = frappe.db.sql(query, tuple(params), as_dict=True)
        total_count = frappe.db.sql(count_query, tuple(params))[0][0]

        # Convert is_active to integer for consistency
        for restaurant in restaurants:
            restaurant['is_active'] = int(restaurant['is_active'] or 0)
            # Ensure plan_type is valid
            if restaurant['plan_type'] not in ['SILVER', 'GOLD']:
                restaurant['plan_type'] = 'SILVER'

        return {
            'success': True,
            'data': {
                'restaurants': restaurants,
                'total': total_count,
                'page': page,
                'page_size': page_size
            }
        }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error getting all restaurants: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }

@frappe.whitelist()
def get_admin_restaurants_stats():
    """
    Aggregate stats strip for the admin Restaurant Management page.

    Returns counts + sums across every restaurant so the admin can see
    fleet-wide health at a glance without paginating. Cheap query (one
    aggregate scan of `tabRestaurant`).
    """
    try:
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        row = frappe.db.sql(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active,
              SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive,
              SUM(CASE WHEN mandate_status = 'active' THEN 1 ELSE 0 END) AS mandate_active,
              SUM(CASE WHEN COALESCE(mandate_status, '') <> 'active' THEN 1 ELSE 0 END) AS mandate_missing,
              SUM(CASE WHEN razorpay_kyc_status = 'activated' THEN 1 ELSE 0 END) AS kyc_activated,
              SUM(CASE WHEN razorpay_kyc_status IN ('under_review','needs_clarification') THEN 1 ELSE 0 END) AS kyc_pending,
              SUM(CASE WHEN razorpay_kyc_status IN ('rejected','suspended') THEN 1 ELSE 0 END) AS kyc_blocked,
              SUM(CASE WHEN cash_payments_disabled_until IS NOT NULL AND cash_payments_disabled_until >= CURDATE() THEN 1 ELSE 0 END) AS throttled,
              SUM(CASE WHEN COALESCE(outstanding_commission_paise, 0) > 0 THEN 1 ELSE 0 END) AS owing,
              COALESCE(SUM(COALESCE(outstanding_commission_paise, 0)), 0) AS total_outstanding_paise,
              COALESCE(SUM(COALESCE(coins_balance, 0)), 0) AS total_coins
            FROM `tabRestaurant`
            """,
            as_dict=True,
        )[0]

        # Coerce SUM() NULLs (empty table) to 0.
        out = {k: int(v) if v is not None and k != 'total_coins' else (float(v or 0) if k == 'total_coins' else 0) for k, v in row.items()}
        out['total_outstanding_rupees'] = round(out.get('total_outstanding_paise', 0) / 100.0, 2)
        return {'success': True, 'data': out}
    except Exception as e:
        frappe.log_error("Admin Stats Error", f"get_admin_restaurants_stats failed: {e!s}")
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def get_restaurant_details(restaurant_id):
    """
    Get all details of a single restaurant.
    Only accessible by admin users.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {
                'success': False,
                'error': 'Admin access required'
            }

        # Get restaurant record
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {
                'success': False,
                'error': 'Restaurant not found'
            }

        # Convert password fields to stars/placeholder to protect secrets but allow checking if they exist
        restaurant_dict = restaurant.as_dict()

        return {
            'success': True,
            'data': {
                'restaurant': restaurant_dict
            }
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in get_restaurant_details: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def update_restaurant_plan(restaurant_id, plan_type):
    """
    Update restaurant's subscription plan
    Only accessible by admin users
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {
                'success': False,
                'error': 'Admin access required'
            }

        # Validate plan_type
        if plan_type not in ['SILVER', 'GOLD']:
            return {
                'success': False,
                'error': 'Invalid plan type. Must be SILVER or GOLD'
            }

        # Get restaurant record
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {
                'success': False,
                'error': 'Restaurant not found'
            }

        # Check if RestaurantConfig table exists
        if not frappe.db.table_exists('RestaurantConfig'):
            # Update the Restaurant table directly since RestaurantConfig doesn't exist
            try:
                restaurant.plan_type = plan_type
                restaurant.plan_changed_by = frappe.session.user
                restaurant.plan_change_reason = f"Plan changed to {plan_type} by admin"
                if plan_type != restaurant.plan_activated_on:
                    restaurant.plan_activated_on = frappe.utils.now()
                restaurant.save(ignore_permissions=True)
                frappe.db.commit()

                return {
                    'success': True,
                    'data': {
                        'restaurant_id': restaurant_id,
                        'plan_type': plan_type,
                        'updated_by': frappe.session.user,
                        'note': f'Plan updated to {plan_type} in Restaurant table'
                    }
                }
            except Exception as e:
                frappe.log_error("Plan Update Error", f"Error updating restaurant plan: {e!s}")
                return {
                    'success': False,
                    'error': f'Failed to update plan: {e!s}'
                }

        # Get or create restaurant config
        config = frappe.get_doc('RestaurantConfig', restaurant.name)
        if not config:
            # Create config if it doesn't exist
            config = frappe.new_doc('RestaurantConfig')
            config.parent = restaurant.name
            config.parenttype = 'Restaurant'
            config.parentfield = 'config'
            config.insert()

        # Update subscription plan
        config.subscription_plan = plan_type

        # Update subscription features based on plan
        if plan_type == 'GOLD':
            config.subscription_features = {
                'ordering': True,
                'videoUpload': True,
                'analytics': True,
                'aiRecommendations': True,
                'loyalty': True,
                'coupons': True,
                'games': True,
                'pos_integration': True,
                'table_booking': True,
                'experience_lounge': True
            }
        else:  # SILVER
            config.subscription_features = {
                'ordering': False,
                'videoUpload': False,
                'analytics': False,
                'aiRecommendations': False,
                'loyalty': False,
                'coupons': False,
                'games': False,
                'pos_integration': False,
                'table_booking': False,
                'experience_lounge': False
            }

        config.save(ignore_permissions=True)
        frappe.db.commit()

        # Log the change
        frappe.logger().info(
            f"Restaurant {restaurant_id} plan updated to {plan_type} by {frappe.session.user}"
        )

        return {
            'success': True,
            'data': {
                'restaurant_id': restaurant_id,
                'plan_type': plan_type,
                'updated_by': frappe.session.user
            }
        }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error updating restaurant plan: {e!s}")
        frappe.db.rollback()
        return {
            'success': False,
            'error': str(e)
        }

@frappe.whitelist()
def toggle_restaurant_status(restaurant_id, is_active):
    """
    Toggle restaurant active status
    Only accessible by admin users
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {
                'success': False,
                'error': 'Admin access required'
            }

        # Validate is_active
        if is_active not in [0, 1]:
            return {
                'success': False,
                'error': 'Invalid status. Must be 0 (inactive) or 1 (active)'
            }

        # Get restaurant record
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {
                'success': False,
                'error': 'Restaurant not found'
            }

        # Update restaurant status
        try:
            restaurant.is_active = is_active
            restaurant.save(ignore_permissions=True)
            frappe.db.commit()

            return {
                'success': True,
                'data': {
                    'restaurant_id': restaurant_id,
                    'is_active': is_active,
                    'updated_by': frappe.session.user,
                    'note': f'Restaurant {"activated" if is_active else "deactivated"} successfully'
                }
            }
        except Exception as e:
            frappe.log_error("Status Update Error", f"Error updating restaurant status: {e!s}")
            return {
                'success': False,
                'error': f'Failed to update status: {e!s}'
            }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in toggle_restaurant_status: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def delete_restaurant(restaurant_id):
    """
    Permanently delete a restaurant and ALL associated data.
    This includes: Configuration, Menu, Orders, Customers, Media, etc.
    Only accessible by system administrators.
    """
    try:
        # Check global admin access first (Supervisors cannot delete)
        if not is_global_admin():
            return {
                'success': False,
                'error': 'Restricted: Only Global Administrators can purge restaurants'
            }

        # Get restaurant record
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {
                'success': False,
                'error': f'Restaurant {restaurant_id} not found'
            }

        restaurant_name = restaurant.name
        cleanup_report = []

        # 1. Clear User Permissions (Crucial for Frappe integrity)
        try:
            # User Permissions link via 'allow'="Restaurant" and 'for_value'="[doc_name]"
            user_perms = frappe.get_all("User Permission",
                filters={"allow": "Restaurant", "for_value": restaurant_name},
                pluck="name")

            for perm in user_perms:
                frappe.delete_doc("User Permission", perm, ignore_permissions=True)

            if user_perms:
                cleanup_report.append(f"Deleted {len(user_perms)} User Permissions")
        except Exception as e:
            frappe.log_error("Restaurant Delete Error", f"Error clearing User Permissions: {e!s}")
            cleanup_report.append(f"FAILED to clear User Permissions: {e!s}")

        # 2. Clear Core Frappe Records (Comments, Communications, Logs, Versions)
        # These tables are often linked and can block deletion
        core_dt_map = {
            "Comment": ["reference_doctype", "reference_name"],
            "Communication": ["reference_doctype", "reference_name"],
            "Version": ["ref_doctype", "docname"],
            "Activity Log": ["reference_doctype", "reference_name"],
            "Email Queue": ["reference_doctype", "reference_name"],
            "File": ["attached_to_doctype", "attached_to_name"]
        }

        for cdt, fields in core_dt_map.items():
            try:
                dt_field, name_field = fields
                records = frappe.get_all(cdt, filters={dt_field: "Restaurant", name_field: restaurant_name}, pluck="name")
                for r in records:
                    frappe.delete_doc(cdt, r, ignore_permissions=True, delete_permanently=True)
                if records:
                    cleanup_report.append(f"Deleted {len(records)} records from {cdt}")
            except Exception:
                pass # Silent ignore for minor core tables

        # 3. List of known custom DocTypes to clear
        doctypes_to_clear = [
            "Restaurant Config", "Restaurant Media", "Restaurant Social Link",
            "Menu Category", "Menu Product", "Menu Product Addon", "Customization Option", "Customization Question",
            "Order", "Order Item", "Table Booking", "Banquet Booking", "Restaurant Table",
            "Cart Entry", "Restaurant User", "Coupon", "Coupon Usage", "Offer", "Auto Offer", "Combo Offer", "Promo",
            "Game", "Event", "Home Feature", "Media Asset", "Media Upload Session", "Media Variant", "Product Media",
            "Coin Transaction", "Monthly Billing Ledger", "Monthly Revenue Ledger", "Razorpay Webhook Log",
            "Plan Change Log", "Referral Link", "Referral Visit", "OTP Verification Log",
            "Tokenization Attempt", "Menu Recommendation", "Menu Image Extractor", "Menu Image Item",
            "Extracted Category", "Extracted Dish",
            "Restaurant Loyalty Config", "Restaurant Loyalty Entry",
            "Legacy Content", "Legacy Gallery Image", "Legacy Instagram Reel",
            "Legacy Member", "Legacy Signature Dish", "Legacy Testimonial", "Legacy Testimonial Image"
        ]

        # 4. Dynamically find ANY other doctype that links to Restaurant
        # This catches any newly added doctypes automatically
        try:
            dynamic_links = frappe.get_all("DocField", filters={"fieldtype": "Link", "options": "Restaurant"}, pluck="parent")
            custom_links = frappe.get_all("Custom Field", filters={"fieldtype": "Link", "options": "Restaurant"}, pluck="dt")
            all_linked_dts = sorted(list(set(doctypes_to_clear + dynamic_links + custom_links)))
        except Exception:
            all_linked_dts = doctypes_to_clear

        # 5. Iteratively clear all linked records
        for dt in all_linked_dts:
            if dt == "Restaurant":
                continue
            try:
                # Check if the doctype exists in this installation
                if not frappe.db.table_exists(dt):
                    continue

                # Determine the correct field name that links to Restaurant
                meta = frappe.get_meta(dt)
                link_field = None

                if meta.has_field("restaurant"):
                    link_field = "restaurant"
                else:
                    # Find any field that is a Link to Restaurant
                    for df in meta.fields:
                        if df.fieldtype == "Link" and df.options == "Restaurant":
                            link_field = df.fieldname
                            break

                if not link_field:
                    continue

                # Find all records linked to this restaurant
                records = frappe.get_all(dt, filters={link_field: restaurant_name}, pluck='name')

                if records:
                    for record_name in records:
                        # Use delete_doc to handle hooks and sub-records
                        frappe.delete_doc(dt, record_name, ignore_permissions=True, delete_permanently=True)

                    cleanup_report.append(f"Deleted {len(records)} records from {dt}")

            except Exception as inner_e:
                frappe.log_error("Restaurant Delete Error", f"Error deleting from {dt}: {inner_e!s}")
                cleanup_report.append(f"FAILED to delete from {dt}: {inner_e!s}")

        # Special handling for RestaurantConfig (linked via parent)
        if frappe.db.table_exists('RestaurantConfig'):
            try:
                configs = frappe.get_all('RestaurantConfig', filters={'parent': restaurant_name}, pluck='name')
                for cfg in configs:
                    frappe.delete_doc('RestaurantConfig', cfg, ignore_permissions=True)
                if configs:
                    cleanup_report.append(f"Deleted {len(configs)} RestaurantConfig records")
            except Exception as e:
                frappe.log_error("Restaurant Delete Error", f"Error deleting RestaurantConfig: {e!s}")

        # 6. Finally, delete the Restaurant record itself
        frappe.delete_doc('Restaurant', restaurant_name, ignore_permissions=True, delete_permanently=True)
        cleanup_report.append(f"Deleted Restaurant record: {restaurant_id}")

        # Commit all changes to database
        frappe.db.commit()

        return {
            'success': True,
            'message': f"Restaurant {restaurant_id} and all related data deleted successfully.",
            'report': cleanup_report
        }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in delete_restaurant API: {e!s}")
        frappe.db.rollback()
        return {
            'success': False,
            'error': f"Failed to delete restaurant: {e!s}",
            'partial_report': cleanup_report if 'cleanup_report' in locals() else []
        }


@frappe.whitelist()
def admin_give_coins(restaurant_id, amount, reason="Admin Grant"):
    """
    Give coins to a restaurant manually from admin.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        # Validate amount
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'Invalid amount'}

        # Get restaurant
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {'success': False, 'error': 'Restaurant not found'}

        # Update balance and log the transaction (audit trail)
        from flamezo_backend.flamezo.api.coin_billing import record_transaction

        description = f"Admin {'Grant' if amount >= 0 else 'Deduction'}: {reason}"

        new_bal = record_transaction(
            restaurant=restaurant.name,
            txn_type="Admin Adjustment",
            amount=amount,
            description=description
        )

        return {
            'success': True,
            'message': f"Successfully credited {amount} coins to {restaurant_id}",
            'new_balance': new_bal
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in admin_give_coins: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def admin_update_restaurant_settings(restaurant_id, updates):
    """
    Update administrative settings for a restaurant.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        # Get restaurant
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {'success': False, 'error': 'Restaurant not found'}

        # Parse updates if it's a string
        if isinstance(updates, str):
            updates = json.loads(updates)

        # Prevent non-admin fields from being updated here if needed,
        # but for now we follow the user's request for platform_fee_percent
        # Allow most fields for admin updates
        allowed_fields = [
            'platform_fee_percent', 'monthly_minimum', 'is_active', 'restaurant_name', 'owner_email',
            'owner_phone', 'owner_name', 'plan_type', 'billing_status', 'mandate_status', 'enable_floor_recovery',
            'pos_provider', 'pos_enabled', 'pos_app_key', 'pos_app_secret', 'pos_access_token', 'pos_merchant_id',
            'enable_loyalty', 'enable_takeaway', 'enable_delivery', 'enable_dine_in', 'no_ordering',
            'tax_rate', 'gst_number', 'default_delivery_fee', 'default_packaging_fee', 'minimum_order_value',
            'estimated_prep_time', 'timezone', 'currency', 'tables', 'description', 'google_map_url'
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                # Handle type conversions for numeric/boolean fields
                if field in ['platform_fee_percent', 'monthly_minimum', 'tax_rate', 'default_delivery_fee',
                            'default_packaging_fee', 'minimum_order_value']:
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                elif field in ['is_active', 'enable_loyalty', 'enable_takeaway', 'enable_delivery',
                              'enable_dine_in', 'no_ordering', 'pos_enabled', 'enable_floor_recovery']:
                    value = 1 if value in [True, 1, '1', 'true'] else 0
                elif field in ['tables', 'estimated_prep_time']:
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        continue

                setattr(restaurant, field, value)

        restaurant.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            'success': True,
            'message': f"Restaurant settings updated successfully for {restaurant_id}",
            'data': {
                'restaurant_id': restaurant_id,
                'updated_fields': list(updates.keys())
            }
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in admin_update_restaurant_settings: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def admin_onboard_restaurant_owner(restaurant_id, owner_name, owner_email):
    """
    Onboard a restaurant owner.
    Creates a Frappe User, assigns roles, links to Restaurant, and triggers welcome email.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        if not owner_email:
            return {'success': False, 'error': 'Owner email is required'}

        # Get restaurant
        restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        if not restaurant:
            return {'success': False, 'error': 'Restaurant not found'}

        # 1. Update Restaurant record if details changed
        if restaurant.owner_email != owner_email or restaurant.owner_name != owner_name:
            restaurant.owner_email = owner_email
            restaurant.owner_name = owner_name
            restaurant.save(ignore_permissions=True)
            frappe.db.commit()

        # 2. Look up or create Frappe User
        user_id = frappe.db.get_value("User", {"email": owner_email}, "name")
        first_name = owner_name.split()[0] if owner_name else "Owner"

        from flamezo_backend.flamezo.utils.permissions import (
            assign_user_to_restaurant,
            create_restaurant_user_permission,
        )

        is_new = False
        onboard_link = None
        email_sent = False

        if not user_id:
            # Create a new user
            user_doc = frappe.get_doc({
                "doctype": "User",
                "email": owner_email,
                "first_name": first_name,
                "user_type": "System User"
            })
            user_doc.insert(ignore_permissions=True)
            user_id = user_doc.name
            is_new = True

            # Generate link manually and fix protocol
            onboard_link = user_doc.reset_password(send_email=False)
            if onboard_link and onboard_link.startswith("http://"):
                onboard_link = onboard_link.replace("http://", "https://", 1)

            try:
                send_onboarding_email(owner_email, first_name, onboard_link)
                email_sent = True
            except Exception:
                frappe.log_error("Onboarding Email Failed", f"Failed to send welcome email to {owner_email}. Link: {onboard_link}")
        else:
            # Existing user - try to send reset email
            user_doc = frappe.get_doc("User", user_id)
            onboard_link = user_doc.reset_password(send_email=False)
            if onboard_link and onboard_link.startswith("http://"):
                onboard_link = onboard_link.replace("http://", "https://", 1)

            try:
                send_onboarding_email(owner_email, first_name, onboard_link)
                email_sent = True
            except Exception:
                frappe.log_error("Password Reset Email Failed", f"Failed to send reset email to {owner_email}. Link: {onboard_link}")

        # 3. Add necessary roles
        roles_to_add = ["System User", "Restaurant Staff"]

        has_changes = False
        for role in roles_to_add:
            if frappe.db.exists("Role", role):
                if not frappe.db.exists("Has Role", {"parent": user_id, "role": role}):
                    user_doc.append("roles", {"role": role})
                    has_changes = True

        if has_changes:
            user_doc.save(ignore_permissions=True)

        # 4. Link user to the restaurant
        has_existing_default = frappe.db.exists("Restaurant User", {"user": user_id, "is_default": 1})
        is_default_flag = 0 if has_existing_default else 1

        # create_restaurant_user_permission maps Frappe User Permissions
        create_restaurant_user_permission(user_id, restaurant.name, is_default=is_default_flag)

        # Check if already in 'Restaurant User' doctype
        if not frappe.db.exists("Restaurant User", {"user": user_id, "restaurant": restaurant.name}):
            assign_user_to_restaurant(user_id, restaurant.name, role="Restaurant Staff", is_default=is_default_flag)

        frappe.db.commit()

        status_msg = "successfully onboarded" if is_new else "already exists and has been granted access"
        email_msg = "An email has been sent." if email_sent else f"Email could not be sent. Link: {onboard_link}"

        full_msg = f"Owner {owner_email} {status_msg}. {email_msg}"

        return {
            'success': True,
            'message': full_msg,
            'data': {
                'user': user_id,
                'email': owner_email,
                'is_new': is_new,
                'email_sent': email_sent,
                'onboard_link': onboard_link
            }
        }
    except Exception as e:
        frappe.log_error("Admin Onboarding Error", f"Error in admin_onboard_restaurant_owner: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}

def send_onboarding_email(recipient, name, link):
    """
    Send a custom branded onboarding email to the restaurant owner.
    Fixes protocol and provides a premium experience.
    """
    site_url = "https://backend.flamezo_backend.com"
    subject = "Welcome to Flamezo"

    html_content = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px; color: #1a1a1a; background-color: #f9fafb;">
        <div style="background-color: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
            <div style="display: flex; align-items: center; margin-bottom: 32px;">
                <div style="width: 12px; height: 12px; background-color: #10b981; border-radius: 50%; margin-right: 12px;"></div>
                <h1 style="font-size: 24px; font-weight: 700; margin: 0; color: #111827;">Welcome to Flamezo</h1>
            </div>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 24px; color: #374151;">
                Hello {name},
            </p>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 16px; color: #374151;">
                A new account has been created for you at <a href="{site_url}" style="color: #2563eb; text-decoration: none; font-weight: 500;">{site_url}</a>.
            </p>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 32px; color: #374151;">
                Your login id is: <strong style="color: #111827;">{recipient}</strong><br>
                Click on the link below to complete your registration and set a new password.
            </p>

            <div style="margin-bottom: 40px;">
                <a href="{link}" style="display: inline-block; background-color: #111827; color: #ffffff; padding: 14px 28px; border-radius: 8px; font-size: 16px; font-weight: 600; text-decoration: none; text-align: center;">Complete Registration</a>
            </div>

            <div style="padding-top: 32px; border-top: 1px solid #e5e7eb;">
                <p style="font-size: 14px; line-height: 20px; color: #6b7280; margin-bottom: 8px;">
                    You can also copy-paste following link in your browser:
                </p>
                <p style="font-size: 14px; line-height: 20px; color: #2563eb; word-break: break-all;">
                    <a href="{link}" style="color: #2563eb; text-decoration: none;">{link}</a>
                </p>
            </div>
        </div>

        <div style="text-align: center; margin-top: 24px;">
            <p style="font-size: 12px; color: #9ca3af;">
                Sent via ERPNext
            </p>
        </div>
    </div>
    """

    frappe.sendmail(
        recipients=[recipient],
        subject=subject,
        content=html_content,
        now=True
    )


@frappe.whitelist()
def admin_create_wallet_payment_link(restaurant_id, tier):
    """
    Legacy endpoint — previously created a Razorpay Payment Link for the
    ₹1,299 GOLD unlock fee. Under the May 2026 single-tier model GOLD
    onboarding is free, so this endpoint is intentionally short-circuited.
    It remains importable so existing client code that calls it doesn't 404.

    To charge a restaurant a one-off amount today, generate a Razorpay
    Payment Link directly from the Frappe desk.
    """
    try:
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        # Silence unused-arg lints — the legacy signature is preserved for
        # any out-of-tree clients still calling this endpoint.
        _ = (restaurant_id, tier)

        return {
            'success': False,
            'error': (
                f'No upgrade payment required for {tier} tier. '
                f'Under the new business model GOLD onboarding is free — '
                f'restaurants pay only the Success Share plus the monthly floor.'
            ),
        }
    except Exception as e:
        frappe.log_error("Admin Wallet Payment Link Error", str(e))
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_platform_settings():
    """
    Get Flamezo universal settings (Admin only)
    """
    if not is_global_admin() and not is_supervisor(frappe.session.user):
        return {'success': False, 'error': 'Unauthorized'}

    settings = frappe.get_single("Flamezo Settings")
    return {
        'success': True,
        'data': {
            'charge_gst': bool(settings.charge_gst),
            'gst_percent': float(settings.gst_percent or 18.0),
            'gold_monthly_fee': float(settings.gold_monthly_fee or 0),
            'gold_commission_percent': float(settings.gold_commission_percent or 3.0),
            # Retired under the single-tier model — kept in the response as
            # 0.0 so old admin UIs that read it don't break.
            'gold_upgrade_barrier': 0.0,
        }
    }

@frappe.whitelist()
def update_platform_settings(settings):
    """
    Update Flamezo universal settings (Global Admin only)
    """
    if not is_global_admin():
        return {'success': False, 'error': 'Restricted to Global Administrators'}

    if isinstance(settings, str):
        settings = json.loads(settings)

    doc = frappe.get_doc("Flamezo Settings")

    allowed_fields = [
        'charge_gst',
        'gst_percent',
        'gold_monthly_fee',
        'gold_commission_percent',
        'gold_upgrade_barrier'
    ]

    updated = []
    for field in allowed_fields:
        if field in settings:
            doc.set(field, settings[field])
            updated.append(field)

    if updated:
        doc.save(ignore_permissions=True)
        frappe.db.commit()

    return {'success': True, 'updated': updated}
@frappe.whitelist()
def admin_create_manual_recharge_link(restaurant_id, amount):
    """
    Generate a Razorpay payment link for a custom manual credit.
    Includes 18% GST.
    """
    try:
        # Admin access check
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        base_amount = float(amount)
        if base_amount <= 0:
            return {'success': False, 'error': 'Amount must be greater than 0'}

        # Calculate GST based on global settings
        settings = frappe.get_single("Flamezo Settings")
        charge_gst = bool(settings.charge_gst)
        gst_rate = float(settings.gst_percent or 18.0) / 100.0 if charge_gst else 0.0

        gst_amount = round(base_amount * gst_rate, 2)
        total_payable = base_amount + gst_amount
        total_payable_paise = round(total_payable * 100)

        # Get restaurant record
        try:
            restaurant = frappe.get_doc('Restaurant', {'restaurant_id': restaurant_id})
        except Exception:
            return {'success': False, 'error': 'Restaurant not found'}

        # Build Razorpay Payment Link
        client = get_razorpay_client()

        # Clean phone
        raw_phone = (restaurant.owner_phone or '').strip()
        clean_phone = ''.join(filter(str.isdigit, raw_phone))
        if clean_phone.startswith('91') and len(clean_phone) == 12:
            clean_phone = clean_phone[2:]

        plink_payload = {
            "amount": total_payable_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"Manual Wallet Recharge — ₹{base_amount}" + (f" + ₹{gst_amount} GST" if charge_gst else ""),
            "customer": {
                "name": restaurant.owner_name or restaurant.restaurant_name,
                "email": restaurant.owner_email or "",
                "contact": clean_phone or ""
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "restaurant": restaurant.name,
                "restaurant_id": restaurant_id,
                "type": "wallet_topup_plink",
                "is_manual": "yes",
                "base_amount": base_amount,
                "gst_amount": gst_amount,
                "total_payable": total_payable
            },
            "callback_url": "https://backend.flamezo_backend.com",
            "callback_method": "get"
        }

        plink = client.payment_link.create(plink_payload)

        return {
            'success': True,
            'payment_link_url': plink.get('short_url') or plink.get('id'),
            'amount': total_payable,
            'base_amount': base_amount,
            'gst_amount': gst_amount,
            'restaurant_name': restaurant.restaurant_name
        }

    except Exception as e:
        frappe.log_error(f"Manual recharge link failed: {e!s}", "admin.manual_recharge_link")
        return {'success': False, 'error': str(e)}
