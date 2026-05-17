# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Marketing Tasks — Background Scheduler Jobs

Schedule:
  - dispatch_scheduled_campaigns  : */15 * * * *
  - fire_triggers                 : */30 * * * *
  - check_campaign_conversions    : hourly

Design decisions:
  - Batch sending (50/chunk) with 0.5s sleep to respect API rate limits
  - Opt-out / TRAI DND compliance via Customer.opted_out_of_marketing
  - Balance check before EACH batch — campaign pauses if coins run out
  - Email subject support on all email sends
  - 'On Order Complete' trigger fired from order hook (not scheduler)
  - Custom SQL segment removed from dispatcher (SQL injection risk)
"""

import frappe
import time
import traceback
from frappe.utils import now_datetime, getdate, add_days

BATCH_SIZE = 50          # messages per batch to avoid API rate limits
BATCH_SLEEP_SEC = 0.5    # seconds between batches


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER ENTRY POINTS
# ═══════════════════════════════════════════════════════════════════

def dispatch_scheduled_campaigns():
    """Every 15 min: pick up Scheduled campaigns whose time has arrived."""
    now = now_datetime()
    pending = frappe.get_all(
        "Marketing Campaign",
        filters={"status": "Scheduled", "scheduled_at": ["<=", now]},
        pluck="name"
    )
    for campaign_id in pending:
        frappe.db.set_value("Marketing Campaign", campaign_id, "status", "Sending")
        frappe.enqueue(
            "flamezo_backend.flamezo.tasks.marketing_tasks.dispatch_campaign_task",
            campaign_id=campaign_id,
            queue="long",
            timeout=7200
        )
    if pending:
        frappe.db.commit()


def fire_triggers():
    """Every 30 min: fire scheduled-category triggers (birthday, win-back, milestone)."""
    active_triggers = frappe.get_all(
        "Marketing Trigger",
        filters={"is_active": 1},
        fields=["name", "trigger_name", "restaurant", "trigger_event", "channel",
                "delay_hours", "days_since_visit", "loyalty_milestone_coins",
                "message_template", "email_subject", "include_coupon", "coupon_code",
                "total_fired"]
    )

    settings = frappe.get_single("Flamezo Settings")
    restaurant_name_cache = {}

    for trigger in active_triggers:
        # Only scheduled-type triggers here; On Order Complete is handled via hook
        if trigger.trigger_event in ("On Order Complete", "On Referral Signup"):
            continue
        try:
            customers_to_fire = _get_trigger_customers(trigger)
            for customer in customers_to_fire:
                _fire_single_trigger(trigger, customer, settings, restaurant_name_cache)
        except Exception as e:
            frappe.log_error(f"Trigger fire failed for {trigger.name}: {str(e)}", "Marketing Task")

    frappe.db.commit()


def check_campaign_conversions():
    """Every hour: attribute conversions to events sent in the last 24h."""
    recent_events = frappe.get_all(
        "Marketing Event",
        filters={
            "status": "Sent",
            "sent_at": [">=", add_days(now_datetime(), -1)]
        },
        fields=["name", "campaign", "restaurant", "customer", "sent_at"]
    )

    campaign_deltas = {}

    for event in recent_events:
        if not event.customer or not event.restaurant:
            continue
        order = frappe.db.get_value(
            "Order",
            filters={
                "platform_customer": event.customer,
                "restaurant": event.restaurant,
                "creation": [">=", event.sent_at],
                "status": ["not in", ["cancelled", "draft"]]
            },
            fieldname=["name", "total"],
            as_dict=True
        )
        if order:
            frappe.db.set_value("Marketing Event", event.name, {
                "status": "Converted",
                "converted_at": now_datetime(),
                "conversion_order": order.name
            })
            if event.campaign:
                delta = campaign_deltas.setdefault(event.campaign, {"count": 0, "revenue": 0})
                delta["count"] += 1
                delta["revenue"] += float(order.total or 0)

    for campaign_id, delta in campaign_deltas.items():
        current = frappe.db.get_value(
            "Marketing Campaign", campaign_id,
            ["total_conversions", "revenue_attributed"], as_dict=True
        )
        frappe.db.set_value("Marketing Campaign", campaign_id, {
            "total_conversions": (current.total_conversions or 0) + delta["count"],
            "revenue_attributed": float(current.revenue_attributed or 0) + delta["revenue"]
        })

    frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════
# CAMPAIGN DISPATCHER (background job)
# ═══════════════════════════════════════════════════════════════════

def dispatch_campaign_task(campaign_id):
    """
    Core dispatcher. Sends in batches of BATCH_SIZE with coin balance check each batch.
    Skips opted-out customers.
    """
    try:
        campaign = frappe.get_doc("Marketing Campaign", campaign_id)
        settings = frappe.get_single("Flamezo Settings")
        coins_per_msg = _get_coins_per_msg(settings, campaign.channel)

        seg_doc = frappe.get_doc("Marketing Segment", campaign.target_segment)
        customers = seg_doc.get_customer_list()

        # Filter opted-out customers
        opted_out = _get_opted_out_phones(campaign.restaurant)
        customers = [c for c in customers if c.get("phone") not in opted_out]

        restaurant_name = (
            frappe.db.get_value("Restaurant", campaign.restaurant, "restaurant_name")
            or campaign.restaurant
        )

        total_sent = 0
        total_failed = 0
        total_cost = 0.0
        paused_reason = None

        # Process in batches
        for chunk_start in range(0, len(customers), BATCH_SIZE):
            chunk = customers[chunk_start: chunk_start + BATCH_SIZE]

            # ✅ FIX: Check balance BEFORE each batch
            balance = float(frappe.db.get_value("Restaurant", campaign.restaurant, "coins_balance") or 0)
            batch_cost = len(chunk) * coins_per_msg
            if balance < batch_cost:
                paused_reason = f"Paused: Insufficient Wallet Balance ({balance:.1f} available, need {batch_cost:.1f})"
                frappe.log_error(
                    f"Campaign {campaign_id} paused mid-send: {paused_reason}", "Marketing Task"
                )
                break

            for customer in chunk:
                try:
                    message = _resolve_template(
                        campaign.message_template,
                        customer_name=customer.get("customer_name") or "Valued Customer",
                        restaurant_name=restaurant_name,
                        loyalty_balance=_get_loyalty_balance(customer.get("customer"), campaign.restaurant),
                        coupon_code=campaign.coupon_code or ""
                    )

                    # ✅ NEW: Frequency Capping (Fatigue Rule)
                    if _is_customer_fatigued(customer.get("customer"), settings):
                        frappe.get_doc({
                            "doctype": "Marketing Event",
                            "campaign": campaign_id,
                            "restaurant": campaign.restaurant,
                            "customer": customer.get("customer"),
                            "channel": campaign.channel,
                            "phone": customer.get("phone"),
                            "status": "FatigueSkipped",
                            "sent_at": now_datetime(),
                            "coins_charged": 0,
                            "error_message": "Global Fatigue Rule: Customer reached message limit for this window."
                        }).insert(ignore_permissions=True)
                        continue

                    success, error = _send_message(
                        channel=campaign.channel,
                        phone=customer.get("phone", ""),
                        message=message,
                        settings=settings,
                        subject=getattr(campaign, "email_subject", None),
                        template_name=getattr(campaign, "whatsapp_template_name", None)
                    )

                    event_doc = frappe.get_doc({
                        "doctype": "Marketing Event",
                        "campaign": campaign_id,
                        "restaurant": campaign.restaurant,
                        "customer": customer.get("customer"),
                        "channel": campaign.channel,
                        "phone": customer.get("phone"),
                        "status": "Sent" if success else "Failed",
                        "error_message": error if not success else None,
                        "sent_at": now_datetime(),
                        "coins_charged": coins_per_msg if success else 0
                    })
                    event_doc.insert(ignore_permissions=True)

                    if success:
                        _safe_deduct_coins(
                            campaign.restaurant, coins_per_msg,
                            f"Marketing {campaign.channel}: '{campaign.campaign_name}'",
                            "Marketing Campaign", campaign_id
                        )
                        total_sent += 1
                        total_cost += coins_per_msg
                    else:
                        total_failed += 1

                except Exception as err:
                    frappe.log_error(
                        f"Campaign {campaign_id} → {customer.get('phone')}: {str(err)}",
                        "Marketing Task"
                    )
                    total_failed += 1

            frappe.db.commit()
            time.sleep(BATCH_SLEEP_SEC)  # Rate limiting between batches

        # Final stats update
        frappe.db.set_value("Marketing Campaign", campaign_id, {
            "status": "Sent" if not paused_reason else "Failed",
            "sent_at": now_datetime(),
            "total_sent": total_sent,
            "total_failed": total_failed,
            "total_cost_coins": total_cost,
            "notes": paused_reason or (frappe.db.get_value("Marketing Campaign", campaign_id, "notes") or "")
        })
        frappe.db.commit()

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Campaign Dispatch Failed: {campaign_id}")
        frappe.db.set_value("Marketing Campaign", campaign_id, "status", "Failed")
        frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════
# ORDER COMPLETE TRIGGER — called from hooks
# ═══════════════════════════════════════════════════════════════════

def fire_order_complete_triggers(order_doc, method=None):
    """
    Called from doc_events -> Order -> after_insert.
    Finds active 'On Order Complete' triggers for the restaurant and enqueues delayed sends.
    """
    restaurant = order_doc.restaurant
    customer_id = order_doc.platform_customer
    if not restaurant or not customer_id:
        return

    # Fast path: check if any active triggers exist for this restaurant
    triggers = frappe.get_all(
        "Marketing Trigger",
        filters={"restaurant": restaurant, "trigger_event": "On Order Complete", "is_active": 1},
        fields=["name", "delay_hours"]
    )
    if not triggers:
        return

    # Check opt-out
    opted_out = frappe.db.get_value("Customer", customer_id, "opted_out_of_marketing")
    if opted_out:
        return

    for trigger in triggers:
        delay_seconds = int((trigger.delay_hours or 0) * 3600)
        frappe.enqueue(
            "flamezo_backend.flamezo.tasks.marketing_tasks._fire_trigger_for_customer",
            trigger_name=trigger.name,
            customer_id=customer_id,
            queue="default",
            timeout=300,
            is_async=True,
            at_front=False,
            enqueue_after_commit=True,
            **{"eta": delay_seconds} if delay_seconds > 0 else {}
        )


def _fire_trigger_for_customer(trigger_name, customer_id):
    """Background job: fire a single trigger for a single customer."""
    trigger = frappe.get_doc("Marketing Trigger", trigger_name)
    if not trigger.is_active:
        return

    customer = frappe.db.get_value(
        "Customer", customer_id,
        ["name", "phone", "customer_name", "opted_out_of_marketing"],
        as_dict=True
    )
    if not customer or not customer.phone or customer.opted_out_of_marketing:
        return

    # Standardize dictionary keys to match batch trigger results
    customer["customer"] = customer["name"]

    settings = frappe.get_single("Flamezo Settings")
    _fire_single_trigger(trigger, customer, settings, {})
    frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════
# OPT-OUT HANDLER — WhatsApp/SMS reply webhook
# ═══════════════════════════════════════════════════════════════════

def handle_opt_out_reply(phone, keyword="STOP"):
    """
    Called when a customer replies with STOP / UNSUBSCRIBE via WhatsApp or SMS.
    Sets opted_out_of_marketing = 1 and records the keyword.
    TRAI DND compliance.
    """
    customer_name = frappe.db.get_value("Customer", {"phone": phone}, "name")
    
    if not customer_name:
        # Try normalized 10-digit phone
        phone_clean = phone.replace("+91", "").replace("+", "").strip()
        if phone_clean.startswith("0"):
            phone_clean = phone_clean[1:]
        
        customer_name = frappe.db.get_value("Customer", {"phone": phone_clean}, "name")

    if not customer_name:
        # Try with common prefixes
        for variant in [f"+91{phone_clean}", f"0{phone_clean}"]:
            customer_name = frappe.db.get_value("Customer", {"phone": variant}, "name")
            if customer_name:
                break

    if not customer_name:
        return False

    frappe.db.set_value("Customer", customer_name, {
        "opted_out_of_marketing": 1,
        "opted_out_at": now_datetime(),
        "opted_out_keyword": (keyword or "STOP")[:50]
    })

    # Log as a Marketing Event for audit trail
    try:
        frappe.get_doc({
            "doctype": "Marketing Event",
            "restaurant": frappe.db.get_value("Customer", customer_name, "first_verified_at_restaurant"),
            "customer": customer_name,
            "channel": "WhatsApp",
            "phone": phone,
            "status": "OptedOut",
            "sent_at": now_datetime(),
            "coins_charged": 0,
            "error_message": f"Customer opted out via keyword: {keyword}"
        }).insert(ignore_permissions=True)
    except Exception:
        pass

    frappe.db.commit()
    return True


# ═══════════════════════════════════════════════════════════════════
# TRIGGER HELPERS
# ═══════════════════════════════════════════════════════════════════

def _get_trigger_customers(trigger):
    """Return customers matching a scheduled trigger event."""
    event = trigger.trigger_event

    if event == "On Birthday":
        return frappe.db.sql("""
            SELECT DISTINCT c.name as customer, c.phone, c.customer_name
            FROM `tabCustomer` c
            JOIN `tabOrder` o ON o.platform_customer = c.name
            WHERE o.restaurant = %s
              AND c.date_of_birth IS NOT NULL
              AND MONTH(c.date_of_birth) = MONTH(CURDATE())
              AND DAY(c.date_of_birth) = DAY(CURDATE())
              AND c.phone IS NOT NULL
              AND (c.opted_out_of_marketing IS NULL OR c.opted_out_of_marketing = 0)
        """, (trigger.restaurant,), as_dict=True)

    elif event == "X Days After Last Visit":
        days = trigger.days_since_visit or 30
        return frappe.db.sql("""
            SELECT c.name as customer, c.phone, c.customer_name
            FROM `tabCustomer` c
            JOIN `tabOrder` o ON o.platform_customer = c.name
            WHERE o.restaurant = %s AND c.phone IS NOT NULL
              AND (c.opted_out_of_marketing IS NULL OR c.opted_out_of_marketing = 0)
            GROUP BY c.name, c.phone, c.customer_name
            HAVING MAX(o.creation) BETWEEN
                DATE_SUB(NOW(), INTERVAL %s DAY) AND
                DATE_SUB(NOW(), INTERVAL %s DAY)
        """, (trigger.restaurant, days + 1, days - 1), as_dict=True)

    elif event == "On Loyalty Milestone":
        milestone = trigger.loyalty_milestone_coins or 500
        return frappe.db.sql("""
            SELECT c.name as customer, c.phone, c.customer_name,
                   SUM(CASE WHEN le.transaction_type = 'Earn' THEN le.coins ELSE -le.coins END) as balance
            FROM `tabCustomer` c
            JOIN `tabRestaurant Loyalty Entry` le ON le.customer = c.name
            WHERE le.restaurant = %s AND c.phone IS NOT NULL
              AND (c.opted_out_of_marketing IS NULL OR c.opted_out_of_marketing = 0)
            GROUP BY c.name, c.phone, c.customer_name
            HAVING balance >= %s
        """, (trigger.restaurant, milestone), as_dict=True)

    return []


def _fire_single_trigger(trigger, customer, settings, restaurant_name_cache):
    """
    Sends one trigger message with full idempotency check.
    Idempotency window: Birthday = 365 days, others = 30 days.
    """
    # Idempotency check
    window_days = 365 if trigger.trigger_event == "On Birthday" else 30
    already_fired = frappe.db.exists("Marketing Event", {
        "trigger": trigger.name,
        "customer": customer.get("customer"),
        "sent_at": [">=", add_days(getdate(), -window_days)],
        "status": ["not in", ["Failed", "OptedOut"]]
    })
    if already_fired:
        return

    # Coin balance check
    settings_coins = _get_coins_per_msg(settings, trigger.channel)
    balance = float(frappe.db.get_value("Restaurant", trigger.restaurant, "coins_balance") or 0)
    if balance < settings_coins:
        frappe.log_error(
            f"Trigger {trigger.name}: Insufficient coins for {customer.get('phone')} (balance={balance:.1f})",
            "Marketing Task"
        )
        return

    # Resolve restaurant name
    if trigger.restaurant not in restaurant_name_cache:
        restaurant_name_cache[trigger.restaurant] = (
            frappe.db.get_value("Restaurant", trigger.restaurant, "restaurant_name") or trigger.restaurant
        )

    message = _resolve_template(
        trigger.message_template,
        customer_name=customer.get("customer_name") or "Valued Customer",
        restaurant_name=restaurant_name_cache[trigger.restaurant],
        loyalty_balance=_get_loyalty_balance(customer.get("customer"), trigger.restaurant),
        coupon_code=trigger.coupon_code or ""
    )

    # ✅ NEW: Frequency Capping (Fatigue Rule)
    if _is_customer_fatigued(customer.get("customer"), settings):
        frappe.get_doc({
            "doctype": "Marketing Event",
            "trigger": trigger.name,
            "restaurant": trigger.restaurant,
            "customer": customer.get("customer"),
            "channel": trigger.channel,
            "phone": customer.get("phone"),
            "status": "FatigueSkipped",
            "sent_at": now_datetime(),
            "coins_charged": 0,
            "error_message": "Global Fatigue Rule: Customer reached message limit for this window."
        }).insert(ignore_permissions=True)
        return

    success, error = _send_message(
        channel=trigger.channel,
        phone=customer.get("phone", ""),
        message=message,
        settings=settings,
        subject=getattr(trigger, "email_subject", None),
        template_name=getattr(trigger, "whatsapp_template_name", None)
    )

    frappe.get_doc({
        "doctype": "Marketing Event",
        "trigger": trigger.name,
        "restaurant": trigger.restaurant,
        "customer": customer.get("customer"),
        "channel": trigger.channel,
        "phone": customer.get("phone"),
        "status": "Sent" if success else "Failed",
        "error_message": error if not success else None,
        "sent_at": now_datetime(),
        "coins_charged": settings_coins if success else 0
    }).insert(ignore_permissions=True)

    if success:
        _safe_deduct_coins(
            trigger.restaurant, settings_coins,
            f"Trigger: '{trigger.trigger_name}' → {customer.get('phone')}",
            "Marketing Trigger", trigger.name
        )
        frappe.db.set_value("Marketing Trigger", trigger.name, "total_fired",
                            (trigger.total_fired or 0) + 1)


# ═══════════════════════════════════════════════════════════════════
# PRIVATE HELPERS
# ═══════════════════════════════════════════════════════════════════

def _get_opted_out_phones(restaurant):
    """Returns a set of opted-out phone numbers for a restaurant's customers."""
    rows = frappe.db.sql("""
        SELECT DISTINCT c.phone
        FROM `tabCustomer` c
        JOIN `tabOrder` o ON o.platform_customer = c.name
        WHERE o.restaurant = %s AND c.opted_out_of_marketing = 1 AND c.phone IS NOT NULL
    """, (restaurant,))
    return {r[0] for r in rows}


