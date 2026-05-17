# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
import json

def notify_order_update(doc, method=None):
	"""
	Publishes real-time update when an Order is created or updated.
	Event: 'order_update'
	Room: User-specific or Session-specific
	
	Also enqueues a free FCM Web Push notification so customers are notified
	even when their browser tab is closed / in background.
	"""
	try:
		# ── Socket.IO realtime (instant, requires tab open) ──────────────────
		if doc.customer:
			frappe.publish_realtime(
				event='order_update',
				message={'id': doc.order_id, 'status': doc.status, 'order_number': doc.order_number},
				user=doc.customer
			)
		
		# Also notify via phone if platform_customer exists (for guests who verified phone)
		if doc.platform_customer:
			frappe.publish_realtime(
				event='order_update',
				message={'id': doc.order_id, 'status': doc.status, 'order_number': doc.order_number},
				room=f"customer:{doc.platform_customer}"
			)

		# Also notify the restaurant dashboard (merchants see live order updates)
		if doc.restaurant:
			frappe.publish_realtime(
				event='order_update',
				message={
					'id': doc.order_id,
					'status': doc.status,
					'order_number': doc.order_number,
					'restaurant': doc.restaurant
				},
				room=f"restaurant:{doc.restaurant}"
			)

		# ── FCM Web Push (background tab / closed browser) ───────────────────
		# Enqueue as a background job so doc_event doesn't block the request.
		# Cost: ZERO — FCM sends web push for free.
		statuses_that_need_push = [
			'confirmed', 'preparing', 'ready', 'delivered', 'billed', 'cancelled'
		]
		if (doc.status or '').lower() in statuses_that_need_push:
			frappe.enqueue(
				'flamezo_backend.flamezo.api.push_notifications.send_order_status_push_to_customer',
				order_name=doc.name,
				queue='short',
				timeout=30,
				is_async=True
			)
	except Exception as e:
		frappe.log_error(f"Error in notify_order_update: {str(e)}", "Realtime Update Error")

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

def notify_cart_update(doc, method=None):
	"""
	Publishes real-time update when a Cart Entry is modified.
	Event: 'cart_update'
	"""
	try:
		if doc.user:
			frappe.publish_realtime(
				event='cart_update',
				message={'restaurantId': doc.restaurant},
				user=doc.user
			)
		elif doc.session_id:
			frappe.publish_realtime(
				event='cart_update',
				message={'restaurantId': doc.restaurant},
				room=f"session:{doc.session_id}"
			)
	except Exception as e:
		frappe.log_error(f"Error in notify_cart_update: {str(e)}", "Realtime Update Error")

def notify_new_order_to_merchant(doc, method=None):
	"""
	Fires when a new Order is inserted.
	Sends a free FCM push to all logged-in merchant devices so they never
	miss an order even if the dashboard tab is minimised.
	"""
	try:
		if doc.status in ('confirmed', 'pending_verification', 'Pending Verification'):
			frappe.enqueue(
				'flamezo_backend.flamezo.api.push_notifications.send_new_order_push_to_merchant',
				order_name=doc.name,
				queue='short',
				timeout=30,
				is_async=True
			)
	except Exception as e:
		frappe.log_error(f"Error in notify_new_order_to_merchant: {str(e)}", "Realtime Update Error")


def notify_whatsapp_intent(doc):
	"""
	Publishes real-time update to the restaurant dashboard when a WhatsApp order 
	intent is captured (shadow order).
	Event: 'whatsapp_intent'
	Room: Restaurant-specific
	"""
	try:
		frappe.publish_realtime(
			event='whatsapp_intent',
			message={
				'name': doc.name,
				'order_number': doc.order_number,
				'customer_name': doc.customer_name,
				'total': doc.total,
				'creation': doc.creation
			},
			room=f"restaurant:{doc.restaurant}"
		)
	except Exception as e:
		frappe.log_error(f"Error in notify_whatsapp_intent: {str(e)}", "Realtime Update Error")
