import uuid

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from frappe.utils import flt

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils import redis_counters as rc
from flamezo_backend.flamezo.utils import geo
from flamezo_backend.flamezo.api.flamezo import _format_outlet_card, _batch_active_offers_count, _DISCOVERY_FIELDS


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _publish_post_update(post_id, event_type, payload):
    """Live-update push for a club post's likes/comments — joined via the
    stock `doc_subscribe("Creator Club Post", post_id)` realtime room (see
    the Guest-read permission row on that DocType). Callers always call this
    right after their own explicit `frappe.db.commit()`, so this emits
    immediately rather than via `after_commit=True` — that flag schedules
    the emit for the *next* commit, and since ours already happened, it
    would silently never fire. Best-effort: a Redis/socketio hiccup must
    never fail the underlying mutation, same rationale as crowd.py's
    `send_message` realtime publish."""
    try:
        frappe.publish_realtime(
            "club_post_update",
            {"type": event_type, "post_id": post_id, **payload},
            doctype="Creator Club Post",
            docname=post_id,
        )
    except Exception:
        pass


def _require_session(phone):
    """Mutating club endpoints must be backed by a real, verified session for
    that exact phone — not just a client-supplied string (see crowd.py for the
    same pattern/rationale)."""
    if not has_active_customer_session(phone):
        frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
    return phone


def _optional_verified_phone(phone):
    """For public/guest-readable listings that optionally take a phone (only
    used to annotate 'am I following this club') — treat an unverified phone
    as anonymous instead of hard-failing, so logged-out browsing still works."""
    if phone and not has_active_customer_session(phone):
        return None
    return phone


def _format_club(c, phone=None, member_set=None):
    if member_set is None:
        member_set = set()
    return {
        "id": c.name,
        "club_name": c.club_name or "",
        "niche": c.niche or "",
        "description": c.description or "",
        "cover_image": c.cover_image or "",
        "category": c.category or "",
        "followers_count": c.followers_count or 0,
        "is_following": c.name in member_set,
        "creator_id": c.creator or "",
        "creator_name": c.creator_display_name or "",
        "creator_image": c.creator_profile_image or "",
        # Only present when the listing call passed viewer lat/lng — nearest
        # located talk from this club, for a "4km away" hint on the card.
        "nearest_talk_distance_km": c.get("nearest_talk_distance_km"),
        # True only for the exact phone that owns this club's Flamezo
        # Creator record — gates the post composer / pin / delete controls.
        # Never trust a client-side flag for this; always resolved here.
        # Normalized on both sides — Flamezo Creator.customer_phone is
        # sometimes seeded with a +91 prefix while session/Customer phones
        # never carry one; a raw string compare silently locks out the real
        # admin (caught via real-device testing, not the unit tests, since
        # those used one identical literal for both sides).
        "is_admin": bool(phone) and normalize_phone(phone) == normalize_phone(c.creator_phone),
    }


def _get_member_set(phone):
    if not phone:
        return set()
    rows = frappe.db.sql(
        "SELECT club FROM `tabCreator Club Member` WHERE customer_phone=%s",
        phone,
        as_dict=True,
    )
    return {r.club for r in rows}


def _creator_id_for_phone(phone):
    """Resolves the Flamezo Creator record owned by this phone, if any —
    the reverse of `_club_creator_phone`. `customer_phone` isn't always
    stored bare (some rows carry a +91 prefix), so match on either form
    rather than assuming the caller's phone matches exactly."""
    if not phone:
        return None
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    return frappe.db.get_value(
        "Flamezo Creator",
        {"customer_phone": ["in", [normalized, f"+91{normalized}", f"91{normalized}"]]},
        "name",
    )


# ── club listing ─────────────────────────────────────────────────────────────

def _nearest_post_distance_map(club_ids, user_lat, user_lon, sample_per_club=20):
    """{club_id: nearest_pinned_post_distance_km} — cheapest signal for "is
    this club active near me", sampled off each club's most recent located
    posts rather than scanning every post (a club can have thousands)."""
    if not club_ids or not user_lat or not user_lon:
        return {}
    placeholders = ",".join(["%s"] * len(club_ids))
    rows = frappe.db.sql(
        f"""
        SELECT club, latitude, longitude FROM (
            SELECT club, latitude, longitude,
                   ROW_NUMBER() OVER (PARTITION BY club ORDER BY creation DESC) AS rn
            FROM `tabCreator Club Post`
            -- Float fields default to NOT NULL 0, never actual NULL — "unset"
            -- is 0 here, same convention as Outlet.latitude/longitude
            -- elsewhere in this codebase.
            WHERE club IN ({placeholders}) AND latitude != 0 AND longitude != 0
        ) ranked WHERE rn <= %s
        """,
        list(club_ids) + [sample_per_club],
        as_dict=True,
    )
    nearest = {}
    for r in rows:
        d = geo.haversine_km(user_lat, user_lon, flt(r.latitude), flt(r.longitude))
        if r.club not in nearest or d < nearest[r.club]:
            nearest[r.club] = d
    return nearest


