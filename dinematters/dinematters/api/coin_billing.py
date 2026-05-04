"""
DineMatters Wallet Billing System
Unified wallet for AI credits, Commissions, and Platform Fees.
1 INR = 1 Wallet Unit
"""
import frappe
import razorpay
import math
from datetime import datetime
from frappe import _
from dinematters.dinematters.utils.razorpay_utils import get_razorpay_client, get_razorpay_config
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api

# ─── Constants ───────────────────────────────────────────────────────────────
INR_PER_WALLET_UNIT = 1
COINS_PER_ENHANCEMENT = 5   # ₹5
COINS_PER_GENERATION = 10   # ₹10
AUTO_RECHARGE_DAILY_LIMIT = 5000.0  # Safety cap per day
AUTO_RECHARGE_HARD_CAP = 15000.0   # RBI AFA Limit for single transaction

# Bonus Thresholds
BONUS_TIER_1_MIN = 2999.0  # 10% Bonus
BONUS_TIER_2_MIN = 4999.0  # 20% Bonus

# ─── Internal helpers ─────────────────────────────────────────────────────────

def get_bonus_units(base_amount):
    """
    Calculate bonus units based on the recharge amount.
    - Below 2999: Round up to next whole number (e.g. 999 -> 1000)
    - 2999 to 4998: 10% Bonus
    - 4999 and above: 20% Bonus
    """
    amount = float(base_amount)
    bonus = 0
    
    if amount >= BONUS_TIER_2_MIN:
        bonus = amount * 0.20
    elif amount >= BONUS_TIER_1_MIN:
        bonus = amount * 0.10
    elif amount >= 999:
        # Mini-bonus for the starter pack (999 -> 1000)
        bonus = 1.0 if amount < 1000 else 0
        
    return round(bonus, 2)

# (Internal Razorpay helper moved to utils.razorpay_utils)


def record_transaction(restaurant, txn_type, amount, description="", payment_id=None, ref_doctype=None, ref_name=None, gst_amount=0, total_paid=0, fail_below=None):
    """Atomically update restaurant balance and create a transaction log."""
    # Re-read balance with row lock
    balance_info = frappe.db.sql(
        "SELECT coins_balance FROM `tabRestaurant` WHERE name = %s FOR UPDATE",
        (restaurant,)
    )
    current_balance = (balance_info[0][0] if balance_info and balance_info[0][0] is not None else 0.0)

    is_deduction = txn_type in ["AI Deduction", "Commission Deduction", "Daily SILVER Floor", "Daily GOLD Floor", "Daily DIAMOND Floor", "Daily GOLD Subscription", "Daily DIAMOND Subscription", "Lead Unlock", "Delivery Fee"]
    
    if is_deduction:
        new_balance = current_balance - abs(amount)
    elif txn_type in ["Purchase", "Free Coins", "Refund", "Autopay Recharge"]:
        new_balance = current_balance + abs(amount)
    elif txn_type == "Admin Adjustment":
        new_balance = current_balance + amount
    else:
        new_balance = current_balance + amount
    
    # Atomic Guardrail: Stop if balance would fall below allowed limit
    if fail_below is not None and new_balance < fail_below:
        frappe.throw(
            _("Transaction failed: Insufficient Wallet Balance. Required: {0}, Available: {1} (Limit: {2})").format(
                abs(amount), current_balance, fail_below
            ), 
            frappe.ValidationError
        )

    frappe.db.set_value("Restaurant", restaurant, "coins_balance", new_balance)

    txn = frappe.get_doc({
        "doctype": "Coin Transaction",
        "restaurant": restaurant,
        "transaction_type": txn_type,
        "amount": -abs(amount) if is_deduction else abs(amount),
        "gst_amount": gst_amount,
        "total_paid_inr": total_paid or (amount + gst_amount),
        "balance_after": new_balance,
        "description": description,
        "payment_id": payment_id,
        "reference_doctype": ref_doctype,
        "reference_name": ref_name,
    })
    txn.insert(ignore_permissions=True)
    
    # Trigger auto-recharge check if balance falls below threshold
    if txn_type in ["AI Deduction", "Commission Deduction", "Daily SILVER Floor", "Daily GOLD Floor", "Daily DIAMOND Floor", "Daily GOLD Subscription", "Daily DIAMOND Subscription", "Delivery Fee"]:
        check_and_trigger_auto_recharge(restaurant, new_balance)

        # Check for system suspension (-100 grace limit)
        if new_balance < -100:
             res_doc = frappe.get_doc("Restaurant", restaurant)
             res_doc.suspend_restaurant_billing(reason="Exceeded -₹100 Grace Period")

    frappe.db.commit()
    return new_balance


