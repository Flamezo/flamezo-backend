"""
Merchant Standing Offer — creator-marketplace-blueprint.html §17. A
merchant sets always-on terms once; any qualifying creator redeems
without asking. Redemption creates a real Collab Deal (the Sept 2026
fix documented in the blueprint) so it goes through the exact same
Delivery Proof verification and reputation scoring as every other deal
— a creator building trust through standing offers is never a
second-class citizen here.
"""

import json

import frappe
from frappe import _
from datetime import datetime

from frappe.utils import flt, getdate, now_datetime, nowtime, today

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.creator_badges import get_creator_badge_tier

RENEGE_STRIKE_LIMIT = 2  # blueprint §17 — mirrors the creator-side suspension threshold
COOLDOWN_DAYS = 30  # reuses creator_collabs.COOLDOWN_DAYS's value — see module docstring's "one system, not two" note


def _require_own_creator(phone: str) -> str:
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
	creator_name = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
	if not creator_name:
		normalized = normalize_phone(phone)
		for row in frappe.db.get_all("Flamezo Creator", fields=["name", "customer_phone"]):
			if normalize_phone(row.customer_phone or "") == normalized:
				creator_name = row.name
				break
	if not creator_name:
		frappe.throw(_("No creator profile found for this phone."), frappe.DoesNotExistError)
	return creator_name


def _load_offer(offer_id):
	if not frappe.db.exists("Merchant Standing Offer", offer_id):
		frappe.throw(_("Standing offer not found"), frappe.DoesNotExistError)
	return frappe.get_doc("Merchant Standing Offer", offer_id)


# ── merchant: create / manage ───────────────────────────────────────────

@frappe.whitelist()
def create_standing_offer(
	outlet_id, deliverable, reward_type, reward_value_inr,
	reward_item=None, min_followers=0, min_rating=0, min_score_percentile=0,
	valid_days_of_week=None, valid_time_start=None, valid_time_end=None,
	daily_cap=0, monthly_cap=0,
):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	offer = frappe.get_doc({
		"doctype": "Merchant Standing Offer", "outlet": outlet, "deliverable": deliverable,
		"reward_type": reward_type, "reward_value_inr": reward_value_inr, "reward_item": reward_item,
		"min_followers": min_followers, "min_rating": min_rating, "min_score_percentile": min_score_percentile,
		"valid_days_of_week": valid_days_of_week, "valid_time_start": valid_time_start, "valid_time_end": valid_time_end,
		"daily_cap": daily_cap, "monthly_cap": monthly_cap,
	})
	offer.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"offer_id": offer.name}}


@frappe.whitelist()
def update_standing_offer(outlet_id, offer_id, **fields):
	offer = _load_offer(offer_id)
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	if offer.outlet != outlet:
		frappe.throw(_("This standing offer isn't yours."), frappe.PermissionError)
	allowed = {
		"active", "deliverable", "reward_type", "reward_item", "reward_value_inr",
		"min_followers", "min_rating", "min_score_percentile",
		"valid_days_of_week", "valid_time_start", "valid_time_end",
		"daily_cap", "monthly_cap", "auto_approve",
	}
	for k, v in fields.items():
		if k in allowed:
			offer.set(k, v)
	offer.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"offer_id": offer.name}}


@frappe.whitelist()
def list_my_standing_offers(outlet_id=None):
	if not outlet_id:
		return {"success": True, "data": {"offers": []}}
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	rows = frappe.db.get_all(
		"Merchant Standing Offer", filters={"outlet": outlet},
		fields=[
			"name", "active", "suspended", "deliverable", "reward_type", "reward_item", "reward_value_inr",
			"min_followers", "min_rating", "min_score_percentile", "daily_cap", "monthly_cap",
			"redeemed_count", "renege_strikes",
		],
		order_by="creation desc",
	)
	return {"success": True, "data": {"offers": rows}}


# ── creator: discover / redeem ──────────────────────────────────────────

