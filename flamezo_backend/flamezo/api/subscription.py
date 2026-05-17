# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Subscription API Endpoints

Provides API endpoints for subscription plan management and feature access checks.
"""

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.feature_gate import check_feature_access, get_plan_features


@frappe.whitelist()
def get_restaurant_plan(restaurant_id):
    """
    Get current subscription plan for a restaurant
    
    Args:
        restaurant_id (str): Restaurant ID
    
    Returns:
        dict: Restaurant plan information
    """
    if not restaurant_id:
        frappe.throw(_('Restaurant ID is required'))
    
    restaurant = frappe.get_doc('Restaurant', restaurant_id)
    
    return {
        'restaurant_id': restaurant.name,
        'restaurant_name': restaurant.restaurant_name,
        'plan_type': restaurant.plan_type or 'SILVER',
        'plan_activated_on': restaurant.plan_activated_on,
        'plan_changed_by': restaurant.plan_changed_by,
        'features': get_plan_features(restaurant.plan_type or 'SILVER'),
        'limits': {
            'max_images': restaurant.max_images_silver if restaurant.plan_type == 'SILVER' else -1,
            'current_images': restaurant.current_image_count or 0,
            'video_upload': restaurant.plan_type == 'GOLD',
            'ordering': True,  # Both plans support ordering (Silver tied to loyalty)
        },
        'metrics': {
            'total_orders': restaurant.total_orders or 0,
            'total_revenue': restaurant.total_revenue or 0,
            'commission_earned': restaurant.commission_earned or 0,
        } if restaurant.plan_type == 'GOLD' else None
    }


@frappe.whitelist()
def check_access(restaurant_id, feature_name):
    """
    Check if restaurant has access to a specific feature
    
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
    Get feature comparison between SILVER and GOLD plans

    Args:
        restaurant_id (str, optional): Restaurant ID to show personalized rates

    Returns:
        dict: Plan comparison data
    """
    default_rate = frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent") or 1.5
    commission_rate = f"{float(default_rate)}%"
    if restaurant_id:
        try:
            rate = frappe.db.get_value("Restaurant", restaurant_id, "platform_fee_percent")
            if rate is not None:
                commission_rate = f"{float(rate)}%"
        except Exception:
            pass

    price_floor = frappe.db.get_single_value("Flamezo Settings", "gold_monthly_fee") or 399.0

    return {
        'SILVER': {
            'name': 'Flamezo Silver',
            'price': 'Free',
            'commission': '0%',
            'features': {
                'included': [
                    'Digital QR menu',
                    'Basic restaurant website',
                    'Menu management (unlimited items)',
                    'Photo uploads (max 200 images)',
                    'Dine-in ordering via QR',
                    'Flamezo loyalty cash (earn & redeem)',
                    'Listed on Flamezo Club app',
                    'Contact & location display',
                    'Social media links',
                ],
                'excluded': [
                    'Customer CRM & data',
                    'Marketing campaigns (SMS/WhatsApp/Email)',
                    'Coupons & targeted offers',
                    'Analytics dashboard',
                    'Video content',
                    'POS integration',
                    'Custom branding (no DM logo removal)',
                    'Table & banquet booking',
                    'Data export',
                ],
                'branding': 'Mandatory "Powered by Flamezo" branding',
                'qr_logo': 'Flamezo logo watermark on QR codes',
                'note': 'Loyalty and ordering are linked — disabling loyalty also disables ordering and Club listing.'
            }
        },
        'GOLD': {
            'name': 'Flamezo Gold',
            'price': f'₹{float(price_floor)} floor / mo + {commission_rate} on orders',
            'commission': commission_rate,
            'features': {
                'included': [
                    'All SILVER features',
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
                    'Unlimited photo uploads',
                    'Gamification (spin/scratch)',
                    'Staff management & roles',
                ],
                'branding': 'Minimal "Powered by Flamezo" footer',
                'qr_logo': 'Your custom restaurant logo on QR codes'
            }
        }
    }


@frappe.whitelist()
def get_upgrade_benefits(restaurant_id):
    """
    Get personalized upgrade benefits for a restaurant
    
    Args:
        restaurant_id (str): Restaurant ID
    
    Returns:
        dict: Upgrade benefits and recommendations
    """
    restaurant = frappe.get_doc('Restaurant', restaurant_id)
    
    already_gold = restaurant.plan_type == 'GOLD'
    return {
        'already_gold': already_gold,
        'current_plan': restaurant.plan_type,
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
                    f'Just {float(restaurant.platform_fee_percent or frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent") or 1.5)}% commission — only pay when you earn',
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
        'cta': 'Upgrade to GOLD to own and grow your customer relationships'
    }