def check_and_trigger_auto_recharge(restaurant, current_balance):
    """Check if balance is below threshold and trigger background recharge."""
    res_doc = frappe.get_doc("Restaurant", restaurant)
    
    if not res_doc.auto_recharge_enabled:
        return

    # Skip if we already have a healthy balance
    if current_balance >= res_doc.auto_recharge_threshold:
        return
        
    # Enforce daily safety limit
    today = datetime.now().date()
    if res_doc.last_auto_recharge_date != today:
        # Reset counter for a new day
        frappe.db.set_value("Restaurant", restaurant, {
            "daily_auto_recharge_count": 0,
            "last_auto_recharge_date": today
        })
        current_daily_vol = 0
    else:
        current_daily_vol = res_doc.daily_auto_recharge_count or 0

    if current_daily_vol + res_doc.auto_recharge_amount > AUTO_RECHARGE_DAILY_LIMIT:
        frappe.log_error(f"Auto-recharge blocked by safety limit for {restaurant}. Daily limit: ₹{AUTO_RECHARGE_DAILY_LIMIT}", "Autopay Safety")
        return

    # Trigger async recharge task
    frappe.enqueue(
        "dinematters.dinematters.api.coin_billing.trigger_auto_recharge",
        restaurant=restaurant,
        enqueue_after_commit=True
    )


