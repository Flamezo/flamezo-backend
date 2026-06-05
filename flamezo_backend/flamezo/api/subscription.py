# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Subscription API Endpoints

Provides API endpoints for subscription plan management and feature access checks.

New model (May 2026): GOLD is the only active tier. Every onboarded restaurant
gets the full feature set on day 1 — free onboarding, no monthly floor, plus
Success Share on online orders (default 3% for new restaurants, 1.5%
grandfathered for ones onboarded before May 2026).
"""

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.feature_gate import check_feature_access, get_plan_features


@frappe.whitelist()
def get_restaurant_plan(restaurant_id):
    """
    Get current subscription plan for a restaurant.

    Args:
        restaurant_id (str): Restaurant ID

    Returns:
        dict: Restaurant plan information
    """
    if not restaurant_id:
        frappe.throw(_('Restaurant ID is required'))

    restaurant = frappe.get_doc('Restaurant', restaurant_id)
    plan_type = restaurant.plan_type or 'GOLD'

    return {
        'restaurant_id': restaurant.name,
        'restaurant_name': restaurant.restaurant_name,
        'plan_type': plan_type,
        'plan_activated_on': restaurant.plan_activated_on,
        'plan_changed_by': restaurant.plan_changed_by,
        'features': get_plan_features(plan_type),
        'limits': {
            # All onboarded restaurants get unlimited images.
            'max_images': -1,
            'current_images': restaurant.current_image_count or 0,
            'video_upload': True,
            'ordering': True,
        },
        'metrics': {
            'total_orders': restaurant.total_orders or 0,
            'total_revenue': restaurant.total_revenue or 0,
            'commission_earned': restaurant.commission_earned or 0,
        },
    }


@frappe.whitelist()
def check_access(restaurant_id, feature_name):
    """
    Check if restaurant has access to a specific feature.

    Args:
        restaurant_id (str): Restaurant ID
        feature_name (str): Feature identifier

    Returns:
        dict: Feature access information
    """
    return check_feature_access(restaurant_id, feature_name)


@frappe.whitelist()
def get_plan_comparison(restaurant_id=None):
    """
    Return the active plan description.

    Kept as `get_plan_comparison` for client backwards-compatibility.
    """
    default_rate = frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent") or 3.0
    commission_rate = f"{float(default_rate)}%"
    if restaurant_id:
        try:
            rate = frappe.db.get_value("Restaurant", restaurant_id, "platform_fee_percent")
            if rate is not None:
                commission_rate = f"{float(rate)}%"
        except Exception:
            pass

    price_floor = frappe.db.get_single_value("Flamezo Settings", "gold_monthly_fee") or 0

    return {
        'GOLD': {
            'name': 'Flamezo',
            'price': f'Free onboarding · ₹{float(price_floor):.0f} floor / mo + {commission_rate} on online orders',
            'commission': commission_rate,
            'features': {
                'included': [
                    'Digital QR menu (unlimited items, unlimited photos)',
                    'Dine-in, takeaway, and delivery ordering',
                    'Flamezo loyalty coins (earn & redeem across the network)',
                    'Listed on the FLAMEZO consumer app',
                    'Customer CRM — own your customer data',
                    'Marketing campaigns (SMS, WhatsApp, Email)',
                    'Event-based automation triggers',
                    'Coupons & targeted discount offers',
                    'Analytics dashboard',
                    'Video content support',
                    'AI-powered menu recommendations',
                    'Custom branding (remove Flamezo logo)',
                    'Custom logo on QR codes',
                    'Table & banquet booking',
                    'POS integration (PetPooja, UrbanPiper, RestroWorks)',
                    'Google Business Profile sync & AI review replies',
                    'AI SEO blog auto-generation',
                    'Data export (CSV/PDF)',
                    'Gamification (spin/scratch)',
                    'Staff management & roles',
                ],
                'branding': 'Minimal "Powered by Flamezo" footer',
                'qr_logo': 'Your custom restaurant logo on QR codes',
                'note': 'You pay nothing until your customers pay you. The floor only kicks in once you start taking online payments.'
            }
        }
    }


@frappe.whitelist()
def get_upgrade_benefits(restaurant_id):
    """
    Legacy endpoint kept for backwards compatibility with old merchant builds.

    Under the new model every restaurant is already on the only available tier,
    so this always reports `already_gold: True`. The benefits payload is left in
    place so the existing UI continues to render without breaking.
    """
    restaurant = frappe.get_doc('Restaurant', restaurant_id)

    return {
        'already_gold': True,
        'current_plan': restaurant.plan_type or 'GOLD',
        'benefits': [
            {
                'category': 'Own Your Customers',
                'items': [
                    'CRM — see who ordered, how often, contact details',
                    'Customer segmentation (loyal, lapsed, high-spenders)',
                    'Import existing customer list',
                ]
            },
            {
                'category': 'Bring Them Back',
                'items': [
                    'Marketing campaigns via SMS, WhatsApp, Email',
                    'Event-based automation (e.g. 7 days no visit → send offer)',
                    'Coupons & targeted discount offers',
                    f'Just {float(restaurant.platform_fee_percent or frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent") or 3.0)}% Success Share — only pay when you earn',
                ]
            },
            {
                'category': 'Look More Professional',
                'items': [
                    'Remove Flamezo branding completely',
                    'Custom logo on QR codes',
                    'AI SEO blog auto-generation',
                    'Google Business Profile sync & AI review replies',
                ]
            },
            {
                'category': 'Run the Business Better',
                'items': [
                    'Analytics dashboard (top items, peak hours, revenue)',
                    'Table & banquet booking',
                    'POS integration (PetPooja, UrbanPiper, RestroWorks)',
                    'Data export (CSV/PDF)',
                    'Staff roles & permissions',
                ]
            },
        ],
        'cta': 'You already have everything Flamezo offers.'
    }
