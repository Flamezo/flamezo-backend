import json

import frappe
from frappe.utils import now_datetime

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
def get_all_outlets(page=1, page_size=20, search=None, filters=None):
    """
    Get all outlets with their plan details
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
            where_conditions.append("(r.outlet_name LIKE %s OR r.outlet_id LIKE %s OR r.owner_email LIKE %s)")
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
                        'is_active', 'outlet_type',
                        'mandate_status', 'razorpay_kyc_status', 'route_mode',
                        'branch_group',
                    )
                    if fieldname == 'is_signature' and operator == '=' and str(value) in ('1', 'yes', 'true'):
                        # Signature = the flag is set OR the merchant sits at the
                        # 11% signature rate (typing 11% auto-activates Signature,
                        # so legacy 11% rows are treated as Signature too).
                        where_conditions.append(
                            "(COALESCE(r.is_signature, 0) = 1 "
                            "OR ABS(COALESCE(r.platform_fee_percent, 0) - 11) < 0.001)"
                        )
                    elif fieldname == 'is_signature' and operator == '=' and str(value) in ('0', 'no', 'false'):
                        # Normal = the exact inverse of Signature above.
                        where_conditions.append(
                            "(COALESCE(r.is_signature, 0) = 0 "
                            "AND ABS(COALESCE(r.platform_fee_percent, 0) - 11) >= 0.001)"
                        )
                    elif fieldname in allowed_eq_fields:
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
            r.outlet_id as outlet_id,
            r.outlet_name as outlet_name,
            r.owner_email,
            r.owner_phone,
            r.is_active,
            r.creation,
            r.modified,
            COALESCE(r.coins_balance, 0) as coins_balance,
            COALESCE(r.platform_fee_percent, {def_comm}) as platform_fee_percent,
            COALESCE(r.mandate_status, '') as mandate_status,
            COALESCE(r.outstanding_commission_paise, 0) as outstanding_commission_paise,
            r.cash_payments_disabled_until,
            COALESCE(r.cash_sweep_failure_count, 0) as cash_sweep_failure_count,
            COALESCE(r.razorpay_kyc_status, '') as razorpay_kyc_status,
            COALESCE(r.route_mode, '') as route_mode,
            COALESCE(r.is_signature, 0) as is_signature,
            COALESCE(r.is_featured, 0) as is_featured,
            r.limelight_start_date,
            r.limelight_end_date,
            COALESCE(r.outlet_type, 'dining') as outlet_type
        """

        if config_table_exists:
            query = f"""
                SELECT {_select_cols}
                FROM `tabOutlet` r
                LEFT JOIN `tabRestaurantConfig` rc ON r.name = rc.parent
                {where_clause}
                ORDER BY r.creation DESC
                LIMIT {limit_start}, {page_size}
            """
            count_query = f"SELECT COUNT(*) FROM `tabOutlet` r {where_clause}"
        else:
            query = f"""
                SELECT {_select_cols}
                FROM `tabOutlet` r
                {where_clause}
                ORDER BY r.creation DESC
                LIMIT {limit_start}, {page_size}
            """
            count_query = f"SELECT COUNT(*) FROM `tabOutlet` r {where_clause}"

        restaurants = frappe.db.sql(query, tuple(params), as_dict=True)
        total_count = frappe.db.sql(count_query, tuple(params))[0][0]

        # Convert is_active to integer for consistency
        for restaurant in restaurants:
            restaurant['is_active'] = int(restaurant['is_active'] or 0)
            restaurant['plan_type'] = 'GOLD'  # defaulted

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
def get_admin_outlets_stats():
    """
    Aggregate stats strip for the admin Outlet Management page.

    Returns counts + sums across every outlet so the admin can see
    fleet-wide health at a glance without paginating. Cheap query (one
    aggregate scan of `tabOutlet`).
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
            FROM `tabOutlet`
            """,
            as_dict=True,
        )[0]

        # Coerce SUM() NULLs (empty table) to 0.
        out = {k: int(v) if v is not None and k != 'total_coins' else (float(v or 0) if k == 'total_coins' else 0) for k, v in row.items()}
        out['total_outstanding_rupees'] = round(out.get('total_outstanding_paise', 0) / 100.0, 2)
        return {'success': True, 'data': out}
    except Exception as e:
        frappe.log_error("Admin Stats Error", f"get_admin_outlets_stats failed: {e!s}")
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def get_outlet_details(outlet_id):
    """
    Get all details of a single outlet.
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
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {
                'success': False,
                'error': 'Outlet not found'
            }

        restaurant_dict = restaurant.as_dict()
        # Password fields come back as None from as_dict() — read the decrypted value explicitly.
        try:
            restaurant_dict['onboarding_password'] = restaurant.get_password('onboarding_password') or None
        except Exception:
            restaurant_dict['onboarding_password'] = None

        return {
            'success': True,
            'data': {
                'restaurant': restaurant_dict
            }
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in get_outlet_details: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }


# Deprecated: update_outlet_plan removed as plan_type is no longer used
def update_outlet_plan(outlet_id, plan_type):
    return {
        'success': False,
        'error': 'Plan updates are deprecated. All outlets use the default GOLD plan.'
    }

@frappe.whitelist()
def toggle_outlet_status(outlet_id, is_active):
    """
    Toggle outlet active status
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
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {
                'success': False,
                'error': 'Outlet not found'
            }

        # Update restaurant status
        try:
            restaurant.is_active = is_active
            restaurant.save(ignore_permissions=True)
            frappe.db.commit()

            return {
                'success': True,
                'data': {
                    'outlet_id': outlet_id,
                    'is_active': is_active,
                    'updated_by': frappe.session.user,
                    'note': f'Outlet {"activated" if is_active else "deactivated"} successfully'
                }
            }
        except Exception as e:
            frappe.log_error("Status Update Error", f"Error updating restaurant status: {e!s}")
            return {
                'success': False,
                'error': f'Failed to update status: {e!s}'
            }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in toggle_outlet_status: {e!s}")
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def delete_outlet(outlet_id):
    """
    Permanently delete an outlet and ALL associated data.
    This includes: Configuration, Menu, Orders, Customers, Media, etc.
    Only accessible by system administrators.
    """
    try:
        # Check global admin access first (Supervisors cannot delete)
        if not is_global_admin():
            return {
                'success': False,
                'error': 'Restricted: Only Global Administrators can purge outlets'
            }

        # Get restaurant record
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {
                'success': False,
                'error': f'Outlet {outlet_id} not found'
            }

        restaurant_name = restaurant.name
        cleanup_report = []

        # 1. Clear User Permissions (Crucial for Frappe integrity)
        try:
            # User Permissions link via 'allow'="Outlet" and 'for_value'="[doc_name]"
            user_perms = frappe.get_all("User Permission",
                filters={"allow": "Outlet", "for_value": restaurant_name},
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
                records = frappe.get_all(cdt, filters={dt_field: "Outlet", name_field: restaurant_name}, pluck="name")
                for r in records:
                    frappe.delete_doc(cdt, r, ignore_permissions=True, delete_permanently=True)
                if records:
                    cleanup_report.append(f"Deleted {len(records)} records from {cdt}")
            except Exception:
                pass # Silent ignore for minor core tables

        # 3. Explicit deletion order — children before parents to avoid FK violations.
        #
        # Key constraints:
        #   Menu Product Addon / Customization* → before Menu Product
        #   Menu Product                        → before Media Asset (Menu Product references it)
        #   Menu Image Item / Extracted*        → before Menu Image Extractor
        #   Menu Image Extractor                → before Restaurant
        #   Media Variant / Product Media       → before Media Asset
        #   Media Asset                         → before Restaurant
        #   Order Item                          → before Order
        #   Coupon Usage                        → before Coupon
        DELETION_ORDER = [
            # Level 0: pure leaf nodes
            "Menu Product Addon", "Customization Option", "Customization Question",
            "Order Item", "Coupon Usage",
            "Menu Image Item", "Extracted Category", "Extracted Dish",
            "Media Variant", "Product Media",
            "Referral Visit",
            "Legacy Gallery Image", "Legacy Instagram Reel", "Legacy Member",
            "Legacy Signature Dish", "Legacy Testimonial Image", "Legacy Testimonial",
            # Level 1: reference leaf nodes or other intermediates
            "Menu Product",          # references Media Asset — must precede it
            "Menu Recommendation",
            "Menu Image Extractor",  # references Restaurant — must precede deletion
            # Level 2: now safe (no longer referenced)
            "Media Asset", "Media Upload Session",
            "Menu Category",
            # Level 3: remaining restaurant-linked docs
            "Outlet Config", "Restaurant Media", "Restaurant Social Link",
            "Outlet Table", "Table Booking", "Banquet Booking",
            "Order",
            "Outlet User",
            "Coupon", "Offer", "Auto Offer", "Combo Offer", "Promo",
            "Game", "Event", "Home Feature",
            "Coin Transaction", "Monthly Billing Ledger", "Monthly Revenue Ledger",
            "Razorpay Webhook Log", "Plan Change Log",
            "Referral Link", "OTP Verification Log", "Tokenization Attempt",
            "Outlet Loyalty Config", "Outlet Loyalty Entry",
            "Legacy Content",
        ]

        # 4. Append any newly-added doctypes discovered dynamically (placed after known deps).
        try:
            dynamic_links = frappe.get_all("DocField", filters={"fieldtype": "Link", "options": "Outlet"}, pluck="parent")
            custom_links = frappe.get_all("Custom Field", filters={"fieldtype": "Link", "options": "Outlet"}, pluck="dt")
            known = set(DELETION_ORDER)
            extra = [dt for dt in (dynamic_links + custom_links) if dt not in known and dt != "Outlet"]
            all_linked_dts = DELETION_ORDER + extra
        except Exception:
            all_linked_dts = DELETION_ORDER

        # 5. Delete in dependency order
        for dt in all_linked_dts:
            if dt == "Outlet":
                continue
            try:
                # Check if the doctype exists in this installation
                if not frappe.db.table_exists(dt):
                    continue

                # Determine the correct field name that links to Restaurant
                meta = frappe.get_meta(dt)
                link_field = None

                if meta.has_field("outlet"):
                    link_field = "outlet"
                else:
                    # Find any field that is a Link to Restaurant
                    for df in meta.fields:
                        if df.fieldtype == "Link" and df.options == "Outlet":
                            link_field = df.fieldname
                            break

                if not link_field:
                    continue

                # Find all records linked to this restaurant
                records = frappe.get_all(dt, filters={link_field: restaurant_name}, pluck='name')

                if records:
                    for record_name in records:
                        if dt == "Media Asset":
                            # Hard-delete the R2 objects (variants + raw + poster) before
                            # removing the DB row — plain delete_doc leaves files orphaned.
                            try:
                                from flamezo_backend.flamezo.media.cleanup import _hard_delete_asset
                                _hard_delete_asset(record_name)
                            except Exception as r2_e:
                                frappe.log_error("Restaurant Delete Error", f"R2 cleanup failed for {record_name}: {r2_e!s}")
                                # Still delete the DB record even if R2 fails
                                frappe.delete_doc(dt, record_name, ignore_permissions=True, delete_permanently=True, force=1)
                        else:
                            # force=1 bypasses Frappe's FK link checker; safe here because
                            # we are intentionally purging all data for this restaurant.
                            frappe.delete_doc(dt, record_name, ignore_permissions=True, delete_permanently=True, force=1)

                    cleanup_report.append(f"Deleted {len(records)} records from {dt}")

            except Exception as inner_e:
                frappe.log_error("Restaurant Delete Error", f"Error deleting from {dt}: {inner_e!s}")
                cleanup_report.append(f"FAILED to delete from {dt}: {inner_e!s}")

        # Special handling for RestaurantConfig (linked via parent)
        if frappe.db.table_exists('RestaurantConfig'):
            try:
                configs = frappe.get_all('RestaurantConfig', filters={'parent': restaurant_name}, pluck='name')
                for cfg in configs:
                    frappe.delete_doc('RestaurantConfig', cfg, ignore_permissions=True, force=1)
                if configs:
                    cleanup_report.append(f"Deleted {len(configs)} RestaurantConfig records")
            except Exception as e:
                frappe.log_error("Restaurant Delete Error", f"Error deleting RestaurantConfig: {e!s}")

        # 6. Finally, delete the Restaurant record itself
        frappe.delete_doc('Outlet', restaurant_name, ignore_permissions=True, delete_permanently=True, force=1)
        cleanup_report.append(f"Deleted Restaurant record: {outlet_id}")

        # Commit all changes to database
        frappe.db.commit()

        return {
            'success': True,
            'message': f"Outlet {outlet_id} and all related data deleted successfully.",
            'report': cleanup_report
        }

    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in delete_outlet API: {e!s}")
        frappe.db.rollback()
        return {
            'success': False,
            'error': f"Failed to delete outlet: {e!s}",
            'partial_report': cleanup_report if 'cleanup_report' in locals() else []
        }


@frappe.whitelist()
def admin_give_coins(outlet_id, amount, reason="Admin Grant"):
    """
    Give coins to an outlet manually from admin.
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
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {'success': False, 'error': 'Outlet not found'}

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
            'message': f"Successfully credited {amount} coins to {outlet_id}",
            'new_balance': new_bal
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in admin_give_coins: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def admin_update_outlet_settings(outlet_id, updates):
    """
    Update administrative settings for an outlet.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        # Get restaurant
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {'success': False, 'error': 'Outlet not found'}

        # Parse updates if it's a string
        if isinstance(updates, str):
            updates = json.loads(updates)

        # Prevent non-admin fields from being updated here if needed,
        # but for now we follow the user's request for platform_fee_percent
        # Allow most fields for admin updates
        allowed_fields = [
            'platform_fee_percent', 'is_active', 'is_featured', 'is_signature',
            'limelight_start_date', 'limelight_end_date',
            'outlet_name', 'owner_email',
            'owner_phone', 'owner_name', 'billing_status', 'mandate_status',
            'enable_loyalty', 'enable_dine_in',
            'tax_rate', 'gst_number',
            'timezone', 'currency', 'tables', 'description', 'google_map_url',
            'outlet_type'
        ]

        # outlet_type: use db.set_value to bypass Frappe's Select validation.
        # Pop it before the main loop so it never goes through restaurant.save().
        if 'outlet_type' in updates:
            valid_types = {'dining', 'cafe', 'wellness', 'fitness', 'sports_court', 'sports_venue', 'fashion'}
            new_type = updates.pop('outlet_type')
            if new_type in valid_types:
                frappe.db.set_value('Outlet', restaurant.name, 'outlet_type', new_type)

        # If nothing else to update, just commit and return — avoids a
        # redundant restaurant.save() that races with the set_value above.
        remaining = {k: v for k, v in updates.items() if k in allowed_fields}
        if not remaining:
            frappe.db.commit()
            return {
                'success': True,
                'message': f"Outlet settings updated successfully for {outlet_id}",
                'data': {'outlet_id': outlet_id, 'updated_fields': list(updates.keys())}
            }

        for field, value in remaining.items():
            if field in ['platform_fee_percent', 'tax_rate']:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            elif field in ['is_active', 'is_featured', 'is_signature', 'enable_loyalty', 'enable_dine_in']:
                value = 1 if value in [True, 1, '1', 'true'] else 0
            elif field in ['tables']:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            setattr(restaurant, field, value)

        restaurant.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            'success': True,
            'message': f"Outlet settings updated successfully for {outlet_id}",
            'data': {
                'outlet_id': outlet_id,
                'updated_fields': list(updates.keys())
            }
        }
    except Exception as e:
        frappe.log_error("Admin API Error", f"Error in admin_update_outlet_settings: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def admin_onboard_outlet_owner(outlet_id, owner_name, owner_email):
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
        restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        if not restaurant:
            return {'success': False, 'error': 'Outlet not found'}

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

        # Generate password
        import string
        import random
        clean_name = ''.join(e for e in restaurant.outlet_name if e.isalnum())
        if not clean_name:
            clean_name = outlet_id.replace('-', '')
            
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        symbols = ['!', '@', '#', '$', '%', '&', '*']
        random_symbol = random.choice(symbols)
        
        generated_password = f"{clean_name.capitalize()}{random_symbol}{suffix}!"

        # Save generated password for admin visibility
        restaurant.onboarding_password = generated_password
        restaurant.save(ignore_permissions=True)
        frappe.db.commit()

        is_new = False
        email_sent = False

        if not user_id:
            # Create a new user
            user_doc = frappe.get_doc({
                "doctype": "User",
                "email": owner_email,
                "first_name": first_name,
                "user_type": "System User",
                "send_welcome_email": 0
            })
            user_doc.insert(ignore_permissions=True)
            user_id = user_doc.name
            is_new = True
        else:
            user_doc = frappe.get_doc("User", user_id)

        # Set the password directly
        from frappe.utils.password import update_password
        update_password(user=owner_email, pwd=generated_password)

        try:
            send_onboarding_email(owner_email, first_name, generated_password)
            email_sent = True
        except Exception as e:
            frappe.log_error("Onboarding Email Failed", f"Failed to send welcome email to {owner_email}. Error: {e}")

        # 3. Add necessary roles
        # The restaurant OWNER must be a Restaurant Admin (not Staff) so they can
        # manage their own branch team. Merchant-level only — never a global role.
        roles_to_add = ["System User", "Outlet Admin"]

        has_changes = False
        for role in roles_to_add:
            if frappe.db.exists("Role", role):
                if not frappe.db.exists("Has Role", {"parent": user_id, "role": role}):
                    user_doc.append("roles", {"role": role})
                    has_changes = True

        if has_changes:
            user_doc.save(ignore_permissions=True)

        # 4. Link user to the restaurant
        has_existing_default = frappe.db.exists("Outlet User", {"user": user_id, "is_default": 1})
        is_default_flag = 0 if has_existing_default else 1

        # create_restaurant_user_permission maps Frappe User Permissions
        create_restaurant_user_permission(user_id, restaurant.name, is_default=is_default_flag)

        # Check if already in 'Outlet User' doctype
        if not frappe.db.exists("Outlet User", {"user": user_id, "outlet": restaurant.name}):
            assign_user_to_restaurant(user_id, restaurant.name, role="Outlet Admin", is_default=is_default_flag)

        frappe.db.commit()

        status_msg = "successfully onboarded" if is_new else "already exists and has been granted access"
        email_msg = "An email has been sent with credentials." if email_sent else "Email could not be sent."

        full_msg = f"Owner {owner_email} {status_msg}. {email_msg}"

        return {
            'success': True,
            'message': full_msg,
            'data': {
                'user': user_id,
                'email': owner_email,
                'is_new': is_new,
                'email_sent': email_sent,
                'generated_password': generated_password
            }
        }
    except Exception as e:
        frappe.log_error("Admin Onboarding Error", f"Error in admin_onboard_outlet_owner: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def admin_assign_owner_to_branches(owner_email, owner_name=None, branch_ids=None, role="Outlet Admin"):
    """Platform-admin action: assign ONE user (typically a multi-branch owner) to
    several restaurant branches in a single call.

      • Creates the Frappe User on first assignment (+ password + welcome email).
      • Inserts a Restaurant User row per branch. The RestaurantUser doctype's
        after_insert hook adds the matching Frappe role AND busts the access
        cache automatically, so access reflects immediately.
      • Grants ONLY the merchant role (Restaurant Admin / Restaurant Staff) —
        NEVER a global role (System Manager / Supervisor), so the owner stays
        confined to their own branches and can switch between them.
      • Idempotent: branches the user already belongs to are skipped.

    Args:
        owner_email : login email — the SAME email is used across all branches.
        owner_name  : display name (only used when creating a new user).
        branch_ids  : list of Restaurant docnames/ids (JSON string or list accepted).
        role        : "Outlet Admin" (default) or "Outlet Staff".

    Returns per-branch results so the UI can show assigned / skipped / not_found.
    """
    try:
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        owner_email = (owner_email or "").strip().lower()
        if not owner_email:
            return {'success': False, 'error': 'Owner email is required'}

        # Guardrail: merchant-level roles only. A global role would leak access to
        # every restaurant — exactly what we must never give a merchant.
        if role not in ("Outlet Admin", "Outlet Staff"):
            role = "Outlet Admin"

        # branch_ids may arrive as a JSON string (HTTP) or comma list.
        if isinstance(branch_ids, str):
            try:
                branch_ids = json.loads(branch_ids)
            except Exception:
                branch_ids = [b.strip() for b in branch_ids.split(",") if b.strip()]
        if not branch_ids or not isinstance(branch_ids, (list, tuple)):
            return {'success': False, 'error': 'At least one branch is required'}

        from flamezo_backend.flamezo.utils.permissions import (
            assign_user_to_restaurant,
            create_restaurant_user_permission,
        )
        from frappe.utils.password import update_password
        import string
        import random

        # --- Find or create the Frappe User ---
        user_id = frappe.db.get_value("User", {"email": owner_email}, "name")
        is_new_user = False
        generated_password = None
        first_name = (owner_name or owner_email.split("@")[0]).split()[0]

        if not user_id:
            user_doc = frappe.get_doc({
                "doctype": "User",
                "email": owner_email,
                "first_name": first_name,
                "user_type": "System User",
                "send_welcome_email": 0,
            })
            user_doc.insert(ignore_permissions=True)
            user_id = user_doc.name
            is_new_user = True

            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            symbol = random.choice(['!', '@', '#', '$', '%', '&', '*'])
            generated_password = f"Flamezo{symbol}{suffix}!"
            update_password(user=owner_email, pwd=generated_password)

        # --- Resolve + assign each branch (idempotent) ---
        results = []
        for raw in branch_ids:
            bid = raw.strip() if isinstance(raw, str) else raw
            if not bid:
                continue

            branch = frappe.db.get_value("Outlet", bid, "name")
            if not branch:
                try:
                    from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
                    branch = get_restaurant_from_id(bid)
                except Exception:
                    branch = None
            if not branch:
                results.append({'branch': bid, 'status': 'not_found'})
                continue

            if frappe.db.exists("Outlet User", {"user": user_id, "outlet": branch}):
                results.append({'branch': branch, 'status': 'skipped'})
                continue

            # First branch this user is given becomes the default (if none yet).
            has_default = frappe.db.exists("Outlet User", {"user": user_id, "is_default": 1})
            is_default_flag = 0 if has_default else 1
            try:
                assign_user_to_restaurant(user_id, branch, role=role, is_default=is_default_flag)
                create_restaurant_user_permission(user_id, branch, is_default=is_default_flag)
                results.append({'branch': branch, 'status': 'assigned'})
            except Exception as e:
                results.append({'branch': branch, 'status': 'failed', 'error': str(e)})

        frappe.db.commit()

        # --- Welcome email once, only when we just created the user ---
        email_sent = False
        if is_new_user and generated_password:
            try:
                send_onboarding_email(owner_email, first_name, generated_password)
                email_sent = True
            except Exception as e:
                frappe.log_error("Owner Assign Email Failed", f"{owner_email}: {e!s}")

        assigned = [r for r in results if r['status'] == 'assigned']
        return {
            'success': True,
            'message': f"{owner_email}: {len(assigned)} branch(es) assigned.",
            'data': {
                'user': user_id,
                'email': owner_email,
                'is_new_user': is_new_user,
                'email_sent': email_sent,
                'generated_password': generated_password if is_new_user else None,
                'role': role,
                'results': results,
            }
        }
    except Exception as e:
        frappe.log_error("Admin Assign Owner Error", f"admin_assign_owner_to_branches: {e!s}")
        frappe.db.rollback()
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def admin_list_branch_access(multi_only=0):
    """Admin: list every user and the branches they can access, grouped by email.

    Returns each email with its branch count and the branch names — so the admin
    can see at a glance "which email has how many branches" (owners = many,
    managers = one). Pass multi_only=1 to list only multi-branch users (owners).
    """
    try:
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        rows = frappe.db.sql(
            """
            SELECT ru.user, ru.outlet, ru.role,
                   COALESCE(r.outlet_name, ru.outlet) AS outlet_name
            FROM `tabOutlet User` ru
            LEFT JOIN `tabOutlet` r ON r.name = ru.outlet
            WHERE ru.is_active = 1
            ORDER BY ru.user
            """,
            as_dict=True,
        )

        grouped = {}
        for row in rows:
            g = grouped.setdefault(row.user, {'user': row.user, 'branches': []})
            g['branches'].append({
                'name': row.outlet,
                'outlet_name': row.outlet_name,
                'role': row.role,
            })

        users = []
        for g in grouped.values():
            g['count'] = len(g['branches'])
            users.append(g)

        if int(multi_only or 0):
            users = [u for u in users if u['count'] > 1]

        # Most branches first, then alphabetical by email.
        users.sort(key=lambda x: (-x['count'], x['user']))

        return {'success': True, 'data': {'users': users, 'total': len(users)}}
    except Exception as e:
        frappe.log_error("Admin Branch Access List Error", f"admin_list_branch_access: {e!s}")
        return {'success': False, 'error': str(e)}


def send_onboarding_email(recipient, name, password):
    """
    Send a custom branded onboarding email to the restaurant owner with credentials.
    """
    import urllib.parse
    site_url = "https://backend.flamezo.in"
    subject = "Welcome to Flamezo - Your Account Credentials"
    login_url = f"{site_url}/flamezo_backend/login?email={urllib.parse.quote(recipient)}&pwd={urllib.parse.quote(password)}"

    html_content = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px; color: #1a1a1a; background-color: #f9fafb;">
        <div style="background-color: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
            <div style="text-align: center; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #f3f4f6;">
                <img src="https://flamezo.in/logo.png" alt="Flamezo Logo" style="height: 40px; object-fit: contain; margin-bottom: 20px;" />
                <h1 style="font-size: 24px; font-weight: 700; margin: 0; color: #111827;">Welcome to Flamezo</h1>
            </div>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 24px; color: #374151;">
                Hello {name},
            </p>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 16px; color: #374151;">
                A new account has been created for you at <a href="{site_url}" style="color: #2563eb; text-decoration: none; font-weight: 500;">{site_url}</a>.
            </p>

            <p style="font-size: 16px; line-height: 24px; margin-bottom: 32px; color: #374151;">
                Your login credentials are:<br><br>
                Email: <strong style="color: #111827;">{recipient}</strong><br>
                Password: <strong style="color: #111827;">{password}</strong><br><br>
                You can log in and change your password anytime from your dashboard.
            </p>

            <div style="margin-bottom: 40px;">
                <a href="{login_url}" style="display: inline-block; background-color: #111827; color: #ffffff; padding: 14px 28px; border-radius: 8px; font-size: 16px; font-weight: 600; text-decoration: none; text-align: center;">Login to Dashboard</a>
            </div>

            <div style="padding-top: 32px; border-top: 1px solid #e5e7eb;">
                <p style="font-size: 14px; line-height: 20px; color: #6b7280; margin-bottom: 8px;">
                    Please keep these credentials safe.
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
def admin_create_wallet_payment_link(outlet_id, tier):
    """
    Legacy endpoint — previously created a Razorpay Payment Link for the
    unlock fee. Under the single-tier model onboarding is free, so this endpoint is intentionally short-circuited.
    It remains importable so existing client code that calls it doesn't 404.

    To charge an outlet a one-off amount today, generate a Razorpay
    Payment Link directly from the Frappe desk.
    """
    try:
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        # Silence unused-arg lints — the legacy signature is preserved for
        # any out-of-tree clients still calling this endpoint.
        _ = (outlet_id, tier)

        return {
            'success': False,
            'error': (
                f'No upgrade payment required. '
                f'Under the new business model, onboarding is free — '
                f'restaurants pay only the Success Share.'
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
def admin_create_manual_recharge_link(outlet_id, amount):
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
            restaurant = frappe.get_doc('Outlet', {'outlet_id': outlet_id})
        except Exception:
            return {'success': False, 'error': 'Outlet not found'}

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
                "name": restaurant.owner_name or restaurant.outlet_name,
                "email": restaurant.owner_email or "",
                "contact": clean_phone or ""
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "restaurant": restaurant.name,
                "outlet_id": outlet_id,
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
            'outlet_name': restaurant.outlet_name
        }

    except Exception as e:
        frappe.log_error(f"Manual recharge link failed: {e!s}", "admin.manual_recharge_link")
        return {'success': False, 'error': str(e)}


# ── Customer Management (Admin / Supervisor only) ─────────────────────────────

@frappe.whitelist()
def admin_get_all_customers(search=None, page=1, page_size=20, sort_by='modified', sort_order='desc'):
    """Platform-wide customer list for admin/supervisor."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    page      = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset    = (page - 1) * page_size

    search_sql = ""
    params: list = []
    if search:
        search_sql = "AND (c.customer_name LIKE %s OR c.phone LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]

    _sort_map = {
        "name":            "c.customer_name",
        "created":         "c.creation",
        "last_seen":       "c.modified",
        "loyalty_balance": "COALESCE(loyalty_stats.balance, 0)",
        "lifetime_earned": "COALESCE(loyalty_stats.lifetime_earned, 0)",
    }
    sort_col  = _sort_map.get(sort_by, "c.modified")
    order_dir = "DESC" if str(sort_order).lower() == "desc" else "ASC"

    rows = frappe.db.sql(f"""
        SELECT
            c.name,
            c.customer_name,
            c.phone,
            c.date_of_birth,
            c.creation,
            c.modified,
            COALESCE(loyalty_stats.balance, 0)        AS loyalty_balance,
            COALESCE(loyalty_stats.lifetime_earned, 0) AS lifetime_earned,
            COALESCE(loyalty_stats.total_redeemed, 0)  AS total_redeemed
        FROM `tabCustomer` c
        LEFT JOIN (
            SELECT customer,
                GREATEST(0, SUM(CASE
                    WHEN transaction_type = 'Earn' AND is_settled = 1
                     AND (expiry_date IS NULL OR expiry_date >= CURDATE())
                    THEN coins
                    WHEN transaction_type = 'Redeem' AND is_settled = 1
                    THEN -coins
                    ELSE 0 END)) AS balance,
                SUM(CASE WHEN transaction_type = 'Earn' AND is_settled = 1 THEN coins ELSE 0 END) AS lifetime_earned,
                SUM(CASE WHEN transaction_type = 'Redeem' AND is_settled = 1 THEN coins ELSE 0 END) AS total_redeemed
            FROM `tabOutlet Loyalty Entry`
            GROUP BY customer
        ) loyalty_stats ON loyalty_stats.customer = c.name
        WHERE 1=1 {search_sql}
        ORDER BY {sort_col} {order_dir}
        LIMIT %s OFFSET %s
    """, params + [page_size, offset], as_dict=True)

    total = frappe.db.sql(f"""
        SELECT COUNT(*) AS cnt FROM `tabCustomer` c
        WHERE 1=1 {search_sql}
    """, params, as_dict=True)[0].cnt

    return {
        "success": True,
        "data": {
            "customers": [
                {
                    "id":              r.name,
                    "name":            r.customer_name or r.name,
                    "phone":           r.phone or "",
                    "birthday":        str(r.date_of_birth) if r.date_of_birth else None,
                    "created":         str(r.creation),
                    "last_seen":       str(r.modified),
                    "loyalty_balance": int(r.loyalty_balance or 0),
                    "lifetime_earned": int(r.lifetime_earned or 0),
                    "total_redeemed":  int(r.total_redeemed or 0),
                }
                for r in rows
            ],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }
    }


@frappe.whitelist()
def admin_get_all_events(search=None, page=1, page_size=20, sort_by='date', sort_order='desc', status=None):
    """Platform-wide event list for admin/supervisor — every merchant's events
    with the outlet name joined in. Mirrors admin_get_all_customers."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    page      = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset    = (page - 1) * page_size

    conds  = ["1=1"]
    params: list = []
    if search:
        conds.append("(e.title LIKE %s OR e.category LIKE %s OR e.location LIKE %s OR r.outlet_name LIKE %s)")
        s = f"%{search}%"
        params += [s, s, s, s]
    if status in ("upcoming", "recurring", "past"):
        conds.append("e.status = %s")
        params.append(status)

    _sort_map = {
        "title":    "e.title",
        "date":     "e.date",
        "created":  "e.creation",
        "modified": "e.modified",
        "outlet":   "r.outlet_name",
        "category": "e.category",
    }
    sort_col  = _sort_map.get(sort_by, "e.date")
    order_dir = "DESC" if str(sort_order).lower() == "desc" else "ASC"
    where     = " AND ".join(conds)

    rows = frappe.db.sql(f"""
        SELECT
            e.name, e.title, e.category, e.status, e.is_active, e.featured,
            e.date, e.time, e.end_time, e.location, e.image_src,
            e.outlet, COALESCE(r.outlet_name, e.outlet) AS outlet_name
        FROM `tabEvent` e
        LEFT JOIN `tabOutlet` r ON r.name = e.outlet
        WHERE {where}
        ORDER BY {sort_col} {order_dir}
        LIMIT %s OFFSET %s
    """, params + [page_size, offset], as_dict=True)

    total = frappe.db.sql(f"""
        SELECT COUNT(*) AS cnt
        FROM `tabEvent` e
        LEFT JOIN `tabOutlet` r ON r.name = e.outlet
        WHERE {where}
    """, params, as_dict=True)[0].cnt

    return {
        "success": True,
        "data": {
            "events": [
                {
                    "id":          r.name,
                    "title":       r.title or r.name,
                    "category":    r.category or "",
                    "status":      r.status or "",
                    "is_active":   int(r.is_active or 0),
                    "featured":    int(r.featured or 0),
                    "date":        str(r.date) if r.date else None,
                    "time":        str(r.time) if r.time else None,
                    "end_time":    str(r.end_time) if r.end_time else None,
                    "location":    r.location or "",
                    "image_src":   r.image_src or "",
                    "outlet":      r.outlet or "",
                    "outlet_name": r.outlet_name or r.outlet or "",
                }
                for r in rows
            ],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }
    }


@frappe.whitelist()
def admin_create_event(title, restaurant=None, description=None, category=None, date=None,
                       time=None, end_time=None, location=None, google_maps_link=None,
                       registration_link=None, image_src=None, featured=0, status="upcoming"):
    """Create a platform Event (admin/supervisor). An event is standalone —
    `restaurant` is OPTIONAL and only links it to a merchant when one is given."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)
    if not (title or "").strip():
        frappe.throw("Event title is required")
    # Merchant is optional; validate only when one was actually provided.
    if restaurant and not frappe.db.exists("Outlet", restaurant):
        frappe.throw("The selected merchant does not exist")

    doc = frappe.get_doc({
        "doctype": "Event",
        "outlet": restaurant or None,
        "title": title.strip(),
        "description": description or "",
        "category": category or "",
        "date": date or None,
        "time": time or None,
        "end_time": end_time or None,
        "location": location or "",
        "google_maps_link": google_maps_link or "",
        "registration_link": registration_link or "",
        "image_src": image_src or "",
        "featured": 1 if str(featured) in ("1", "true", "yes", "True") else 0,
        "status": status if status in ("upcoming", "recurring", "past") else "upcoming",
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"id": doc.name, "title": doc.title}}


@frappe.whitelist()
def admin_get_event_detail(event_id):
    """Full event detail for admin/supervisor, including joined-customer/attendee
    tracking via Event Registration."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    if not frappe.db.exists("Event", event_id):
        return {"success": False, "error": "Event not found"}

    e = frappe.get_doc("Event", event_id)
    outlet_name = ""
    if e.outlet:
        outlet_name = frappe.db.get_value("Outlet", e.outlet, "outlet_name") or ""

    days = [d for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday") if e.get(d)]

    try:
        media = json.loads(e.get("media_gallery") or "[]")
        if not isinstance(media, list):
            media = []
    except Exception:
        media = []

    attendee_rows = frappe.get_all(
        "Event Registration",
        filters={"event": event_id},
        fields=["customer", "customer_name", "customer_phone", "joined_at"],
        order_by="joined_at desc",
    )
    attendees = [
        {
            "id": a.customer or "",
            "name": a.customer_name or a.customer_phone or "Guest",
            "phone": a.customer_phone or "",
            "joined_at": str(a.joined_at) if a.joined_at else "",
        }
        for a in attendee_rows
    ]

    return {
        "success": True,
        "data": {
            "event": {
                "id":               e.name,
                "title":            e.title or e.name,
                "description":      e.description or "",
                "category":         e.category or "",
                "status":           e.status or "",
                "is_active":        int(e.is_active or 0),
                "featured":         int(e.featured or 0),
                "date":             str(e.date) if e.date else None,
                "time":             str(e.time) if e.time else None,
                "end_time":         str(e.end_time) if e.end_time else None,
                "location":         e.location or "",
                "google_maps_link": e.get("google_maps_link") or "",
                "registration_link": e.get("registration_link") or "",
                "image_src":        e.image_src or "",
                "image_alt":        e.get("image_alt") or "",
                "media":            media,
                "repeat_this_event": int(e.get("repeat_this_event") or 0),
                "repeat_on":        e.get("repeat_on") or "",
                "repeat_till":      str(e.repeat_till) if e.get("repeat_till") else None,
                "repeat_days":      days,
                "display_order":    int(e.get("display_order") or 0),
                "created":          str(e.creation),
                "modified":         str(e.modified),
            },
            "outlet":      e.outlet or "",
            "outlet_name": outlet_name or e.outlet or "",
            "attendees": attendees,
            "attendees_count": len(attendees),
            "attendees_available": True,
        }
    }


@frappe.whitelist()
def admin_get_customer_full_profile(customer_id):
    """
    Full platform-level "Customer 360" profile for admin/supervisor.
    Aggregates every doctype that links back to this customer (by Customer ID
    where available, falling back to phone for phone-only doctypes) so nothing
    about the customer's cross-outlet history is missed: orders, all booking
    types, per-outlet visit/spend breakdown, loyalty ledger, referrals, UGC
    submissions/vouchers/redemptions/fraud flags, coupon & offer activity,
    saved addresses, recent sessions/devices, and social/community engagement.
    """
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    if not frappe.db.exists("Customer", customer_id):
        return {"success": False, "error": "Customer not found"}

    customer = frappe.get_doc("Customer", customer_id)
    phone = customer.phone

    # ── Orders (across all restaurants) ────────────────────────────────────────
    orders = frappe.get_all(
        "Order",
        filters={"platform_customer": customer_id},
        fields=["name", "order_id", "order_number", "outlet", "status", "payment_status",
                "payment_method", "order_type", "acquisition_source", "subtotal", "discount",
                "loyalty_discount", "loyalty_coins_redeemed", "coupon", "tax", "total", "creation"],
        order_by="creation desc",
        limit_page_length=200
    )

    # ── Table, Banquet, Court Bookings & Service Appointments ──────────────────
    table_bookings = frappe.get_all(
        "Table Booking",
        filters={"platform_customer": customer_id},
        fields=["name", "outlet", "booking_number", "date", "time_slot", "status", "creation"],
        order_by="creation desc",
        limit_page_length=100
    )
    banquet_bookings = frappe.get_all(
        "Banquet Booking",
        filters={"platform_customer": customer_id},
        fields=["name", "outlet", "booking_number", "date", "event_type", "status", "creation"],
        order_by="creation desc",
        limit_page_length=50
    )
    # Court Booking / Service Appointment only carry customer_phone, no Customer link.
    court_bookings = frappe.get_all(
        "Court Booking",
        filters={"customer_phone": phone},
        fields=["name", "outlet", "court_name", "sport_type", "booking_date", "start_time",
                "end_time", "slot_price", "consumer_fee", "payment_status", "status", "creation"],
        order_by="creation desc",
        limit_page_length=100
    ) if phone else []
    service_appointments = frappe.get_all(
        "Service Appointment",
        filters={"customer_phone": phone},
        fields=["name", "outlet", "catalogue_item_name", "sub_item_name", "sub_item_price",
                "appointment_date", "appointment_time", "duration_minutes", "status", "creation"],
        order_by="creation desc",
        limit_page_length=100
    ) if phone else []

    # ── Loyalty Ledger (full, all restaurants) ────────────────────────────────
    loyalty_entries = frappe.get_all(
        "Outlet Loyalty Entry",
        filters={"customer": customer_id},
        fields=["name", "outlet", "transaction_type", "coins", "reason",
                "posting_date", "expiry_date", "is_settled", "reference_doctype", "reference_name"],
        order_by="creation desc",
        limit_page_length=500
    )

    # Balance
    from frappe.utils import today as _today
    balance = max(0, sum(
        e.coins if e.transaction_type == "Earn" and e.is_settled and (not e.expiry_date or str(e.expiry_date) >= _today())
        else (-e.coins if e.transaction_type == "Redeem" and e.is_settled else 0)
        for e in loyalty_entries
    ))
    lifetime_earned = sum(e.coins for e in loyalty_entries if e.transaction_type == "Earn" and e.is_settled)

    # ── Referral — who referred this customer ─────────────────────────────────
    referral_rel = frappe.db.get_value(
        "Customer Referral",
        {"referee": customer_id},
        ["referrer", "orders_credited", "cashback_total", "status", "activated_on"],
        as_dict=True
    )
    referrer_name = None
    referrer_phone = None
    if referral_rel and referral_rel.referrer:
        referrer_doc = frappe.db.get_value(
            "Customer", referral_rel.referrer,
            ["customer_name", "phone"], as_dict=True
        )
        if referrer_doc:
            referrer_name  = referrer_doc.customer_name
            referrer_phone = referrer_doc.phone

    # ── Referrals made by this customer ──────────────────────────────────────
    referrals_made = frappe.get_all(
        "Customer Referral",
        filters={"referrer": customer_id},
        fields=["referee", "orders_credited", "cashback_total", "status", "activated_on"],
        limit_page_length=50
    )
    for r in referrals_made:
        rd = frappe.db.get_value("Customer", r.referee, ["customer_name", "phone"], as_dict=True) or {}
        r["referee_name"]  = rd.get("customer_name", r.referee)
        r["referee_phone"] = rd.get("phone", "")

    # ── UGC Submissions, Vouchers, Redemptions, Fraud Flags ────────────────────
    ugc_submissions = frappe.get_all(
        "UGC Story Submission",
        filters={"customer": customer_id},
        fields=["name", "outlet", "order", "status", "order_amount",
                "cashback_coins", "submission_date", "story_verified_at", "proof_submitted_at",
                "proof_video", "ai_view_count", "ai_confidence", "ai_tamper_signals",
                "review_notes", "rejection_reason", "story_shared_at", "ai_provider"],
        order_by="creation desc",
        limit_page_length=50
    )
    # Resolve proof video file URL
    for u in ugc_submissions:
        u["proof_video_url"] = None
        if u.get("proof_video"):
            try:
                u["proof_video_url"] = frappe.db.get_value("File", u["proof_video"], "file_url")
            except Exception:
                pass

    ugc_vouchers = frappe.get_all(
        "UGC Voucher",
        filters={"customer": customer_id},
        fields=["name", "voucher_code", "outlet", "status", "ugc_submission",
                "original_amount", "balance", "issued_at", "expires_at", "pin_activated_at"],
        order_by="issued_at desc",
        limit_page_length=50
    )
    ugc_voucher_redemptions = frappe.get_all(
        "UGC Voucher Redemption",
        filters={"customer": customer_id},
        fields=["name", "voucher", "outlet", "order", "redeemed_at", "bill_amount",
                "amount_used", "balance_before", "balance_after", "dish_name", "dish_price"],
        order_by="redeemed_at desc",
        limit_page_length=100
    )
    ugc_fraud_flags = frappe.get_all(
        "UGC Fraud Flag",
        filters={"customer": customer_id},
        fields=["name", "is_active", "blocked_until", "outlet", "reference_submission", "reason", "creation"],
        order_by="creation desc",
        limit_page_length=20
    )

    # ── Coupon Usage & Offer Claims (Hot Drops / deals) ────────────────────────
    coupon_usage = frappe.get_all(
        "Coupon Usage",
        filters={"customer": customer_id},
        fields=["name", "coupon", "order", "usage_date", "discount_amount", "outlet"],
        order_by="usage_date desc",
        limit_page_length=100
    )
    offer_claims = frappe.get_all(
        "Offer Claim",
        or_filters=(
            [{"customer": customer_id}, {"customer_phone": phone}] if phone else [{"customer": customer_id}]
        ),
        fields=["name", "outlet", "coupon", "coupon_code", "claimed_at", "locked_until",
                "is_paid", "paid_amount", "paid_at"],
        order_by="claimed_at desc",
        limit_page_length=100
    )

    # ── Saved Addresses ──────────────────────────────────────────────────────
    addresses = frappe.get_all(
        "Customer Address",
        filters={"customer": customer_id},
        fields=["name", "label", "address_type", "is_default", "address_line_1",
                "area", "city", "pincode", "delivery_notes"],
        order_by="is_default desc, creation desc",
        limit_page_length=20
    )

    # ── Recent Sessions / Devices (never expose session_token) ────────────────
    sessions = frappe.get_all(
        "Customer Session",
        or_filters=(
            [{"customer": customer_id}, {"phone": phone}] if phone else [{"customer": customer_id}]
        ),
        fields=["device_info", "ip_address", "last_used_at", "revoked", "expires_at"],
        order_by="last_used_at desc",
        limit_page_length=10
    )

    # ── Social / Community Engagement (aggregate counts — high-volume tables) ─
    engagement = {}
    if phone:
        engagement = {
            "chills_likes":            frappe.db.count("Chills Like", {"customer_phone": phone}),
            "chills_saves":            frappe.db.count("Chills Save", {"customer_phone": phone}),
            "chills_outlet_follows":   frappe.db.count("Chills Outlet Follow", {"customer_phone": phone}),
            "creator_club_memberships": frappe.db.count("Creator Club Member", {"customer_phone": phone}),
            "crowd_messages_sent":     frappe.db.count("Crowd Chat Message", {"sender_phone": phone}),
            "crowd_groups_joined":     frappe.db.count("Crowd Request Member", {"customer_phone": phone, "status": "approved"}),
            "crowd_reports_filed":     frappe.db.count("Crowd Report", {"reporter_phone": phone}),
            "crowd_reports_against":   frappe.db.count("Crowd Report", {"reported_phone": phone}),
        }
    else:
        engagement = {k: 0 for k in (
            "chills_likes", "chills_saves", "chills_outlet_follows", "creator_club_memberships",
            "crowd_messages_sent", "crowd_groups_joined", "crowd_reports_filed", "crowd_reports_against",
        )}

    # ── Restaurant names map ──────────────────────────────────────────────────
    all_rest_ids = set(
        [b.outlet for b in table_bookings] +
        [b.outlet for b in banquet_bookings] +
        [b.outlet for b in court_bookings] +
        [b.outlet for b in service_appointments] +
        [o.outlet for o in orders] +
        [e.outlet for e in loyalty_entries] +
        [u.outlet for u in ugc_submissions] +
        [v.outlet for v in ugc_vouchers] +
        [r.outlet for r in ugc_voucher_redemptions] +
        [f.outlet for f in ugc_fraud_flags] +
        [c.outlet for c in coupon_usage] +
        [c.outlet for c in offer_claims]
    )
    all_rest_ids.discard(None)
    rest_name_map = {}
    if all_rest_ids:
        rest_rows = frappe.get_all(
            "Outlet", filters={"name": ["in", list(all_rest_ids)]},
            fields=["name", "outlet_name as outlet_name"]
        )
        rest_name_map = {r.name: r.outlet_name for r in rest_rows}

    def rn(rid):
        return rest_name_map.get(rid, rid)

    # ── Outlets-visited breakdown ──────────────────────────────────────────────
    # Every distinct place this customer has actually engaged with in person:
    # orders (spend + visit signal), plus each booking type (visit signal only).
    outlet_stats = {}

    def _touch(rid, when, spend=0, kind=None):
        if not rid:
            return
        s = outlet_stats.setdefault(rid, {
            "restaurant": rid, "outlet_name": rn(rid),
            "visit_count": 0, "total_spent": 0.0, "last_visited": None,
            "orders": 0, "table_bookings": 0, "banquet_bookings": 0,
            "court_bookings": 0, "service_appointments": 0,
        })
        s["visit_count"] += 1
        s["total_spent"] += float(spend or 0)
        if kind:
            s[kind] += 1
        w = str(when) if when else None
        if w and (not s["last_visited"] or w > s["last_visited"]):
            s["last_visited"] = w

    for o in orders:
        _touch(o.outlet, o.creation, spend=o.total if o.payment_status == "completed" else 0, kind="orders")
    for b in table_bookings:
        _touch(b.outlet, b.creation, kind="table_bookings")
    for b in banquet_bookings:
        _touch(b.outlet, b.creation, kind="banquet_bookings")
    for b in court_bookings:
        _touch(b.outlet, b.creation, kind="court_bookings")
    for b in service_appointments:
        _touch(b.outlet, b.creation, kind="service_appointments")

    outlets_visited = sorted(outlet_stats.values(), key=lambda s: s["last_visited"] or "", reverse=True)

    completed_orders = [o for o in orders if o.payment_status == "completed"]
    total_spend = sum(float(o.total or 0) for o in completed_orders)

    return {
        "success": True,
        "data": {
            "customer": {
                "id":           customer.name,
                "name":         customer.customer_name,
                "phone":        customer.phone,
                "email":        customer.email,
                "birthday":     str(customer.date_of_birth) if customer.date_of_birth else None,
                "created":      str(customer.creation),
                "verified_at":  str(customer.verified_at) if customer.verified_at else None,
                "first_verified_at_restaurant": rn(customer.first_verified_at_restaurant) if customer.first_verified_at_restaurant else None,
                "last_visited": str(customer.last_visited) if customer.last_visited else None,
                "opted_out_of_marketing": bool(customer.opted_out_of_marketing),
            },
            "stats": {
                "restaurants_visited": len(outlets_visited),
                "total_orders":        len(orders),
                "total_spend":         total_spend,
                "avg_order_value":     (total_spend / len(completed_orders)) if completed_orders else 0,
                "total_bookings":      len(table_bookings) + len(banquet_bookings) + len(court_bookings) + len(service_appointments),
                "loyalty_balance":     balance,
                "lifetime_earned":     lifetime_earned,
                "total_redeemed":      sum(e.coins for e in loyalty_entries if e.transaction_type == "Redeem" and e.is_settled),
                "ugc_wallet_balance":  sum(float(v.balance or 0) for v in ugc_vouchers if v.status == "active"),
                "coupons_used":        len(coupon_usage),
                "total_coupon_savings": sum(float(c.discount_amount or 0) for c in coupon_usage),
                "fraud_flagged":       any(f.is_active for f in ugc_fraud_flags),
            },
            "outlets_visited": outlets_visited,
            "orders": [
                {**dict(o), "outlet_name": rn(o.outlet)}
                for o in orders
            ],
            "table_bookings": [
                {**dict(b), "outlet_name": rn(b.outlet)}
                for b in table_bookings
            ],
            "banquet_bookings": [
                {**dict(b), "outlet_name": rn(b.outlet)}
                for b in banquet_bookings
            ],
            "court_bookings": [
                {**dict(b), "outlet_name": rn(b.outlet)}
                for b in court_bookings
            ],
            "service_appointments": [
                {**dict(b), "outlet_name": rn(b.outlet)}
                for b in service_appointments
            ],
            "loyalty": {
                "balance":        balance,
                "lifetime_earned": lifetime_earned,
                "entries": [
                    {**dict(e), "outlet_name": rn(e.outlet)}
                    for e in loyalty_entries
                ],
            },
            "referral": {
                "referred_by": {
                    "referrer_id":    referral_rel.referrer if referral_rel else None,
                    "referrer_name":  referrer_name,
                    "referrer_phone": referrer_phone,
                    "orders_credited": int(referral_rel.orders_credited or 0) if referral_rel else 0,
                    "cashback_total":  float(referral_rel.cashback_total or 0) if referral_rel else 0,
                    "status":          referral_rel.status if referral_rel else None,
                } if referral_rel else None,
                "referrals_made": [dict(r) for r in referrals_made],
            },
            "ugc": [
                {**dict(u), "outlet_name": rn(u.outlet)}
                for u in ugc_submissions
            ],
            "ugc_vouchers": [
                {**dict(v), "outlet_name": rn(v.outlet)}
                for v in ugc_vouchers
            ],
            "ugc_voucher_redemptions": [
                {**dict(r), "outlet_name": rn(r.outlet)}
                for r in ugc_voucher_redemptions
            ],
            "ugc_fraud_flags": [
                {**dict(f), "outlet_name": rn(f.outlet)}
                for f in ugc_fraud_flags
            ],
            "coupon_usage": [
                {**dict(c), "outlet_name": rn(c.outlet)}
                for c in coupon_usage
            ],
            "offer_claims": [
                {**dict(c), "outlet_name": rn(c.outlet)}
                for c in offer_claims
            ],
            "addresses": [dict(a) for a in addresses],
            "sessions": [dict(s) for s in sessions],
            "engagement": engagement,
        }
    }


@frappe.whitelist()
def admin_adjust_customer_loyalty(customer_id, outlet_id, coins, reason, transaction_type="Earn"):
    """Manual loyalty adjustment — admin/supervisor only."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    coins = int(coins)
    if coins <= 0 or coins > 500:
        frappe.throw("Adjustment must be 1–500 coins")

    from flamezo_backend.flamezo.utils.loyalty import add_loyalty_coins
    add_loyalty_coins(
        customer=customer_id,
        restaurant=outlet_id,
        coins=coins,
        reason=reason or "Manual Adjustment",
        transaction_type=transaction_type,
    )
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def admin_delete_customer(customer_id):
    """Hard-delete a customer and all their data. Irreversible. Admin only."""
    if not is_supervisor():
        frappe.throw("Permission denied", frappe.PermissionError)

    if not frappe.db.exists("Customer", customer_id):
        frappe.throw("Customer not found")

    phone = frappe.db.get_value("Customer", customer_id, "phone") or ""

    # Delete every custom doctype that links to Customer before calling
    # frappe.delete_doc, so Frappe's link-check doesn't block the delete.
    _customer_linked_doctypes = [
        # (doctype, filter_field)
        ("Customer Session",          "customer"),
        ("Outlet Loyalty Entry",  "customer"),
        ("Order",                     "customer"),
        ("Table Booking",             "customer"),
        ("Banquet Booking",           "customer"),
        ("Coupon Usage",              "customer"),
        ("Offer Claim",               "customer"),
        ("UGC Story Submission",      "customer"),
        ("UGC Voucher",               "customer"),
        ("UGC Voucher Redemption",    "customer"),
        ("UGC Fraud Flag",            "customer"),
        ("Customer Data Unlock",      "customer"),
        ("Customer Referral",         "customer"),
        ("Referral Link",             "customer"),
    ]

    for doctype, field in _customer_linked_doctypes:
        try:
            if frappe.db.table_exists(doctype):
                frappe.db.delete(doctype, {field: customer_id})
        except Exception as e:
            frappe.log_error(f"admin_delete_customer: could not delete {doctype}: {e}", "CustomerDelete")

    # Customer Session also links by phone (not customer id) in some setups
    if phone:
        try:
            if frappe.db.table_exists("Customer Session"):
                frappe.db.delete("Customer Session", {"phone": phone})
        except Exception:
            pass

    # Customer Referral has referee/referrer fields too
    try:
        frappe.db.delete("Customer Referral", {"referee": customer_id})
        frappe.db.delete("Customer Referral", {"referrer": customer_id})
    except Exception:
        pass

    frappe.db.commit()

    frappe.delete_doc("Customer", customer_id, force=True, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def admin_generate_bulk_food_photos(outlet_id):
    """
    Enqueue a background job to generate Fal.ai food photos for all
    products in an outlet that currently lack media.
    """
    try:
        # Check admin access first
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        frappe.enqueue(
            'flamezo_backend.flamezo.api.admin.process_bulk_food_photos',
            outlet_id=outlet_id,
            queue='long',
            timeout=3600
        )

        return {
            'success': True,
            'message': 'Bulk photo generation job enqueued successfully.'
        }
    except Exception as e:
        frappe.log_error("Bulk Photo Gen Error", f"Failed to enqueue: {str(e)}")
        return {'success': False, 'error': str(e)}

def process_bulk_food_photos(outlet_id):
    try:
        products = frappe.get_all('Menu Product', filters={'outlet': outlet_id}, pluck='name')
        for product_name in products:
            product = frappe.get_doc('Menu Product', product_name)

            # Skip: product already has at least one media item
            if product.product_media:
                continue

            # Skip: an active (non-failed) job already exists for this product.
            # Prevents duplicate jobs when the button is clicked twice or after a
            # partial run leaves pending/processing/completed records behind.
            active_job = frappe.db.exists("AI Image Generation", {
                "outlet": outlet_id,
                "owner_doctype": "Menu Product",
                "owner_name": product_name,
                "status": ["in", ["Pending_Upload", "Processing", "Completed"]],
            })
            if active_job:
                continue

            doc = frappe.get_doc({
                "doctype": "AI Image Generation",
                "outlet": outlet_id,
                "owner_doctype": "Menu Product",
                "owner_name": product_name,
                "original_image_url": "",
                "status": "Pending_Upload"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

            frappe.enqueue(
                "flamezo_backend.flamezo.api.ai_media.process_ai_image_enhancement",
                queue="default",
                timeout=300,
                generation_name=doc.name,
                mode="generate",
                include_branding=False,
                coins_to_refund=0,
            )
    except Exception as e:
        frappe.log_error("Bulk Photo Gen Background Error", str(e))