def trigger_auto_recharge(restaurant):
    """Charge the restaurant for coins using their saved mandate."""
    try:
        res_doc = frappe.get_doc("Restaurant", restaurant)
        # DYNAMIC RECHARGE LOGIC (Grace + configured min, at least 300)
        current_bal = float(res_doc.coins_balance or 0)
        debt_to_clear = abs(min(0, current_bal))

        configured_recharge = float(res_doc.auto_recharge_amount or 1000)
        actual_top_up = max(configured_recharge, 300.0)

        base_amount = debt_to_clear + actual_top_up
        
        # Consistent 18% GST for all wallet transactions
        gst_rate = 0.18
        gst_amount = round(base_amount * gst_rate, 2)
        total_payable = base_amount + gst_amount
        recharge_amt_paise = int(round(total_payable * 100))

        # Safety: Hard Cap for RBI AFA (₹15,000)
        if total_payable > AUTO_RECHARGE_HARD_CAP:
            total_payable = AUTO_RECHARGE_HARD_CAP
            base_amount = round(total_payable / (1 + gst_rate), 2)
            gst_amount = total_payable - base_amount
            recharge_amt_paise = int(AUTO_RECHARGE_HARD_CAP * 100)

        # Guard: must have active mandate and saved token
        if res_doc.mandate_status != "active" or not res_doc.razorpay_token_id or not res_doc.razorpay_customer_id:
            frappe.log_error(
                f"Auto-recharge skipped for {restaurant}: mandate not active or token missing. "
                f"mandate_status={res_doc.mandate_status}, token={bool(res_doc.razorpay_token_id)}",
                "Autopay Skip"
            )
            return

        client = get_razorpay_client()

        # STEP 1: Create Razorpay Order with token notification (RBI pre-debit rule)
        import time
        payment_after_ts = int(time.time()) + (36 * 3600) + (5 * 60)  # 36h 5m minimum TAT

        order = client.order.create({
            "amount": recharge_amt_paise,
            "currency": "INR",
            "payment_capture": True,
            "receipt": f"autopay_{restaurant[:20]}_{int(time.time())}",
            "notification": {
                "token_id": res_doc.razorpay_token_id,
                "payment_after": payment_after_ts
            },
            "notes": {
                "restaurant": restaurant,
                "type": "auto_recharge",
                "base_amount": base_amount,
                "gst_amount": gst_amount,
                "total_payable": total_payable,
                "debt_cleared": str(debt_to_clear),
                "topup_added": str(actual_top_up)
            }
        })

        order_id = order.get("id")
        if not order_id:
            frappe.log_error(f"Auto-recharge order creation returned no id for {restaurant}", "Autopay Error")
            return

        # STEP 2: Create recurring payment via saved mandate token
        # SDK: client.payment.createRecurring() maps to POST /v1/payments/create/recurring
        contact = res_doc.get("owner_phone") or "9999999999"
        email = res_doc.get("owner_email") or f"billing@{restaurant.replace(' ', '').lower()}.com"

        payment = client.payment.createRecurring({
            "email": email,
            "contact": contact,
            "amount": recharge_amt_paise,
            "currency": "INR",
            "order_id": order_id,
            "customer_id": res_doc.razorpay_customer_id,
            "token": res_doc.razorpay_token_id,
            "recurring": True,
            "description": f"DineMatters Autopay: Rs.{total_payable:.0f} for {restaurant}",
            "notes": {
                "restaurant": restaurant,
                "type": "auto_recharge",
                "base_amount": base_amount,
                "gst_amount": gst_amount,
                "total_payable": total_payable,
                "debt_cleared": str(debt_to_clear),
                "topup_added": str(actual_top_up)
            }
        })

        pay_status = payment.get("status") if isinstance(payment, dict) else None
        razorpay_payment_id = payment.get("razorpay_payment_id") or payment.get("id")

        frappe.log_error(
            f"Auto-recharge initiated for {restaurant}: order={order_id}, "
            f"payment_id={razorpay_payment_id}, status={pay_status}, amount=Rs.{total_payable}",
            "Autopay Info"
        )

        if pay_status in ["captured", "authorized"]:
            _credit_autopay_coins(restaurant, base_amount, razorpay_payment_id, res_doc.auto_recharge_threshold, gst_amount=gst_amount, total_paid=total_payable)

        elif pay_status == "created":
            # Async banks (HDFC, Axis, etc.) - coins credited when webhook payment.captured fires
            frappe.log_error(
                f"Auto-recharge async (status=created) for {restaurant}. "
                f"Coins will be credited when webhook fires for {razorpay_payment_id}",
                "Autopay Async"
            )

        elif pay_status == "failed":
            frappe.log_error(f"Auto-recharge payment failed for {restaurant}: {payment}", "Autopay Failed")

    except Exception as e:
        frappe.log_error(f"Auto-recharge failed for {restaurant}: {str(e)}", "Autopay Error")


def _credit_autopay_coins(restaurant, recharge_amt, payment_id, threshold, gst_amount=0, total_paid=0):
    """Credit auto-recharge coins after confirmed payment. Idempotent."""
    already_credited = frappe.db.exists("Coin Transaction", {
        "restaurant": restaurant,
        "payment_id": payment_id,
        "transaction_type": "Autopay Recharge"
    })
    if already_credited:
        return

    record_transaction(
        restaurant=restaurant,
        txn_type="Autopay Recharge",
        amount=recharge_amt,
        description=f"Auto-Recharge triggered (Balance was below Rs.{threshold})",
        payment_id=payment_id,
        gst_amount=gst_amount,
        total_paid=total_paid
    )

    frappe.db.sql("""
        UPDATE `tabRestaurant`
        SET daily_auto_recharge_count = daily_auto_recharge_count + %s,
            last_auto_recharge_date = %s
        WHERE name = %s
    """, (recharge_amt, datetime.now().date(), restaurant))

    frappe.db.commit()



# ─── Public APIs ──────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=False)
def deduct_coins(restaurant, amount, type, description="", ref_doctype=None, ref_name=None):
    """
    Public API to deduct coins from a restaurant.
    Throws ValidationError if balance is insufficient.
    """
    # Trigger auto-recharge check early so it can process in background
    balance = frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0.0
    check_and_trigger_auto_recharge(restaurant, balance)

    # For automated or platform deductions, we allow going down to the grace limit (-100)
    # For user-triggered AI actions, we could be stricter (e.g. fail if < 0), 
    # but currently we allow usage up to the suspension limit.
    fail_limit = -100.0
    
    return record_transaction(
        restaurant=restaurant,
        txn_type=type,
        amount=amount,
        description=description,
        ref_doctype=ref_doctype,
        ref_name=ref_name,
        fail_below=fail_limit
    )


