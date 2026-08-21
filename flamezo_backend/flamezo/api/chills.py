import uuid
import json as _json
import frappe
from frappe import _
from frappe.utils import now_datetime, today, cint

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session
from flamezo_backend.flamezo.utils import redis_counters as rc

# ── Tag limits ───────────────────────────────────────────────────────────────
MAX_NICHE_TAGS = 8
MAX_CUSTOM_TAGS = 5

# ── Duration cap ────────────────────────────────────────────────────────────
# Chills is discovery content (decide-in-seconds swiping), not storytelling —
# short-form completion rates drop off sharply past ~30-40s, and this app's
# own uploaded content rarely runs longer anyway. Enforced here (the
# authoritative check) AND client-side in chills_upload_screen.dart's
# kMaxChillsDurationSeconds (fail fast, don't waste upload bandwidth on a
# video that'll just get rejected) — keep both in sync if this ever changes.
MAX_CHILLS_DURATION_SECONDS = 60

# ── helpers ─────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _require_session(phone):
    """Mutating endpoints must be backed by a real, verified session for that
    exact phone — not just a client-supplied string (see crowd.py/clubs.py for
    the same pattern/rationale)."""
    if not has_active_customer_session(phone):
        frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
    return phone


def _redis_key(prefix, *parts):
    return f"chills:{prefix}:" + ":".join(str(p) for p in parts)


def _reject_if_too_long(object_key):
    """Authoritative duration check — downloads the raw upload and probes it
    with ffprobe (the client-side check is trust-nothing UX, easily bypassed
    by a direct API call). Best-effort: if the file can't be probed for any
    reason, don't block the publish over an infra hiccup — the length cap is
    a product decision, not a security boundary, so failing open here is the
    right tradeoff (mirrors this module's existing best-effort patterns)."""
    import os
    import tempfile
    from flamezo_backend.flamezo.media.storage import download_object
    from flamezo_backend.flamezo.media.processors import VideoProcessor

    try:
        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "probe_input")
            download_object(object_key, local_path)
            meta = VideoProcessor(local_path, tmp).get_metadata()
            duration = meta.get("duration") or 0
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Chills duration probe failed: {object_key}")
        return

    if duration > MAX_CHILLS_DURATION_SECONDS:
        frappe.throw(
            _(f"Chills videos can be up to {MAX_CHILLS_DURATION_SECONDS} seconds — this one is {int(duration)}s. Trim it and try again."),
            frappe.ValidationError,
        )


def _parse_list(val):
    """Parse a JSON-encoded list or pass-through a list. Returns [] on failure."""
    if not val:
        return []
    try:
        parsed = _json.loads(val) if isinstance(val, str) else val
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _validate_tags(niche_raw, custom_raw):
    """
    Parse, validate against taxonomy, deduplicate, and cap both tag lists.
    Returns (niche_list, custom_list) as plain Python lists.
    Raises frappe.ValidationError if limits exceeded.
    """
    from flamezo_backend.flamezo.utils.niche_taxonomy import TAXONOMY_IDS

    niche = _parse_list(niche_raw)
    custom = _parse_list(custom_raw)

    # Validate niche IDs against known taxonomy
    niche = [i for i in niche if isinstance(i, str) and i.strip() and i in TAXONOMY_IDS]

    # Clean custom tags
    custom = [t.strip() for t in custom if isinstance(t, str) and t.strip()]

    # Deduplicate preserving insertion order
    seen: set = set()
    niche = [i for i in niche if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]
    seen = set()
    custom = [t for t in custom if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    if len(niche) > MAX_NICHE_TAGS:
        frappe.throw(_(f"Maximum {MAX_NICHE_TAGS} niche tags allowed per Chills"))
    if len(custom) > MAX_CUSTOM_TAGS:
        frappe.throw(_(f"Maximum {MAX_CUSTOM_TAGS} custom tags allowed per Chills"))

    return niche, custom


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


def _get_creator_follow_set(phone):
    """Set of Flamezo Creator IDs the phone follows, via their Creator Club
    membership (`clubs.follow_club`). Mirrors `_get_outlet_follow_set`'s
    cache-then-DB pattern; invalidated from `clubs.py` on every follow toggle."""
    if not phone:
        return set()
    cache_key = _redis_key("creator_follows", phone)
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return set(cached)
    rows = frappe.db.sql(
        """
        SELECT DISTINCT cc.creator
        FROM `tabCreator Club Member` ccm
        JOIN `tabCreator Club` cc ON cc.name = ccm.club
        WHERE ccm.customer_phone = %s
        """,
        phone,
        as_dict=True,
    )
    ids = [r.creator for r in rows if r.creator]
    frappe.cache().set_value(cache_key, ids, expires_in_sec=120)
    return set(ids)


def _get_offers_count_map(outlet_ids):
    """Returns {outlet_id: active_coupon_count} for a list of outlets."""
    if not outlet_ids:
        return {}
    placeholders = ",".join(["%s"] * len(outlet_ids))
    rows = frappe.db.sql(
        f"""
        SELECT outlet, COUNT(*) AS cnt
        FROM `tabCoupon`
        WHERE outlet IN ({placeholders})
          AND is_active = 1
        GROUP BY outlet
        """,
        list(outlet_ids),
        as_dict=True,
    )
    return {r.outlet: r.cnt for r in rows}


def _get_outlet_ratings_map(outlet_ids):
    """Returns {outlet_id: rating} for a list of outlets."""
    if not outlet_ids:
        return {}
    placeholders = ",".join(["%s"] * len(outlet_ids))
    rows = frappe.db.sql(
        f"SELECT name, rating FROM `tabOutlet` WHERE name IN ({placeholders})",
        list(outlet_ids),
        as_dict=True,
    )
    return {r.name: float(r.rating) for r in rows if r.rating}


def _get_outlet_followers_map(outlet_ids):
    """Returns {outlet_id: follower_count} — real count of `Chills Outlet Follow` rows per outlet."""
    if not outlet_ids:
        return {}
    placeholders = ",".join(["%s"] * len(outlet_ids))
    rows = frappe.db.sql(
        f"""
        SELECT outlet, COUNT(*) AS cnt
        FROM `tabChills Outlet Follow`
        WHERE outlet IN ({placeholders})
        GROUP BY outlet
        """,
        list(outlet_ids),
        as_dict=True,
    )
    return {r.outlet: r.cnt for r in rows}


def _format_chills(c, liked_set, saved_set, follow_set, offers_map, rating_map=None, followers_map=None, counts_map=None):
    rating_map = rating_map or {}
    followers_map = followers_map or {}
    counts = (counts_map or {}).get(c.name, {})
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
            "rating": rating_map.get(c.outlet),
            "followersCount": followers_map.get(c.outlet, 0),
        },
        "description": c.description or "",
        "audio": c.audio or "",
        "nicheTags": _parse_list(c.niche_tags),
        "customTags": _parse_list(c.custom_tags),
        "location": {
            "name": getattr(c, "location_name", None) or "",
            "lat": float(getattr(c, "location_lat", None) or 0),
            "lng": float(getattr(c, "location_lng", None) or 0),
            "radius": int(getattr(c, "location_radius", None) or 0),
        } if getattr(c, "location_name", None) else None,
        # Redis-authoritative (see redis_counters.py) — `c.*_count` is only
        # the fallback for an item that predates the backfill.
        "likes": counts.get("likes", c.likes_count or 0),
        "saves": counts.get("saves", c.saves_count or 0),
        "shares": counts.get("shares", c.shares_count or 0),
        "views": counts.get("views", c.views_count or 0),
        "isLiked": c.name in liked_set,
        "isSaved": c.name in saved_set,
        "offersCount": offers_map.get(c.outlet, 0) if c.outlet else 0,
        "published_at": str(c.published_at) if c.published_at else "",
    }


