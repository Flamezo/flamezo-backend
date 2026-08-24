"""
Merchant-facing Club Talks API.

The customer app's Club Talks (see api/clubs.py) authenticates with a customer
phone + X-Customer-Token session and only lets a club's owning Flamezo Creator
post. The merchant dashboard has neither — it is Frappe-login + outlet_id. This
module bridges the two: it resolves a merchant's outlet to a Flamezo Creator +
Creator Club (auto-provisioning both on first use), authorises via the merchant's
Frappe session + outlet ownership, and reuses api/clubs.py's formatting/counter
helpers so a merchant post is a first-class Creator Club Post — it shows up in the
same app feed customers see, authored under the merchant's (outlet) name.

Only the merchant (= club admin) can post; app users only comment. Posts support
text, image, and video (video is dashboard-only to author; the app renders it via
the synthetic `chills` payload in clubs._format_post).
"""

import uuid

import frappe
from frappe import _

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone
from flamezo_backend.flamezo.utils import redis_counters as rc
from flamezo_backend.flamezo.api import clubs as _clubs


# outlet_type (Outlet.outlet_type) → Creator Club.category (its Select options)
_OUTLET_TYPE_TO_CATEGORY = {
    "dining": "dining",
    "cafe": "cafe",
    "wellness": "wellness",
    "fitness": "fitness",
    "sports_court": "sports",
    "sports_venue": "sports",
    "fashion": "fashion",
}