@frappe.whitelist(allow_guest=True)
def get_creator_clubs(phone=None, category=None, search=None, page=1, limit=20, latitude=None, longitude=None):
    phone = _optional_verified_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit
    user_lat = flt(latitude) if latitude else None
    user_lon = flt(longitude) if longitude else None

    conditions = ["cc.is_active=1"]
    params = []

    if category:
        conditions.append("cc.category=%s")
        params.append(category)

    if search:
        conditions.append("(cc.club_name LIKE %s OR cc.niche LIKE %s)")
        s = f"%{search}%"
        params += [s, s]

    # A creator never needs to "discover" their own club — it belongs in
    # the dedicated "Your Club" slot (get_my_creator_club), not mixed into
    # suggestions/search/all-clubs where it reads as someone else's club
    # you could follow.
    my_creator_id = _creator_id_for_phone(phone) if phone else None
    if my_creator_id:
        conditions.append("cc.creator != %s")
        params.append(my_creator_id)

    where = " AND ".join(conditions)

    if user_lat and user_lon:
        # Location changes ranking, not the result set — pull a wider pool,
        # re-sort by proximity + weight, then paginate the sorted pool.
        pool_rows = frappe.db.sql(
            f"""
            SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
                   cc.category, cc.followers_count, cc.creator,
                   fc.display_name AS creator_display_name,
                   fc.profile_image AS creator_profile_image,
                   fc.customer_phone AS creator_phone
            FROM `tabCreator Club` cc
            LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
            WHERE {where}
            ORDER BY cc.followers_count DESC, cc.creation DESC
            LIMIT %s
            """,
            params + [max(limit * 4, 200)],
            as_dict=True,
        )
        distance_map = _nearest_post_distance_map([r.name for r in pool_rows], user_lat, user_lon)
        max_followers = max((r.followers_count or 0) for r in pool_rows) or 1

        def _rank(r):
            dist = distance_map.get(r.name)  # None = club has no located talks yet
            pop = min((r.followers_count or 0) / max_followers, 1.0)
            return geo.blended_score(dist, preference_score=pop, engagement_score=pop)

        pool_rows.sort(key=_rank, reverse=True)
        has_more = len(pool_rows) > offset + limit
        clubs = pool_rows[offset:offset + limit]
        for c in clubs:
            d = distance_map.get(c.name)
            c["nearest_talk_distance_km"] = round(d, 1) if d is not None else None
    else:
        rows = frappe.db.sql(
            f"""
            SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
                   cc.category, cc.followers_count, cc.creator,
                   fc.display_name AS creator_display_name,
                   fc.profile_image AS creator_profile_image,
                   fc.customer_phone AS creator_phone
            FROM `tabCreator Club` cc
            LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
            WHERE {where}
            ORDER BY cc.followers_count DESC, cc.creation DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit + 1, offset],
            as_dict=True,
        )
        has_more = len(rows) > limit
        clubs = rows[:limit]

    member_set = _get_member_set(phone)

    return {"success": True, "data": {
        "clubs": [_format_club(c, phone, member_set) for c in clubs],
        "page": page,
        "has_more": has_more,
    }}


@frappe.whitelist(allow_guest=True)
def get_club_detail(club_id, phone=None):
    phone = _optional_verified_phone(phone)
    if not club_id:
        frappe.throw(_("club_id is required"))

    rows = frappe.db.sql(
        """
        SELECT cc.*, fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image,
               fc.customer_phone AS creator_phone
        FROM `tabCreator Club` cc
        LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
        WHERE cc.name=%s AND cc.is_active=1
        """,
        club_id,
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Club not found"), frappe.DoesNotExistError)

    club = rows[0]
    member_set = _get_member_set(phone)
    result = _format_club(club, phone, member_set)
    result["recent_posts"] = frappe.db.count("Creator Club Post", {"club": club_id})
    result["notify_new_posts"] = bool(
        phone
        and frappe.db.get_value(
            "Creator Club Member", {"club": club_id, "customer_phone": phone}, "notify_new_posts"
        )
    )
    return {"success": True, "data": result}


@frappe.whitelist(allow_guest=True)
def toggle_club_notifications(club_id, phone):
    """Member-only — the bell only means anything once you're actually
    getting this club's posts in the first place (see `follow_club`)."""
    phone = _require_phone(phone)
    _require_session(phone)
    member = frappe.db.get_value("Creator Club Member", {"club": club_id, "customer_phone": phone}, "name")
    if not member:
        frappe.throw(_("Join this club to get notified of new posts."), frappe.ValidationError)
    current = frappe.db.get_value("Creator Club Member", member, "notify_new_posts")
    new_value = 0 if current else 1
    frappe.db.set_value("Creator Club Member", member, "notify_new_posts", new_value)
    frappe.db.commit()
    return {"success": True, "data": {"notify_new_posts": bool(new_value)}}


# ── follow / unfollow ────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def follow_club(club_id, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if not club_id:
        frappe.throw(_("club_id is required"))

    if not frappe.db.exists("Creator Club", {"name": club_id, "is_active": 1}):
        frappe.throw(_("Club not found"), frappe.DoesNotExistError)

    exists = frappe.db.exists("Creator Club Member", {"club": club_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Creator Club Member", exists, ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabCreator Club` SET followers_count = GREATEST(followers_count - 1, 0) WHERE name=%s",
            club_id,
        )
        # Bust the Chills feed's creator-follow-set cache (see
        # chills._get_creator_follow_set) — otherwise the "pushed to
        # followers" boost keeps using a stale follow list for up to 2 min.
        frappe.cache().delete_value(f"chills:creator_follows:{phone}")
        return {"success": True, "data": {"following": False}}
    else:
        doc = frappe.get_doc({
            "doctype": "Creator Club Member",
            "club": club_id,
            "customer_phone": phone,
            "joined_at": now_datetime(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabCreator Club` SET followers_count = followers_count + 1 WHERE name=%s",
            club_id,
        )
        frappe.cache().delete_value(f"chills:creator_follows:{phone}")
        return {"success": True, "data": {"following": True}}


# ── club posts ────────────────────────────────────────────────────────────────

def _format_post(p, chills_map=None, liked_set=None, views_map=None, tagged_map=None, user_lat=None, user_lon=None):
    liked_set = liked_set or set()
    p_lat = flt(p.get("latitude")) if p.get("latitude") else None
    p_lon = flt(p.get("longitude")) if p.get("longitude") else None
    distance_km = None
    if user_lat and user_lon and p_lat and p_lon:
        distance_km = round(geo.haversine_km(user_lat, user_lon, p_lat, p_lon), 1)
    post = {
        "id": p.name,
        "club_id": p.club,
        "post_type": p.post_type,
        "content": p.content or "",
        "likes_count": p.likes_count or 0,
        "comments_count": p.comments_count or 0,
        "views_count": (views_map or {}).get(p.name, getattr(p, "views_count", 0) or 0),
        "is_liked": p.name in liked_set,
        "tagged_outlets": (tagged_map or {}).get(p.name, []),
        "created_at": str(p.creation) if p.creation else "",
        "latitude": p_lat,
        "longitude": p_lon,
        "location_area": p.get("location_area") or "",
        "location_city": p.get("location_city") or "",
        "distance_km": distance_km,
    }
    if p.post_type == "image":
        post["image_url"] = p.image_url or ""
    if p.post_type == "chills" and p.reel:
        chills = (chills_map or {}).get(p.reel)
        if chills:
            post["chills"] = {
                "id": chills.name,
                "videoUrl": chills.video_url or "",
                "thumbnail": chills.thumbnail_url or "",
                "description": chills.description or "",
                "likes": chills.likes_count or 0,
                "views": chills.views_count or 0,
            }
    return post


def _get_post_like_set(phone, post_ids):
    if not phone or not post_ids:
        return set()
    placeholders = ",".join(["%s"] * len(post_ids))
    rows = frappe.db.sql(
        f"""
        SELECT post FROM `tabCreator Club Post Like`
        WHERE customer_phone=%s AND post IN ({placeholders})
        """,
        [phone] + post_ids,
        as_dict=True,
    )
    return {r.post for r in rows}


def _get_tagged_outlets_map(post_ids):
    """Batch-fetch each post's tagged outlets (the restaurants featured in a
    post — e.g. "Best 5 cafes in Surat") to avoid N+1, same pattern as
    `_get_post_like_set`. Reuses `_format_outlet_card` so a tagged outlet is
    shaped exactly like every other outlet card in the app (full
    OutletListItem — CollaboratorsBlock renders these via FlamezoGroupItem,
    which needs rating/image/offers, not just an id+name).
    {post_id: [outlet_card_dict, ...]}"""
    if not post_ids:
        return {}
    post_placeholders = ",".join(["%s"] * len(post_ids))
    outlet_cols = ", ".join(f"r.{f}" for f in _DISCOVERY_FIELDS)
    rows = frappe.db.sql(
        f"""
        SELECT t.post AS tag_post, {outlet_cols}
        FROM `tabCreator Club Post Tag` t
        JOIN `tabOutlet` r ON r.name = t.outlet
        WHERE t.post IN ({post_placeholders})
        ORDER BY t.creation ASC
        """,
        post_ids,
        as_dict=True,
    )
    offers_map = _batch_active_offers_count([r.name for r in rows]) if rows else {}
    tagged_map = {}
    for r in rows:
        tagged_map.setdefault(r.tag_post, []).append(_format_outlet_card(r, None, None, offers_map))
    return tagged_map


def _club_creator_phone(club_id):
    """Resolves the phone that owns `club_id`'s Flamezo Creator record —
    the single source of truth for admin/ownership checks on that club.
    Normalized (bare 10-digit) — Flamezo Creator.customer_phone isn't always
    stored that way (some rows carry a +91 prefix), unlike every other
    phone source in this app."""
    club_creator = frappe.db.get_value("Creator Club", club_id, "creator")
    if not club_creator:
        return None
    raw = frappe.db.get_value("Flamezo Creator", club_creator, "customer_phone")
    return normalize_phone(raw) if raw else None


def _require_club_admin(club_id, phone):
    if normalize_phone(phone) != _club_creator_phone(club_id):
        frappe.throw(_("Only this club's creator can do that."), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def get_club_posts(club_id, phone=None, page=1, limit=20, post_type=None, latitude=None, longitude=None):
    phone = _optional_verified_phone(phone)
    if not club_id:
        frappe.throw(_("club_id is required"))

    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit
    user_lat = flt(latitude) if latitude else None
    user_lon = flt(longitude) if longitude else None

    if not frappe.db.exists("Creator Club", {"name": club_id, "is_active": 1}):
        frappe.throw(_("Club not found"), frappe.DoesNotExistError)

    conditions = ["club=%s"]
    params = [club_id]
    if post_type:
        conditions.append("post_type=%s")
        params.append(post_type)
    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT name, club, post_type, reel, image_url, content, likes_count, comments_count,
               views_count, creation, latitude, longitude, location_area, location_city
        FROM `tabCreator Club Post`
        WHERE {where}
        ORDER BY creation DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit + 1, offset],
        as_dict=True,
    )

    has_more = len(rows) > limit
    posts = rows[:limit]

    # Batch-fetch Chills docs for post_type=chills to avoid N+1
    chills_ids = [p.reel for p in posts if p.post_type == "chills" and p.reel]
    chills_map = {}
    if chills_ids:
        placeholders = ",".join(["%s"] * len(chills_ids))
        chills_rows = frappe.db.sql(
            f"""
            SELECT name, video_url, thumbnail_url, description, likes_count, views_count
            FROM `tabChills`
            WHERE name IN ({placeholders})
            """,
            chills_ids,
            as_dict=True,
        )
        chills_map = {c.name: c for c in chills_rows}

    liked_set = _get_post_like_set(phone, [p.name for p in posts])
    views_map = rc.get_counts(
        "club_post_views", [p.name for p in posts],
        {p.name: p.views_count or 0 for p in posts},
    )
    tagged_map = _get_tagged_outlets_map([p.name for p in posts])

    return {"success": True, "data": {
        "posts": [_format_post(p, chills_map, liked_set, views_map, tagged_map, user_lat, user_lon) for p in posts],
        "page": page,
        "has_more": has_more,
        "is_admin": bool(phone) and normalize_phone(phone) == _club_creator_phone(club_id),
    }}


@frappe.whitelist(allow_guest=True)
def get_creator_feed(phone=None, limit=20, cursor=None, latitude=None, longitude=None):
    """"Latest from Creators" home feed — real posts aggregated across
    clubs, not the single-club view get_club_posts gives. Personalized to
    clubs the caller follows; falls back to recent posts across all active
    clubs when they follow none (new user) or aren't logged in, so the feed
    is never empty. Keyset-paginated on (creation, name) — page/offset
    would skip/duplicate rows as new posts land across many clubs at once,
    same reasoning as get_club_post_comments' cursor.

    When latitude/longitude are given, each fetched window is re-ranked by
    the shared location score before being returned (same "wider pool, sort,
    cut" pattern as flamezo.get_all_outlets) — nearby talks surface first
    without breaking the underlying keyset cursor, since the cursor still
    walks the raw creation-ordered rows underneath."""
    phone = _optional_verified_phone(phone)
    limit = min(int(limit), 50)
    user_lat = flt(latitude) if latitude else None
    user_lon = flt(longitude) if longitude else None
    fetch_limit = (limit * 4 if (user_lat and user_lon) else limit) + 1

    conditions = ["cc.is_active=1"]
    params = []

    member_clubs = _get_member_set(phone) if phone else set()
    if member_clubs:
        placeholders = ",".join(["%s"] * len(member_clubs))
        conditions.append(f"cp.club IN ({placeholders})")
        params += list(member_clubs)

    if cursor:
        cursor_row = frappe.db.get_value("Creator Club Post", cursor, "creation")
        if cursor_row:
            conditions.append("(cp.creation < %s OR (cp.creation = %s AND cp.name < %s))")
            params += [cursor_row, cursor_row, cursor]

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT cp.name, cp.club, cp.post_type, cp.reel, cp.image_url, cp.content,
               cp.likes_count, cp.comments_count, cp.views_count, cp.creation,
               cp.latitude, cp.longitude, cp.location_area, cp.location_city,
               cc.club_name, cc.cover_image AS club_cover_image, cc.followers_count,
               fc.display_name AS creator_display_name, fc.profile_image AS creator_profile_image
        FROM `tabCreator Club Post` cp
        JOIN `tabCreator Club` cc ON cc.name = cp.club
        LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
        WHERE {where}
        ORDER BY cp.creation DESC, cp.name DESC
        LIMIT %s
        """,
        params + [fetch_limit],
        as_dict=True,
    )

    if user_lat and user_lon:
        # Re-rank this window by location + engagement; the cursor for the
        # *next* page is still taken from the raw (unsorted) tail below, so
        # pagination keeps walking forward through real time correctly.
        raw_has_more = len(rows) > fetch_limit - 1
        window = rows[: fetch_limit - 1]
        next_cursor_row = window[-1] if window else None

        max_engagement = max((r.likes_count or 0) + (r.comments_count or 0) for r in window) or 1

        def _rank(r):
            dist = None
            if r.latitude and r.longitude:
                dist = geo.haversine_km(user_lat, user_lon, flt(r.latitude), flt(r.longitude))
            eng = min(((r.likes_count or 0) + (r.comments_count or 0)) / max_engagement, 1.0)
            return geo.blended_score(dist, engagement_score=eng)

        window.sort(key=_rank, reverse=True)
        posts = window[:limit]
        has_more = raw_has_more or len(window) > limit
        # Cursor must stay tied to real creation order, not the re-ranked
        # order, or a later page could re-show/re-skip rows.
        next_cursor_name = next_cursor_row.name if next_cursor_row else None
    else:
        has_more = len(rows) > limit
        posts = rows[:limit]
        next_cursor_name = posts[-1].name if posts else None

    post_ids = [p.name for p in posts]

    chills_ids = [p.reel for p in posts if p.post_type == "chills" and p.reel]
    chills_map = {}
    if chills_ids:
        placeholders = ",".join(["%s"] * len(chills_ids))
        chills_rows = frappe.db.sql(
            f"""
            SELECT name, video_url, thumbnail_url, description, likes_count, views_count
            FROM `tabChills`
            WHERE name IN ({placeholders})
            """,
            chills_ids,
            as_dict=True,
        )
        chills_map = {c.name: c for c in chills_rows}

    liked_set = _get_post_like_set(phone, post_ids)
    views_map = rc.get_counts("club_post_views", post_ids, {p.name: p.views_count or 0 for p in posts})
    tagged_map = _get_tagged_outlets_map(post_ids)
    member_set = _get_member_set(phone)

    formatted = []
    for p in posts:
        item = _format_post(p, chills_map, liked_set, views_map, tagged_map, user_lat, user_lon)
        item.update({
            "club_name": p.club_name or "",
            "club_cover_image": p.club_cover_image or "",
            "creator_name": p.creator_display_name or "",
            "creator_image": p.creator_profile_image or "",
            "is_following": p.club in member_set,
        })
        formatted.append(item)

    return {"success": True, "data": {
        "posts": formatted,
        "has_more": has_more,
        "next_cursor": next_cursor_name,
        "is_personalized": bool(member_clubs),
    }}


@frappe.whitelist(allow_guest=True)
def record_club_post_view(post_id, phone=None):
    """Idempotent per phone+post+day — mirrors `chills.record_chills_view`
    exactly (same dedup mechanism, same Redis-buffered counter infra via
    `redis_counters.py`). Guest views are deduped per-device would need a
    device id we don't have here, so anonymous calls fall back to a shared
    'anon' bucket for the day — same tradeoff Chills already makes."""
    if not post_id:
        return {"success": True, "data": {"ok": False}}
    if not frappe.db.exists("Creator Club Post", post_id):
        return {"success": True, "data": {"ok": False}}
    site = getattr(frappe.local, "site", "default")
    cache_key = f"{site}:club_post:view:{post_id}:{phone or 'anon'}:{today()}"
    if frappe.cache().get(cache_key):
        return {"success": True, "data": {"ok": False, "reason": "already_counted"}}
    frappe.cache().set(cache_key, 1, ex=86400)
    rc.bump_count("club_post_views", post_id, 1)
    return {"success": True, "data": {"ok": True}}


# ── club post mutations ──────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def create_club_post(club_id, phone, post_type, content=None, image_key=None, reel_id=None,
                      tagged_outlet_ids=None, latitude=None, longitude=None,
                      location_area=None, location_city=None):
    phone = _require_phone(phone)
    _require_session(phone)
    if not club_id:
        frappe.throw(_("club_id is required"))
    if post_type not in ("chills", "image", "text"):
        frappe.throw(_("Invalid post_type"))

    post_lat = post_lon = None
    if latitude is not None and longitude is not None:
        post_lat, post_lon = flt(latitude), flt(longitude)
        if not (-90 <= post_lat <= 90 and -180 <= post_lon <= 180):
            frappe.throw(_("Invalid location"))

    club = frappe.db.get_value("Creator Club", {"name": club_id, "is_active": 1}, ["name", "creator"], as_dict=True)
    if not club:
        frappe.throw(_("Club not found"), frappe.DoesNotExistError)
    _require_club_admin(club_id, phone)

    # Comma-separated outlet ids featured in this post (e.g. "Best 5 cafes
    # in Surat" tags those 5 outlets) — same convention as other list-ish
    # params elsewhere in this API (e.g. sender_interests). Silently drops
    # any id that isn't a real, active outlet — never lets a bad id 500 the
    # whole post.
    tag_ids = [t.strip() for t in (tagged_outlet_ids or "").split(",") if t.strip()]
    tag_ids = list(dict.fromkeys(tag_ids))[:5]  # dedupe, cap at 5 tagged outlets
    if tag_ids:
        valid = frappe.db.sql_list(
            f"""SELECT name FROM `tabOutlet` WHERE is_active=1 AND name IN ({",".join(["%s"] * len(tag_ids))})""",
            tag_ids,
        )
        tag_ids = [t for t in tag_ids if t in valid]

    image_url = None
    if post_type == "text" and not (content and content.strip()):
        frappe.throw(_("content is required for a text post"))
    if post_type == "image":
        if not image_key:
            frappe.throw(_("image_key is required for an image post"))
        from flamezo_backend.flamezo.utils.r2_storage import object_exists, public_url
        if not object_exists(image_key):
            frappe.throw(_("Image not found on storage. Please upload first."))
        image_url = public_url(image_key)
        # Compress the raw upload (resized WebP), point the post at the smaller
        # copy and drop the original. Best-effort: any failure keeps the raw.
        try:
            import os
            import tempfile
            from flamezo_backend.flamezo.media.storage import download_object, upload_bytes, delete_object, get_cdn_url
            from flamezo_backend.flamezo.media.processors import compress_image_bytes

            with tempfile.TemporaryDirectory() as _tmp:
                _raw_path = os.path.join(_tmp, "raw")
                download_object(image_key, _raw_path)
                with open(_raw_path, "rb") as _f:
                    _raw = _f.read()
            _comp, _ctype, _ext = compress_image_bytes(_raw)
            if _ctype:
                _base = image_key.rsplit(".", 1)[0] if "." in image_key else image_key
                _comp_key = f"{_base}.{_ext}"
                upload_bytes(_comp_key, _comp, content_type=_ctype)
                image_url = get_cdn_url(_comp_key)
                if _comp_key != image_key:
                    try:
                        delete_object(image_key)
                    except Exception:
                        pass
        except Exception:
            frappe.log_error(frappe.get_traceback(), "club post image compress")
    if post_type == "chills" and not reel_id:
        frappe.throw(_("reel_id is required for a chills post"))
    if post_type == "chills" and not frappe.db.exists("Chills", reel_id):
        frappe.throw(_("Chills not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc({
        "doctype": "Creator Club Post",
        "club": club_id,
        "creator": club.creator,
        "post_type": post_type,
        "content": (content or "").strip(),
        "image_url": image_url,
        "reel": reel_id if post_type == "chills" else None,
        "latitude": post_lat,
        "longitude": post_lon,
        "location_area": (location_area or "").strip()[:140] or None,
        "location_city": (location_city or "").strip()[:80] or None,
    })
    doc.insert(ignore_permissions=True)

    for tag_outlet_id in tag_ids:
        frappe.get_doc({
            "doctype": "Creator Club Post Tag", "post": doc.name, "outlet": tag_outlet_id,
        }).insert(ignore_permissions=True)

    frappe.db.commit()

    # Fanned out off the request path — a club can have thousands of
    # members, each notification insert + push send is its own DB/HTTP
    # round trip, and none of that should block the admin's "post" tap.
    frappe.enqueue(
        "flamezo_backend.flamezo.api.clubs._notify_club_members_new_post",
        queue="short",
        post_id=doc.name,
        club_id=club_id,
    )

    chills_map = {}
    if post_type == "chills":
        chills_map = {reel_id: frappe.db.get_value(
            "Chills", reel_id,
            ["name", "video_url", "thumbnail_url", "description", "likes_count", "views_count"],
            as_dict=True,
        )}
    tagged_map = _get_tagged_outlets_map([doc.name]) if tag_ids else {}
    return {"success": True, "data": _format_post(doc, chills_map, tagged_map=tagged_map)}


def _notify_club_members_new_post(post_id, club_id):
    """Background job (see `create_club_post`) — one in-app + push
    notification per member who has `notify_new_posts` enabled."""
    from flamezo_backend.flamezo.api.notifications_consumer import create_notification

    club_name = frappe.db.get_value("Creator Club", club_id, "club_name") or "a club you follow"
    content = frappe.db.get_value("Creator Club Post", post_id, "content") or ""
    preview = content[:80] if content else "Tap to view the new post"

    members = frappe.db.sql_list(
        "SELECT customer_phone FROM `tabCreator Club Member` WHERE club=%s AND notify_new_posts=1",
        club_id,
    )
    for phone in members:
        create_notification(
            phone,
            title=f"New post in {club_name}",
            body=preview,
            notification_type="club",
            reference_doctype="Creator Club Post",
            reference_name=post_id,
            deep_link=f"/club/{club_id}",
        )


@frappe.whitelist(allow_guest=True)
def delete_club_post(post_id, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if not post_id:
        frappe.throw(_("post_id is required"))

    club_id = frappe.db.get_value("Creator Club Post", post_id, "club")
    if not club_id:
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)
    _require_club_admin(club_id, phone)

    for like_id in frappe.db.sql_list(
        "SELECT name FROM `tabCreator Club Post Like` WHERE post=%s", post_id
    ):
        frappe.delete_doc("Creator Club Post Like", like_id, ignore_permissions=True)
    for tag_id in frappe.db.sql_list(
        "SELECT name FROM `tabCreator Club Post Tag` WHERE post=%s", post_id
    ):
        frappe.delete_doc("Creator Club Post Tag", tag_id, ignore_permissions=True)
    frappe.delete_doc("Creator Club Post", post_id, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"id": post_id}}


@frappe.whitelist(allow_guest=True)
def like_club_post(post_id, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if not post_id:
        frappe.throw(_("post_id is required"))

    if not frappe.db.exists("Creator Club Post", post_id):
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)

    exists = frappe.db.exists("Creator Club Post Like", {"post": post_id, "customer_phone": phone})
    if exists:
        frappe.delete_doc("Creator Club Post Like", exists, ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabCreator Club Post` SET likes_count = GREATEST(likes_count - 1, 0) WHERE name=%s",
            post_id,
        )
        frappe.db.commit()
        likes_count = frappe.db.get_value("Creator Club Post", post_id, "likes_count")
        _publish_post_update(post_id, "like", {"likes_count": likes_count})
        return {"success": True, "data": {"liked": False, "id": post_id}}
    else:
        doc = frappe.get_doc({"doctype": "Creator Club Post Like", "post": post_id, "customer_phone": phone})
        doc.insert(ignore_permissions=True)
        frappe.db.sql(
            "UPDATE `tabCreator Club Post` SET likes_count = likes_count + 1 WHERE name=%s",
            post_id,
        )
        frappe.db.commit()
        likes_count = frappe.db.get_value("Creator Club Post", post_id, "likes_count")
        _publish_post_update(post_id, "like", {"likes_count": likes_count})
        return {"success": True, "data": {"liked": True, "id": post_id}}


# ── club post comments ───────────────────────────────────────────────────────

def _format_comment(c):
    return {
        "id": c.name,
        "post_id": c.post,
        "author_id": c.customer_phone,
        "author_name": c.customer_name or "",
        "content": c.content or "",
        "created_at": str(c.creation) if c.creation else "",
    }


def _customer_display_name(phone):
    name = frappe.db.get_value("Customer", {"phone": phone}, "customer_name")
    return name or f"Customer {phone}"


@frappe.whitelist(allow_guest=True)
def get_club_post_comments(post_id, phone=None, cursor=None, limit=20):
    """Keyset-paginated, oldest → newest. `cursor` is the name of the oldest
    comment already loaded by the client; passing it fetches the next page of
    older comments. Returns ascending order either way so the client can
    render/prepend directly without re-sorting."""
    phone = _optional_verified_phone(phone)
    if not post_id:
        frappe.throw(_("post_id is required"))
    if not frappe.db.exists("Creator Club Post", post_id):
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)

    limit = min(int(limit), 50)
    conditions = ["post=%s"]
    params = [post_id]

    if cursor:
        cursor_creation = frappe.db.get_value("Creator Club Post Comment", cursor, "creation")
        if cursor_creation:
            conditions.append("(creation < %s OR (creation = %s AND name < %s))")
            params += [cursor_creation, cursor_creation, cursor]

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT name, post, customer_phone, customer_name, content, creation
        FROM `tabCreator Club Post Comment`
        WHERE {where}
        ORDER BY creation DESC, name DESC
        LIMIT %s
        """,
        params + [limit + 1],
        as_dict=True,
    )

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1].name if has_more and page else None
    page.reverse()  # oldest → newest for direct rendering

    return {"success": True, "data": {
        "comments": [_format_comment(c) for c in page],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }}


@frappe.whitelist(allow_guest=True)
def create_club_post_comment(post_id, phone, content):
    phone = _require_phone(phone)
    _require_session(phone)
    if not post_id:
        frappe.throw(_("post_id is required"))
    content = (content or "").strip()
    if not content:
        frappe.throw(_("content is required"))
    if len(content) > 1000:
        frappe.throw(_("Comment is too long"))

    post_club = frappe.db.get_value("Creator Club Post", post_id, "club")
    if not post_club:
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc({
        "doctype": "Creator Club Post Comment",
        "post": post_id,
        "customer_phone": phone,
        "customer_name": _customer_display_name(phone),
        "content": content,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.sql(
        "UPDATE `tabCreator Club Post` SET comments_count = comments_count + 1 WHERE name=%s",
        post_id,
    )
    frappe.db.commit()
    comments_count = frappe.db.get_value("Creator Club Post", post_id, "comments_count")
    _publish_post_update(
        post_id,
        "comment_added",
        {"comments_count": comments_count, "comment": _format_comment(doc)},
    )

    # Notify the club admin (the post's only possible author — see
    # `_require_club_admin` in `create_club_post`) unless they're commenting
    # on their own post.
    admin_phone = _club_creator_phone(post_club)
    if admin_phone and normalize_phone(phone) != admin_phone:
        from flamezo_backend.flamezo.api.notifications_consumer import create_notification
        create_notification(
            admin_phone,
            title=f"{doc.customer_name or 'Someone'} commented on your post",
            body=content[:80],
            notification_type="club",
            reference_doctype="Creator Club Post",
            reference_name=post_id,
            deep_link=f"/club/{post_club}",
        )

    return {"success": True, "data": _format_comment(doc)}


@frappe.whitelist(allow_guest=True)
def delete_club_post_comment(comment_id, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if not comment_id:
        frappe.throw(_("comment_id is required"))

    row = frappe.db.get_value(
        "Creator Club Post Comment", comment_id, ["post", "customer_phone"], as_dict=True
    )
    if not row:
        frappe.throw(_("Comment not found"), frappe.DoesNotExistError)

    is_author = normalize_phone(phone) == normalize_phone(row.customer_phone)
    is_admin = normalize_phone(phone) == _club_creator_phone(
        frappe.db.get_value("Creator Club Post", row.post, "club")
    )
    if not (is_author or is_admin):
        frappe.throw(_("You can only delete your own comments."), frappe.PermissionError)

    frappe.delete_doc("Creator Club Post Comment", comment_id, ignore_permissions=True)
    frappe.db.sql(
        "UPDATE `tabCreator Club Post` SET comments_count = GREATEST(comments_count - 1, 0) WHERE name=%s",
        row.post,
    )
    frappe.db.commit()
    comments_count = frappe.db.get_value("Creator Club Post", row.post, "comments_count")
    _publish_post_update(
        row.post,
        "comment_deleted",
        {"comments_count": comments_count, "comment_id": comment_id},
    )
    return {"success": True, "data": {"id": comment_id}}


# ── club post image upload ───────────────────────────────────────────────────

@frappe.whitelist()
def request_club_post_upload(club_id, filename, content_type, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    _require_club_admin(club_id, phone)
    from flamezo_backend.flamezo.utils.r2_storage import generate_presigned_put

    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else "jpg"
    object_key = f"club-posts/{club_id}/{uuid.uuid4()}.{ext}"
    upload_url = generate_presigned_put(object_key, content_type, expires=3600)
    return {"success": True, "data": {"upload_url": upload_url, "object_key": object_key, "expires_in": 3600}}


@frappe.whitelist(allow_guest=True)
def get_my_clubs(phone):
    phone = _require_phone(phone)
    _require_session(phone)

    rows = frappe.db.sql(
        """
        SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
               cc.category, cc.followers_count, cc.creator,
               fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image,
               fc.customer_phone AS creator_phone
        FROM `tabCreator Club Member` ccm
        JOIN `tabCreator Club` cc ON cc.name = ccm.club
        LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
        WHERE ccm.customer_phone=%s AND cc.is_active=1
        ORDER BY ccm.creation DESC
        """,
        phone,
        as_dict=True,
    )

    member_set = {r.name for r in rows}
    return {"success": True, "data": {
        "clubs": [_format_club(c, phone, member_set) for c in rows]
    }}


@frappe.whitelist(allow_guest=True)
def get_my_creator_club(phone):
    """The club(s) the caller themselves created (as creator/admin) — the
    "Your Club" quick-access slot on Club Talks, kept separate from
    get_my_clubs (membership/follows) and always excluded from
    get_creator_clubs' discover listing (see that function's own-club
    filter). A creator only ever owns one club today, but this returns a
    list rather than assuming that stays true forever."""
    phone = _require_phone(phone)
    _require_session(phone)

    my_creator_id = _creator_id_for_phone(phone)
    if not my_creator_id:
        return {"success": True, "data": {"clubs": []}}

    rows = frappe.db.sql(
        """
        SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
               cc.category, cc.followers_count, cc.creator,
               fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image,
               fc.customer_phone AS creator_phone
        FROM `tabCreator Club` cc
        LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
        WHERE cc.creator=%s AND cc.is_active=1
        ORDER BY cc.creation ASC
        """,
        my_creator_id,
        as_dict=True,
    )
    member_set = _get_member_set(phone)
    return {"success": True, "data": {
        "clubs": [_format_club(c, phone, member_set) for c in rows]
    }}