def _fetch_interaction_sets(phone, chills_ids):
    """Redis-authoritative (see redis_counters.py) — no DB round-trip here
    once `backfill_from_db()` has run. Degrades to "nothing liked/saved"
    rather than erroring if Redis is unreachable."""
    if not phone or not chills_ids:
        return set(), set()
    liked = rc.members_for("chills_likes", chills_ids, phone)
    saved = rc.members_for("chills_saves", chills_ids, phone)
    return liked, saved


def _fetch_counts_map(items):
    """Batched Redis likes/saves/views for a list of Chills rows — each
    dict falls back to that row's own DB column if Redis has no entry yet."""
    ids = [c.name for c in items]
    likes_fallback = {c.name: c.likes_count or 0 for c in items}
    saves_fallback = {c.name: c.saves_count or 0 for c in items}
    views_fallback = {c.name: c.views_count or 0 for c in items}
    shares_fallback = {c.name: getattr(c, "shares_count", 0) or 0 for c in items}
    likes = rc.get_counts("chills_likes", ids, likes_fallback)
    saves = rc.get_counts("chills_saves", ids, saves_fallback)
    views = rc.get_counts("chills_views", ids, views_fallback)
    shares = rc.get_counts("chills_shares", ids, shares_fallback)
    return {
        i: {"likes": likes.get(i, 0), "saves": saves.get(i, 0), "views": views.get(i, 0), "shares": shares.get(i, 0)}
        for i in ids
    }


# ── feed ────────────────────────────────────────────────────────────────────

