# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Migration Script: Add Subscription Fields to Restaurant

This script migrates existing restaurants to the new subscription model:
1. Sets all existing restaurants to GOLD plan (to avoid disruption)
2. Initializes subscription fields with default values
3. Sets plan activation date to current date
"""

import frappe
from frappe import _


def execute():
	"""Execute migration for subscription model"""
	frappe.logger().info("Starting subscription model migration...")
	
	try:
		# Get all existing restaurants
		restaurants = frappe.get_all('Restaurant', fields=['name', 'restaurant_name'])
		
		frappe.logger().info(f"Found {len(restaurants)} restaurants to migrate")
		
		migrated_count = 0
		error_count = 0
		
		import json
		now = frappe.utils.now()
		
		for restaurant in restaurants:
			try:
				# Use SQL update to avoid validation issues
				plan_change_history = json.dumps([{
					'date': now,
					'from': None,
					'to': 'GOLD',
					'by': 'Administrator',
					'reason': 'Initial migration - all existing restaurants set to GOLD plan'
				}])
				
				frappe.db.sql("""
					UPDATE `tabRestaurant`
					SET 
						plan_type = 'GOLD',
						plan_activated_on = %s,
						plan_changed_by = 'Administrator',
						max_images_silver = 200,
						current_image_count = 0,
						total_orders = 0,
						total_revenue = 0,
						commission_earned = 0,
						plan_change_history = %s,
						modified = %s,
						modified_by = 'Administrator'
					WHERE name = %s
				""", (now, plan_change_history, now, restaurant.name))
				
				migrated_count += 1
				
				# Create initial Plan Change Log
				try:
					plan_log = frappe.get_doc({
						'doctype': 'Plan Change Log',
						'restaurant': restaurant.name,
						'previous_plan': '',
						'new_plan': 'GOLD',
						'changed_by': 'Administrator',
						'changed_on': now,
						'change_reason': 'Initial migration - all existing restaurants set to GOLD plan',
						'ip_address': 'Migration Script'
					})
					plan_log.flags.ignore_permissions = True
					plan_log.insert(ignore_permissions=True)
				except Exception as log_error:
					# Log error but don't fail migration
					frappe.logger().error(f"Error creating plan log for {restaurant.name}: {str(log_error)}")
				
			except Exception as e:
				error_count += 1
				frappe.logger().error(f"Error migrating restaurant {restaurant.name}: {str(e)}")
				continue
		
		frappe.db.commit()
		
		# Log summary
		frappe.logger().info(f"Migration completed: {migrated_count} restaurants migrated, {error_count} errors")
		
		if error_count > 0:
			frappe.logger().warning(f"Migration completed with {error_count} errors. Check error logs for details.")
		
		print(f"✅ Subscription model migration completed successfully!")
		print(f"   - Migrated: {migrated_count} restaurants")
		print(f"   - Errors: {error_count}")
		print(f"   - All existing restaurants set to GOLD plan")
		
	except Exception as e:
		frappe.logger().error(f"Fatal error during migration: {str(e)}")
		frappe.db.rollback()
		raise