def _is_customer_fatigued(customer_id, settings):
    """
    Checks if a customer has reached the global marketing fatigue limit.
    Returns True if limit reached, False otherwise.
    """
    max_msgs = int(getattr(settings, "marketing_max_msgs_per_window", 2) or 2)
    window_days = int(getattr(settings, "marketing_fatigue_window_days", 7) or 7)

    # Count 'Sent' marketing events in the window
    # Note: we ignore 'Failed' or 'OptedOut' as they didn't consume customer attention/balance
    count = frappe.db.count("Marketing Event", {
        "customer": customer_id,
        "status": "Sent",
        "sent_at": [">=", add_days(now_datetime(), -window_days)]
    })

    return count >= max_msgs


def _safe_deduct_coins(restaurant, amount, description, ref_doctype, ref_name):
    """Wrapper around deduct_coins — logs but never raises."""
    try:
        from flamezo_backend.flamezo.api.coin_billing import deduct_coins
        deduct_coins(
            restaurant=restaurant,
            amount=amount,
            type="Marketing Deduction",
            description=description,
            ref_doctype=ref_doctype,
            ref_name=ref_name
        )
    except Exception as e:
        frappe.log_error(f"Coin deduction failed [{ref_name}]: {str(e)}", "Marketing Task")


def _get_coins_per_msg(settings, channel):
    if channel in ("WhatsApp", "WhatsApp Cloud API"):
        return float(getattr(settings, "marketing_whatsapp_coins_per_msg", None) or 1.20)
    elif channel == "SMS":
        return float(getattr(settings, "marketing_sms_coins_per_msg", None) or 0.25)
    elif channel == "Email":
        return float(getattr(settings, "marketing_email_coins_per_msg", None) or 0.05)
    return 0.25


