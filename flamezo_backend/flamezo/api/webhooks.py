"""
Razorpay Webhook Handler for Flamezo
"""

import frappe
import json
import hmac
import hashlib
from frappe import _
from datetime import datetime
from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config, get_razorpay_client
from flamezo_backend.flamezo.utils import commission_engine
from flamezo_backend.flamezo.utils import razorpay_route as route_adapter


def verify_razorpay_signature(body, signature, webhook_secret):
	"""Verify Razorpay webhook signature"""
	if not webhook_secret:
		frappe.throw(_("Razorpay webhook secret not configured"))
	
	generated_signature = hmac.new(
		webhook_secret.encode('utf-8'),
		body,
		hashlib.sha256
	).hexdigest()
	
	return hmac.compare_digest(generated_signature, signature)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def razorpay_webhook():
	"""Handle Razorpay webhook events"""
	try:
		# Get raw request data
		request = frappe.local.request
		body = request.get_data()
		signature = request.headers.get("X-Razorpay-Signature", "")
		
		# Webhook secret: under the May 2026 Route hybrid model, there are
		# no per-restaurant Razorpay keys — every webhook is signed by
		# Flamezo's platform secret. `get_razorpay_config()` returns the
		# platform live/test secret based on `razorpay_live_mode`.
		cfg = get_razorpay_config()
		webhook_secret = cfg.get("webhook_secret")

		# Verify signature
		if not verify_razorpay_signature(body, signature, webhook_secret):
			frappe.log_error("Invalid Razorpay webhook signature", "razorpay.webhook")
			frappe.throw(_("Invalid signature"))
		
		# Parse payload
		payload = json.loads(body.decode('utf-8'))
		event_type = payload.get("event")
		
		# Log webhook for audit
		frappe.log_error(f"Razorpay Webhook: {event_type}\n{json.dumps(payload, indent=2)}", "razorpay.webhook.received")
		
		# Check for duplicate events using event ID
		event_id = payload.get("event_id")
		if event_id and frappe.db.exists("Razorpay Webhook Log", {"event_id": event_id}):
			frappe.log_error(f"Duplicate webhook event: {event_id}", "razorpay.webhook.duplicate")
			return {"success": True, "message": "Duplicate event ignored"}
		
		# Create webhook log entry
		webhook_log = frappe.get_doc({
			"doctype": "Razorpay Webhook Log",
			"event_id": event_id,
			"event_type": event_type,
			"payload": json.dumps(payload),
			"processed": False
		})
		try:
			webhook_log.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(f"Failed to insert webhook log: {event_id}", "razorpay.webhook.log_insert")

		# Enqueue processing
		try:
			frappe.enqueue('flamezo_backend.flamezo.api.webhook_worker.process_webhook_log',
				webhook_log_name=webhook_log.name,
				queue='long',
				timeout=600,
				user='Administrator'
			)
		except Exception as e:
			frappe.log_error(f"Failed to enqueue webhook processing: {str(e)}", "razorpay.webhook.enqueue_error")

		return {"success": True, "message": "Webhook received"}
		
	except Exception as e:
		frappe.log_error(f"Razorpay webhook processing failed: {str(e)}", "razorpay.webhook.error")
		return {"success": False, "error": str(e)}


