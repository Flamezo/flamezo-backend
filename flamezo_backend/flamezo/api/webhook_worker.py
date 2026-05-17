import frappe
import json
from flamezo_backend.flamezo.api.webhooks import (
    handle_payment_captured,
    handle_refund_processed,
    handle_payment_link_paid,
    handle_payment_failed,
    handle_subscription_event,
    handle_dispute_event,
    handle_operational_event
)


def process_webhook_log(webhook_log_name=None, webhook_log_doc=None, **kwargs):
    """Background worker: process a stored webhook log entry.

    Call via:
        frappe.enqueue('flamezo_backend.flamezo.api.webhook_worker.process_webhook_log',
            webhook_log_name='RZP-WH-...', user='Administrator')
    """

    if not webhook_log_doc and not webhook_log_name:
        return

    if not webhook_log_doc:
        webhook_log_doc = frappe.get_doc('Razorpay Webhook Log', webhook_log_name)

    # Skip if already processed
    if getattr(webhook_log_doc, 'processed', False):
        return

    try:
        payload = json.loads(webhook_log_doc.payload)
    except Exception:
        frappe.log_error('Invalid webhook payload: ' + (webhook_log_doc.name or ''), 'razorpay.webhook')
        webhook_log_doc.processed = True
        webhook_log_doc.save(ignore_permissions=True)
        return

    event_type = payload.get('event')

    # Mapping of 34 events to logical handlers
    handlers = {
        # Success Group
        'payment.captured': handle_payment_captured,
        'order.paid': handle_payment_captured,
        'payment.authorized': handle_payment_captured,
        'payment_link.paid': handle_payment_link_paid,
        
        # Failure Group
        'payment.failed': handle_payment_failed,
        'refund.failed': handle_payment_failed,
        'order.notification.failed': handle_payment_failed,
        'payment_link.expired': handle_payment_failed,
        'payment_link.cancelled': handle_payment_failed,
        
        # Subscription / Mandate Group
        'subscription.authenticated': handle_subscription_event,
        'subscription.activated': handle_subscription_event,
        'subscription.charged': handle_subscription_event,
        'subscription.paused': handle_subscription_event,
        'subscription.resumed': handle_subscription_event,
        'subscription.pending': handle_subscription_event,
        'subscription.halted': handle_subscription_event,
        'subscription.cancelled': handle_subscription_event,
        'subscription.completed': handle_subscription_event,
        'subscription.updated': handle_subscription_event,
        'token.confirmed': handle_subscription_event,
        
        # Refund Group
        'refund.processed': handle_refund_processed,
        'refund.created': handle_refund_processed,
        'refund.speed_changed': handle_operational_event,
        
        # Dispute Group (Risk Management)
        'payment.dispute.created': handle_dispute_event,
        'payment.dispute.won': handle_dispute_event,
        'payment.dispute.lost': handle_dispute_event,
        'payment.dispute.closed': handle_dispute_event,
        'payment.dispute.under_review': handle_dispute_event,
        'payment.dispute.action_required': handle_dispute_event,
        
        # Operational Group
        'settlement.processed': handle_operational_event,
        'payment.downtime.started': handle_operational_event,
        'payment.downtime.updated': handle_operational_event,
        'payment.downtime.resolved': handle_operational_event,
        
        # Others
        'payment_link.partially_paid': handle_payment_link_paid,
        'order.notification.delivered': handle_operational_event
    }

    result = None
    handler = handlers.get(event_type)
    
    if handler:
        try:
            result = handler(payload)
        except Exception as e:
            frappe.log_error(f"Error in Razorpay Webhook Handler ({event_type}): {str(e)}", "razorpay.webhook.handler_error")
            result = {"success": False, "error": str(e)}
    else:
        frappe.log_error(f'Unhandled webhook event in worker: {event_type}', 'razorpay.webhook.worker')

    # Mark processed and persist result
    webhook_log_doc.reload()
    webhook_log_doc.processed = True
    try:
        webhook_log_doc.processing_result = json.dumps(result) if result else None
    except Exception:
        webhook_log_doc.processing_result = str(result)

    webhook_log_doc.save(ignore_permissions=True)

    return result