def _resolve_template(template, **vars):
    """Replace {{variable}} placeholders."""
    result = str(template or "")
    for key, value in vars.items():
        result = result.replace(f"{{{{{key}}}}}", str(value or ""))
    return result


def _get_loyalty_balance(customer_id, restaurant):
    if not customer_id:
        return 0
    try:
        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
        return get_loyalty_balance(customer_id, restaurant)
    except Exception:
        return 0


def _send_message(channel, phone, message, settings, subject=None, template_name=None):
    """Route message to correct channel. Returns (success, error_or_None)."""
    if not phone:
        return False, "No phone number"
    try:
        if channel == "SMS":
            return _send_sms(phone, message, settings)
        elif channel == "WhatsApp":
            return _send_whatsapp(phone, message, settings)
        elif channel == "WhatsApp Cloud API":
            return _send_whatsapp_cloud_api(phone, message, settings, template_name=template_name)
        elif channel == "Email":
            return _send_email(phone, message, settings, subject=subject)
        return False, f"Unknown channel: {channel}"
    except Exception as e:
        return False, str(e)


def _send_sms(phone, message, settings):
    """Send via Fast2SMS. Max 160 chars recommended."""
    api_key = getattr(settings, "fast2sms_api_key", None)
    if not api_key:
        return False, "No Fast2SMS API key configured"
    
    import requests
    phone_clean = phone.replace("+91", "").replace("+", "").strip()
    
    sender_id = getattr(settings, "fast2sms_sender_id", None)
    template_id = getattr(settings, "fast2sms_dlt_template_id", None)
    
    if sender_id and template_id:
        payload = {
            "route": "dlt",
            "sender_id": sender_id,
            "message": template_id,
            "variables_values": message[:30],
            "numbers": phone_clean
        }
        try:
            res = requests.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": api_key, "Content-Type": "application/json"},
                json=payload, timeout=10
            )
            data = res.json() if res.text else {}
            return (True, None) if data.get("return") else (False, str(data.get("message", "Fast2SMS DLT error")))
        except Exception as e:
            return False, str(e)
    else:
        try:
            res = requests.get(
                "https://www.fast2sms.com/dev/bulkV2",
                params={"authorization": api_key, "message": message[:320], "numbers": phone_clean, "route": "q"},
                timeout=10
            )
            data = res.json() if res.text else {}
            return (True, None) if data.get("return") else (False, str(data.get("message", "Fast2SMS error")))
        except Exception as e:
            return False, str(e)