def handle_payment_captured(payload):
	"""Handle payment.captured, order.paid, and payment.authorized events"""
	try:
		event = payload.get("event")
		payment_data = payload.get("payload", {}).get("payment", {}).get("entity", {})
		order_data = payload.get("payload", {}).get("order", {}).get("entity", {})
		
		order_id = payment_data.get("order_id") or order_data.get("id")
		payment_id = payment_data.get("id")
		
		notes = payment_data.get("notes") or order_data.get("notes") or {}
		restaurant_from_notes = notes.get("restaurant_id")
		request_type = notes.get("type")
		
		# Handle Mandate Tokenization
		if request_type == "tokenization" or (order_id and notes.get("attempt_id")):
			try:
				customer_id = payment_data.get("customer_id") or payment_data.get("customer")
				# Multi-method token extraction (Card, UPI, Netbanking)
				token_id = (
					payment_data.get("token_id") or 
					payment_data.get("token") or 
					(payment_data.get("card") or {}).get("token") or 
					(payment_data.get("card") or {}).get("token_id") or
					payload.get("payload", {}).get("token", {}).get("entity", {}).get("id") or
					payload.get("payload", {}).get("token", {}).get("entity", {}).get("token")
				)

				if restaurant_from_notes and frappe.db.exists("Restaurant", restaurant_from_notes):
					if customer_id:
						frappe.db.set_value("Restaurant", restaurant_from_notes, "razorpay_customer_id", customer_id)
					if token_id:
						frappe.db.set_value("Restaurant", restaurant_from_notes, {
							"razorpay_token_id": token_id, 
							"mandate_status": "active"
						})
					frappe.db.commit()
				
				# Log capture in Tokenization Attempt
				attempt_id = notes.get("attempt_id") or order_id
				if attempt_id and frappe.db.exists("Tokenization Attempt", attempt_id):
					frappe.db.set_value("Tokenization Attempt", attempt_id, {
						"razorpay_payment_id": payment_id,
						"customer_id": customer_id,
						"token_id": token_id,
						"status": "captured",
						"processed": 1
					})
					frappe.db.commit()

				return {"success": True, "message": "Tokenization recorded", "payment_id": payment_id}
			except Exception as e:
				frappe.log_error(f"Failed to persist tokenization info: {str(e)}", "razorpay.webhook.token_save")
				return {"error": str(e)}

		# Handle Coin Purchase
		if request_type == "coin_purchase":
			try:
				restaurant = restaurant_from_notes or notes.get("restaurant")
				coins = float(notes.get("coins") or 0)
				if restaurant and coins > 0:
					from flamezo_backend.flamezo.api.coin_billing import record_transaction
					record_transaction(
						restaurant=restaurant,
						txn_type="Purchase",
						amount=coins,
						description=f"Coin Purchase: {coins} Coins",
						payment_id=payment_id
					)
					return {"success": True, "message": "Coins added successfully"}
			except Exception as e:
				frappe.log_error(f"Coin purchase failed: {str(e)}", "razorpay.webhook.coin_purchase")
				return {"error": str(e)}

		# Handle Auto-Recharge (async bank confirmation e.g. HDFC, Axis)
		if request_type == "auto_recharge":
			try:
				restaurant = restaurant_from_notes or notes.get("restaurant")
				if restaurant and frappe.db.exists("Restaurant", restaurant):
					from flamezo_backend.flamezo.api.coin_billing import _credit_autopay_coins
					threshold = frappe.db.get_value("Restaurant", restaurant, "auto_recharge_threshold") or 300
					recharge_amt = float(payment_data.get("amount") or 0) / 100.0
					
					# Derive base amount if GST was included
					# In trigger_auto_recharge, we now store base_amount in notes
					base_amount = notes.get("base_amount")
					gst_amount = notes.get("gst_amount")
					total_payable = notes.get("total_payable")

					if not base_amount:
						# Fallback for legacy or if notes missing: Assume 18% GST was included
						base_amount = round(recharge_amt / 1.18, 2)
						gst_amount = round(recharge_amt - base_amount, 2)
						total_payable = recharge_amt

					if base_amount > 0:
						_credit_autopay_coins(restaurant, float(base_amount), payment_id, threshold, gst_amount=float(gst_amount or 0), total_paid=float(total_payable or recharge_amt))
						return {"success": True, "message": f"Auto-recharge coins credited for {restaurant}", "credited": base_amount}
			except Exception as e:
				frappe.log_error(f"Auto-recharge webhook credit failed: {str(e)}", "razorpay.webhook.auto_recharge")
				return {"error": str(e)}

		# Handle Monthly Bill payment confirmation
		if request_type == "monthly_bill":
			try:
				ledger_name = notes.get("ledger")
				if ledger_name and frappe.db.exists("Monthly Billing Ledger", ledger_name):
					frappe.db.set_value("Monthly Billing Ledger", ledger_name, {
						"payment_status": "paid",
						"razorpay_payment_id": payment_id
					})
					frappe.db.commit()
					return {"success": True, "message": f"Monthly bill {ledger_name} marked paid"}
			except Exception as e:
				frappe.log_error(f"Monthly bill webhook failed: {str(e)}", "razorpay.webhook.monthly_bill")
				return {"error": str(e)}

		# Handle Cash Commission Sweep (Tier 2 autopay) — distribute captured
		# amount across open ledgers FIFO, reset failure counter.
		if request_type == "cash_sweep":
			try:
				restaurant = restaurant_from_notes or notes.get("restaurant")
				amount_paise = int(payment_data.get("amount") or notes.get("outstanding_paise") or 0)
				if restaurant and amount_paise > 0:
					applied = commission_engine.apply_autopay_sweep_capture(
						restaurant=restaurant,
						amount_paise=amount_paise,
						razorpay_payment_id=payment_id,
					)
					return {"success": True, "cash_sweep_applied_paise": applied, "restaurant": restaurant}
			except Exception as e:
				frappe.log_error(f"Cash sweep webhook failed: {str(e)}", "razorpay.webhook.cash_sweep")
				return {"error": str(e)}

		# Handle Standard Order Payment
		if order_id:
			orders = frappe.get_all(
				"Order",
				filters={"razorpay_order_id": order_id},
				fields=["name", "restaurant", "total", "platform_fee_amount",
				        "cash_netoff_applied_paise", "settlement_mode"],
			)
			if orders:
				order_row = orders[0]
				order_name = order_row.name

				# Persist Route transfer_id (if any) so refunds can reverse
				# the merchant slice. Razorpay surfaces it under
				# payload.payment.entity.transfers[0].id once the split runs.
				transfer_id = None
				try:
					transfer_entities = (
						payment_data.get("transfers") or
						payload.get("payload", {}).get("transfer", {}).get("entity", {}) or {}
					)
					if isinstance(transfer_entities, list) and transfer_entities:
						transfer_id = transfer_entities[0].get("id")
					elif isinstance(transfer_entities, dict):
						transfer_id = transfer_entities.get("id")
				except Exception:
					transfer_id = None

				order_update = {
					"razorpay_payment_id": payment_id,
					"transaction_id": payment_id,
					"payment_status": "completed",
					"status": "Auto Accepted",
				}
				if transfer_id:
					order_update["razorpay_transfer_id"] = transfer_id
				frappe.db.set_value("Order", order_name, order_update)
				frappe.db.commit()

				# Tier 1 net-off: record settlement against open Commission
				# Ledger Entries for the portion of the platform-side capture
				# that was earmarked for cash debt recovery.
				netoff_paise = int(order_row.get("cash_netoff_applied_paise") or 0)
				if netoff_paise > 0:
					try:
						commission_engine.apply_online_netoff(
							restaurant=order_row.restaurant,
							online_order_name=order_name,
							netoff_amount_paise=netoff_paise,
							razorpay_payment_id=payment_id,
						)
					except Exception as e:
						frappe.log_error(
							f"Tier 1 net-off settlement failed for order {order_name}: {e}",
							"commission_engine.tier1.webhook",
						)

				# Update monthly ledger
				update_monthly_ledger(order_row.restaurant, order_row.total, order_row.platform_fee_amount)
				return {"success": True, "order_updated": order_name, "netoff_applied_paise": netoff_paise}

		return {"success": True, "message": "Event processed but no specific action taken"}
		
	except Exception as e:
		frappe.log_error(f"Payment capture handler failed: {str(e)}", "razorpay.webhook.payment_captured")
		return {"error": str(e)}