_CHILLS_FEED_COLUMNS = """
    c.name, c.outlet, c.outlet_name, c.outlet_city,
    (SELECT r.logo FROM `tabOutlet` r WHERE r.name = c.outlet) AS outlet_logo,
    c.outlet_lat, c.outlet_lng, c.video_url, c.thumbnail_url,
    c.description, c.audio, c.niche_tags, c.custom_tags,
    c.location_name, c.location_lat, c.location_lng, c.location_radius,
    c.likes_count, c.saves_count, c.shares_count, c.views_count,
    c.published_at
"""


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

    # "Pushed to followers" boost: only on the very first page (no cursor
    # yet), pull in the most recent Chills from outlets/creators this phone
    # follows, then fill the rest of the page chronologically as normal,
    # explicitly excluding whatever was already shown via the boost.
    #
    # Deliberately NOT applied on later pages — the boosted set isn't a
    # contiguous chronological window, so there's no single cursor value
    # that could resume it correctly. Every page after the first is pure
    # `ORDER BY published_at DESC`, exactly as before, so pagination stays
    # exact (no skipped/duplicated items deeper in the feed). This is the
    # standard "boost the top of the feed, chronological beyond that"
    # pattern — it's where personalization is most visible anyway.
    followed_rows = []
    if phone and not cursor and limit >= 2:
        follow_outlets = _get_outlet_follow_set(phone)
        follow_creators = _get_creator_follow_set(phone)
        if follow_outlets or follow_creators:
            clauses = []
            boost_params = []
            if follow_outlets:
                placeholders = ",".join(["%s"] * len(follow_outlets))
                clauses.append(f"c.outlet IN ({placeholders})")
                boost_params += list(follow_outlets)
            if follow_creators:
                placeholders = ",".join(["%s"] * len(follow_creators))
                clauses.append(f"c.creator IN ({placeholders})")
                boost_params += list(follow_creators)
            # Capped at half the page (not `limit`) so at least `limit -
            # boost_limit >= 1` slots always remain for the general
            # chronological query below — guarantees `remaining` (and thus
            # the next page's cursor) can never come up empty while
            # `has_more` is true, which would otherwise silently drop
            # whatever general content fell chronologically between the
            # boosted items. "Mostly" per the ask, not "exclusively."
            boost_limit = max(1, limit // 2)
            followed_rows = frappe.db.sql(
                f"""
                SELECT {_CHILLS_FEED_COLUMNS}
                FROM `tabChills` c
                WHERE {where} AND ({" OR ".join(clauses)})
                ORDER BY c.published_at DESC, c.name DESC
                LIMIT %s
                """,
                params + boost_params + [boost_limit],
                as_dict=True,
            )

    remaining = max(limit - len(followed_rows), 0)
    exclude_clause = ""
    exclude_params = []
    if followed_rows:
        placeholders = ",".join(["%s"] * len(followed_rows))
        exclude_clause = f" AND c.name NOT IN ({placeholders})"
        exclude_params = [r.name for r in followed_rows]

    general_rows = frappe.db.sql(
        f"""
        SELECT {_CHILLS_FEED_COLUMNS}
        FROM `tabChills` c
        WHERE {where}{exclude_clause}
        ORDER BY c.published_at DESC, c.name DESC
        LIMIT %s
        """,
        params + exclude_params + [remaining + 1],
        as_dict=True,
    )

    has_more = len(general_rows) > remaining
    items = followed_rows + general_rows[:remaining]

    chills_ids = [c.name for c in items]
    outlet_ids = list({c.outlet for c in items if c.outlet})

    liked_set, saved_set = _fetch_interaction_sets(phone, chills_ids)
    follow_set = _get_outlet_follow_set(phone) if phone else set()
    offers_map = _get_offers_count_map(outlet_ids)
    rating_map = _get_outlet_ratings_map(outlet_ids)
    followers_map = _get_outlet_followers_map(outlet_ids)
    counts_map = _fetch_counts_map(items)

    # The cursor only ever tracks the chronological (general) tail — the
    # one-off followed boost never participates in pagination math (see
    # comment above), so it's irrelevant here even though its items are
    # included in `items`/the response.
    next_cursor = None
    if has_more and general_rows[:remaining]:
        last = general_rows[:remaining][-1]
        next_cursor = f"{last.published_at}|{last.name}"

    result = {
        "reels": [_format_chills(c, liked_set, saved_set, follow_set, offers_map, rating_map, followers_map, counts_map) for c in items],
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
    counts_map = _fetch_counts_map([item])
    follow_set = _get_outlet_follow_set(phone) if phone else set()
    outlet_ids = [item.outlet] if item.outlet else []
    offers_map = _get_offers_count_map(outlet_ids)
    rating_map = _get_outlet_ratings_map(outlet_ids)
    followers_map = _get_outlet_followers_map(outlet_ids)
    return {"success": True, "data": _format_chills(item, liked_set, saved_set, follow_set, offers_map, rating_map, followers_map, counts_map)}


# ── interactions ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def like_chills(chills_id, phone):
    phone = _require_phone(phone)
    if not chills_id:
        frappe.throw(_("chills_id is required"))
    if not frappe.db.exists("Chills", chills_id):
        frappe.throw(_("Chills not found"), frappe.DoesNotExistError)

    # Redis is authoritative for the toggle + live count (see
    # redis_counters.py) — no synchronous DB write on the hot path. The
    # durable `Chills Like` row is reconciled by a queued background job,
    # and the counter column by the periodic flush job (hooks.py).
    liked = rc.toggle_member("chills_likes", chills_id, phone)
    rc.bump_count("chills_likes", chills_id, 1 if liked else -1)
    frappe.enqueue(
        "flamezo_backend.flamezo.utils.redis_counters.persist_toggle",
        queue="short",
        join_doctype="Chills Like",
        join_parent_field="chills",
        item_id=chills_id,
        phone=phone,
        active=liked,
    )
    return {"success": True, "data": {"liked": liked, "id": chills_id}}


@frappe.whitelist(allow_guest=True)
def save_chills(chills_id, phone):
    phone = _require_phone(phone)
    if not chills_id:
        frappe.throw(_("chills_id is required"))
    if not frappe.db.exists("Chills", chills_id):
        frappe.throw(_("Chills not found"), frappe.DoesNotExistError)

    saved = rc.toggle_member("chills_saves", chills_id, phone)
    rc.bump_count("chills_saves", chills_id, 1 if saved else -1)
    frappe.enqueue(
        "flamezo_backend.flamezo.utils.redis_counters.persist_toggle",
        queue="short",
        join_doctype="Chills Save",
        join_parent_field="chills",
        item_id=chills_id,
        phone=phone,
        active=saved,
    )
    return {"success": True, "data": {"saved": saved, "id": chills_id}}


@frappe.whitelist(allow_guest=True)
def get_saved_chills(phone, cursor=None, limit=20):
    """Paginated list of a customer's saved Chills, most-recently-saved
    first. Returns private data (not just a toggle mutation like
    save_chills/like_chills), so unlike those it requires a real verified
    session for the exact phone — same gate as follow_outlet."""
    phone = _require_phone(phone)
    _require_session(phone)
    limit = min(int(limit), 30)

    conditions = ["s.customer_phone=%s", "c.status='published'"]
    params = [phone]

    if cursor:
        try:
            cur_ts, cur_name = cursor.split("|", 1)
            conditions.append("(s.creation < %s OR (s.creation = %s AND s.name < %s))")
            params += [cur_ts, cur_ts, cur_name]
        except ValueError:
            pass

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT {_CHILLS_FEED_COLUMNS}, s.creation AS saved_at, s.name AS save_name
        FROM `tabChills Save` s
        INNER JOIN `tabChills` c ON c.name = s.chills
        WHERE {where}
        ORDER BY s.creation DESC, s.name DESC
        LIMIT %s
        """,
        params + [limit + 1],
        as_dict=True,
    )

    has_more = len(rows) > limit
    items = rows[:limit]

    chills_ids = [c.name for c in items]
    outlet_ids = list({c.outlet for c in items if c.outlet})

    # Every item here is, by definition, saved by this phone — but reuse
    # the shared fetch (rather than hardcoding isSaved=True) so likes are
    # still populated correctly per item.
    liked_set, saved_set = _fetch_interaction_sets(phone, chills_ids)
    follow_set = _get_outlet_follow_set(phone)
    offers_map = _get_offers_count_map(outlet_ids)
    rating_map = _get_outlet_ratings_map(outlet_ids)
    followers_map = _get_outlet_followers_map(outlet_ids)
    counts_map = _fetch_counts_map(items)

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last.saved_at}|{last.save_name}"

    return {
        "success": True,
        "data": {
            "reels": [
                _format_chills(c, liked_set, saved_set, follow_set, offers_map, rating_map, followers_map, counts_map)
                for c in items
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        },
    }


@frappe.whitelist(allow_guest=True)
def record_chills_view(chills_id, phone):
    """Idempotent per phone+chills+day. Increments views_count once per day.
    The counter itself is Redis-buffered (see redis_counters.py) — the
    per-day dedup key below is a separate, unrelated Redis entry, already
    the right pattern, just no longer feeding a synchronous DB write."""
    if not chills_id:
        return {"success": True, "data": {"ok": False}}
    site = getattr(frappe.local, "site", "default")
    cache_key = f"{site}:chills:view:{chills_id}:{phone or 'anon'}:{today()}"
    if frappe.cache().get(cache_key):
        return {"success": True, "data": {"ok": False, "reason": "already_counted"}}
    frappe.cache().set(cache_key, 1, ex=86400)
    rc.bump_count("chills_views", chills_id, 1)
    return {"success": True, "data": {"ok": True}}


@frappe.whitelist(allow_guest=True)
def follow_outlet(outlet_id, phone):
    """Toggle Join/Joined on an outlet in the Chills tab."""
    phone = _require_phone(phone)
    _require_session(phone)
    if not outlet_id:
        frappe.throw(_("outlet_id is required"))

    exists = frappe.db.exists("Chills Outlet Follow", {"outlet": outlet_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Chills Outlet Follow", exists, ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(_redis_key("outlet_follows", phone))
        followers_count = frappe.db.count("Chills Outlet Follow", {"outlet": outlet_id})
        return {"success": True, "data": {"following": False, "outlet_id": outlet_id, "followers_count": followers_count}}
    else:
        doc = frappe.get_doc({
            "doctype": "Chills Outlet Follow",
            "outlet": outlet_id,
            "customer_phone": phone,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(_redis_key("outlet_follows", phone))
        followers_count = frappe.db.count("Chills Outlet Follow", {"outlet": outlet_id})
        return {"success": True, "data": {"following": True, "outlet_id": outlet_id, "followers_count": followers_count}}


@frappe.whitelist(allow_guest=True)
def is_following_outlet(outlet_id, phone=None):
    """Single-outlet follow-status + real member count — seeds the
    Join/Joined button and the "N Members" label on both the Chills tab and
    the outlet detail page. Anonymous/unverified callers always see
    `following: false` rather than erroring, so guest browsing still works;
    `followers_count` is real either way (not gated on auth, it's public)."""
    if not outlet_id:
        return {"success": True, "data": {"following": False, "followers_count": 0}}
    following = bool(
        phone and has_active_customer_session(phone)
        and frappe.db.exists("Chills Outlet Follow", {"outlet": outlet_id, "customer_phone": phone})
    )
    followers_count = frappe.db.count("Chills Outlet Follow", {"outlet": outlet_id})
    return {"success": True, "data": {"following": following, "followers_count": followers_count}}


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

    _reject_if_too_long(object_key)

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

    # Compress the raw upload to a small 720p variant in the background
    # (same pipeline UGC uses), then swap the URLs and drop the raw.
    _enqueue_chills_compression(doc.name, object_key)

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
        WHERE outlet = %s AND is_active = 1
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
def increment_shares(chills_id, phone=None):
    """Redis-buffered (see redis_counters.py) and — unlike before — actually
    deduped: previously this had NO idempotency guard at all, so a retried
    request or a double-tap silently double-counted every time. When a
    phone is available (the normal case), dedupe once per phone+chills+
    minute, same shape as record_chills_view's per-day dedup. Anonymous
    callers fall back to a short per-chills cooldown — coarser, but still
    catches the common double-tap case."""
    if not chills_id:
        frappe.throw(_("chills_id is required"))
    if not frappe.db.exists("Chills", chills_id):
        frappe.throw(_("Chills not found"), frappe.DoesNotExistError)

    site = getattr(frappe.local, "site", "default")
    dedup_key = f"{site}:chills:share:{chills_id}:{phone}" if phone else f"{site}:chills:share_anon:{chills_id}"
    if frappe.cache().get(dedup_key):
        return {"success": True, "data": {"shares": rc.get_count("chills_shares", chills_id), "deduped": True}}
    frappe.cache().set(dedup_key, 1, ex=60)

    rc.bump_count("chills_shares", chills_id, 1)
    return {"success": True, "data": {"shares": rc.get_count("chills_shares", chills_id)}}


# ── merchant dashboard endpoints ─────────────────────────────────────────────

def _resolve_outlet(outlet_id):
    from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
    name = frappe.db.get_value("Outlet", outlet_id, "name") or get_restaurant_from_id(outlet_id)
    if not name:
        frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)
    return name


def _assert_outlet_access(outlet, phone=None):
    """Allow Restaurant Admin/Staff (Frappe session) OR owner phone (app merchants)."""
    # Phone-based auth path (app merchants, frappe.session.user = Guest)
    if phone:
        phone = phone.strip()
        row = frappe.db.get_value("Outlet", outlet, ["owner_phone", "contact_phone"], as_dict=True)
        if row and phone in (row.get("owner_phone") or "", row.get("contact_phone") or ""):
            return
        frappe.throw(_("You don't have access to this outlet."), frappe.PermissionError)

    # Frappe session auth path (dashboard)
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Authentication required."), frappe.AuthenticationError)
    roles = frappe.get_roles(user)
    GLOBAL_ADMIN = {"System Manager", "Flamezo Admin", "Flamezo Supervisor"}
    if user == "Administrator" or any(r in GLOBAL_ADMIN for r in roles) or "Outlet Admin" in roles:
        return
    rec_role = frappe.db.get_value(
        "Outlet User", {"user": user, "outlet": outlet, "is_active": 1}, "role"
    )
    if rec_role not in ("Outlet Admin", "Outlet Staff"):
        frappe.throw(_("You don't have access to this outlet."), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def merchant_request_chills_upload(outlet_id, filename, content_type, kind="video", phone=None):
    """Presigned R2 PUT URL for merchant Chills upload. Accepts Frappe session OR owner phone."""
    from flamezo_backend.flamezo.utils.r2_storage import generate_presigned_put
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    # Derive extension from actual content_type so the key stays accurate
    ext_map = {
        "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
        "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    }
    ext = ext_map.get(content_type, "mp4" if kind == "video" else "jpg")
    object_key = f"chills/merchant/{outlet}/{uuid.uuid4()}.{ext}"
    upload_url = generate_presigned_put(object_key, content_type, expires=3600)
    return {"success": True, "data": {"upload_url": upload_url, "object_key": object_key, "expires_in": 3600}}


@frappe.whitelist(allow_guest=True)
def merchant_publish_chills(
    outlet_id, object_key, description, thumbnail_key=None, phone=None,
    niche_tags=None, custom_tags=None,
    location_name=None, location_lat=None, location_lng=None, location_radius=None,
):
    """Publish a merchant Chills video. Accepts Frappe session OR owner phone."""
    from flamezo_backend.flamezo.utils.r2_storage import public_url
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    _reject_if_too_long(object_key)

    video_url = public_url(object_key)
    thumbnail_url = public_url(thumbnail_key) if thumbnail_key else ""

    niche_list, custom_list = _validate_tags(niche_tags, custom_tags)

    loc_name = (location_name or "").strip()[:200]
    try:
        loc_lat = float(location_lat) if location_lat is not None and location_lat != "" else 0.0
        loc_lng = float(location_lng) if location_lng is not None and location_lng != "" else 0.0
        loc_radius = int(location_radius) if location_radius is not None and location_radius != "" else 0
    except (ValueError, TypeError):
        loc_lat, loc_lng, loc_radius = 0.0, 0.0, 0

    doc = frappe.get_doc({
        "doctype": "Chills",
        "outlet": outlet,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "description": (description or "").strip()[:500],
        "niche_tags": _json.dumps(niche_list) if niche_list else "",
        "custom_tags": _json.dumps(custom_list) if custom_list else "",
        "location_name": loc_name,
        "location_lat": loc_lat,
        "location_lng": loc_lng,
        "location_radius": loc_radius,
        "status": "published",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Compress in the background (720p + poster), swap URLs, delete the raw.
    _enqueue_chills_compression(doc.name, object_key)

    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))

    return {"success": True, "data": {"chills_id": doc.name, "video_url": video_url}}


# ── Background compression (reuses the UGC media pipeline) ─────────────────────

def _enqueue_chills_compression(chills_id, raw_object_key):
    """Queue the transcode job for a freshly-published Chills video. Best-effort:
    if enqueue fails the reel still plays from its raw upload."""
    if not raw_object_key:
        return
    try:
        frappe.enqueue(
            "flamezo_backend.flamezo.api.chills._compress_chills_video",
            queue="long",
            timeout=1800,
            enqueue_after_commit=True,
            chills_id=chills_id,
            raw_object_key=raw_object_key,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Chills compress enqueue failed: {chills_id}")


def _compress_chills_video(chills_id, raw_object_key):
    """Transcode a raw Chills upload to a compressed 720p MP4 + poster (the same
    ffmpeg pipeline UGC uses), point the Chills doc at the compressed CDN URLs.

    The raw original is kept (NOT deleted) — Aug 2026 change. R2 storage is
    ~$0.015/GB-month with no egress fees, so keeping it costs almost nothing,
    and it means a future pipeline improvement (better codec, different
    resolution, a bug fix) can re-derive a new variant from the real source
    instead of re-compressing an already-lossy file — the same pattern
    Instagram/TikTok/YouTube all follow (never serve the raw master directly,
    but never destroy it either).

    Idempotent: variant keys are derived from the raw key, so a retry re-uploads
    to the same paths. Non-fatal: on any failure the reel keeps its raw URL.
    """
    import os
    import tempfile
    from flamezo_backend.flamezo.media.storage import (
        download_object, upload_object, get_cdn_url,
    )
    from flamezo_backend.flamezo.media.processors import process_video

    if not frappe.db.exists("Chills", chills_id):
        return

    base, _dot, _ext = raw_object_key.rpartition(".")
    base = base or raw_object_key
    comp_key = f"{base}_720p.mp4"
    poster_key = f"{base}_poster.jpg"

    with tempfile.TemporaryDirectory() as tmp:
        raw_path = os.path.join(tmp, "raw_input")
        try:
            download_object(raw_object_key, raw_path)
            result = process_video(raw_path, tmp) or {}
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Chills transcode failed: {chills_id}")
            return

        video_path = result.get("video_path")
        poster_path = result.get("poster_path")
        if not isinstance(video_path, str) or not os.path.exists(video_path):
            # Nothing produced — leave the raw upload in place.
            frappe.log_error(f"Chills transcode produced no output for {chills_id}", "Chills Compress")
            return

        upload_object(video_path, comp_key, content_type="video/mp4")
        video_url = get_cdn_url(comp_key)

        thumbnail_url = None
        if isinstance(poster_path, str) and os.path.exists(poster_path):
            upload_object(poster_path, poster_key, content_type="image/jpeg")
            thumbnail_url = get_cdn_url(poster_key)

        updates = {"video_url": video_url}
        if thumbnail_url:
            updates["thumbnail_url"] = thumbnail_url
        # Point the reel at the compressed variant. The raw original is
        # intentionally left in place at raw_object_key — see docstring.
        frappe.db.set_value("Chills", chills_id, updates, update_modified=False)
        frappe.db.commit()

    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))


@frappe.whitelist(allow_guest=True)
def suggest_chills_tags(outlet_id, caption, phone=None):
    """
    AI-powered niche tag suggestion.
    Uses outlet name + type + video caption → Gemini → taxonomy IDs.
    Returns up to 6 valid taxonomy IDs ordered by relevance.
    """
    import json as _json
    import re as _re
    from flamezo_backend.flamezo.services.ai.base import get_gemini_client, handle_ai_error
    from flamezo_backend.flamezo.utils.niche_taxonomy import TAXONOMY_IDS, taxonomy_prompt_block

    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    caption = (caption or "").strip()
    if not caption:
        frappe.throw(_("caption is required"))

    outlet_row = frappe.db.get_value(
        "Outlet", outlet, ["outlet_name", "outlet_type"], as_dict=True
    )
    outlet_name = (outlet_row.get("outlet_name") or outlet) if outlet_row else outlet
    outlet_type = (outlet_row.get("outlet_type") or "Business") if outlet_row else "Business"

    tax_block = taxonomy_prompt_block()
    prompt = f"""You are a content tagging assistant for Flamezo, a lifestyle discovery platform in India.

An outlet called "{outlet_name}" (business type: {outlet_type}) posted a short video with caption:
"{caption}"

From the taxonomy below, select 3 to 6 IDs that most precisely describe what this video is about.
Rules:
- Prefer the most specific (leaf) nodes over broad parent nodes.
- Include a parent only when the video clearly covers the whole category.
- Do NOT include tags from unrelated industries.
- Return ONLY a JSON array of IDs. No explanation.

Example output: ["dining-cafe-specialty", "dining-cafe-brunch"]

Taxonomy (id: breadcrumb):
{tax_block}"""

    try:
        model = get_gemini_client()
        gen_config = {
            "temperature": 0.1,
            "top_p": 0.95,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        response = model.generate_content(prompt, generation_config=gen_config)
        raw = response.text.strip()
        raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.MULTILINE)
        raw = _re.sub(r"\s*```\s*$", "", raw, flags=_re.MULTILINE).strip()
        ids = _json.loads(raw)
        if not isinstance(ids, list):
            ids = []
        valid = [i for i in ids if isinstance(i, str) and i in TAXONOMY_IDS][:6]
        return {"success": True, "data": {"tags": valid}}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "suggest_chills_tags")
        return {"success": False, "data": {"tags": []}, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def resolve_custom_tag(outlet_id, tag_text, phone=None):
    """
    Resolve a user-typed custom tag against the niche taxonomy.
    Returns {matched, tag_id?, tag_label?, partial?} or {matched: false} for novel tags.
    Novel tags should be stored as custom_tags on the Chills doc (separate from niche_tags).
    """
    import json as _json
    import re as _re
    from flamezo_backend.flamezo.services.ai.base import get_gemini_client, handle_ai_error
    from flamezo_backend.flamezo.utils.niche_taxonomy import TAXONOMY_IDS, taxonomy_prompt_block

    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    tag_text = (tag_text or "").strip()
    if not tag_text:
        frappe.throw(_("tag_text is required"))

    tax_block = taxonomy_prompt_block()
    prompt = f"""You are a taxonomy matching assistant for Flamezo, a lifestyle discovery platform.

A merchant typed this custom tag: "{tag_text}"

Decide if any taxonomy entry is a DIRECT or CLOSE semantic match for "{tag_text}".

Rules:
1. DIRECT match — tag clearly describes a product/service in that taxonomy category.
   Return: {{"matched": true, "tag_id": "<id>", "tag_label": "<breadcrumb label>"}}
2. PARTIAL match — tag is more specific than any leaf but a parent is the best approximation.
   Return: {{"matched": true, "tag_id": "<closest id>", "tag_label": "<breadcrumb label>", "partial": true}}
3. NOVEL — tag does not belong in any of the 7 industries, or describes a modifier/feature rather than a business type (e.g. "cloud gaming setup" is a home setup, not a gaming venue; "pet photography" is photography, not a pet store; "biryani recipe" is a recipe, not a restaurant).
   Return: {{"matched": false}}

Be conservative. If the connection requires a stretch, return matched=false.
Return ONLY valid JSON. No explanation.

Taxonomy:
{tax_block}"""

    try:
        model = get_gemini_client()
        gen_config = {
            "temperature": 0.1,
            "top_p": 0.95,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        response = model.generate_content(prompt, generation_config=gen_config)
        raw = response.text.strip()
        raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.MULTILINE)
        raw = _re.sub(r"\s*```\s*$", "", raw, flags=_re.MULTILINE).strip()
        result = _json.loads(raw)
        if not isinstance(result, dict):
            return {"success": True, "data": {"matched": False}}

        matched = bool(result.get("matched"))
        if matched:
            tag_id = result.get("tag_id", "")
            # Validate returned ID is actually in our taxonomy
            if tag_id not in TAXONOMY_IDS:
                return {"success": True, "data": {"matched": False}}
            return {
                "success": True,
                "data": {
                    "matched": True,
                    "tag_id": tag_id,
                    "tag_label": result.get("tag_label", ""),
                    "partial": bool(result.get("partial", False)),
                },
            }
        return {"success": True, "data": {"matched": False}}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "resolve_custom_tag")
        return {"success": False, "data": {"matched": False}, "error": str(e)}


@frappe.whitelist()
def get_merchant_chills(outlet_id, cursor=None, limit=20):
    """Paginated list of Chills belonging to an outlet for the merchant dashboard."""
    limit = min(int(limit), 50)
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet)

    conditions = ["outlet = %s", "status != 'removed'"]
    params = [outlet]

    if cursor:
        try:
            cur_ts, cur_name = cursor.split("|", 1)
            conditions.append("(published_at < %s OR (published_at = %s AND name < %s))")
            params += [cur_ts, cur_ts, cur_name]
        except ValueError:
            pass

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT name, video_url, thumbnail_url, description, audio,
               niche_tags, custom_tags,
               location_name, location_lat, location_lng, location_radius,
               views_count, likes_count, saves_count, shares_count,
               status, published_at
        FROM `tabChills`
        WHERE {where}
        ORDER BY published_at DESC, name DESC
        LIMIT %s
        """,
        params + [limit + 1],
        as_dict=True,
    )

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last.published_at}|{last.name}"

    return {
        "success": True,
        "data": {
            "videos": [
                {
                    "id": r.name,
                    "videoUrl": r.video_url or "",
                    "thumbnail": r.thumbnail_url or "",
                    "description": r.description or "",
                    "audio": r.audio or "",
                    "nicheTags": _parse_list(r.niche_tags),
                    "customTags": _parse_list(r.custom_tags),
                    "location": {
                        "name": r.location_name or "",
                        "lat": float(r.location_lat or 0),
                        "lng": float(r.location_lng or 0),
                        "radius": int(r.location_radius or 0),
                    } if r.location_name else None,
                    "views": cint(r.views_count),
                    "likes": cint(r.likes_count),
                    "saves": cint(r.saves_count),
                    "shares": cint(r.shares_count),
                    "status": r.status,
                    "published_at": str(r.published_at) if r.published_at else "",
                }
                for r in items
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        },
    }


@frappe.whitelist()
def get_chills_outlet_analytics(outlet_id):
    """Aggregate Chills performance stats for a merchant outlet."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet)

    agg = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total_videos,
            COALESCE(SUM(views_count), 0)  AS total_views,
            COALESCE(SUM(likes_count), 0)  AS total_likes,
            COALESCE(SUM(saves_count), 0)  AS total_saves,
            COALESCE(SUM(shares_count), 0) AS total_shares
        FROM `tabChills`
        WHERE outlet = %s AND status = 'published'
        """,
        outlet,
        as_dict=True,
    )
    a = agg[0] if agg else {}

    total_videos = cint(a.get("total_videos"))
    total_views  = cint(a.get("total_views"))
    total_likes  = cint(a.get("total_likes"))
    total_saves  = cint(a.get("total_saves"))
    total_shares = cint(a.get("total_shares"))
    avg_views    = round(total_views / total_videos, 1) if total_videos else 0
    engagement   = round((total_likes + total_saves) / total_views * 100, 1) if total_views else 0

    top_rows = frappe.db.sql(
        """
        SELECT name, video_url, thumbnail_url, description,
               views_count, likes_count, saves_count, shares_count, published_at
        FROM `tabChills`
        WHERE outlet = %s AND status = 'published'
        ORDER BY views_count DESC
        LIMIT 1
        """,
        outlet,
        as_dict=True,
    )
    top_video = None
    if top_rows:
        t = top_rows[0]
        top_video = {
            "id": t.name,
            "thumbnail": t.thumbnail_url or t.video_url or "",
            "description": t.description or "",
            "views": cint(t.views_count),
            "likes": cint(t.likes_count),
            "saves": cint(t.saves_count),
            "shares": cint(t.shares_count),
            "published_at": str(t.published_at) if t.published_at else "",
        }

    return {
        "success": True,
        "data": {
            "total_videos": total_videos,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_saves": total_saves,
            "total_shares": total_shares,
            "avg_views_per_video": avg_views,
            "engagement_rate": engagement,
            "top_video": top_video,
        },
    }


@frappe.whitelist(allow_guest=True)
def merchant_update_chills_tags(outlet_id, chills_id, niche_tags=None, custom_tags=None, phone=None):
    """Update niche_tags and custom_tags on an existing Chills doc."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    if not chills_id:
        frappe.throw(_("chills_id is required"))

    owner_outlet = frappe.db.get_value("Chills", chills_id, "outlet")
    if owner_outlet != outlet:
        frappe.throw(_("This video does not belong to your outlet."), frappe.PermissionError)

    if frappe.db.get_value("Chills", chills_id, "status") == "removed":
        frappe.throw(_("Cannot update a removed Chills."))

    niche_list, custom_list = _validate_tags(niche_tags, custom_tags)

    frappe.db.set_value("Chills", chills_id, {
        "niche_tags": _json.dumps(niche_list) if niche_list else "",
        "custom_tags": _json.dumps(custom_list) if custom_list else "",
    })
    frappe.db.commit()

    # Bust any cached feed slices that include this chills
    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))

    return {
        "success": True,
        "data": {
            "chills_id": chills_id,
            "nicheTags": niche_list,
            "customTags": custom_list,
        },
    }