def _send_sms_fast2sms(phone, message, settings):
    api_key = getattr(settings, "fast2sms_api_key", None)
    if not api_key:
        return False, "No SMS API key configured"
    import requests
    phone_clean = phone.replace("+91", "").replace("+", "").strip()
    res = requests.get(
        "https://www.fast2sms.com/dev/bulkV2",
        params={"authorization": api_key, "message": message[:320], "numbers": phone_clean, "route": "q"},
        timeout=10
    )
    data = res.json()
    return (True, None) if data.get("return") else (False, str(data.get("message", "Fast2SMS error")))


def _send_whatsapp(phone, message, settings):
    """
    Send via Evolution API.
    """
    from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_message
    return send_whatsapp_message(phone, message, settings=settings)


def _send_whatsapp_cloud_api(phone, message, settings, template_name=None):
    """
    Send via Meta WhatsApp Cloud API (Official).
    Requires a pre-approved template if sending marketing messages.
    """
    access_token = settings.get_password("whatsapp_cloud_api_token")
    phone_id = getattr(settings, "whatsapp_cloud_api_phone_id", None)
    
    # Use per-campaign/trigger template if provided, else fallback to global settings
    if not template_name:
        template_name = getattr(settings, "marketing_wa_template_name", None)

    if not access_token or not phone_id:
        return False, "WhatsApp Cloud API credentials not configured"

    import requests
    import json

    # Normalize phone number to E.164 (e.g. 91xxxxxxxxxx)
    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "").strip()
    if len(phone_clean) == 10:
        phone_clean = "91" + phone_clean

    # Meta Cloud API uses Templates for business-initiated marketing conversations.
    # We will assume 'message' is a simple string for now, but in production,
    # you usually send template parameters.
    
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # If a template name is configured, we try to send a template message.
    # Otherwise, we send a text message (which only works if the user replied in the last 24h).
    if template_name:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"}
            }
        }
        # hello_world takes 0 parameters. Real templates take the message text as a parameter.
        if template_name != "hello_world":
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": message[:1000]}
                    ]
                }
            ]
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_clean,
            "type": "text",
            "text": {"preview_url": False, "body": message}
        }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        data = res.json()
        if res.status_code in [200, 201] and not data.get("error"):
            return True, None
        
        error_msg = data.get("error", {}).get("message", "Unknown Meta API error")
        return False, f"Meta Cloud API Error: {error_msg}"
    except Exception as e:
        return False, str(e)