def handle_refund_processed(payload):
	"""Handle refund.processed and refund.created events.

	For Route direct_split orders, Razorpay's `reverse_all=1` flag on the
	refund auto-claws back the merchant portion — we don't need to call the
	reversal API here. If the refund was initiated without reverse_all, the
	platform eats the merchant slice (a deliberate ops choice).

	For cash orders that somehow received a Razorpay refund (shouldn't happen
	normally — cash refunds go cash-out), we void the Commission Ledger
	Entry. This is the safety net.
	"""
	try:
		refund_data = payload.get("payload", {}).get("refund", {}).get("entity", {})
		payment_id = refund_data.get("payment_id")
		refund_amount = refund_data.get("amount") or 0

		orders = frappe.get_all(
			"Order",
			filters={"razorpay_payment_id": payment_id},
			fields=["name", "restaurant", "total", "platform_fee_amount", "settlement_mode"],
		)

		if orders:
			order = frappe.get_doc("Order", orders[0].name)
			total_amount_paise = int(order.total * 100)
			refund_ratio = (refund_amount / total_amount_paise) if total_amount_paise else 0
			platform_fee_refund = int((order.platform_fee_amount or 0) * refund_ratio)

			full_refund = refund_amount >= total_amount_paise
			if full_refund:
				frappe.db.set_value("Order", order.name, {"payment_status": "refunded", "status": "cancelled"})
			else:
				frappe.db.set_value("Order", order.name, "payment_status", "partially_refunded")

			frappe.db.commit()
			reverse_monthly_ledger(order.restaurant, refund_amount, platform_fee_refund)

			# Cashback clawback on PARTIAL refunds — proportional to the refunded
			# fraction. (Full refunds set status='cancelled' above, which fires
			# handle_order_cancellation to reverse the FULL cashback; we skip full
			# here to avoid a double reversal.) Idempotent per refund id.
			if not full_refund and order.platform_customer and int(order.coins_earned or 0) > 0:
				from flamezo_backend.flamezo.utils.loyalty import reverse_earned_cashback
				refund_id = refund_data.get("id")
				to_reverse = int(round(int(order.coins_earned or 0) * refund_ratio))
				if to_reverse > 0:
					reverse_earned_cashback(
						customer=order.platform_customer,
						restaurant=order.restaurant,
						coins_to_reverse=to_reverse,
						reason="Refund Reversal",
						description=(f"Order {order.name} partially refunded ₹{int(refund_amount / 100)} "
						             f"(refund {refund_id}) — ₹{to_reverse} cashback reversed"),
						ref_doctype="Order",
						ref_name=order.name,
						refund_id=refund_id,
					)
					frappe.db.commit()

			# If this order had a cash ledger entry (extremely rare — implies
			# a cash order that was later upgraded to online refund), void it
			# on full refund only.
			if full_refund:
				try:
					commission_engine.void_for_order(order.name, reason="Order fully refunded via Razorpay")
				except Exception as e:
					frappe.log_error(
						f"Failed to void commission ledger on refund for {order.name}: {e}",
						"commission_engine.refund_void",
					)

		return {"success": True, "refund_processed": True}
	except Exception as e:
		frappe.log_error(f"Refund handler failed: {str(e)}", "razorpay.webhook.refund")
		return {"error": str(e)}