@frappe.whitelist(allow_guest=True)
def merchant_update_chills_location(
    outlet_id, chills_id,
    location_name=None, location_lat=None, location_lng=None, location_radius=None,
    phone=None,
):
    """Update the location pin on an existing Chills doc. Pass empty strings to clear."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet, phone=phone)

    if not chills_id:
        frappe.throw(_("chills_id is required"))

    owner_outlet = frappe.db.get_value("Chills", chills_id, "outlet")
    if owner_outlet != outlet:
        frappe.throw(_("This video does not belong to your outlet."), frappe.PermissionError)

    if frappe.db.get_value("Chills", chills_id, "status") == "removed":
        frappe.throw(_("Cannot update a removed Chills."))

    loc_name = (location_name or "").strip()[:200]
    try:
        loc_lat = float(location_lat) if location_lat is not None and location_lat != "" else 0.0
        loc_lng = float(location_lng) if location_lng is not None and location_lng != "" else 0.0
        loc_radius = int(location_radius) if location_radius is not None and location_radius != "" else 0
    except (ValueError, TypeError):
        frappe.throw(_("Invalid location coordinates."))
        loc_lat, loc_lng, loc_radius = 0.0, 0.0, 0  # unreachable but satisfies linter

    frappe.db.set_value("Chills", chills_id, {
        "location_name": loc_name,
        "location_lat": loc_lat,
        "location_lng": loc_lng,
        "location_radius": loc_radius,
    })
    frappe.db.commit()

    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))

    return {
        "success": True,
        "data": {
            "chills_id": chills_id,
            "location": {
                "name": loc_name,
                "lat": loc_lat,
                "lng": loc_lng,
                "radius": loc_radius,
            } if loc_name else None,
        },
    }


@frappe.whitelist()
def delete_merchant_chills(outlet_id, chills_id):
    """Soft-delete a Chills doc (set status = removed)."""
    outlet = _resolve_outlet(outlet_id)
    _assert_outlet_access(outlet)

    if not chills_id:
        frappe.throw(_("chills_id is required"))

    owner_outlet = frappe.db.get_value("Chills", chills_id, "outlet")
    if owner_outlet != outlet:
        frappe.throw(_("This video does not belong to your outlet."), frappe.PermissionError)

    frappe.db.set_value("Chills", chills_id, "status", "removed")
    frappe.db.commit()

    frappe.cache().delete_value(_redis_key("feed", "anon", "start", 10))

    return {"success": True, "data": {"chills_id": chills_id}}


@frappe.whitelist(allow_guest=True)
def get_merchant_outlet_location(phone):
    """
    Resolve the merchant's outlet from their phone number and return
    the outlet id, name, and coordinates. Used by the app to pre-seed
    the chills upload location field.
    """
    if not phone:
        frappe.throw(_("phone is required"), frappe.ValidationError)

    phone = phone.strip()

    row = frappe.db.sql(
        """
        SELECT name, outlet_name, latitude, longitude
        FROM `tabOutlet`
        WHERE (owner_phone = %s OR contact_phone = %s)
          AND is_active = 1
        LIMIT 1
        """,
        (phone, phone),
        as_dict=True,
    )

    if not row:
        return {"success": True, "data": None}

    r = row[0]
    lat = float(r.latitude or 0)
    lng = float(r.longitude or 0)

    return {
        "success": True,
        "data": {
            "outlet_id": r.name,
            "outlet_name": r.outlet_name or r.name,
            "lat": lat,
            "lng": lng,
            "has_coords": bool(lat and lng),
        },
    }
