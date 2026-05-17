# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Marketing Studio API (v2 — Production Ready)
All restaurant-scoped endpoints: GOLD-only via @require_plan.
Opt-out endpoint: public (called by whitelisted webhook from Evolution API).
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.feature_gate import require_plan
import json


# ═══════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
@require_plan('GOLD')
def get_marketing_overview(restaurant_id):
    """Summary KPIs for Marketing Studio dashboard."""
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)

    try:
        from frappe.utils import get_first_day, getdate
        today = getdate()
        month_start = get_first_day(today)

        stats = frappe.db.sql("""
            SELECT
                COUNT(*) as total_sent,
                SUM(coins_charged) as total_coins,
                COUNT(CASE WHEN status = 'Converted' THEN 1 END) as total_conversions,
                COUNT(CASE WHEN channel = 'SMS' THEN 1 END) as sms_count,
                COUNT(CASE WHEN channel = 'WhatsApp' THEN 1 END) as wa_count,
                COUNT(CASE WHEN channel = 'Email' THEN 1 END) as email_count
            FROM `tabMarketing Event`
            WHERE restaurant = %s AND sent_at >= %s AND status NOT IN ('Failed', 'OptedOut')
        """, (restaurant, month_start), as_dict=True)[0]

        active_triggers = frappe.db.count("Marketing Trigger", {"restaurant": restaurant, "is_active": 1})
        opted_out_count = frappe.db.sql("""
            SELECT COUNT(DISTINCT c.name) FROM `tabCustomer` c
            JOIN `tabOrder` o ON o.platform_customer = c.name
            WHERE o.restaurant = %s AND c.opted_out_of_marketing = 1
        """, (restaurant,))[0][0] or 0

        conversion_rate = 0
        if (stats.total_sent or 0) > 0:
            conversion_rate = round(((stats.total_conversions or 0) / stats.total_sent) * 100, 1)

        daily_trend = frappe.db.sql("""
            SELECT DATE(sent_at) as date, channel, COUNT(*) as count
            FROM `tabMarketing Event`
            WHERE restaurant = %s AND sent_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
              AND status NOT IN ('Failed', 'OptedOut')
            GROUP BY DATE(sent_at), channel
            ORDER BY date ASC
        """, (restaurant,), as_dict=True)

        recent_campaigns = frappe.get_all(
            "Marketing Campaign",
            filters={"restaurant": restaurant},
            fields=["name", "campaign_name", "channel", "status", "total_recipients",
                    "total_sent", "total_conversions", "total_cost_coins", "sent_at", "creation"],
            order_by="creation desc",
            limit=5
        )

        return {
            "success": True,
            "data": {
                "total_sent_month": int(stats.total_sent or 0),
                "total_coins_month": float(stats.total_coins or 0),
                "conversion_rate": conversion_rate,
                "active_triggers": active_triggers,
                "opted_out_count": opted_out_count,
                "channel_breakdown": {
                    "sms": int(stats.sms_count or 0),
                    "whatsapp": int(stats.wa_count or 0),
                    "email": int(stats.email_count or 0)
                },
                "daily_trend": daily_trend,
                "recent_campaigns": recent_campaigns
            }
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Marketing Overview Error")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# SEGMENTS
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
@require_plan('GOLD')
def get_segments(restaurant_id):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    segments = frappe.get_all(
        "Marketing Segment",
        filters={"restaurant": restaurant},
        fields=["name", "segment_name", "description", "criteria_type",
                "estimated_reach", "last_computed_at", "days_since_last_visit",
                "min_visit_count", "min_total_spent"],
        order_by="modified desc"
    )
    return {"success": True, "data": segments}


@frappe.whitelist()
@require_plan('GOLD')
def save_segment(restaurant_id, segment_data):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    if isinstance(segment_data, str):
        segment_data = json.loads(segment_data)

    # Block Custom SQL at API level
    if segment_data.get("criteria_type") == "Custom SQL":
        return {"success": False, "error": "Custom SQL segments are disabled for security. Use 'Manual' with phone numbers."}

    segment_data["restaurant"] = restaurant
    existing = frappe.db.get_value(
        "Marketing Segment",
        {"segment_name": segment_data.get("segment_name"), "restaurant": restaurant},
        "name"
    )

    if existing:
        doc = frappe.get_doc("Marketing Segment", existing)
        doc.update(segment_data)
        doc.save(ignore_permissions=True)
    else:
        segment_data["doctype"] = "Marketing Segment"
        doc = frappe.get_doc(segment_data)
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"success": True, "data": {"name": doc.name, "estimated_reach": doc.estimated_reach}}


@frappe.whitelist()
@require_plan('GOLD')
def preview_segment_reach(restaurant_id, criteria_type, days_since_last_visit=30,
                           min_visit_count=5, min_total_spent=1000, customer_ids=None):
    if criteria_type == "Custom SQL":
        return {"success": False, "error": "Custom SQL is disabled."}
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    temp_doc = frappe.new_doc("Marketing Segment")
    temp_doc.restaurant = restaurant
    temp_doc.criteria_type = criteria_type
    temp_doc.days_since_last_visit = cint(days_since_last_visit)
    temp_doc.min_visit_count = cint(min_visit_count)
    temp_doc.min_total_spent = flt(min_total_spent)
    temp_doc.customer_ids = customer_ids
    count = temp_doc.compute_reach(dry_run=True)
    return {"success": True, "data": {"estimated_reach": count}}