def handle_account_status(payload):
	"""Handle `account.*` events from Razorpay Route Linked Account onboarding.

	Razorpay emits these as the KYC team reviews submitted documents.
	Statuses we care about: `under_review`, `needs_clarification`,
	`activated`, `rejected`, `suspended`.

	The Route adapter owns the status mapping + side effects (e.g. promoting
	the restaurant from flamezo_hold → direct_split on activation). We just
	dispatch.
	"""
	try:
		event = payload.get("event") or ""
		entity = (
			payload.get("payload", {}).get("account", {}).get("entity")
			or payload.get("payload", {}).get("account_v2", {}).get("entity")
			or {}
		)
		account_id = entity.get("id") or payload.get("account_id")
		# Status may live under `status` or be derived from the event suffix
		# (e.g. account.activated → activated).
		status = (entity.get("status") or "").lower()
		if not status and "." in event:
			status = event.split(".", 1)[1]

		if not account_id:
			return {"success": False, "error": "no_account_id"}

		route_adapter.update_kyc_status(account_id, status, raw_event=payload)
		return {"success": True, "account_id": account_id, "status": status}
	except Exception as e:
		frappe.log_error(f"Account status handler failed: {str(e)}", "razorpay.webhook.account")
		return {"error": str(e)}


def handle_transfer_event(payload):
	"""Handle `transfer.*` events.

	The Route split itself is processed automatically by Razorpay; we mainly
	use these for audit + to record the `transfer_id` against the order
	(also captured on payment.captured as a belt-and-suspenders fallback).
	`transfer.failed` is the interesting one — it means the split couldn't
	be completed, the full amount stayed in Flamezo's account, and we need
	to flag the order for manual settlement.
	"""
	try:
		event = payload.get("event") or ""
		entity = payload.get("payload", {}).get("transfer", {}).get("entity", {})
		transfer_id = entity.get("id")
		source_order_id = entity.get("source")  # Razorpay order id
		notes = entity.get("notes") or {}

		# Lookup our internal Order by Razorpay order id
		order_name = notes.get("order") or frappe.db.get_value(
			"Order", {"razorpay_order_id": source_order_id}, "name"
		)
		if not order_name:
			return {"success": True, "message": "transfer event for unknown order"}

		update = {}
		if transfer_id:
			update["razorpay_transfer_id"] = transfer_id

		if event == "transfer.failed":
			# Bail out of split — order now sits in flamezo_hold for manual
			# settlement. The amount Flamezo collected won't increase, but
			# it also means we don't owe a transfer that was never sent.
			update["settlement_mode"] = "flamezo_hold"
			frappe.log_error(
				f"Transfer.failed for order {order_name}: {entity!r}",
				"razorpay.webhook.transfer_failed",
			)

		if update:
			frappe.db.set_value("Order", order_name, update)
			frappe.db.commit()

		return {"success": True, "event": event, "order": order_name}
	except Exception as e:
		frappe.log_error(f"Transfer handler failed: {str(e)}", "razorpay.webhook.transfer")
		return {"error": str(e)}