def _within_time_window(offer):
	if not offer.valid_days_of_week and not offer.valid_time_start:
		return True
	if offer.valid_days_of_week:
		today_abbr = getdate(today()).strftime("%a")
		days = [d.strip() for d in offer.valid_days_of_week.split(",") if d.strip()]
		if today_abbr not in days:
			return False
	if offer.valid_time_start and offer.valid_time_end:
		now_t = datetime.strptime(nowtime()[:5], "%H:%M").time()
		start_t = datetime.strptime(offer.valid_time_start, "%H:%M").time()
		end_t = datetime.strptime(offer.valid_time_end, "%H:%M").time()
		if start_t <= end_t:
			if not (start_t <= now_t <= end_t):
				return False
		else:  # window crosses midnight
			if not (now_t >= start_t or now_t <= end_t):
				return False
	return True


def _redemptions_today(offer_name) -> int:
	return frappe.db.count("Collab Deal", {"standing_offer": offer_name, "creation": [">=", today()]})


def _redemptions_this_month(offer_name) -> int:
	month_start = getdate(today()).replace(day=1)
	return frappe.db.count("Collab Deal", {"standing_offer": offer_name, "creation": [">=", month_start]})


def _cooldown_remaining_days(outlet_id, creator_id) -> int:
	"""Same COOLDOWN_DAYS value, same meaning, as creator_collabs.py's own
	cooldown check — but against Collab Deal releases (the real
	completion record for anything going through the marketplace),
	not just Creator Collab Invite, since a Standing Offer redemption
	never creates one of those."""
	last_released = frappe.db.get_value(
		"Collab Deal", {"outlet": outlet_id, "creator": creator_id, "status": "released"},
		"released_at", order_by="released_at desc",
	)
	if not last_released:
		return 0
	days_since = (now_datetime() - frappe.utils.get_datetime(last_released)).days
	return max(0, COOLDOWN_DAYS - days_since)


def _creator_avg_rating(creator_name) -> float:
	return flt(frappe.db.get_value(
		"Creator Collab Invite", {"creator": creator_name, "merchant_rating": [">", 0]}, "avg(merchant_rating)"
	))


def _creator_score_percentile(creator_name) -> float:
	return flt(frappe.db.get_value(
		"Creator Weekly Score", {"creator": creator_name}, "percentile", order_by="week_start desc"
	))


def _offer_qualifies(offer, creator, followers, rating, percentile):
	if not offer.active or offer.suspended:
		return False, "not_available"
	if offer.min_followers and followers < offer.min_followers:
		return False, "followers_too_low"
	if offer.min_rating and rating < offer.min_rating:
		return False, "rating_too_low"
	if offer.min_score_percentile and percentile < offer.min_score_percentile:
		return False, "score_percentile_too_low"
	if not _within_time_window(offer):
		return False, "outside_availability_window"
	if offer.daily_cap and _redemptions_today(offer.name) >= offer.daily_cap:
		return False, "daily_cap_reached"
	if offer.monthly_cap and _redemptions_this_month(offer.name) >= offer.monthly_cap:
		return False, "monthly_cap_reached"
	if _cooldown_remaining_days(offer.outlet, creator) > 0:
		return False, "cooldown_active"
	return True, None


@frappe.whitelist(allow_guest=True)
def list_available_standing_offers(phone):
	"""'Hosting creators now' — every currently-redeemable offer for this
	creator right now. Matches against the subset of blueprint §16's
	eight keys that exist today: followers, rating, score percentile,
	availability window, caps, cooldown. Audience-city-share and
	category-overlap need the Creator Portfolio layer (§15-16, not yet
	built) — honestly omitted rather than faked."""
	creator_name = _require_own_creator(phone)
	followers = frappe.db.get_value("Flamezo Creator", creator_name, "meta_followers") or 0
	rating = _creator_avg_rating(creator_name)
	percentile = _creator_score_percentile(creator_name)

	rows = frappe.db.get_all(
		"Merchant Standing Offer", filters={"active": 1, "suspended": 0},
		fields=[
			"name", "outlet", "deliverable", "reward_type", "reward_item", "reward_value_inr",
			"min_followers", "min_rating", "min_score_percentile",
		],
	)
	available = []
	for offer_row in rows:
		offer = frappe.get_doc("Merchant Standing Offer", offer_row.name)
		ok, _reason = _offer_qualifies(offer, creator_name, followers, rating, percentile)
		if ok:
			outlet_name = frappe.db.get_value("Outlet", offer.outlet, "outlet_name")
			available.append({
				"offer_id": offer.name, "outlet_id": offer.outlet, "outlet_name": outlet_name,
				"deliverable": offer.deliverable, "reward_type": offer.reward_type,
				"reward_item": offer.reward_item, "reward_value_inr": offer.reward_value_inr,
			})
	return {"success": True, "data": {"offers": available}}