@frappe.whitelist(allow_guest=False)
def refund_coins(restaurant, amount, description="", ref_doctype=None, ref_name=None):
    """Refund coins to a restaurant."""
    return record_transaction(
        restaurant=restaurant,
        txn_type="Refund",
        amount=amount,
        description=description,
        ref_doctype=ref_doctype,
        ref_name=ref_name
    )


@frappe.whitelist(allow_guest=False)
def get_coin_billing_info(restaurant):
    """Returns the restaurant's coin balance and billing settings."""
    from dinematters.dinematters.tasks.subscription_tasks import sync_restaurant_subscription
    # Fail-safe: Check for overdue plan switches before returning info
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    sync_restaurant_subscription(restaurant)
    
    res = frappe.get_doc("Restaurant", restaurant)
    settings = frappe.get_single("Dinematters Settings")
    
    return {
        "coins_balance": res.coins_balance or 0,
        "auto_recharge_enabled": res.auto_recharge_enabled,
        "auto_recharge_threshold": res.auto_recharge_threshold,
        "auto_recharge_amount": res.auto_recharge_amount,
        "mandate_active": res.mandate_status == "active",
        "daily_limit": AUTO_RECHARGE_DAILY_LIMIT,
        "current_daily_vol": res.daily_auto_recharge_count or 0,
        "deferred_plan_type": res.deferred_plan_type,
        "plan_change_date": res.plan_change_date,
        "billing_status": res.billing_status or "active",
        "onboarding_date": res.onboarding_date,
        "last_auto_recharge_date": res.last_auto_recharge_date,
        # Plan Defaults for Upgrade UI
        # Keys match frontend BillingInfo interface exactly
        "monthly_minimum": float(res.monthly_minimum or 0),
        "platform_fee_percent": float(res.platform_fee_percent or 0),
        "plan_defaults": {
            "silver_monthly": 0.0,
            "pro_monthly": float(settings.gold_monthly_fee or 999.0),       # GOLD monthly min
            "lux_monthly": float(settings.diamond_monthly_floor or 399.0), # DIAMOND monthly min
            "lux_commission": float(settings.diamond_commission_percent or 1.5),
            "lux_barrier": float(settings.diamond_upgrade_barrier or 1299.0) # DIAMOND upgrade balance requirement
        }
    }

@frappe.whitelist(allow_guest=False)
def update_subscription_plan(restaurant, plan_type):
    """
    Schedule a restaurant subscription tier update (SILVER/GOLD/DIAMOND).
    All plan changes follow the 'Tomorrow Rule' (effective at 00:00).
    """
    if plan_type not in ["SILVER", "GOLD", "DIAMOND"]:
        frappe.throw(_("Invalid plan type. Options: SILVER, GOLD, DIAMOND"))
    
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    current_plan = frappe.db.get_value("Restaurant", restaurant, "plan_type")
    if current_plan == plan_type:
        return {"success": True, "message": f"Already on {plan_type} plan."}

    # 1. Entrance Barrier Check (Monthly Minimum Coins for GOLD/DIAMOND)
    res_info = frappe.db.get_value("Restaurant", restaurant, ["coins_balance", "monthly_minimum"], as_dict=True)
    balance = float(res_info.coins_balance or 0.0)

    settings = frappe.get_single("Dinematters Settings")

    if plan_type == "GOLD":
        # Check against restaurant's own minimum, fallback to global default
        min_required = float(res_info.monthly_minimum if res_info.monthly_minimum else (settings.gold_monthly_fee or 999.0))
        if balance < min_required:
            frappe.throw(_(f"Insufficient balance to upgrade to GOLD. Minimum Rs.{min_required} required. Current: {balance}"), frappe.ValidationError)
    
    if plan_type == "DIAMOND":
        # DIAMOND upgrade barrier is a platform-wide constant (manageable in Settings)
        min_required = float(settings.diamond_upgrade_barrier or 1299.0)
        if balance < min_required:
            frappe.throw(_(f"Insufficient balance to upgrade to DIAMOND. Minimum Rs.{min_required} required. Current: {balance}"), frappe.ValidationError)

    # 2. Defer activation to Tomorrow 00:00
    from frappe.utils import add_days, getdate
    tomorrow = add_days(getdate(), 1)
    
    frappe.db.set_value("Restaurant", restaurant, {
        "deferred_plan_type": plan_type,
        "plan_change_date": tomorrow,
        "plan_changed_by": frappe.session.user
    })
    
    frappe.db.commit()
    return {
        "success": True, 
        "deferred": True,
        "plan_type": plan_type,
        "effective_date": tomorrow,
        "message": f"Plan change to {plan_type} scheduled. It will be effective from {tomorrow} at 12:00 AM."
    }

