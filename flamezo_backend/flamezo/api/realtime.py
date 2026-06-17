# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
import json

def notify_product_update(doc, method=None):
	"""
	Publishes real-time update when a Menu Product is updated.
	Event: 'product_update'
	Room: Restaurant-specific
	"""
	try:
		frappe.publish_realtime(
			event='product_update',
			message={
				'id': doc.product_id,
				'isActive': doc.is_active,
				'price': doc.price,
				'originalPrice': doc.original_price,
				'restaurantId': doc.restaurant
			},
			room=f"restaurant:{doc.restaurant}"
		)
	except Exception as e:
		frappe.log_error(f"Error in notify_product_update: {str(e)}", "Realtime Update Error")