@frappe.whitelist()
@require_plan('GOLD')
def delete_segment(restaurant_id, segment_name):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    doc_name = frappe.db.get_value(
        "Marketing Segment", {"segment_name": segment_name, "restaurant": restaurant}, "name"
    )
    if doc_name:
        frappe.delete_doc("Marketing Segment", doc_name, ignore_permissions=True)
        frappe.db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# CAMPAIGNS
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
@require_plan('GOLD')
def get_campaigns(restaurant_id, status=None):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    filters = {"restaurant": restaurant}
    if status:
        filters["status"] = status

    campaigns = frappe.get_all(
        "Marketing Campaign",
        filters=filters,
        fields=["name", "campaign_name", "channel", "status", "target_segment",
                "total_recipients", "total_sent", "total_failed", "total_conversions",
                "total_cost_coins", "revenue_attributed", "scheduled_at", "sent_at", "creation"],
        order_by="creation desc"
    )
    return {"success": True, "data": campaigns}


@frappe.whitelist()
@require_plan('GOLD')
def create_campaign(restaurant_id, campaign_data):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    if isinstance(campaign_data, str):
        campaign_data = json.loads(campaign_data)

    campaign_data["doctype"] = "Marketing Campaign"
    campaign_data["restaurant"] = restaurant
    campaign_data["status"] = "Draft"

    doc = frappe.get_doc(campaign_data)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"name": doc.name}}


@frappe.whitelist()
@require_plan('GOLD')
def send_campaign(campaign_id):
    """Validate balance → enqueue dispatch."""
    restaurant_id = frappe.db.get_value("Marketing Campaign", campaign_id, "restaurant")
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)

    doc = frappe.get_doc("Marketing Campaign", campaign_id)
    if doc.status not in ["Draft", "Scheduled"]:
        return {"success": False, "error": f"Cannot send a campaign with status '{doc.status}'"}

    settings = frappe.get_single("Flamezo Settings")
    coins_per_msg = _get_coins_per_msg(settings, doc.channel)

    seg_doc = frappe.get_doc("Marketing Segment", doc.target_segment)
    estimated_reach = seg_doc.compute_reach()
    estimated_cost = estimated_reach * coins_per_msg
    balance = float(frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0)

    if balance < estimated_cost * 0.5:  # Require at least 50% coverage upfront
        return {
            "success": False,
            "error": (
                f"Insufficient Wallet Balance. Estimated cost: {estimated_cost:.1f} ₹"
                f"({estimated_reach} recipients × {coins_per_msg} coins/{doc.channel}). "
                f"Current balance: {balance:.1f} ₹"
            )
        }

    frappe.db.set_value("Marketing Campaign", campaign_id, {
        "total_recipients": estimated_reach,
        "status": "Sending"
    })
    frappe.db.commit()

    frappe.enqueue(
        "flamezo_backend.flamezo.tasks.marketing_tasks.dispatch_campaign_task",
        campaign_id=campaign_id,
        queue="long",
        timeout=7200,
        enqueue_after_commit=True
    )

    return {
        "success": True,
        "data": {
            "campaign_id": campaign_id,
            "estimated_reach": estimated_reach,
            "estimated_cost": round(estimated_cost, 2)
        }
    }


@frappe.whitelist()
@require_plan('GOLD')
def get_campaign_analytics(campaign_id):
    restaurant_id = frappe.db.get_value("Marketing Campaign", campaign_id, "restaurant")
    validate_restaurant_for_api(restaurant_id, frappe.session.user)

    campaign = frappe.get_doc("Marketing Campaign", campaign_id)
    events = frappe.get_all(
        "Marketing Event",
        filters={"campaign": campaign_id},
        fields=["name", "customer", "phone", "channel", "status",
                "sent_at", "converted_at", "coins_charged", "error_message", "conversion_order"],
        order_by="sent_at desc",
        limit=500
    )

    status_counts = {}
    for event in events:
        status_counts[event.status] = status_counts.get(event.status, 0) + 1

    return {
        "success": True,
        "data": {
            "campaign": {
                "name": campaign.name,
                "campaign_name": campaign.campaign_name,
                "channel": campaign.channel,
                "status": campaign.status,
                "total_recipients": campaign.total_recipients,
                "total_sent": campaign.total_sent,
                "total_failed": campaign.total_failed,
                "total_conversions": campaign.total_conversions,
                "total_cost_coins": campaign.total_cost_coins,
                "revenue_attributed": campaign.revenue_attributed,
                "sent_at": campaign.sent_at,
                "message_template": campaign.message_template
            },
            "status_breakdown": status_counts,
            "events": events
        }
    }