def _resolve_merchant_club(outlet_id, create=True):
    """Resolve (and on first use provision) the Flamezo Creator + Creator Club
    that represent this merchant outlet. Auth: the caller's Frappe session must
    own the outlet. Returns a context dict, or None when create=False and no
    club exists yet."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please sign in to continue."), frappe.AuthenticationError)

    outlet = validate_restaurant_for_api(outlet_id, user=user)
    o = frappe.db.get_value(
        "Outlet", outlet,
        ["outlet_name", "owner_phone", "logo", "outlet_type"],
        as_dict=True,
    )
    phone = normalize_phone(o.owner_phone) if o and o.owner_phone else None
    if not phone:
        # Reads (create=False) must never crash — an outlet without an owner
        # phone simply has no club yet, so return None and let the caller show
        # an empty state. Only the write path (create=True) needs the phone.
        if not create:
            return None
        frappe.throw(_("Add an owner phone number to this outlet to use Club Talks."))

    outlet_name = o.outlet_name or outlet
    logo = o.logo or ""

    creator = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
    if not creator:
        if not create:
            return None
        creator = frappe.get_doc({
            "doctype": "Flamezo Creator",
            "customer_phone": phone,
            "display_name": outlet_name,
            "status": "approved",
            "profile_image": logo,
        }).insert(ignore_permissions=True).name

    club = frappe.db.get_value("Creator Club", {"creator": creator}, "name")
    if not club:
        if not create:
            return None
        club = frappe.get_doc({
            "doctype": "Creator Club",
            "creator": creator,
            "club_name": outlet_name,
            "category": _OUTLET_TYPE_TO_CATEGORY.get(o.outlet_type or "", "dining"),
            "cover_image": logo,
            "is_active": 1,
        }).insert(ignore_permissions=True).name
        frappe.db.commit()

    return {
        "club": club, "creator": creator, "phone": phone,
        "outlet": outlet, "outlet_name": outlet_name, "logo": logo,
    }


# ── feed (view others' posts, hot-ranked) ─────────────────────────────────────

# "Hot" score: engagement decayed by age (Reddit/HN style). New posts start high
# and fade with age; engagement lifts them back up. Nothing random, nothing stuck.
_HOT_SCORE = (
    "((cp.likes_count + 2*cp.comments_count + 0.1*cp.views_count + 1) "
    "/ POW(TIMESTAMPDIFF(HOUR, cp.creation, NOW()) + 2, 1.5))"
)


@frappe.whitelist()
def merchant_get_feed(outlet_id, page=1, limit=20, exclude_own=0):
    """Club Talks "Discover" feed — posts across all active clubs, hot-ranked.
    Pass exclude_own=1 to hide the merchant's own club (the dashboard's
    Discover tab, which shows only OTHER creators' posts)."""
    # Read: the Discover feed shows every creator's posts, so a merchant with no
    # owner phone / no club of their own can still browse — don't provision/throw.
    ctx = _resolve_merchant_club(outlet_id, create=False)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    extra = ""
    params = []
    if ctx and int(exclude_own or 0):
        extra = "AND cp.club != %s"
        params.append(ctx["club"])

    rows = frappe.db.sql(
        f"""
        SELECT cp.name, cp.club, cp.post_type, cp.reel, cp.image_url, cp.video_url,
               cp.content, cp.niche_tags, cp.custom_tags, cp.location_name,
               cp.location_lat, cp.location_lng, cp.location_radius,
               cp.likes_count, cp.comments_count, cp.views_count, cp.creation,
               cc.club_name, cc.cover_image AS club_cover_image, cc.creator,
               fc.display_name AS creator_display_name, fc.profile_image AS creator_profile_image,
               {_HOT_SCORE} AS hot_score
        FROM `tabCreator Club Post` cp
        JOIN `tabCreator Club` cc ON cc.name = cp.club AND cc.is_active = 1
        LEFT JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
        WHERE 1=1 {extra}
        ORDER BY hot_score DESC, cp.creation DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit + 1, offset],
        as_dict=True,
    )
    has_more = len(rows) > limit
    posts = rows[:limit]
    post_ids = [p.name for p in posts]

    chills_map = _clubs_chills_map(posts)
    liked_set = _clubs._get_post_like_set(ctx["phone"], post_ids) if ctx else set()
    views_map = rc.get_counts("club_post_views", post_ids, {p.name: p.views_count or 0 for p in posts})
    tagged_map = _clubs._get_tagged_outlets_map(post_ids)
    my_club = ctx["club"] if ctx else None

    out = []
    for p in posts:
        item = _clubs._format_post(p, chills_map, liked_set, views_map, tagged_map)
        item["club_name"] = p.club_name or ""
        item["creator_name"] = p.creator_display_name or p.club_name or ""
        item["creator_image"] = p.creator_profile_image or p.club_cover_image or ""
        item["is_mine"] = p.club == my_club
        out.append(item)

    return {"success": True, "data": {
        "posts": out, "page": page, "has_more": has_more,
        "my_club_id": my_club,
    }}


@frappe.whitelist()
def merchant_get_my_posts(outlet_id, page=1, limit=20):
    """The merchant's OWN club posts (newest first) — the dashboard's My Club tab."""
    # Reads never provision/throw: no owner phone or no club yet → just no posts.
    ctx = _resolve_merchant_club(outlet_id, create=False)
    if not ctx:
        # Tell the UI whether the block is a missing owner phone (must be added
        # before posting) vs simply not having posted yet.
        outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
        needs_phone = not frappe.db.get_value("Outlet", outlet, "owner_phone")
        return {"success": True, "data": {
            "posts": [], "page": 1, "has_more": False, "my_club_id": None,
            "needs_phone": bool(needs_phone),
        }}
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    rows = frappe.db.sql(
        """
        SELECT name, club, post_type, reel, image_url, video_url, content,
               niche_tags, custom_tags, location_name, location_lat, location_lng, location_radius,
               likes_count, comments_count, views_count, creation
        FROM `tabCreator Club Post`
        WHERE club = %s
        ORDER BY creation DESC
        LIMIT %s OFFSET %s
        """,
        [ctx["club"], limit + 1, offset],
        as_dict=True,
    )
    has_more = len(rows) > limit
    posts = rows[:limit]
    post_ids = [p.name for p in posts]

    chills_map = _clubs_chills_map(posts)
    liked_set = _clubs._get_post_like_set(ctx["phone"], post_ids)
    views_map = rc.get_counts("club_post_views", post_ids, {p.name: p.views_count or 0 for p in posts})
    tagged_map = _clubs._get_tagged_outlets_map(post_ids)

    out = []
    for p in posts:
        item = _clubs._format_post(p, chills_map, liked_set, views_map, tagged_map)
        item["club_name"] = ctx["outlet_name"]
        item["creator_name"] = ctx["outlet_name"]
        item["creator_image"] = ctx["logo"]
        item["is_mine"] = True
        out.append(item)

    return {"success": True, "data": {
        "posts": out, "page": page, "has_more": has_more, "my_club_id": ctx["club"],
        "needs_phone": False,
    }}


@frappe.whitelist()
def merchant_search_outlets(outlet_id, q=None, limit=10):
    """Search active outlets to tag as collaborators on a Club Talks post
    (excludes the merchant's own outlet). Dedicated to Club Talks — independent
    of the map-discovery endpoint."""
    ctx = _resolve_merchant_club(outlet_id, create=False) or {}
    self_outlet = ctx.get("outlet")
    limit = min(int(limit or 10), 20)
    q = (q or "").strip()

    conditions = ["is_active = 1"]
    params = []
    if self_outlet:
        conditions.append("name != %s")
        params.append(self_outlet)
    if q:
        conditions.append("(outlet_name LIKE %s OR outlet_id LIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT name, outlet_id, outlet_name, logo
        FROM `tabOutlet`
        WHERE {where}
        ORDER BY outlet_name ASC
        LIMIT %s
        """,
        params + [limit],
        as_dict=True,
    )
    return {"success": True, "data": {"outlets": rows}}


def _clubs_chills_map(posts):
    chills_ids = [p.reel for p in posts if p.post_type == "chills" and p.reel]
    if not chills_ids:
        return {}
    placeholders = ",".join(["%s"] * len(chills_ids))
    rows = frappe.db.sql(
        f"""SELECT name, video_url, thumbnail_url, description, likes_count, views_count
            FROM `tabChills` WHERE name IN ({placeholders})""",
        chills_ids, as_dict=True,
    )
    return {c.name: c for c in rows}


# ── compose / delete (merchant is the admin) ──────────────────────────────────

@frappe.whitelist()
def merchant_request_upload(outlet_id, filename, content_type):
    """Presigned R2 PUT for a post's image/video. Same key layout as the app."""
    ctx = _resolve_merchant_club(outlet_id)
    from flamezo_backend.flamezo.utils.r2_storage import generate_presigned_put

    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else "bin"
    object_key = f"club-posts/{ctx['club']}/{uuid.uuid4()}.{ext}"
    upload_url = generate_presigned_put(object_key, content_type or "application/octet-stream", expires=3600)
    return {"success": True, "data": {"upload_url": upload_url, "object_key": object_key, "expires_in": 3600}}


@frappe.whitelist()
def merchant_create_post(outlet_id, post_type, content=None, image_key=None,
                         video_key=None, tagged_outlet_ids=None,
                         niche_tags=None, custom_tags=None,
                         location_name=None, location_lat=None,
                         location_lng=None, location_radius=None):
    ctx = _resolve_merchant_club(outlet_id)
    if post_type not in ("text", "image", "video"):
        frappe.throw(_("Invalid post_type"))

    from flamezo_backend.flamezo.utils.r2_storage import object_exists, public_url

    image_url = None
    video_url = None
    if post_type == "text":
        if not (content and content.strip()):
            frappe.throw(_("Write something to post."))
    elif post_type == "image":
        if not image_key:
            frappe.throw(_("image_key is required for an image post"))
        if not object_exists(image_key):
            frappe.throw(_("Image not found on storage. Please upload first."))
        image_url = public_url(image_key)
        image_url = _compress_image_best_effort(image_key, image_url)
    elif post_type == "video":
        if not video_key:
            frappe.throw(_("video_key is required for a video post"))
        if not object_exists(video_key):
            frappe.throw(_("Video not found on storage. Please upload first."))
        video_url = public_url(video_key)

    # dedupe + cap tagged outlets, drop inactive (same rule as clubs.create_club_post)
    tag_ids = [t.strip() for t in (tagged_outlet_ids or "").split(",") if t.strip()]
    tag_ids = list(dict.fromkeys(tag_ids))[:5]
    if tag_ids:
        valid = frappe.db.sql_list(
            f"""SELECT name FROM `tabOutlet` WHERE is_active=1 AND name IN ({",".join(["%s"] * len(tag_ids))})""",
            tag_ids,
        )
        tag_ids = [t for t in tag_ids if t in valid]

    # Niche/custom tags + location, validated the same way as Chills (reuse its
    # taxonomy-aware validator so the tag sets stay consistent across features).
    import json as _json
    from flamezo_backend.flamezo.api.chills import _validate_tags
    niche_list, custom_list = _validate_tags(niche_tags, custom_tags)
    loc_name = (location_name or "").strip()[:200]
    try:
        loc_lat = float(location_lat) if location_lat not in (None, "") else 0.0
        loc_lng = float(location_lng) if location_lng not in (None, "") else 0.0
        loc_radius = int(location_radius) if location_radius not in (None, "") else 0
    except (TypeError, ValueError):
        loc_lat, loc_lng, loc_radius = 0.0, 0.0, 0

    doc = frappe.get_doc({
        "doctype": "Creator Club Post",
        "club": ctx["club"],
        "creator": ctx["creator"],
        "post_type": post_type,
        "content": (content or "").strip(),
        "image_url": image_url,
        "video_url": video_url,
        "niche_tags": _json.dumps(niche_list) if niche_list else "",
        "custom_tags": _json.dumps(custom_list) if custom_list else "",
        "location_name": loc_name,
        "location_lat": loc_lat,
        "location_lng": loc_lng,
        "location_radius": loc_radius,
    })
    doc.insert(ignore_permissions=True)
    for tag_outlet_id in tag_ids:
        frappe.get_doc({"doctype": "Creator Club Post Tag", "post": doc.name, "outlet": tag_outlet_id}).insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.enqueue(
        "flamezo_backend.flamezo.api.clubs._notify_club_members_new_post",
        queue="short", post_id=doc.name, club_id=ctx["club"],
    )

    tagged_map = _clubs._get_tagged_outlets_map([doc.name]) if tag_ids else {}
    item = _clubs._format_post(doc, {}, set(), None, tagged_map)
    item["club_name"] = ctx["outlet_name"]
    item["creator_name"] = ctx["outlet_name"]
    item["creator_image"] = ctx["logo"]
    item["is_mine"] = True
    return {"success": True, "data": item}


def _compress_image_best_effort(image_key, fallback_url):
    """Resize→WebP the raw upload, repoint at the smaller copy, drop the original.
    Any failure keeps the raw URL. Mirrors clubs.create_club_post's image path."""
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
            if _comp_key != image_key:
                try:
                    delete_object(image_key)
                except Exception:
                    pass
            return get_cdn_url(_comp_key)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "merchant club post image compress")
    return fallback_url


