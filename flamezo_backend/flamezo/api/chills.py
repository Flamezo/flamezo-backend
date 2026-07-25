import uuid
import frappe
from frappe import _
from frappe.utils import now_datetime, today


# ── helpers ─────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _redis_key(prefix, *parts):
    return f"chills:{prefix}:" + ":".join(str(p) for p in parts)


def _get_outlet_follow_set(phone):
    """Returns set of outlet IDs the phone follows (from Redis or DB)."""
    cache_key = _redis_key("outlet_follows", phone)
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return set(cached)
    rows = frappe.db.sql(
        "SELECT outlet FROM `tabChills Outlet Follow` WHERE customer_phone=%s",
        phone,
        as_dict=True,
    )
    ids = [r.outlet for r in rows]
    frappe.cache().set_value(cache_key, ids, expires_in_sec=120)
    return set(ids)


def _get_offers_count_map(outlet_ids):
    """Returns {outlet_id: active_coupon_count} for a list of outlets."""
    if not outlet_ids:
        return {}
    placeholders = ",".join(["%s"] * len(outlet_ids))
    rows = frappe.db.sql(
        f"""
        SELECT restaurant, COUNT(*) AS cnt
        FROM `tabCoupon`
        WHERE restaurant IN ({placeholders})
          AND is_active = 1
        GROUP BY restaurant
        """,
        list(outlet_ids),
        as_dict=True,
    )
    return {r.restaurant: r.cnt for r in rows}


def _format_chills(c, liked_set, saved_set, follow_set, offers_map):
    return {
        "id": c.name,
        "videoUrl": c.video_url or "",
        "thumbnail": c.thumbnail_url or "",
        "outlet": {
            "id": c.outlet or "",
            "name": c.outlet_name or "",
            "city": c.outlet_city or "",
            "avatar": c.outlet_logo or "",
            "isFollowing": c.outlet in follow_set if c.outlet else False,
            "lat": c.outlet_lat or 0,
            "lng": c.outlet_lng or 0,
        },
        "description": c.description or "",
        "audio": c.audio or "",
        "likes": c.likes_count or 0,
        "saves": c.saves_count or 0,
        "shares": c.shares_count or 0,
        "views": c.views_count or 0,
        "isLiked": c.name in liked_set,
        "isSaved": c.name in saved_set,
        "offersCount": offers_map.get(c.outlet, 0) if c.outlet else 0,
        "published_at": str(c.published_at) if c.published_at else "",
    }


def _fetch_interaction_sets(phone, chills_ids):
    if not phone or not chills_ids:
        return set(), set()
    placeholders = ",".join(["%s"] * len(chills_ids))
    liked = {
        r[0]
        for r in frappe.db.sql(
            f"SELECT chills FROM `tabChills Like` WHERE customer_phone=%s AND chills IN ({placeholders})",
            [phone] + list(chills_ids),
        )
    }
    saved = {
        r[0]
        for r in frappe.db.sql(
            f"SELECT chills FROM `tabChills Save` WHERE customer_phone=%s AND chills IN ({placeholders})",
            [phone] + list(chills_ids),
        )
    }
    return liked, saved


