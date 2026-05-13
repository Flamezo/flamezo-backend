# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
API endpoints for UI - doctype meta, permissions, etc.
"""

import frappe
from frappe import _
import json


@frappe.whitelist()
def get_doctype_meta(doctype):
	"""Get doctype metadata including fields and permissions"""
	try:
		meta = frappe.get_meta(doctype)
		
		# Get fields - meta.fields is a list of DocField objects
		fields = []
		if meta.fields:
			for field in meta.fields:
				# Skip system fields and section breaks
				if field.fieldtype in ['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button']:
					continue
				
				field_data = {
					'fieldname': field.fieldname,
					'label': field.label or field.fieldname,
					'fieldtype': field.fieldtype,
					'options': getattr(field, 'options', None),
					'required': getattr(field, 'reqd', 0) == 1,
					'read_only': getattr(field, 'read_only', 0) == 1,
					'default': getattr(field, 'default', None),
					'description': getattr(field, 'description', None),
					'hidden': getattr(field, 'hidden', 0) == 1,
					'depends_on': getattr(field, 'depends_on', None),
					'fetch_from': getattr(field, 'fetch_from', None),
				}
				
				# Add child table info
				if field.fieldtype == 'Table':
					field_data['child_doctype'] = field.options
				
				fields.append(field_data)
		
		# Get permissions for current user
		permissions = get_user_permissions(doctype)
		
		# Check if workflow exists
		has_workflow = False
		try:
			from frappe.model.workflow import get_workflow_name
			workflow_name = get_workflow_name(doctype)
			has_workflow = bool(workflow_name)
		except:
			pass
		
		# Return in format expected by frappe-react-sdk (wrapped in 'message')
		return {
			'doctype': doctype,
			'name_field': meta.get('title_field') or 'name',
			'autoname': meta.get('autoname'),
			'fields': fields,
			'permissions': permissions,
			'is_submittable': getattr(meta, 'is_submittable', 0) == 1,
			'has_workflow': has_workflow,
		}
	except Exception as e:
		frappe.log_error(f"Error getting doctype meta for {doctype}: {str(e)}")
		return {
			'success': False,
			'error': str(e)
		}


@frappe.whitelist()
def get_user_permissions(doctype):
	"""Get user permissions for a doctype"""
	try:
		user = frappe.session.user
		
		# Check permissions
		can_read = frappe.has_permission(doctype, 'read', user=user)
		can_write = frappe.has_permission(doctype, 'write', user=user)
		can_create = frappe.has_permission(doctype, 'create', user=user)
		can_delete = frappe.has_permission(doctype, 'delete', user=user)
		can_submit = frappe.has_permission(doctype, 'submit', user=user) if frappe.get_meta(doctype).is_submittable else False
		can_cancel = frappe.has_permission(doctype, 'cancel', user=user) if frappe.get_meta(doctype).is_submittable else False
		
		return {
			'read': can_read,
			'write': can_write,
			'create': can_create,
			'delete': can_delete,
			'submit': can_submit,
			'cancel': can_cancel,
		}
	except Exception as e:
		frappe.log_error(f"Error getting permissions: {str(e)}")
		return {
			'read': False,
			'write': False,
			'create': False,
			'delete': False,
			'submit': False,
			'cancel': False,
		}





@frappe.whitelist()
def get_user_restaurants():
	"""Get restaurants that the current user has permission to access"""
	try:
		from dinematters.dinematters.utils.permissions import get_user_restaurant_ids
		
		user = frappe.session.user
		restaurant_ids = get_user_restaurant_ids(user)
		
		if not restaurant_ids:
			return {
				'restaurants': []
			}
		
		# Get restaurant details - using ignore_permissions for the IDs we already verified
		restaurants = frappe.get_all(
			"Restaurant",
			filters={"name": ["in", restaurant_ids]},
			fields=["name", "restaurant_id", "restaurant_name", "owner_email", "is_active", "plan_type", "city", "state", "creation", "modified", "company", "logo"],
			order_by="creation desc",
			ignore_permissions=True
		)
		
		return {
			'restaurants': restaurants
		}
	except Exception as e:
		frappe.log_error(f"Error getting user restaurants for {frappe.session.user}: {str(e)}")
		return {
			'restaurants': [],
			'error': str(e)
		}


@frappe.whitelist()
def get_restaurant_setup_progress(restaurant_id):
	"""Get setup progress for a restaurant - check which steps are completed"""
	try:
		from dinematters.dinematters.utils.permissions import validate_restaurant_access
		
		# Validate user has access
		if not validate_restaurant_access(frappe.session.user, restaurant_id):
			frappe.throw("You don't have permission to access this restaurant")
		
		progress = {
			'restaurant': frappe.db.exists("Restaurant", restaurant_id),
			'config': frappe.db.exists("Restaurant Config", {"restaurant": restaurant_id}),
			'users': frappe.db.exists("Restaurant User", {"restaurant": restaurant_id}),
			'categories': frappe.db.exists("Menu Category", {"restaurant": restaurant_id}),
			'products': frappe.db.exists("Menu Product", {"restaurant": restaurant_id}),
			'offers': frappe.db.exists("Offer", {"restaurant": restaurant_id}),
			'coupons': frappe.db.exists("Coupon", {"restaurant": restaurant_id}),
			'events': frappe.db.exists("Event", {"restaurant": restaurant_id}),
			'games': frappe.db.exists("Game", {"restaurant": restaurant_id}),
			'home_features': frappe.db.exists("Home Feature", {"restaurant": restaurant_id}),
			'table_booking': frappe.db.exists("Table Booking", {"restaurant": restaurant_id}),
			'banquet_booking': frappe.db.exists("Banquet Booking", {"restaurant": restaurant_id}),
		}
		
		return progress
	except Exception as e:
		frappe.log_error(f"Error getting restaurant setup progress: {str(e)}")
		return {
			'error': str(e)
		}


@frappe.whitelist()
def get_setup_wizard_steps(restaurant=None):
	"""Get steps for restaurant setup wizard - tier-aware filtering"""
	plan_type = 'GOLD' # Default to GOLD to see all steps for admin/system
	if restaurant:
		plan_type = frappe.db.get_value('Restaurant', restaurant, 'plan_type') or 'SILVER'

	all_steps = [
		{
			'id': 'restaurant',
			'title': 'Create Restaurant',
			'description': 'Set up your restaurant basic information (name, address, owner details)',
			'doctype': 'Restaurant',
			'required': True,
			'depends_on': None,
		},
		{
			'id': 'config',
			'title': 'Restaurant Configuration',
			'description': 'Configure branding, colors, settings, tax, delivery fees, and features',
			'doctype': 'Restaurant Config',
			'required': True,
			'depends_on': 'restaurant',
		},
		{
			'id': 'users',
			'title': 'Staff Members',
			'description': 'View and manage staff members for your restaurant (Owner is automatically created)',
			'doctype': 'Restaurant User',
			'required': False,
			'depends_on': 'restaurant',
			'view_only': True,
		},
		{
			'id': 'categories',
			'title': 'Menu Categories',
			'description': 'View and manage menu categories for your restaurant',
			'doctype': 'Menu Category',
			'required': False,
			'depends_on': 'restaurant',
			'view_only': True,
		},
		{
			'id': 'products',
			'title': 'Menu Products',
			'description': 'View and manage menu products for your restaurant',
			'doctype': 'Menu Product',
			'required': False,
			'depends_on': 'restaurant',
			'view_only': True,
		},
		{
			'id': 'coupons',
			'title': 'Create Coupons',
			'description': 'Set up discount coupons for customers',
			'doctype': 'Coupon',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'coupons'
		},
		{
			'id': 'events',
			'title': 'Create Events',
			'description': 'Set up events, special occasions, or themed nights',
			'doctype': 'Event',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'events'
		},
		{
			'id': 'games',
			'title': 'Add Games',
			'description': 'Add interactive games for customer engagement',
			'doctype': 'Game',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'games'
		},
		{
			'id': 'home_features',
			'title': 'Home Features',
			'description': 'Configure features to display on your restaurant homepage',
			'doctype': 'Home Feature',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'home_features'
		},
		{
			'id': 'table_booking',
			'title': 'Table Booking Setup',
			'description': 'Configure table booking settings and availability',
			'doctype': 'Table Booking',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'table_booking'
		},
		{
			'id': 'banquet_booking',
			'title': 'Banquet Booking Setup',
			'description': 'Set up banquet and large party booking options',
			'doctype': 'Banquet Booking',
			'required': False,
			'depends_on': 'restaurant',
			'feature': 'table_booking'
		},
		{
			'id': 'legacy',
			'title': 'Legacy Content',
			'description': 'Configure your restaurant story, heritage, testimonials, and gallery',
			'doctype': 'Legacy Content',
			'required': False,
			'depends_on': 'restaurant',
		},
	]

	from dinematters.dinematters.utils.feature_gate import FEATURE_PLAN_MAP
	
	filtered_steps = []
	for step in all_steps:
		feature = step.get('feature')
		if not feature:
			filtered_steps.append(step)
			continue
			
		required_plans = FEATURE_PLAN_MAP.get(feature, ['SILVER', 'GOLD'])
		if plan_type in required_plans:
			step_copy = step.copy()
			step_copy['required_plans'] = required_plans
			filtered_steps.append(step_copy)
			
	return {
		'steps': filtered_steps
	}