@frappe.whitelist(allow_guest=True)
def redeem_standing_offer(phone, offer_id):
	"""Creates a real Collab Deal — deal_type=barter, escrow_required
	False (handshake path, same as any sub-ceiling barter — see
	blueprint §12), standing_offer set instead of gig/direct_invite.
	Delivery Proof is still required before it counts as released; this
	is NOT a shortcut around verification, only around the
	ask-and-wait negotiation step."""
	creator_name = _require_own_creator(phone)
	offer = _load_offer(offer_id)

	followers = frappe.db.get_value("Flamezo Creator", creator_name, "meta_followers") or 0
	rating = _creator_avg_rating(creator_name)
	percentile = _creator_score_percentile(creator_name)
	ok, reason = _offer_qualifies(offer, creator_name, followers, rating, percentile)
	if not ok:
		frappe.throw(_("This offer isn't available to you right now ({0}).").format(reason), frappe.ValidationError)

	terms = {
		"deliverable_type": offer.deliverable, "reward_type": offer.reward_type,
		"reward_item": offer.reward_item, "source": "standing_offer",
	}
	deal = frappe.get_doc({
		"doctype": "Collab Deal", "creator": creator_name, "outlet": offer.outlet,
		"standing_offer": offer.name, "deal_type": "barter", "fair_value_inr": offer.reward_value_inr,
		"terms_json": json.dumps(terms), "deadline": frappe.utils.add_days(today(), 7),
		"free_item_ref": offer.reward_item if offer.reward_type in ("free_item", "both") else None,
	})
	deal.insert(ignore_permissions=True)
	deal.status = "accepted"  # both sides already committed — nothing left to negotiate
	deal.save(ignore_permissions=True)

	frappe.db.set_value("Merchant Standing Offer", offer.name, "redeemed_count", (offer.redeemed_count or 0) + 1)
	frappe.db.commit()
	return {"success": True, "data": {"deal_id": deal.name, "status": deal.status}}


# ── merchant accountability ─────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def flag_renege(phone, deal_id, reason=None):
	"""Creator flags a specific standing-offer redemption as reneged
	(merchant promised the terms then didn't honour them outside the
	server-side-applied-discount path). One flag suspends the offer
	pending review; two strikes total keeps it suspended until ops
	looks at it — mirrors the creator-side suspension symmetry."""
	if not frappe.db.exists("Collab Deal", deal_id):
		frappe.throw(_("Deal not found"), frappe.DoesNotExistError)
	deal = frappe.get_doc("Collab Deal", deal_id)
	creator_name = _require_own_creator(phone)
	if deal.creator != creator_name:
		frappe.throw(_("This deal isn't yours."), frappe.PermissionError)
	if not deal.standing_offer:
		frappe.throw(_("This deal didn't come from a standing offer."), frappe.ValidationError)

	offer = frappe.get_doc("Merchant Standing Offer", deal.standing_offer)
	offer.renege_strikes = (offer.renege_strikes or 0) + 1
	if offer.renege_strikes >= RENEGE_STRIKE_LIMIT:
		offer.suspended = 1
	offer.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.log_error(
		title="standing_offers.flag_renege",
		message=f"Deal {deal.name}, offer {offer.name}: {reason or 'no reason given'}",
	)
	return {"success": True, "data": {"renege_strikes": offer.renege_strikes, "suspended": bool(offer.suspended)}}
