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
"""

import frappe
from frappe import _
from frappe.exceptions import PermissionError
from functools import wraps
import json


# Feature list
ALL_FEATURES = [
    'pos_integration',
    'coupons',
    'data_export',
    'customer',
    'customer_pay_and_usage',
    'marketing_studio',
    'games',
    'video_upload',
    'analytics',
    'ai_recommendations',
    'custom_branding',
    'table_booking',
    'ordering',
    'order_settings',
    'whatsapp_orders',
    'loyalty',
    'basic_menu',
    'qr_code',
    'website'
]


def require_plan(*required_plans):
    """
    No-op decorator — retained so that existing call-sites continue to work
    without code changes. It simply passes through with zero overhead.
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
    Check if a restaurant has access to a specific feature (always True).
    """
    if not restaurant_id:
        frappe.throw(_('Restaurant ID is required'))
    
    return {
        'has_access': True,
        'current_plan': '',
        'required_plans': [],
        'feature': feature_name
    }


def get_plan_features(plan_type=None):
    """
    Get list of all features available (all features are available).
    """
    return ALL_FEATURES


def check_image_upload_limit(restaurant_id):
    """
    Check if restaurant has reached image upload limit (always True/unlimited).
    """
    restaurant = frappe.get_doc('Restaurant', restaurant_id)
    return {
        'can_upload': True,
        'current_count': restaurant.current_image_count or 0,
        'max_limit': -1,  # Unlimited
        'plan_type': ''
    }


def increment_image_count(restaurant_id):
    """
    Increment image count for restaurant (used after successful upload)
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
	Helper to get the current plan tier for a restaurant (returns empty).
	"""
	return ""