def handle_payment_link_paid(payload):
	"""Handle payment_link.paid event.
	Supports two flows:
	  1. wallet_topup_plink — Admin-created link for wallet top-up (GOLD).
	     Auto-credits the restaurant wallet via record_transaction (idempotent).
	  2. Legacy monthly revenue ledger payment links (existing behaviour).
	"""
	try:
		event = payload.get("event")
		payment_link_data = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
		payment_link_id = payment_link_data.get("id")
		notes = payment_link_data.get("notes", {}) or {}

		# ── Wallet Top-up via Admin Payment Link ────────────────────────────
		plink_type = notes.get("type")
		if plink_type == "wallet_topup_plink":
			restaurant_name = notes.get("restaurant")  # Frappe doc name
			tier = notes.get("tier", "")

			if not restaurant_name or not frappe.db.exists("Restaurant", restaurant_name):
				frappe.log_error(
					f"payment_link.paid: restaurant '{restaurant_name}' not found in notes for plink {payment_link_id}",
					"razorpay.wallet_topup_plink"
				)
				return {"success": False, "error": "Restaurant not found"}

			# Fetch the actual paid amount from Razorpay's event payload
			amount_paid_paise = payment_link_data.get("amount_paid") or payment_link_data.get("amount") or 0
			amount_inr = float(amount_paid_paise) / 100.0

			# Prioritize base_amount from notes (GST exclusion logic)
			base_amount = notes.get("base_amount")
			gst_amount = notes.get("gst_amount")
			total_payable = notes.get("total_payable")

			if not base_amount:
				# Fallback: Assume 18% GST was included in the total paid
				base_amount = round(amount_inr / 1.18, 2)
				gst_amount = round(amount_inr - base_amount, 2)
				total_payable = amount_inr
			
			amount_to_credit = float(base_amount)

			# Get payment_id for idempotency (comes from the payment sub-entity)
			payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
			payment_id = payment_entity.get("id") or payment_link_id

			# Idempotency guard: prevent double-credit for the same payment
			already_credited = frappe.db.exists("Coin Transaction", {
				"restaurant": restaurant_name,
				"payment_id": payment_id,
				"transaction_type": "Purchase"
			})

			if already_credited:
				frappe.log_error(
					f"Wallet topup already credited for payment {payment_id} / plink {payment_link_id}. Skipped.",
					"razorpay.wallet_topup_plink.duplicate"
				)
				return {"success": True, "message": "Already credited (idempotent skip)"}

			description = f"Wallet Top-up via Admin Payment Link — {tier} Plan (₹{int(amount_inr)})"
			if not tier:
				description = f"Manual Wallet Recharge (₹{int(amount_inr)})"

			from flamezo_backend.flamezo.api.coin_billing import record_transaction
			new_balance = record_transaction(
				restaurant=restaurant_name,
				txn_type="Purchase",
				amount=amount_to_credit,
				description=description,
				payment_id=payment_id,
				gst_amount=float(gst_amount or 0),
				total_paid=float(total_payable or amount_inr)
			)
			frappe.db.commit()

			frappe.log_error(
				f"Wallet top-up credited: ₹{amount_to_credit} (Paid ₹{amount_inr}) to {restaurant_name} (tier={tier}). "
				f"New balance: {new_balance}. payment_id={payment_id}",
				"razorpay.wallet_topup_plink.success"
			)
			return {"success": True, "wallet_credited": amount_to_credit, "total_paid": amount_inr, "new_balance": new_balance}

		# ── Legacy: Monthly Revenue Ledger payment links ─────────────────────
		ledgers = frappe.get_all("Monthly Revenue Ledger", filters={"payment_link_id": payment_link_id}, fields=["name"])
		if ledgers:
			frappe.db.set_value("Monthly Revenue Ledger", ledgers[0].name, {
				"status": "paid",
				"paid_date": datetime.now().date()
			})
			frappe.db.commit()

		return {"success": True, "pl_paid": True}

	except Exception as e:
		frappe.log_error(f"Payment link handler failed: {str(e)}", "razorpay.webhook.pl_paid")
		return {"error": str(e)}