@frappe.whitelist()
@require_plan('GOLD')
def cancel_campaign(campaign_id):
    restaurant_id = frappe.db.get_value("Marketing Campaign", campaign_id, "restaurant")
    validate_restaurant_for_api(restaurant_id, frappe.session.user)
    doc = frappe.get_doc("Marketing Campaign", campaign_id)
    if doc.status not in ["Draft", "Scheduled"]:
        return {"success": False, "error": "Only Draft or Scheduled campaigns can be cancelled."}
    frappe.db.set_value("Marketing Campaign", campaign_id, "status", "Cancelled")
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
@require_plan('GOLD')
def delete_campaign(campaign_id):
    restaurant_id = frappe.db.get_value("Marketing Campaign", campaign_id, "restaurant")
    validate_restaurant_for_api(restaurant_id, frappe.session.user)
    doc = frappe.get_doc("Marketing Campaign", campaign_id)
    # Only allow deleting Drafts. Sent/Failed campaigns should be preserved for analytics.
    if doc.status != "Draft":
        return {"success": False, "error": "Only Draft campaigns can be deleted. Please Cancel scheduled ones instead."}
    
    frappe.delete_doc("Marketing Campaign", campaign_id, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# TRIGGERS (AUTOMATION)
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
@require_plan('GOLD')
def get_triggers(restaurant_id):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    triggers = frappe.get_all(
        "Marketing Trigger",
        filters={"restaurant": restaurant},
        fields=["name", "trigger_name", "trigger_event", "channel", "is_active",
                "delay_hours", "days_since_visit", "loyalty_milestone_coins",
                "total_fired", "message_template", "email_subject", "include_coupon", "coupon_code"],
        order_by="modified desc"
    )
    return {"success": True, "data": triggers}


@frappe.whitelist()
@require_plan('GOLD')
def save_trigger(restaurant_id, trigger_data):
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    if isinstance(trigger_data, str):
        trigger_data = json.loads(trigger_data)

    trigger_data["restaurant"] = restaurant
    existing_name = trigger_data.pop("name", None)

    if existing_name and frappe.db.exists("Marketing Trigger", existing_name):
        doc = frappe.get_doc("Marketing Trigger", existing_name)
        doc.update(trigger_data)
        doc.save(ignore_permissions=True)
    else:
        trigger_data["doctype"] = "Marketing Trigger"
        doc = frappe.get_doc(trigger_data)
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"success": True, "data": {"name": doc.name}}


@frappe.whitelist()
@require_plan('GOLD')
def delete_trigger(trigger_name):
    restaurant_id = frappe.db.get_value("Marketing Trigger", trigger_name, "restaurant")
    validate_restaurant_for_api(restaurant_id, frappe.session.user)
    frappe.delete_doc("Marketing Trigger", trigger_name, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# OPT-OUT — PUBLIC WEBHOOK (called by Evolution API on STOP reply)
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def handle_marketing_optout(phone, keyword="STOP", webhook_secret=None):
    """
    Called when Evolution API receives a customer reply with STOP/UNSUBSCRIBE.
    The webhook_secret must match the value in Flamezo Settings for security.
    """
    settings = frappe.get_single("Flamezo Settings")
    expected_secret = getattr(settings, "evolution_api_key", None)
    if webhook_secret != expected_secret:
        frappe.throw("Unauthorized", frappe.AuthenticationError)

    from flamezo_backend.flamezo.tasks.marketing_tasks import handle_opt_out_reply
    success = handle_opt_out_reply(phone=phone, keyword=keyword)
    return {"success": success}


@frappe.whitelist()
@require_plan('GOLD')
def get_optout_stats(restaurant_id):
    """Returns opt-out statistics for the restaurant."""
    restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    total_opted_out = frappe.db.sql("""
        SELECT COUNT(DISTINCT c.name)
        FROM `tabCustomer` c
        JOIN `tabOrder` o ON o.platform_customer = c.name
        WHERE o.restaurant = %s AND c.opted_out_of_marketing = 1
    """, (restaurant,))[0][0] or 0

    recent_optouts = frappe.db.sql("""
        SELECT c.phone, c.customer_name, c.opted_out_at, c.opted_out_keyword
        FROM `tabCustomer` c
        JOIN `tabOrder` o ON o.platform_customer = c.name
        WHERE o.restaurant = %s AND c.opted_out_of_marketing = 1
        ORDER BY c.opted_out_at DESC
        LIMIT 20
    """, (restaurant,), as_dict=True)

    return {"success": True, "data": {"total_opted_out": total_opted_out, "recent": recent_optouts}}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _get_coins_per_msg(settings, channel):
    if channel == "WhatsApp":
        return float(getattr(settings, "marketing_whatsapp_coins_per_msg", None) or 1.20)
    elif channel == "SMS":
        return float(getattr(settings, "marketing_sms_coins_per_msg", None) or 0.25)
    elif channel == "Email":
        return float(getattr(settings, "marketing_email_coins_per_msg", None) or 0.05)
    return 0.25