@frappe.whitelist(allow_guest=False)
def update_autopay_settings(restaurant, enabled, threshold, amount):
    """Update autopay configuration."""
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    frappe.db.set_value("Restaurant", restaurant, {
        "auto_recharge_enabled": 1 if enabled else 0,
        "auto_recharge_threshold": float(threshold),
        "auto_recharge_amount": float(amount)
    })
    frappe.db.commit()
    return {"success": True}

@frappe.whitelist(allow_guest=False)
def create_coin_purchase_order(restaurant, amount):
    """
    Create Razorpay order for manual coin purchase.
    Implements upfront 18% GST collection.
    """
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    base_amount = float(amount)
    bonus_units = get_bonus_units(base_amount)
    total_units = base_amount + bonus_units

    gst_rate = 0.18
    gst_amount = base_amount * gst_rate
    total_payable = base_amount + gst_amount
    
    amount_paise = int(total_payable * 100)
    
    client = get_razorpay_client()
    razorpay_order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1,
        "notes": {
            "restaurant": restaurant,
            "coins": total_units, # Note: Includes bonus
            "base_amount": base_amount,
            "bonus_units": bonus_units,
            "gst_amount": gst_amount,
            "total_payable": total_payable,
            "type": "coin_purchase"
        }
    })
    
    cfg = get_razorpay_config()
    key_id = cfg.get("key_id")
    return {
        "success": True,
        "razorpay_order_id": razorpay_order["id"],
        "amount": amount_paise,
        "base_amount": base_amount,
        "gst_amount": gst_amount,
        "total_payable": total_payable,
        "key_id": key_id
    }
