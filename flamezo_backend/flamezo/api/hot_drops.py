# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Hot Drops — time-boxed, urgency-driven flash-deal strip shown at the very
top of the consumer Discover feed (above "In the limelight"), Instagram-
Stories-style. Was previously 100% hardcoded mock data client-side
(flamezo-app's HotDropsStrip) — this is the real backend for it.

Design: a Hot Drop = an existing Coupon (reuses its discount/redemption
logic and the whole Offer Claim flow) + a real one-off start/end DATETIME
window (nothing in Coupon's schema supports "tonight only, not every
night" — Coupon.valid_from/until is Date-only, valid_time_start/end is a
*recurring daily* window) + optional multi-image story content, uploaded
through the same presigned-R2-PUT pipeline Chills already uses.

Business rules (explicit product decisions, not my defaults):
  - No plan gating — open to every merchant, free growth feature.
  - Max 3 concurrent active/upcoming Hot Drops per outlet (MAX_LIVE_HOT_DROPS_PER_OUTLET
    in the Hot Drop doctype controller — enforced there as the backstop,
    and again here for a clean merchant-facing error before it ever reaches
    the doctype's validate()).
"""

import json
import uuid
import hashlib
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, cint

from flamezo_backend.flamezo.doctype.hot_drop.hot_drop import MAX_LIVE_HOT_DROPS_PER_OUTLET


# ── Outlet resolution / access (same shape as chills.py, courts.py, etc. —
#    each api module owns its own small copy rather than a shared import,
#    matching this codebase's existing convention) ─────────────────────────

def _resolve_outlet(outlet_id):
    name = frappe.db.get_value("Restaurant", outlet_id, "name")
    if not name:
        from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
        name = get_restaurant_from_id(outlet_id)
    if not name:
        frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)
    return name


def _assert_outlet_access(outlet, phone=None):
    """Allow Restaurant Admin/Staff (Frappe session, the web merchant
    dashboard) OR owner phone (a future mobile merchant app)."""
    if phone:
        phone = phone.strip()
        row = frappe.db.get_value("Restaurant", outlet, ["owner_phone", "contact_phone"], as_dict=True)
        if row and phone in (row.get("owner_phone") or "", row.get("contact_phone") or ""):
            return
        frappe.throw(_("You don't have access to this outlet."), frappe.PermissionError)

    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Authentication required."), frappe.AuthenticationError)
    roles = frappe.get_roles(user)
    GLOBAL_ADMIN = {"System Manager", "Flamezo Admin", "Flamezo Supervisor"}
    if user == "Administrator" or any(r in GLOBAL_ADMIN for r in roles) or "Restaurant Admin" in roles:
        return
    rec_role = frappe.db.get_value(
        "Restaurant User", {"user": user, "restaurant": outlet, "is_active": 1}, "role"
    )
    if rec_role not in ("Restaurant Admin", "Restaurant Staff"):
        frappe.throw(_("You don't have access to this outlet."), frappe.PermissionError)


def _seeded_tiebreak_key(seed, item_id):
    """Same fairness mechanism as get_discovery_feed's — see that
    function's docstring for the full rationale. Kept as a local copy
    (rather than importing flamezo.py's private helper) so this module
    doesn't take on a cross-module dependency for a two-line hash."""
    h = hashlib.md5(f"{seed}:{item_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _parse_story_images(raw):
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return [u for u in parsed if isinstance(u, str) and u] if isinstance(parsed, list) else []
    except Exception:
        return []


# ── Merchant: story image upload (presigned R2 PUT, same trio Chills uses) ─

@frappe.whitelist(allow_guest=True)
def request_hot_drop_story_upload(outlet_id, filename, content_type, phone=None):
    """Presigned R2 PUT URL for a Hot Drop story image."""
    from flamezo_backend.flamezo.utils.r2_storage import generate_presigned_put
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    ext = ext_map.get(content_type, "jpg")
    object_key = f"hotdrops/{outlet}/{uuid.uuid4()}.{ext}"
    upload_url = generate_presigned_put(object_key, content_type, expires=3600)
    return {"success": True, "data": {"upload_url": upload_url, "object_key": object_key, "expires_in": 3600}}


# ── Merchant: create / end / list ──────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def create_hot_drop(outlet_id, deal_label, starts_at, ends_at, story_image_keys=None, coupon=None, phone=None):
    """
    Create a Hot Drop.

    story_image_keys: JSON array (or list) of R2 object keys returned by
      request_hot_drop_story_upload, in display order. Optional — if empty,
      the consumer feed falls back to the outlet's gallery cover photo /
      logo at read time (never blocks a merchant from posting for lack of a
      fresh photo).
    coupon: an existing Coupon doc name for this SAME outlet, or omitted for
      a standalone teaser Hot Drop with no formal redeemable code.
    """
    from flamezo_backend.flamezo.utils.r2_storage import object_exists, public_url

    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    deal_label = (deal_label or "").strip()
    if not deal_label:
        frappe.throw(_("Deal label is required."), frappe.ValidationError)

    starts_dt = get_datetime(starts_at)
    ends_dt = get_datetime(ends_at)
    if ends_dt <= starts_dt:
        frappe.throw(_("End time must be after start time."), frappe.ValidationError)

    # Clean, merchant-facing cap message BEFORE the doctype's own validate()
    # backstop (same rule, checked twice by design — see hot_drop.py).
    if ends_dt > now_datetime():
        active_count = frappe.db.count(
            "Hot Drop", {"restaurant": outlet, "is_active": 1, "ends_at": [">", now_datetime()]}
        )
        if active_count >= MAX_LIVE_HOT_DROPS_PER_OUTLET:
            frappe.throw(
                _(f"You already have {MAX_LIVE_HOT_DROPS_PER_OUTLET} active/upcoming Hot Drops. "
                  "End one or wait for it to finish before posting another."),
                frappe.ValidationError,
            )

    if coupon:
        coupon_restaurant = frappe.db.get_value("Coupon", coupon, "restaurant")
        if coupon_restaurant != outlet:
            frappe.throw(_("That coupon doesn't belong to this outlet."), frappe.PermissionError)

    keys = story_image_keys
    if isinstance(keys, str):
        try:
            keys = json.loads(keys)
        except Exception:
            keys = []
    keys = keys or []
    verified_urls = []
    for key in keys[:6]:  # sane per-drop cap on story image count
        if object_exists(key):
            verified_urls.append(public_url(key))

    doc = frappe.get_doc({
        "doctype": "Hot Drop",
        "restaurant": outlet,
        "coupon": coupon or None,
        "deal_label": deal_label,
        "starts_at": starts_dt,
        "ends_at": ends_dt,
        "is_active": 1,
        "story_images": json.dumps(verified_urls),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _invalidate_hot_drops_cache()

    return {"success": True, "data": {"name": doc.name}}


@frappe.whitelist(allow_guest=True)
def end_hot_drop_now(outlet_id, hot_drop_name, phone=None):
    """Merchant kill-switch — ends a drop immediately regardless of ends_at."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    owner_restaurant = frappe.db.get_value("Hot Drop", hot_drop_name, "restaurant")
    if owner_restaurant != outlet:
        frappe.throw(_("That Hot Drop doesn't belong to this outlet."), frappe.PermissionError)

    frappe.db.set_value("Hot Drop", hot_drop_name, "is_active", 0)
    frappe.db.commit()
    _invalidate_hot_drops_cache()
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def list_merchant_hot_drops(outlet_id, phone=None):
    """Merchant's own Hot Drops (active/upcoming + recently ended), for the
    dashboard's "Feature as Hot Drop" panel — shows current slot usage
    against the max-3 cap."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    rows = frappe.get_all(
        "Hot Drop",
        filters={"restaurant": outlet},
        fields=["name", "deal_label", "coupon", "starts_at", "ends_at", "is_active", "story_images"],
        order_by="starts_at desc",
        limit_page_length=20,
    )
    now = now_datetime()
    active_slots_used = 0
    out = []
    for r in rows:
        is_live = bool(r.is_active) and r.starts_at <= now <= r.ends_at
        is_upcoming = bool(r.is_active) and r.ends_at > now and r.starts_at > now
        if bool(r.is_active) and r.ends_at > now:
            active_slots_used += 1
        out.append({
            "name": r.name,
            "deal_label": r.deal_label,
            "coupon": r.coupon,
            "starts_at": r.starts_at,
            "ends_at": r.ends_at,
            "is_active": bool(r.is_active),
            "is_live": is_live,
            "is_upcoming": is_upcoming,
            "story_image_count": len(_parse_story_images(r.story_images)),
        })

    return {
        "success": True,
        "data": {
            "hot_drops": out,
            "active_slots_used": active_slots_used,
            "max_slots": MAX_LIVE_HOT_DROPS_PER_OUTLET,
        },
    }


# ── Consumer: the feed the HotDropsStrip widget actually renders ──────────

def _invalidate_hot_drops_cache():
    """Chills-style invalidate-on-write — a merchant ending a drop early (or
    posting a new one) should reflect near-instantly, not sit wrong for up
    to a TTL window. The short TTL below is a fallback safety net under this,
    not the primary freshness mechanism."""
    try:
        # delete_keys appends its own trailing "*" — don't double it up.
        frappe.cache().delete_keys("flamezo:hotdrops:")
    except Exception:
        pass


@frappe.whitelist(allow_guest=True)
def get_hot_drops(city=None, outlet_type=None, latitude=None, longitude=None, limit=20, rotation_seed=None):
    """
    GET /api/method/flamezo_backend.flamezo.api.hot_drops.get_hot_drops

    Returns currently-live and upcoming (next 48h) Hot Drops, ordered
    (live first, then soonest start, then a seeded fairness tiebreak so
    multiple concurrent live drops rotate fairly across merchants — same
    mechanism as get_discovery_feed's sections).

    Each outlet already caps at 3 rows via create_hot_drop's cap check, so
    no additional per-outlet limiting is needed at read time.
    """
    try:
        limit = min(cint(limit) or 20, 50)
        seed = rotation_seed or frappe.utils.today()

        cache_key = f"flamezo:hotdrops:{city or ''}:{outlet_type or ''}:{seed}:{limit}"
        if frappe.session.user == "Guest":
            cached = frappe.cache().get_value(cache_key)
            if cached:
                return json.loads(cached)

        now = now_datetime()
        upcoming_horizon = frappe.utils.add_to_date(now, hours=48)

        sql_filters = [
            "hd.is_active = 1",
            "hd.ends_at > %s",
            "hd.starts_at <= %s",
            "r.is_active = 1",
        ]
        params = [now, upcoming_horizon]
        if city:
            sql_filters.append("r.city LIKE %s")
            params.append(f"%{city}%")
        if outlet_type:
            types = [t.strip() for t in str(outlet_type).split(",") if t.strip()]
            if types:
                phs = ",".join(["%s"] * len(types))
                sql_filters.append(f"r.outlet_type IN ({phs})")
                params.extend(types)

        where_clause = " AND ".join(sql_filters)
        rows = frappe.db.sql(
            f"""
            SELECT hd.name, hd.restaurant, hd.deal_label, hd.starts_at, hd.ends_at, hd.story_images,
                   r.restaurant_name, r.logo, r.latitude, r.longitude
            FROM `tabHot Drop` hd
            INNER JOIN `tabRestaurant` r ON r.name = hd.restaurant
            WHERE {where_clause}
            LIMIT 200
            """,
            params,
            as_dict=True,
        )

        items = []
        for r in rows:
            is_live = r.starts_at <= now <= r.ends_at
            images = _parse_story_images(r.story_images)
            thumbnail = images[0] if images else (r.logo or "")
            items.append({
                "id": r.name,
                "outlet_id": r.restaurant,
                "venue_name": r.restaurant_name,
                "deal_label": r.deal_label,
                "thumbnail": thumbnail,
                "stories": images,
                "starts_at": r.starts_at.isoformat() if hasattr(r.starts_at, "isoformat") else str(r.starts_at),
                "ends_at": r.ends_at.isoformat() if hasattr(r.ends_at, "isoformat") else str(r.ends_at),
                "is_live": is_live,
            })

        items.sort(key=lambda x: (
            0 if x["is_live"] else 1,
            x["starts_at"],
            _seeded_tiebreak_key(seed, x["id"]),
        ))
        items = items[:limit]

        response = {"success": True, "data": {"hot_drops": items}}

        if frappe.session.user == "Guest":
            frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=60)

        return response

    except Exception as e:
        frappe.log_error(f"Error in hot_drops.get_hot_drops: {str(e)}")
        return {"success": False, "error": {"code": "HOT_DROPS_ERROR", "message": str(e)}}


# ── Phase 2: view/tap analytics ────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def track_hot_drop_event(hot_drop_name, event_type):
    """Fire-and-forget engagement tracking. event_type: 'hotdrop_view' (card
    scrolled into view) or 'hotdrop_tap' (story opened) — reuses the same
    Analytics Event table already powering the discovery feed's "popular"
    engagement signal, so this data composes with existing analytics
    without a parallel counter system."""
    if event_type not in ("hotdrop_view", "hotdrop_tap"):
        return {"success": False}
    restaurant = frappe.db.get_value("Hot Drop", hot_drop_name, "restaurant")
    if not restaurant:
        return {"success": False}
    try:
        frappe.get_doc({
            "doctype": "Analytics Event",
            "restaurant": restaurant,
            "event_type": event_type,
            "event_value": hot_drop_name,
            "session_id": "anonymous",  # session_id is reqd on this doctype — matches analytics.py's log_event default
            "platform": "mobile",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        # Analytics is best-effort — never let a tracking failure surface to the user.
        pass
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def get_hot_drop_analytics(outlet_id, hot_drop_name=None, phone=None):
    """
    Merchant-facing: views, taps, and view→claim conversion for a Hot Drop
    (or all of the outlet's Hot Drops if hot_drop_name is omitted). Claims
    are read from the existing Offer Claim table via the drop's linked
    Coupon — no new redemption tracking needed, it falls straight out of
    infrastructure the Coupon system already has.
    """
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    filters = {"restaurant": outlet}
    if hot_drop_name:
        filters["name"] = hot_drop_name
    drops = frappe.get_all(
        "Hot Drop", filters=filters,
        fields=["name", "deal_label", "coupon", "starts_at", "ends_at"],
    )
    if not drops:
        return {"success": True, "data": {"drops": []}}

    names = [d.name for d in drops]
    placeholders = ",".join(["%s"] * len(names))
    engagement = frappe.db.sql(
        f"""
        SELECT event_value AS hot_drop, event_type, COUNT(*) AS cnt
        FROM `tabAnalytics Event`
        WHERE event_type IN ('hotdrop_view', 'hotdrop_tap') AND event_value IN ({placeholders})
        GROUP BY event_value, event_type
        """,
        names,
        as_dict=True,
    )
    eng_map = {}
    for row in engagement:
        eng_map.setdefault(row.hot_drop, {"views": 0, "taps": 0})
        eng_map[row.hot_drop]["views" if row.event_type == "hotdrop_view" else "taps"] = row.cnt

    out = []
    for d in drops:
        claims = 0
        if d.coupon:
            claims = frappe.db.count(
                "Offer Claim",
                {"restaurant": outlet, "coupon": d.coupon, "claimed_at": [">=", d.starts_at]},
            )
        eng = eng_map.get(d.name, {"views": 0, "taps": 0})
        views = eng["views"]
        out.append({
            "name": d.name,
            "deal_label": d.deal_label,
            "views": views,
            "taps": eng["taps"],
            "claims": claims,
            "view_to_claim_rate": round((claims / views) * 100, 1) if views else 0,
        })

    return {"success": True, "data": {"drops": out}}
