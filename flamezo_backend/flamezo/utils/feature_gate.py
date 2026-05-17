# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Feature Gate System for Subscription-based Access Control

This module provides decorators and utilities to restrict feature access
based on restaurant subscription plans (SILVER vs GOLD).

Plan model:
  SILVER (Free): QR menu, WhatsApp orders, order settings, loyalty earn/redeem
                 (platform-managed), listed on Flamezo Club.
                 Loyalty is ON by default; toggling it OFF also disables Club listing.
  GOLD (₹1299 unlock · ₹399/mo floor · 1.5% commission):
                 All SILVER features + full dine-in ordering (real-time, accept, logistics),
                 CRM, marketing studio, coupons, analytics, POS integration,
                 custom branding, data export, and more.
"""

import frappe
from frappe import _
from frappe.exceptions import PermissionError
from functools import wraps
import json
import inspect


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
    Decorator to restrict endpoint access based on subscription plan
    
    Usage:
        @frappe.whitelist()
        @require_plan('GOLD')
        def create_order(restaurant_id, order_data):
            # This endpoint is only accessible to GOLD plan restaurants
            ...
    
    Args:
        *required_plans: Variable number of plan types that can access this feature
                        (e.g., 'GOLD', 'SILVER')
    
    Raises:
        PermissionError: If restaurant's plan is not in required_plans
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Comprehensive argument extraction
            # We look in kwargs, args, and frappe.form_dict (whitelisted fallback)
            identifier = None
            
            # Use inspect to handle positional and keyword arguments correctly
            try:
                sig = inspect.signature(func)
                bound_args = sig.bind_partial(*args, **kwargs)
                for key in ['restaurant_id', 'restaurant']:
                    if key in bound_args.arguments:
                        identifier = bound_args.arguments[key]
                        break
            except Exception:
                pass

            # Fallback to keys_to_check if inspect failed or didn't find specific restaurant keys
            if not identifier:
                keys_to_check = [
                    'restaurant_id', 'restaurant', 
                    'order_id', 'order',
                    'campaign_id', 'trigger_id', 'trigger_name', 
                    'segment_id', 'segment_name', 'target_segment'
                ]
                
                for key in keys_to_check:
                    if kwargs.get(key):
                        identifier = kwargs.get(key)
                        break
                
                if not identifier and args:
                    # Specific hack: if first arg is 10 digits, it's likely a phone, not a restaurant ID
                    if not (isinstance(args[0], str) and len(args[0]) == 10 and args[0].isdigit()):
                        identifier = args[0]
                    elif len(args) > 1:
                        identifier = args[1]
                    
                if not identifier and hasattr(frappe, 'form_dict'):
                    for key in keys_to_check:
                        if frappe.form_dict.get(key):
                            identifier = frappe.form_dict.get(key)
                            break

            if not identifier:
                # Log the error for production debugging
                frappe.log_error(
                    message=f"Function: {func.__name__}\nArgs: {args}\nKwargs: {kwargs}\nForm Dict: {getattr(frappe, 'form_dict', 'N/A')}",
                    title="Feature Gate: Missing Identifier"
                )
                frappe.throw(
                    _('Restaurant ID is required for this operation'),
                    PermissionError
                )
            
            # 2. Intelligent Restaurant Resolution
            restaurant_id = identifier
            
            # If the identifier is NOT a Restaurant doc name, try resolving from sub-entities
            if not frappe.db.exists("Restaurant", identifier):
                resolved = None
                
                # Check Campaign
                if not resolved:
                    resolved = frappe.db.get_value("Marketing Campaign", identifier, "restaurant")
                    if not resolved: # Try by campaign_name if ID match fails
                        resolved = frappe.db.get_value("Marketing Campaign", {"campaign_name": identifier}, "restaurant")
                
                # Check Trigger
                if not resolved:
                    resolved = frappe.db.get_value("Marketing Trigger", identifier, "restaurant")
                    if not resolved:
                        resolved = frappe.db.get_value("Marketing Trigger", {"trigger_name": identifier}, "restaurant")
                        
                # Check Segment
                if not resolved:
                    resolved = frappe.db.get_value("Marketing Segment", identifier, "restaurant")
                    if not resolved:
                        resolved = frappe.db.get_value("Marketing Segment", {"segment_name": identifier}, "restaurant")
                
                # Check Order
                if not resolved:
                    resolved = frappe.db.get_value("Order", identifier, "restaurant")
                
                if resolved:
                    restaurant_id = resolved
                else:
                    # Final attempt: normalize via helper (handles restaurant_id vs name)
                    # We avoid circular import by importing inside or using raw SQL
                    from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
                    restaurant_id = get_restaurant_from_id(identifier) or identifier

            # 3. Plan Validation
            try:
                # We use db.get_value to avoid permission checks on get_doc for Guest users
                plan_type = frappe.db.get_value('Restaurant', restaurant_id, 'plan_type') or 'SILVER'
            except Exception:
                plan_type = 'SILVER' # Default to safest plan if fetch fails

            if plan_type not in required_plans:
                frappe.throw(
                    _('This feature requires {0} plan. Your current plan is {1}. Please upgrade to access this feature.').format(
                        ' or '.join(required_plans),
                        plan_type
                    ),
                    PermissionError
                )
            
            return func(*args, **kwargs)
        
        # Ensure Frappe whitelisting attributes are preserved if applied to the inner function
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
        'current_plan': restaurant.plan_type or 'SILVER',
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
	Helper to get the current plan tier for a restaurant
	"""
	if not restaurant_id:
		return "SILVER"
	
	plan = frappe.db.get_value("Restaurant", restaurant_id, "plan_type")
	return plan if plan else "SILVER"