@frappe.whitelist()
def merchant_delete_post(outlet_id, post_id):
    ctx = _resolve_merchant_club(outlet_id, create=False)
    if not ctx:
        frappe.throw(_("No club to manage yet."))
    club_id = frappe.db.get_value("Creator Club Post", post_id, "club")
    if not club_id:
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)
    if club_id != ctx["club"]:
        frappe.throw(_("You can only delete your own posts."), frappe.PermissionError)

    for like_id in frappe.db.sql_list("SELECT name FROM `tabCreator Club Post Like` WHERE post=%s", post_id):
        frappe.delete_doc("Creator Club Post Like", like_id, ignore_permissions=True)
    for tag_id in frappe.db.sql_list("SELECT name FROM `tabCreator Club Post Tag` WHERE post=%s", post_id):
        frappe.delete_doc("Creator Club Post Tag", tag_id, ignore_permissions=True)
    for cmt_id in frappe.db.sql_list("SELECT name FROM `tabCreator Club Post Comment` WHERE post=%s", post_id):
        frappe.delete_doc("Creator Club Post Comment", cmt_id, ignore_permissions=True)
    frappe.delete_doc("Creator Club Post", post_id, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"id": post_id}}


# ── engagement (merchant can like + read/moderate comments) ───────────────────

@frappe.whitelist()
def merchant_like_post(outlet_id, post_id):
    """Toggle like as the merchant's identity (no customer session needed)."""
    ctx = _resolve_merchant_club(outlet_id)
    if not frappe.db.exists("Creator Club Post", post_id):
        frappe.throw(_("Post not found"), frappe.DoesNotExistError)

    existing = frappe.db.get_value("Creator Club Post Like", {"post": post_id, "customer_phone": ctx["phone"]}, "name")
    if existing:
        frappe.delete_doc("Creator Club Post Like", existing, ignore_permissions=True)
        frappe.db.sql("UPDATE `tabCreator Club Post` SET likes_count = GREATEST(likes_count - 1, 0) WHERE name=%s", post_id)
        liked = False
    else:
        frappe.get_doc({"doctype": "Creator Club Post Like", "post": post_id, "customer_phone": ctx["phone"]}).insert(ignore_permissions=True)
        frappe.db.sql("UPDATE `tabCreator Club Post` SET likes_count = likes_count + 1 WHERE name=%s", post_id)
        liked = True
    frappe.db.commit()
    likes = frappe.db.get_value("Creator Club Post", post_id, "likes_count") or 0
    _clubs._publish_post_update(post_id, "like", {"likes_count": likes})
    return {"success": True, "data": {"liked": liked, "id": post_id, "likes_count": likes}}


