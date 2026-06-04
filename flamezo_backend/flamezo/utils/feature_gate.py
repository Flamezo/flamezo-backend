# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Feature Gate System for Subscription-based Access Control

This module provides decorators and utilities to restrict feature access
based on restaurant subscription plan.

Plan model (May 2026, single-tier platform):
  GOLD (Free onboarding · no monthly floor · Success Share on online orders — default 3% new, 1.5% grandfathered):
        Every onboarded restaurant gets the full feature set immediately —
        QR menu, dine-in/takeaway/delivery ordering, CRM, marketing studio,
        coupons, analytics, POS integration, custom branding, FLAMEZO consumer
        discovery, cross-restaurant loyalty, AI tooling, data export, etc.

  SILVER: legacy tier retained only in the doctype schema for historical
        records. New restaurants never land on SILVER and the migration patch
        `migrate_silver_to_gold_2026` flips any remaining rows to GOLD. The
        SILVER branches below are dead-code-safe fallbacks; they exist purely
        so a stale row cannot crash the gate.
"""

import frappe
from frappe import _
from frappe.exceptions import PermissionError
from functools import wraps
import json


# Feature to Plan Mapping
# Features listed here require specific plan types.
#
# SILVER: ordering + loyalty are available but tied together —
#         toggling loyalty OFF also disables ordering and Club listing.
# GOLD:   everything, plus CRM, marketing, analytics, POS, custom branding, etc.
FEATURE_PLAN_MAP = {
    # GOLD-only features (full dine-in ordering system, CRM, marketing, POS)
    'pos_integration': ['GOLD'],
    'coupons': ['GOLD'],
    'data_export': ['GOLD'],
    'customer': ['SILVER', 'GOLD'],
    'customer_pay_and_usage': ['GOLD'],
    'marketing_studio': ['GOLD'],
    'games': ['GOLD'],
    'video_upload': ['GOLD'],
    'analytics': ['SILVER', 'GOLD'],
    'ai_recommendations': ['GOLD'],
    'custom_branding': ['GOLD'],
    'table_booking': ['GOLD'],
    'ordering': ['GOLD'],  # Full dine-in ordering (real-time, accept, logistics) is GOLD
    'order_settings': ['SILVER', 'GOLD'],

    # SILVER + GOLD features
    'whatsapp_orders': ['SILVER', 'GOLD'],   # WhatsApp is the Silver ordering channel
    'loyalty': ['SILVER', 'GOLD'],            # Loyalty is core Silver benefit
}


def require_plan(*required_plans):
    """
    No-op decorator — GOLD is the only plan as of May 2026.

    Every onboarded restaurant is GOLD. The decorator is retained so that
    existing ``@require_plan('GOLD')`` / ``@require_plan('SILVER', 'GOLD')``
    call-sites continue to work without code changes. It simply passes
    through to the wrapped function with zero overhead.

    If plan-gating is ever reintroduced, restore the validation logic from
    git history (commit before the Boost feature branch).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Preserve Frappe whitelisting attributes
        if hasattr(func, 'whitelisted'):
            wrapper.whitelisted = func.whitelisted
        if hasattr(func, 'allow_guest'):
            wrapper.allow_guest = func.allow_guest

        return wrapper
    return decorator


@frappe.whitelist()
def check_feature_access(restaurant_id, feature_name):
    """
    Check if a restaurant has access to a specific feature
    
    Args:
        restaurant_id (str): Restaurant ID
        feature_name (str): Feature identifier (e.g., 'ordering', 'analytics')
    
    Returns:
        dict: {
            'has_access': bool,
            'current_plan': str,
            'required_plans': list,
            'feature': str
        }
    """
    if not restaurant_id:
        frappe.throw(_('Restaurant ID is required'))
    
    # Get restaurant document
    try:
        restaurant = frappe.get_doc('Restaurant', restaurant_id)
    except frappe.DoesNotExistError:
        frappe.throw(_('Restaurant {0} does not exist').format(restaurant_id))
    
    # Get required plans for this feature. Fallback to all plans if not mapped.
    required_plans = FEATURE_PLAN_MAP.get(feature_name, ['SILVER', 'GOLD'])
    
    # Check if current plan has access
    has_access = restaurant.plan_type in required_plans
    
    return {
        'has_access': has_access,
        'current_plan': restaurant.plan_type or 'GOLD',
        'required_plans': required_plans,
        'feature': feature_name
    }


def get_plan_features(plan_type):
    """
    Get list of all features available for a specific plan

    Args:
        plan_type (str): Plan type ('SILVER' or 'GOLD')

    Returns:
        list: List of feature names available for this plan
    """
    base_features = ['basic_menu', 'qr_code', 'website', 'ordering', 'loyalty']

    if plan_type == 'GOLD':
        # GOLD has access to everything
        return list(FEATURE_PLAN_MAP.keys()) + ['basic_menu', 'qr_code', 'website']
    else:
        # SILVER gets base features + ordering + loyalty (tied together)
        return base_features


def check_image_upload_limit(restaurant_id):
    """
    Check if restaurant has reached image upload limit (SILVER plan only)
    
    Args:
        restaurant_id (str): Restaurant ID
    
    Returns:
        dict: {
            'can_upload': bool,
            'current_count': int,
            'max_limit': int,
            'plan_type': str
        }
    
    Raises:
        PermissionError: If SILVER plan has reached image limit
    """
    restaurant = frappe.get_doc('Restaurant', restaurant_id)
    
    # GOLD plan has unlimited images
    if restaurant.plan_type == 'GOLD':
        return {
            'can_upload': True,
            'current_count': restaurant.current_image_count or 0,
            'max_limit': -1,  # Unlimited
            'plan_type': restaurant.plan_type
        }
    
    # SILVER plan has limit
    current_count = restaurant.current_image_count or 0
    max_limit = restaurant.max_images_silver or 200
    
    can_upload = current_count < max_limit
    
    if not can_upload:
        frappe.throw(
            _('Image upload limit reached ({0}/{1}). Upgrade to GOLD for unlimited images.').format(
                current_count,
                max_limit
            ),
            PermissionError
        )
    
    return {
        'can_upload': can_upload,
        'current_count': current_count,
        'max_limit': max_limit,
        'plan_type': 'SILVER'
    }


def increment_image_count(restaurant_id):
    """
    Increment image count for restaurant (used after successful upload)
    
    Args:
        restaurant_id (str): Restaurant ID
    """
    frappe.db.set_value(
        'Restaurant',
        restaurant_id,
        'current_image_count',
        frappe.db.get_value('Restaurant', restaurant_id, 'current_image_count') + 1
    )
    frappe.db.commit()


def decrement_image_count(restaurant_id):
    """
    Decrement image count for restaurant (used after image deletion)
    
    Args:
        restaurant_id (str): Restaurant ID
    """
    current = frappe.db.get_value('Restaurant', restaurant_id, 'current_image_count') or 0
    if current > 0:
        frappe.db.set_value(
            'Restaurant',
            restaurant_id,
            'current_image_count',
            current - 1
        )
        frappe.db.commit()


def get_restaurant_plan(restaurant_id):
	"""
	Helper to get the current plan tier for a restaurant.

	Returns "GOLD" by default — under the single-tier model that is also the
	correct answer for an unknown / missing restaurant id, and avoids forcing
	loyalty caps onto the more restrictive legacy SILVER tier.
	"""
	if not restaurant_id:
		return "GOLD"

	plan = frappe.db.get_value("Restaurant", restaurant_id, "plan_type")
	return plan if plan else "GOLD"
