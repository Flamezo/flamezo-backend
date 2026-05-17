# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

"""
API endpoint for updating order status without validation issues
"""

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.feature_gate import require_plan


@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def update_status(order_id, status):
	"""
	Update order status using db.set_value to bypass full document validation
	This is used by the Kanban drag-and-drop functionality
	"""
	try:
		# Check if order exists
		if not frappe.db.exists("Order", order_id):
			frappe.throw(_("Order {0} not found").format(order_id))
		
		# Validate status
		valid_statuses = [
			"Pending Payment", "Pending Verification", "Auto Accepted", "Accepted",
			"pending_verification", "confirmed", "preparing", "ready", "In Billing", "delivered", "billed", "cancelled"
		]
		if status not in valid_statuses:
			frappe.throw(_("Invalid status. Must be one of: {0}").format(", ".join(valid_statuses)))
		
		# Update only the status field using db.set_value (bypasses validation)
		frappe.db.set_value("Order", order_id, "status", status, update_modified=True)
		frappe.db.commit()
		
		return {
			"success": True,
			"message": _("Order status updated successfully"),
			"data": {
				"order_id": order_id,
				"status": status
			}
		}
		
	except Exception as e:
		frappe.log_error(f"Error updating order status: {str(e)}")
		frappe.throw(_("Failed to update order status: {0}").format(str(e)))


@frappe.whitelist()
def update_table_number(order_id, table_number):
	"""
	Update order table_number using db.set_value to bypass full document validation
	This is used by the frontend to change table numbers
	"""
	try:
		# Check if order exists
		if not frappe.db.exists("Order", order_id):
			frappe.throw(_("Order {0} not found").format(order_id))
		
		# Validate table_number (can be None or a positive integer)
		if table_number is not None:
			try:
				table_number = int(table_number)
				# Allow table 0 as a valid value (represents 'no table assigned')
				if table_number < 0:
					frappe.throw(_("Table number must be zero or a positive integer"))
			except (ValueError, TypeError):
				frappe.throw(_("Table number must be a valid integer or null"))
		
		# Update only the table_number field using db.set_value (bypasses validation)
		frappe.db.set_value("Order", order_id, "table_number", table_number, update_modified=True)
		frappe.db.commit()
		
		return {
			"success": True,
			"message": _("Order table number updated successfully"),
			"data": {
				"order_id": order_id,
				"table_number": table_number
			}
		}
		
	except Exception as e:
		frappe.log_error(f"Error updating order table number: {str(e)}")
		frappe.throw(_("Failed to update order table number: {0}").format(str(e)))