@frappe.whitelist(allow_guest=False)
def verify_coin_purchase(restaurant, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify a successful manual coin purchase and credit the restaurant.
    """
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    # 1. Verify Signature
    client = get_razorpay_client()
    cfg = get_razorpay_config()
    key_id = cfg.get("key_id")
    
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    
    try:
        client.utility.verify_payment_signature(params_dict)
    except Exception:
        frappe.log_error(f"Coin purchase verification failed for order {razorpay_order_id}", "Coin Billing")
        frappe.throw(_("Payment verification failed. Please contact support."))

    # 2. Retrieve the order from Razorpay to get the 'notes' (verified amount)
    rzp_order = client.order.fetch(razorpay_order_id)
    notes = rzp_order.get("notes", {})
    coins = float(notes.get("coins", 0))
    gst_amount = float(notes.get("gst_amount", 0))
    total_paid = float(notes.get("total_payable", 0))
    
    if coins <= 0:
        frappe.throw(_("Invalid coin amount in payment notes"))

    # 3. Credit the restaurant
    bonus_units = float(notes.get("bonus_units", 0))
    description = f"Manual Wallet Top-up - Ref: {razorpay_payment_id}"
    if bonus_units > 0:
        description += f" (Incl. ₹{bonus_units:g} Bonus)"

    base_amount = float(notes.get("base_amount", 0))

    record_transaction(
        restaurant=restaurant,
        txn_type="Purchase",
        amount=coins,
        description=description,
        payment_id=razorpay_payment_id,
        gst_amount=gst_amount,
        total_paid=total_paid
    )
    
    # 4. Process Referral Bonus if applicable (Amount >= 1000 and it's the first purchase)
    if base_amount >= 1000:
        process_referral_bonus(restaurant)
    
    return {"success": True, "coins_added": coins}

@frappe.whitelist(allow_guest=False)
def process_referral_bonus(restaurant):
	"""
	Check and grant referral bonuses to both parties.
	Triggered on the referee's first recharge of Rs. 1000+.
	"""
	res_doc = frappe.get_doc("Restaurant", restaurant)
	
	# 1. Must have been referred by someone
	if not res_doc.referred_by_restaurant:
		return
	
	# 2. Check if this is the FIRST non-free transaction (The current one is already recorded)
	txn_count = frappe.db.count("Coin Transaction", {
		"restaurant": restaurant,
		"transaction_type": ["in", ["Purchase", "Autopay Recharge"]]
	})
	
	# If count is 1, it means the current transaction is their first ever purchase
	if txn_count != 1:
		return
		
	# 3. Check if referral bonus was already granted (to prevent double-dipping)
	bonus_exists = frappe.db.exists("Coin Transaction", {
		"restaurant": restaurant,
		"transaction_type": "Free Coins",
		"description": ["like", "%Referral Bonus%"]
	})
	
	if bonus_exists:
		return
		
	# 4. Grant Bonus
	bonus_amt = 500
	referrer = res_doc.referred_by_restaurant
	
	# Credit Referrer
	record_transaction(
		restaurant=referrer,
		txn_type="Free Coins",
		amount=bonus_amt,
		description=f"Referral Bonus: You referred {res_doc.restaurant_name}!",
	)
	
	# Credit Referee (the one who just recharged)
	record_transaction(
		restaurant=restaurant,
		txn_type="Free Coins",
		amount=bonus_amt,
		description=f"Referral Bonus: Welcome gift for using {referrer}'s code!",
	)
	
	frappe.db.commit()

@frappe.whitelist(allow_guest=False)
def get_coin_transactions(restaurant, limit=20, offset=0, from_date=None, to_date=None, type=None):
    """Fetch paginated coin transactions for a restaurant with advanced filtering."""
    restaurant = validate_restaurant_for_api(restaurant, frappe.session.user)
    filters = {"restaurant": restaurant}
    
    if from_date and to_date:
        filters["creation"] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
    elif from_date:
        filters["creation"] = [">=", f"{from_date} 00:00:00"]
    elif to_date:
        filters["creation"] = ["<=", f"{to_date} 23:59:59"]
        
    if type == 'credit':
        filters["amount"] = [">", 0]
    elif type == 'debit':
        filters["amount"] = ["<", 0]

    return frappe.db.get_list("Coin Transaction",
        filters=filters,
        fields=["name", "transaction_type", "amount", "gst_amount", "total_paid_inr", "balance_after", "description", "payment_id", "creation", "reference_doctype", "reference_name"],
        order_by="creation desc",
        limit_page_length=int(limit),
        limit_start=int(offset)
    )

@frappe.whitelist(allow_guest=False)
def initialize_free_coins(restaurant):
    """
    Give free signup coins to a new restaurant.
    Ensures they only get it once.
    """
    # 60 coins = 30 legacy credits
    coins_to_add = 60 
    
    # Check if they already got free coins or legacy credits
    existing_coins = frappe.db.count("Coin Transaction", {
        "restaurant": restaurant,
        "transaction_type": "Free Coins",
    })
    # Also check legacy to prevent double-dipping during migration
    existing_credits = frappe.db.count("AI Credit Transaction", {
        "restaurant": restaurant,
        "transaction_type": "Free Credits",
    })
    
    if not existing_coins and not existing_credits:
        record_transaction(
            restaurant=restaurant,
            txn_type="Free Coins",
            amount=coins_to_add,
            description=f"Welcome! Rs.{coins_to_add} free balance to get started.",
        )
        return True
    return False

@frappe.whitelist(allow_guest=False)
def process_monthly_subscription_coin_refill():
    """
    Cron job: Grant 60 free coins to all active GOLD/DIAMOND restaurants monthly.
    """
    from frappe.utils import now
    
    # We target GOLD and DIAMOND plans
    restaurants = frappe.get_all("Restaurant", 
        filters={"plan_type": ["in", ["GOLD", "DIAMOND"]], "is_active": 1},
        pluck="name"
    )
    
    for r in restaurants:
        record_transaction(
            restaurant=r,
            txn_type="Free Coins",
            amount=60,
            description="Monthly Subscription Reward: 60 Free Balance",
        )
    
    frappe.db.commit()