@frappe.whitelist()
def merchant_get_comments(outlet_id, post_id, cursor=None, limit=20):
    """Read comments on a post (merchant is authenticated by outlet ownership).
    Reuses the app's comment formatter/pagination."""
    _resolve_merchant_club(outlet_id, create=False)
    return _clubs.get_club_post_comments(post_id=post_id, phone=None, cursor=cursor, limit=limit)


@frappe.whitelist()
def merchant_delete_comment(outlet_id, comment_id):
    """Delete a comment on one of the merchant's own posts (moderation)."""
    ctx = _resolve_merchant_club(outlet_id, create=False)
    if not ctx:
        frappe.throw(_("No club to manage yet."))
    post_id = frappe.db.get_value("Creator Club Post Comment", comment_id, "post")
    if not post_id:
        frappe.throw(_("Comment not found"), frappe.DoesNotExistError)
    club_id = frappe.db.get_value("Creator Club Post", post_id, "club")
    if club_id != ctx["club"]:
        frappe.throw(_("You can only moderate comments on your own posts."), frappe.PermissionError)

    frappe.delete_doc("Creator Club Post Comment", comment_id, ignore_permissions=True)
    frappe.db.sql("UPDATE `tabCreator Club Post` SET comments_count = GREATEST(comments_count - 1, 0) WHERE name=%s", post_id)
    frappe.db.commit()
    _clubs._publish_post_update(post_id, "comment_deleted", {"comment_id": comment_id})
    return {"success": True, "data": {"id": comment_id}}