# ── feed ────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_chills_feed(phone=None, cursor=None, limit=10):
    limit = min(int(limit), 30)
    cache_key = _redis_key("feed", phone or "anon", cursor or "start", limit)
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    conditions = ["c.status='published'"]
    params = []

    if cursor:
        try:
            cur_ts, cur_name = cursor.split("|", 1)
            conditions.append(
                "(c.published_at < %s OR (c.published_at = %s AND c.name < %s))"
            )
            params += [cur_ts, cur_ts, cur_name]
        except ValueError:
            pass

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT
            c.name, c.outlet, c.outlet_name, c.outlet_city, c.outlet_logo,
            c.outlet_lat, c.outlet_lng, c.video_url, c.thumbnail_url,
            c.description, c.audio,
            c.likes_count, c.saves_count, c.shares_count, c.views_count,
            c.published_at
        FROM `tabChills` c
        WHERE {where}
        ORDER BY c.published_at DESC, c.name DESC
        LIMIT %s
        """,
        params + [limit + 1],
        as_dict=True,
    )

    has_more = len(rows) > limit
    items = rows[:limit]

    chills_ids = [c.name for c in items]
    outlet_ids = list({c.outlet for c in items if c.outlet})

    liked_set, saved_set = _fetch_interaction_sets(phone, chills_ids)
    follow_set = _get_outlet_follow_set(phone) if phone else set()
    offers_map = _get_offers_count_map(outlet_ids)

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last.published_at}|{last.name}"

    result = {
        "reels": [_format_chills(c, liked_set, saved_set, follow_set, offers_map) for c in items],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
    result_wrapped = {"success": True, "data": result}
    frappe.cache().set_value(cache_key, result_wrapped, expires_in_sec=60)
    return result_wrapped


@frappe.whitelist(allow_guest=True)
def get_chills_detail(chills_id, phone=None):
    if not chills_id:
        frappe.throw(_("chills_id is required"))
    rows = frappe.db.sql(
        """
        SELECT c.*
        FROM `tabChills` c
        WHERE c.name = %s AND c.status = 'published'
        """,
        chills_id,
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Chills not found"), frappe.DoesNotExistError)

    item = rows[0]
    liked_set, saved_set = _fetch_interaction_sets(phone, [item.name])
    follow_set = _get_outlet_follow_set(phone) if phone else set()
    offers_map = _get_offers_count_map([item.outlet] if item.outlet else [])
    return {"success": True, "data": _format_chills(item, liked_set, saved_set, follow_set, offers_map)}


# ── interactions ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def like_chills(chills_id, phone):
    phone = _require_phone(phone)
    if not chills_id:
        frappe.throw(_("chills_id is required"))

    exists = frappe.db.exists("Chills Like", {"chills": chills_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Chills Like", exists, ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabChills` SET likes_count = GREATEST(likes_count - 1, 0) WHERE name=%s",
            chills_id,
        )
        frappe.db.commit()
        return {"success": True, "data": {"liked": False, "id": chills_id}}
    else:
        doc = frappe.get_doc({"doctype": "Chills Like", "chills": chills_id, "customer_phone": phone})
        doc.insert(ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabChills` SET likes_count = likes_count + 1 WHERE name=%s",
            chills_id,
        )
        frappe.db.commit()
        return {"success": True, "data": {"liked": True, "id": chills_id}}


@frappe.whitelist(allow_guest=True)
def save_chills(chills_id, phone):
    phone = _require_phone(phone)
    if not chills_id:
        frappe.throw(_("chills_id is required"))

    exists = frappe.db.exists("Chills Save", {"chills": chills_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Chills Save", exists, ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabChills` SET saves_count = GREATEST(saves_count - 1, 0) WHERE name=%s",
            chills_id,
        )
        frappe.db.commit()
        return {"success": True, "data": {"saved": False, "id": chills_id}}
    else:
        doc = frappe.get_doc({"doctype": "Chills Save", "chills": chills_id, "customer_phone": phone})
        doc.insert(ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabChills` SET saves_count = saves_count + 1 WHERE name=%s",
            chills_id,
        )
        frappe.db.commit()
        return {"success": True, "data": {"saved": True, "id": chills_id}}


@frappe.whitelist(allow_guest=True)
def record_chills_view(chills_id, phone):
    """Idempotent per phone+chills+day. Increments views_count once per day."""
    if not chills_id:
        return {"success": True, "data": {"ok": False}}
    site = getattr(frappe.local, "site", "default")
    cache_key = f"{site}:chills:view:{chills_id}:{phone or 'anon'}:{today()}"
    if frappe.cache().get(cache_key):
        return {"success": True, "data": {"ok": False, "reason": "already_counted"}}
    frappe.cache().set(cache_key, 1, ex=86400)
    frappe.db.sql(
        "UPDATE `tabChills` SET views_count = views_count + 1 WHERE name=%s",
        chills_id,
    )
    frappe.db.commit()
    return {"success": True, "data": {"ok": True}}


@frappe.whitelist(allow_guest=True)
def follow_outlet(outlet_id, phone):
    """Toggle Join/Joined on an outlet in the Chills tab."""
    phone = _require_phone(phone)
    if not outlet_id:
        frappe.throw(_("outlet_id is required"))

    exists = frappe.db.exists("Chills Outlet Follow", {"outlet": outlet_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Chills Outlet Follow", exists, ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(_redis_key("outlet_follows", phone))
        return {"success": True, "data": {"following": False, "outlet_id": outlet_id}}
    else:
        doc = frappe.get_doc({
            "doctype": "Chills Outlet Follow",
            "outlet": outlet_id,
            "customer_phone": phone,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(_redis_key("outlet_follows", phone))
        return {"success": True, "data": {"following": True, "outlet_id": outlet_id}}


# ── upload flow ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def request_chills_upload(filename, content_type, phone):
    phone = _require_phone(phone)
    from flamezo_backend.flamezo.utils.r2_storage import generate_presigned_put

    creator = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone, "status": "approved"}, "name")
    if not creator:
        frappe.throw(_("You are not an approved creator"), frappe.PermissionError)

    object_key = f"chills/{creator}/{uuid.uuid4()}.mp4"
    upload_url = generate_presigned_put(object_key, content_type, expires=3600)
    return {"success": True, "data": {"upload_url": upload_url, "object_key": object_key, "expires_in": 3600}}


@frappe.whitelist()
def publish_chills(object_key, description, phone, outlet_id=None, audio=None, thumbnail_key=None):
    phone = _require_phone(phone)
    from flamezo_backend.flamezo.utils.r2_storage import object_exists, public_url

    creator = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone, "status": "approved"}, "name")
    if not creator:
        frappe.throw(_("You are not an approved creator"), frappe.PermissionError)

    if not outlet_id:
        frappe.throw(_("outlet_id is required"))

    if not object_exists(object_key):
        frappe.throw(_("Video not found on storage. Please upload first."))

    video_url = public_url(object_key)
    thumbnail_url = public_url(thumbnail_key) if thumbnail_key else ""

    doc = frappe.get_doc({
        "doctype": "Chills",
        "creator": creator,
        "outlet": outlet_id,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "description": description or "",
        "audio": audio or "",
        "status": "published",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Invalidate feed caches — delete per-phone cached pages
    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))

    return {"success": True, "data": {"chills_id": doc.name, "video_url": video_url}}


# ── prefetch queue ────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_chills_queue(current_id, phone=None, count=3):
    """Return next `count` published chills after current_id for prefetching."""
    count = min(int(count), 10)
    if not current_id:
        frappe.throw(_("current_id is required"))

    anchor = frappe.db.sql(
        "SELECT published_at FROM `tabChills` WHERE name=%s",
        current_id,
        as_dict=True,
    )
    if not anchor:
        return {"success": True, "data": {"queue": []}}

    anchor_ts = anchor[0].published_at

    rows = frappe.db.sql(
        """
        SELECT name, video_url, thumbnail_url
        FROM `tabChills`
        WHERE status = 'published'
          AND (
              published_at < %s
              OR (published_at = %s AND name < %s)
          )
        ORDER BY published_at DESC, name DESC
        LIMIT %s
        """,
        [anchor_ts, anchor_ts, current_id, count],
        as_dict=True,
    )

    return {
        "success": True,
        "data": {
            "queue": [
                {"id": r.name, "videoUrl": r.video_url or "", "thumbnail": r.thumbnail_url or ""}
                for r in rows
            ]
        },
    }


# ── outlet coupons for display ────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_outlet_active_coupons(outlet_id):
    """Return active coupons for an outlet for display in the Chills offers sheet."""
    if not outlet_id:
        return {"success": True, "data": {"offers": []}}

    rows = frappe.db.sql(
        """
        SELECT name, code, discount_value, min_order_amount,
               discount_type, offer_type, description, valid_until
        FROM `tabCoupon`
        WHERE restaurant = %s AND is_active = 1
        ORDER BY discount_value DESC
        LIMIT 20
        """,
        outlet_id,
        as_dict=True,
    )

    offers = []
    for r in rows:
        dtype = r.discount_type or "flat"
        dval = float(r.discount_value or 0)
        title = f"{int(dval)}% OFF" if dtype == "percent" else f"₹{int(dval)} OFF"
        min_order = float(r.min_order_amount or 0)
        subtitle = f"Min order ₹{int(min_order)}" if min_order else "No minimum order"
        offers.append({
            "id": r.name,
            "code": r.code or "",
            "title": title,
            "subtitle": subtitle,
            "description": r.description or "",
            "discountAmount": dval if dtype == "flat" else 0,
            "discountPercent": dval if dtype == "percent" else None,
            "minOrderAmount": min_order,
            "offerType": r.offer_type or "coupon",
            "type": dtype,
            "isEligible": True,
            "iconType": "flash" if dtype == "percent" else "tag",
        })

    return {"success": True, "data": {"offers": offers}}


# ── shares ────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def increment_shares(chills_id):
    """Atomically increment shares_count on a Chills document."""
    if not chills_id:
        frappe.throw(_("chills_id is required"))

    frappe.db.sql(
        "UPDATE `tabChills` SET shares_count = shares_count + 1 WHERE name=%s",
        chills_id,
    )
    frappe.db.commit()

    new_count = frappe.db.get_value("Chills", chills_id, "shares_count") or 0
    return {"success": True, "data": {"shares": new_count}}