def handle_payment_failed(payload):
	"""Handle payment.failed and other failure events"""
	try:
		payment_data = payload.get("payload", {}).get("payment", {}).get("entity", {})
		payment_id = payment_data.get("id")
		
		# Mark ledger failed if applicable
		ledgers = frappe.get_all("Monthly Billing Ledger", filters={"razorpay_payment_id": payment_id}, fields=["name", "restaurant"])
		if ledgers:
			frappe.db.set_value("Monthly Billing Ledger", ledgers[0].name, "payment_status", "failed")
			frappe.db.set_value("Restaurant", ledgers[0].restaurant, "billing_status", "overdue")
			frappe.db.commit()
		return {"success": True, "failure_recorded": True}
	except Exception as e:
		frappe.log_error(f"Payment failure handler failed: {str(e)}", "razorpay.webhook.failed")
		return {"error": str(e)}


def handle_subscription_event(payload):
	"""Handle subscription.* and token.confirmed events"""
	try:
		event = payload.get("event")
		sub_data = payload.get("payload", {}).get("subscription", {}).get("entity", {})
		payment_data = payload.get("payload", {}).get("payment", {}).get("entity", {})
		
		if event == "subscription.charged":
			return handle_payment_captured(payload)
			
		customer_id = sub_data.get("customer_id") or payment_data.get("customer_id") or payload.get("payload", {}).get("token", {}).get("entity", {}).get("customer_id")
		
		# Look for token in all possible sub-payloads (Subscription, Payment, or direct Token entity)
		token_id = (
			payment_data.get("token_id") or 
			payment_data.get("token") or 
			sub_data.get("token_id") or
			payload.get("payload", {}).get("token", {}).get("entity", {}).get("id") or
			payload.get("payload", {}).get("token", {}).get("entity", {}).get("token")
		)
		
		notes = sub_data.get("notes") or payment_data.get("notes") or {}
		restaurant = notes.get("restaurant_id")
		request_type = notes.get("type")
		
		if restaurant and frappe.db.exists("Restaurant", restaurant):
			if event in ["subscription.activated", "subscription.authenticated", "token.confirmed"]:
				frappe.db.set_value("Restaurant", restaurant, "mandate_status", "active")
				if token_id:
					frappe.db.set_value("Restaurant", restaurant, "razorpay_token_id", token_id)
				if customer_id:
					frappe.db.set_value("Restaurant", restaurant, "razorpay_customer_id", customer_id)
				
				# --- Multi-Method Logic: Cancellation & Persistence ---
				if request_type == "tokenization":
					# 1. Update Tokenization Attempt
					attempt_id = notes.get("attempt_id") or sub_data.get("id")
					if attempt_id and frappe.db.exists("Tokenization Attempt", attempt_id):
						frappe.db.set_value("Tokenization Attempt", attempt_id, {
							"customer_id": customer_id,
							"token_id": token_id,
							"status": "captured",
							"processed": 1
						})
					
					# 2. Cancel the Registration-Only Subscription immediately
					if sub_data.get("id") and sub_data.get("status") != "cancelled":
						try:
							client = get_razorpay_client()
							client.subscription.cancel(sub_data.get("id"), {"cancel_at_cycle_end": 0})
						except Exception as e:
							frappe.log_error(f"Failed to cancel registration sub {sub_data.get('id')}: {str(e)}", "razorpay.sub_cancel")

			elif event in ["subscription.paused", "subscription.pending"]:
				frappe.db.set_value("Restaurant", restaurant, "mandate_status", "paused")
			elif event in ["subscription.cancelled", "subscription.halted"]:
				frappe.db.set_value("Restaurant", restaurant, "mandate_status", "inactive")
			
			frappe.db.commit()
			return {"success": True, "event": event, "restaurant": restaurant}
			
		return {"success": True, "message": "No restaurant mapping found"}
	except Exception as e:
		frappe.log_error(f"Subscription handler failed: {str(e)}", "razorpay.webhook.subscription")
		return {"error": str(e)}


