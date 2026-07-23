import frappe
from frappe import _
from frappe.utils import now_datetime


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


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
        "tier": c.tier or "Spark",
        "followers_count": c.followers_count or 0,
        "is_following": c.name in member_set,
        "creator_id": c.creator or "",
        "creator_name": c.creator_display_name or "",
        "creator_image": c.creator_profile_image or "",
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


# ── club listing ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_creator_clubs(phone=None, category=None, search=None, page=1, limit=20):
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    conditions = ["cc.is_active=1"]
    params = []

    if category:
        conditions.append("cc.category=%s")
        params.append(category)

    if search:
        conditions.append("(cc.club_name LIKE %s OR cc.niche LIKE %s)")
        s = f"%{search}%"
        params += [s, s]

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
               cc.category, cc.tier, cc.followers_count, cc.creator,
               fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image
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
    if not club_id:
        frappe.throw(_("club_id is required"))

    rows = frappe.db.sql(
        """
        SELECT cc.*, fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image, fc.creator_tier AS creator_tier
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
    result["creator_tier"] = club.creator_tier or "Spark"
    result["recent_posts"] = frappe.db.count("Creator Club Post", {"club": club_id})
    return {"success": True, "data": result}


# ── follow / unfollow ────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def follow_club(club_id, phone):
    phone = _require_phone(phone)
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
        return {"success": True, "data": {"following": True}}


# ── club posts ────────────────────────────────────────────────────────────────

def _format_post(p, chills_map=None):
    post = {
        "id": p.name,
        "club_id": p.club,
        "post_type": p.post_type,
        "content": p.content or "",
        "likes_count": p.likes_count or 0,
        "comments_count": p.comments_count or 0,
        "created_at": str(p.creation) if p.creation else "",
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


@frappe.whitelist(allow_guest=True)
def get_club_posts(club_id, phone=None, page=1, limit=20):
    if not club_id:
        frappe.throw(_("club_id is required"))

    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    if not frappe.db.exists("Creator Club", {"name": club_id, "is_active": 1}):
        frappe.throw(_("Club not found"), frappe.DoesNotExistError)

    rows = frappe.db.sql(
        """
        SELECT name, club, post_type, reel, image_url, content, likes_count, comments_count, creation
        FROM `tabCreator Club Post`
        WHERE club=%s
        ORDER BY creation DESC
        LIMIT %s OFFSET %s
        """,
        [club_id, limit + 1, offset],
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

    return {"success": True, "data": {
        "posts": [_format_post(p, chills_map) for p in posts],
        "page": page,
        "has_more": has_more,
    }}


@frappe.whitelist(allow_guest=True)
def get_my_clubs(phone):
    phone = _require_phone(phone)

    rows = frappe.db.sql(
        """
        SELECT cc.name, cc.club_name, cc.niche, cc.description, cc.cover_image,
               cc.category, cc.tier, cc.followers_count, cc.creator,
               fc.display_name AS creator_display_name,
               fc.profile_image AS creator_profile_image
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