@frappe.whitelist()
def merchant_get_club_analytics(outlet_id):
    """Aggregate Club Talks performance stats for a merchant outlet."""
    ctx = _resolve_merchant_club(outlet_id, create=False)
    if not ctx:
        return {
            "success": True,
            "data": {
                "total_posts": 0, "total_views": 0, "total_likes": 0,
                "total_comments": 0, "avg_views_per_post": 0, "engagement_rate": 0,
                "top_post": None
            }
        }
    
    club = ctx["club"]

    agg = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total_posts,
            COALESCE(SUM(views_count), 0) AS total_views,
            COALESCE(SUM(likes_count), 0) AS total_likes,
            COALESCE(SUM(comments_count), 0) AS total_comments
        FROM `tabCreator Club Post`
        WHERE club = %s
        """,
        club,
        as_dict=True,
    )
    a = agg[0] if agg else {}

    total_posts = int(a.get("total_posts") or 0)
    total_views = int(a.get("total_views") or 0)
    total_likes = int(a.get("total_likes") or 0)
    total_comments = int(a.get("total_comments") or 0)
    
    avg_views = round(total_views / total_posts, 1) if total_posts else 0
    engagement = round((total_likes + total_comments) / total_views * 100, 1) if total_views else 0

    top_rows = frappe.db.sql(
        """
        SELECT name, post_type, image_url, video_url, content,
               views_count, likes_count, comments_count, creation
        FROM `tabCreator Club Post`
        WHERE club = %s
        ORDER BY views_count DESC
        LIMIT 1
        """,
        club,
        as_dict=True,
    )
    top_post = None
    if top_rows:
        t = top_rows[0]
        # Same format as chills top_video
        thumbnail = t.image_url or (t.video_url if t.post_type == "video" else "")
        top_post = {
            "id": t.name,
            "thumbnail": thumbnail,
            "description": t.content or "",
            "views": int(t.views_count or 0),
            "likes": int(t.likes_count or 0),
            "comments": int(t.comments_count or 0),
            "published_at": str(t.creation) if t.creation else "",
        }

    return {
        "success": True,
        "data": {
            "total_posts": total_posts,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "avg_views_per_post": avg_views,
            "engagement_rate": engagement,
            "top_post": top_post,
        },
    }