def handle_dispute_event(payload):
	"""Handle payment.dispute.* events"""
	try:
		event = payload.get("event")
		dispute_data = payload.get("payload", {}).get("dispute", {}).get("entity", {})
		payment_id = dispute_data.get("payment_id")
		amount = dispute_data.get("amount", 0) / 100.0
		reason = dispute_data.get("reason_code")
		
		msg = f"CRITICAL: Razorpay Dispute {event} for Payment {payment_id}. Amount: INR {amount}. Reason: {reason}"
		frappe.log_error(msg, "razorpay.dispute_alert")
		return {"success": True, "alert_logged": True}
	except Exception:
		return {"success": False}


def handle_operational_event(payload):
	"""Handle informational/ops events (settlements, downtimes)"""
	try:
		return {"success": True, "event_logged": payload.get("event")}
	except Exception:
		return {"success": False}


def update_monthly_ledger(restaurant_id, order_total, platform_fee_amount):
	"""Update monthly revenue ledger with new order"""
	try:
		current_month = datetime.now().strftime("%Y-%m")
		ledger_name = f"MRL-{restaurant_id}-{current_month}"
		
		if not frappe.db.exists("Monthly Revenue Ledger", ledger_name):
			doc = frappe.get_doc({
				"doctype": "Monthly Revenue Ledger",
				"restaurant": restaurant_id,
				"month": current_month,
				"total_gmv": 0,
				"total_platform_fee": 0,
				"minimum_due": 0,
				"status": "pending"
			})
			doc.insert(ignore_permissions=True)
		
		order_total_paise = int(order_total * 100)
		frappe.db.sql(f"""
			UPDATE `tabMonthly Revenue Ledger` 
			SET total_gmv = total_gmv + %s, total_platform_fee = total_platform_fee + %s
			WHERE name = %s
		""", (order_total_paise, float(platform_fee_amount or 0), ledger_name))
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(f"Monthly ledger update failed: {str(e)}", "razorpay.monthly_ledger")


def reverse_monthly_ledger(restaurant_id, refund_amount, platform_fee_refund):
	"""Reverse platform fee in monthly ledger for refunds"""
	try:
		current_month = datetime.now().strftime("%Y-%m")
		ledger_name = f"MRL-{restaurant_id}-{current_month}"
		
		if frappe.db.exists("Monthly Revenue Ledger", ledger_name):
			frappe.db.sql(f"""
				UPDATE `tabMonthly Revenue Ledger` 
				SET total_gmv = GREATEST(0, total_gmv - %s), 
				    total_platform_fee = GREATEST(0, total_platform_fee - %s)
				WHERE name = %s
			""", (refund_amount, platform_fee_refund, ledger_name))
			frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(f"Monthly ledger reversal failed: {str(e)}", "razorpay.monthly_ledger_reverse")