def _send_email(recipient_phone, message, settings, subject=None):
    """Send via Resend.com with a real subject line."""
    resend_key = getattr(settings, "marketing_resend_api_key", None)
    from_email = getattr(settings, "marketing_from_email", None) or "noreply@flamezo_backend.com"

    if not resend_key:
        return False, "Resend API key not configured"

    email = frappe.db.get_value("Customer", {"phone": recipient_phone}, "email")
    if not email:
        return False, "No email address for customer"

    import requests
    res = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json={
            "from": from_email,
            "to": [email],
            "subject": subject or "A special message from your restaurant",
            "text": message,
            "html": f"<p>{message.replace(chr(10), '<br>')}</p>"
        },
        timeout=10
    )
    if res.status_code in [200, 201]:
        return True, None
    return False, f"Resend error: {res.text[:200]}"


# ═══════════════════════════════════════════════════════════════════
# SEO BLOG AUTOMATION
# ═══════════════════════════════════════════════════════════════════

def generate_daily_seo_blog():
    """
    Scheduled task to generate a unique SEO blog post daily at 9:00 AM IST.
    Uses 'Dynamic Entity Injection' for Gold restaurants.
    """
    from flamezo_backend.flamezo.services.ai.seo_blog import ContentGenerator
    import random

    try:
        # 1. Target Selection: Filter for Gold restaurants
        restaurants = frappe.get_all("Restaurant",
            filters={"plan_type": "GOLD", "is_active": 1},
            fields=["name", "restaurant_name", "description", "city", "subdomain"]
        )
        
        if not restaurants:
            # Fallback to any active restaurant if no premium ones exist
            restaurants = frappe.get_all("Restaurant", filters={"is_active": 1}, 
                                       fields=["name", "restaurant_name", "description", "city", "subdomain"])
            
        if not restaurants:
            return {"success": False, "error": "No active restaurants found for blog generation"}

        focus_res = random.choice(restaurants)
        res_id = focus_res.name
        res_name = focus_res.restaurant_name or res_id
        res_city = focus_res.city or "India"
        
        # 2. Context Fetching: Real-time dishes and location
        dishes = frappe.get_all("Menu Product", 
            filters={"restaurant": res_id, "is_active": 1}, 
            limit=20, fields=["name", "product_name", "description", "category_name"])
        
        today_date = frappe.utils.today()
        current_year = today_date.split("-")[0]
        
        context = f"Restaurant: {res_name} in {res_city}. Date: {today_date}.\n"
        if focus_res.description:
            context += f"About: {focus_res.description}\n"
        
        if dishes:
            dish_names_list = [d.product_name for d in dishes if d.product_name]
            dish_list = ", ".join(dish_names_list)
            context += f"Signature Menu Items (Inject these naturally): {dish_list}."
        else:
            dish_names_list = []

        # 3. Image Strategy: Fetch real random food images from ALL Gold restaurants for variety
        image_url = None
        media_pool = []
        
        # Get all recent product media from ALL premium restaurants to ensure uniqueness
        premium_res_ids = [r.name for r in restaurants]
        product_media = frappe.get_all("Product Media", 
            filters={
                "parenttype": "Menu Product",
                "media_type": ["like", "%image%"]
            },
            fields=["media_url", "parent"],
            limit=100
        )
        
        # Filter for only those belonging to premium restaurants
        premium_dishes = frappe.get_all("Menu Product", 
            filters={"restaurant": ["in", premium_res_ids]}, 
            pluck="name"
        )
        
        images = [m.media_url for m in product_media if m.parent in premium_dishes and not m.media_url.endswith(('.mp4', '.mov', '.avi'))]
        
        if images:
            random.shuffle(images)
            image_url = images[0] # Thumbnail
            media_pool = images[1:6] # Up to 5 for in-content injection
        
        # Fallback to restaurant logo if no product images
        if not image_url and hasattr(focus_res, 'logo') and focus_res.logo:
            image_url = focus_res.logo
        
        # 4. Content Generation
        gen = ContentGenerator()
        
        # ✅ DYNAMIC KEYWORD GENERATION (High-End SEO Strategy)
        # Fetch cuisine type from Restaurant if available (field may not exist on all installations)
        try:
            cuisine = frappe.db.get_value("Restaurant", res_id, "cuisine") or "Multi-cuisine"
        except Exception:
            cuisine = "Multi-cuisine"
        location_slug = res_city
        
        # Prepare dish objects for keyword generator
        keywords_dishes = [{"item_name": name} for name in dish_names_list]
        
        dynamic_keywords = gen.generate_dynamic_keywords(
            restaurant_name=res_name,
            location=location_slug,
            dishes=keywords_dishes,
            cuisine=cuisine
        )
        
        # Fallback to static list if AI fails
        if not dynamic_keywords:
            dynamic_keywords = [
                f"best dining experience in {res_city} {current_year}", 
                "future of restaurant technology",
                "how to skyrocket restaurant revenue", 
                "digital transformation in f&b mumbai",
                "ultimate guide to qr code ordering", 
                f"food trends {current_year}",
                "improving customer loyalty in cafes", 
                f"luxury dining in {res_city}"
            ]
        
        keyword = random.choice(dynamic_keywords)
        
        article = gen.generate_article(
            keyword=keyword,
            length=2000, 
            style="premium",
            client_context=context,
            media_urls=media_pool # Pass the pool for in-content injection
        )
        
        meta = gen.generate_premium_metadata(article["content"], keyword)
        
        # 5. Database Storage: Save to native 'Blog Post'
        blog_category = "industry-insights"
        if not frappe.db.exists("Blog Category", blog_category):
            frappe.get_doc({
                "doctype": "Blog Category", 
                "title": "Industry Insights", 
                "name": blog_category
            }).insert(ignore_permissions=True)
            
        # Get or create blogger
        blogger_name = "Flamezo Team"
        if not frappe.db.exists("Blogger", blogger_name):
            frappe.get_doc({
                "doctype": "Blogger",
                "short_name": "Flamezo Team",
                "full_name": "Flamezo Team",
                "name": blogger_name
            }).insert(ignore_permissions=True)
            
        blog_post = frappe.get_doc({
            "doctype": "Blog Post",
            "title": article["title"],
            "blog_intro": article["excerpt"],
            "content": article["content"],
            "meta_description": meta.get("meta_description") or article["excerpt"],
            "meta_title": meta.get("meta_title") or article["title"],
            "published": 1,
            "published_on": frappe.utils.today(),
            "blogger": blogger_name,
            "blog_category": blog_category,
            "meta_image": image_url # Real restaurant/dish image for SEO rich snippets
        })
        
        blog_post.insert(ignore_permissions=True)
        
        # ✅ FORCE SAVE TAGS: _user_tags expects a comma-separated string, not a list
        if meta.get("tags"):
            tags = meta.get("tags")
            if isinstance(tags, list):
                tags = ",".join(str(t) for t in tags)
            frappe.db.set_value("Blog Post", blog_post.name, "_user_tags", tags)
        
        frappe.db.commit()
        
        print(f"✓ Blog Post created: {blog_post.name} (Title: {article['title']})")
        frappe.log_error(f"Daily SEO Blog Generated (10/10): {blog_post.name}", "Marketing AI Blog")
        
        return {"success": True, "blog_post": blog_post.name, "restaurant": res_name}

    except Exception as e:
        error_msg = f"Error generating daily SEO blog: {str(e)}\n{traceback.format_exc()}"
        print(f"✗ ERROR: {error_msg}")
        frappe.log_error(error_msg, "Marketing AI Blog Failure")
        return {"success": False, "error": str(e)}
