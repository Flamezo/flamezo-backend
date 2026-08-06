import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_days

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _require_session(phone):
    """Every mutating/private crowd endpoint must be backed by a real, verified
    session for that exact phone — not just a client-supplied string. Without
    this, any caller who knows/guesses a phone number could act as that user
    (approve/reject members, send chat messages, cancel requests, etc.)."""
    if not has_active_customer_session(phone):
        frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
    return phone


def _optional_verified_phone(phone):
    """For public/guest-readable listings that optionally take a phone (only
    used to annotate 'have I requested this' / exclude my own crowds) — if a
    phone is supplied but doesn't belong to an active session, treat the
    caller as anonymous instead of hard-failing, so logged-out browsing still
    works. Never trust an unverified phone for personalized data."""
    if phone and not has_active_customer_session(phone):
        return None
    return phone


def _format_request(r, phone=None, requested_set=None, member_status_map=None):
    if requested_set is None:
        requested_set = set()
    if member_status_map is None:
        member_status_map = {}
    interests = [i.strip() for i in (r.interests or "").split(",") if i.strip()]
    return {
        "id": r.name,
        "creator_phone": r.creator_phone,
        "creator_name": r.creator_name or "",
        "creator_image": r.creator_image or "",
        "title": r.title or "",
        "description": r.description or "",
        "category": r.category or "",
        "tier": r.tier or "",
        "outlet_id": r.outlet or "",
        "outlet_name": r.outlet_restaurant_name or "",
        "venue_name": r.venue_name or "",
        "date": str(r.date) if r.date else "",
        "time": str(r.time)[:5] if r.time else "",
        "max_members": r.max_members or 4,
        "current_members": r.current_members or 1,
        "gender_preference": r.gender_preference or "any",
        "age_range_min": r.age_range_min or None,
        "age_range_max": r.age_range_max or None,
        "interests": interests,
        "status": r.status,
        "expires_at": str(r.expires_at) if r.expires_at else "",
        "has_requested": r.name in requested_set,
        "my_member_status": member_status_map.get(r.name),
    }


def _get_requested_set(phone, request_ids):
    if not phone or not request_ids:
        return set(), {}
    placeholders = ",".join(["%s"] * len(request_ids))
    rows = frappe.db.sql(
        f"SELECT request, status FROM `tabCrowd Request Member` WHERE customer_phone=%s AND request IN ({placeholders})",
        [phone] + list(request_ids),
        as_dict=True,
    )
    requested_set = {r.request for r in rows}
    status_map = {r.request: r.status for r in rows}
    return requested_set, status_map


# ── public listing ────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_crowd_requests(phone=None, category=None, page=1, limit=20, timing=None, gender_preference=None):
    phone = _optional_verified_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    conditions = ["cr.status='open'", "(cr.expires_at IS NULL OR cr.expires_at > %s)"]
    params = [now_datetime()]

    if category:
        conditions.append("cr.category=%s")
        params.append(category)

    if phone:
        conditions.append("cr.creator_phone != %s")
        params.append(phone)

    # Timing filter
    if timing == "happening_now":
        conditions.append("cr.date = CURDATE()")
        conditions.append(
            "(cr.time IS NULL OR ABS(TIMESTAMPDIFF(MINUTE, NOW(), CONCAT(cr.date, ' ', cr.time))) <= 120)"
        )
    elif timing == "today":
        conditions.append("cr.date = CURDATE()")
    elif timing == "this_week":
        conditions.append("cr.date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)")

    # Gender preference filter (show Team Ups targeting that preference)
    if gender_preference and gender_preference != "any":
        conditions.append("cr.gender_preference = %s")
        params.append(gender_preference)

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.tier, cr.outlet, cr.venue_name,
               cr.date, cr.time, cr.max_members, cr.current_members,
               cr.gender_preference, cr.age_range_min, cr.age_range_max,
               cr.interests, cr.status, cr.expires_at,
               r.restaurant_name AS outlet_restaurant_name
        FROM `tabCrowd Request` cr
        LEFT JOIN `tabRestaurant` r ON r.name = cr.outlet
        WHERE {where}
        ORDER BY
          CASE WHEN cr.expires_at IS NOT NULL AND TIMESTAMPDIFF(MINUTE, NOW(), cr.expires_at) <= 120
               THEN 0 ELSE 1 END ASC,
          cr.date ASC,
          cr.creation ASC
        LIMIT %s OFFSET %s
        """,
        params + [limit + 1, offset],
        as_dict=True,
    )

    has_more = len(rows) > limit
    requests = rows[:limit]

    req_ids = [r.name for r in requests]
    requested_set, status_map = _get_requested_set(phone, req_ids)

    return {"success": True, "data": {
        "requests": [_format_request(r, phone, requested_set, status_map) for r in requests],
        "page": page,
        "has_more": has_more,
    }}


@frappe.whitelist(allow_guest=True)
def get_crowd_request_detail(request_id, phone=None):
    """Single Team Up with full member list — used by detail screen and chat header."""
    phone = _optional_verified_phone(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    rows = frappe.db.sql(
        """
        SELECT cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.tier, cr.outlet, cr.venue_name,
               cr.date, cr.time, cr.max_members, cr.current_members,
               cr.gender_preference, cr.age_range_min, cr.age_range_max,
               cr.interests, cr.status, cr.expires_at,
               r.restaurant_name AS outlet_restaurant_name
        FROM `tabCrowd Request` cr
        LEFT JOIN `tabRestaurant` r ON r.name = cr.outlet
        WHERE cr.name=%s
        LIMIT 1
        """,
        [request_id],
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Team Up not found"), frappe.DoesNotExistError)

    req = rows[0]
    requested_set, status_map = _get_requested_set(phone, [request_id]) if phone else (set(), {})
    formatted = _format_request(req, phone, requested_set, status_map)

    members = frappe.db.sql(
        """
        SELECT name AS id, customer_phone, customer_name, customer_image,
               intro_message, status, attended, responded_at
        FROM `tabCrowd Request Member`
        WHERE request=%s
        ORDER BY creation ASC
        """,
        [request_id],
        as_dict=True,
    )
    formatted["members"] = [
        {
            "id": m.id,
            "customer_phone": m.customer_phone,
            "customer_name": m.customer_name or "",
            "customer_image": m.customer_image or "",
            "intro_message": m.intro_message or "",
            "status": m.status,
            "attended": bool(m.attended),
            "responded_at": str(m.responded_at) if m.responded_at else "",
        }
        for m in members
    ]
    return {"success": True, "data": formatted}


@frappe.whitelist(allow_guest=True)
def create_crowd_request(phone, title, date, category=None, description=None,
                         outlet_id=None, venue_name=None, time=None,
                         max_members=4, gender_preference="any",
                         age_range_min=None, age_range_max=None, interests=None,
                         creator_name=None, creator_image=None, expires_at=None,
                         tier=None):
    phone = _require_phone(phone)
    _require_session(phone)
    if not title:
        frappe.throw(_("title is required"))
    if not date:
        frappe.throw(_("date is required"))

    if outlet_id and not frappe.db.exists("Restaurant", outlet_id):
        frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)

    # Use caller-supplied expires_at (spontaneous Team Up) or default to 48h after event date
    if not expires_at:
        event_dt = get_datetime(str(date) + " 00:00:00")
        expires_at = add_days(event_dt, 2)

    doc = frappe.get_doc({
        "doctype": "Crowd Request",
        "creator_phone": phone,
        "creator_name": creator_name or "",
        "creator_image": creator_image or "",
        "title": title,
        "description": description or "",
        "category": category or "",
        "outlet": outlet_id or None,
        "venue_name": venue_name or "",
        "date": date,
        "time": time or None,
        "max_members": int(max_members),
        "current_members": 1,
        "gender_preference": gender_preference or "any",
        "age_range_min": int(age_range_min) if age_range_min else None,
        "age_range_max": int(age_range_max) if age_range_max else None,
        "interests": interests or "",
        "tier": tier or "",
        "status": "open",
        "expires_at": expires_at,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"request_id": doc.name}}


# ── join flow ─────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def request_to_join(request_id, phone, customer_name=None, intro_message=None, customer_image=None):
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "expires_at", "creator_phone", "current_members", "max_members"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.status != "open":
        frappe.throw(_("This crowd request is no longer open"))
    if crowd.expires_at and get_datetime(str(crowd.expires_at)) < get_datetime(str(now_datetime())):
        frappe.throw(_("This crowd request has expired"))
    if crowd.creator_phone == phone:
        frappe.throw(_("You cannot join your own crowd request"))
    if frappe.db.exists("Crowd Request Member", {"request": request_id, "customer_phone": phone}):
        frappe.throw(_("You have already requested to join this crowd"))

    _check_join_eligibility(phone, customer_name)

    doc = frappe.get_doc({
        "doctype": "Crowd Request Member",
        "request": request_id,
        "customer_phone": phone,
        "customer_name": customer_name or "",
        "customer_image": customer_image or "",
        "intro_message": intro_message or "",
        "status": "pending",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"member_id": doc.name, "status": "pending"}}


@frappe.whitelist(allow_guest=True)
def manage_join_request(request_id, member_id, action, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if action not in ("approve", "reject"):
        frappe.throw(_("action must be 'approve' or 'reject'"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "creator_phone", "current_members", "max_members"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.creator_phone != phone:
        frappe.throw(_("Only the creator can manage join requests"), frappe.PermissionError)
    if crowd.status not in ("open", "closed"):
        frappe.throw(_("Cannot manage a completed or cancelled crowd request"))

    member = frappe.db.get_value(
        "Crowd Request Member",
        member_id,
        ["name", "status", "request", "customer_phone"],
        as_dict=True,
    )
    if not member or member.request != request_id:
        frappe.throw(_("Member record not found"), frappe.DoesNotExistError)
    if member.status != "pending":
        frappe.throw(_("This join request has already been processed"))

    if action == "approve":
        # Atomically claim a capacity slot — this single UPDATE...WHERE *is*
        # the lock. Two concurrent approvals (or an approval racing a crowd
        # that just hit max_members) can never both succeed: whichever commits
        # second always affects 0 rows here, so current_members can never
        # overshoot max_members no matter how many pending members exist or
        # how many approve calls land at once. Previously this was a plain
        # read-current_members-then-write, which both undercounted under
        # concurrent approvals (lost update) and let approvals continue after
        # the crowd was already marked 'closed' for being full.
        frappe.db.sql(
            """
            UPDATE `tabCrowd Request`
            SET current_members = current_members + 1,
                status = IF(current_members + 1 >= max_members, 'closed', status)
            WHERE name = %s AND current_members < max_members
            """,
            [request_id],
        )
        if not frappe.db.sql("SELECT ROW_COUNT()")[0][0]:
            frappe.throw(_("This crowd is already full"))

    # Atomically transition the member out of 'pending' — the WHERE guard
    # protects against a double-tap/duplicate call processing the same
    # member twice (the earlier read-based check above has a race window).
    new_status = "approved" if action == "approve" else "rejected"
    frappe.db.sql(
        """
        UPDATE `tabCrowd Request Member`
        SET status = %s, responded_at = %s
        WHERE name = %s AND status = 'pending'
        """,
        [new_status, now_datetime(), member_id],
    )
    if not frappe.db.sql("SELECT ROW_COUNT()")[0][0]:
        # Lost the race on the member row after already claiming a capacity
        # slot above — give it back rather than leak a phantom seat.
        if action == "approve":
            frappe.db.sql(
                """
                UPDATE `tabCrowd Request`
                SET current_members = GREATEST(current_members - 1, 1),
                    status = IF(status = 'closed', 'open', status)
                WHERE name = %s
                """,
                [request_id],
            )
        frappe.throw(_("This join request has already been processed"))

    if action == "approve" and member.customer_phone:
        # Notify the approved member via push
        frappe.enqueue(
            "flamezo_backend.flamezo.api.crowd._send_approval_push",
            queue="short",
            member_phone=member.customer_phone,
            request_id=request_id,
            now=False,
        )

    frappe.db.commit()
    return {"success": True, "data": {"member_id": member_id, "status": new_status}}


# ── my requests / joins ───────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_crowd_requests(phone, page=1, limit=20):
    phone = _require_phone(phone)
    _require_session(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    rows = frappe.db.sql(
        """
        SELECT cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.tier, cr.outlet, cr.venue_name,
               cr.date, cr.time, cr.max_members, cr.current_members,
               cr.gender_preference, cr.age_range_min, cr.age_range_max,
               cr.interests, cr.status, cr.expires_at,
               r.restaurant_name AS outlet_restaurant_name
        FROM `tabCrowd Request` cr
        LEFT JOIN `tabRestaurant` r ON r.name = cr.outlet
        WHERE cr.creator_phone=%s
        ORDER BY cr.creation DESC
        LIMIT %s OFFSET %s
        """,
        [phone, limit + 1, offset],
        as_dict=True,
    )

    has_more = len(rows) > limit
    requests = rows[:limit]

    # Batch-fetch every request's members in one query (keyed by request id)
    # instead of one query per request — avoids an N+1 as a creator's request
    # count grows.
    members_by_request = {}
    req_ids = [req.name for req in requests]
    if req_ids:
        placeholders = ",".join(["%s"] * len(req_ids))
        member_rows = frappe.db.sql(
            f"""
            SELECT request, name AS id, customer_phone, customer_name, customer_image,
                   intro_message, status, responded_at
            FROM `tabCrowd Request Member`
            WHERE request IN ({placeholders})
            ORDER BY creation DESC
            """,
            req_ids,
            as_dict=True,
        )
        for m in member_rows:
            members_by_request.setdefault(m.request, []).append(m)

    result = []
    for req in requests:
        formatted = _format_request(req)
        formatted["members"] = [
            {
                "id": m.id,
                "customer_phone": m.customer_phone,
                "customer_name": m.customer_name or "",
                "customer_image": m.customer_image or "",
                "intro_message": m.intro_message or "",
                "status": m.status,
                "responded_at": str(m.responded_at) if m.responded_at else "",
            }
            for m in members_by_request.get(req.name, [])
        ]
        result.append(formatted)

    return {"success": True, "data": {"requests": result, "page": page, "has_more": has_more}}


@frappe.whitelist(allow_guest=True)
def get_my_crowd_joins(phone, page=1, limit=20):
    phone = _require_phone(phone)
    _require_session(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    rows = frappe.db.sql(
        """
        SELECT crm.name AS member_id, crm.status AS my_status, crm.intro_message,
               cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.tier, cr.outlet, cr.venue_name,
               cr.date, cr.time, cr.max_members, cr.current_members,
               cr.gender_preference, cr.age_range_min, cr.age_range_max,
               cr.interests, cr.status, cr.expires_at,
               r.restaurant_name AS outlet_restaurant_name
        FROM `tabCrowd Request Member` crm
        JOIN `tabCrowd Request` cr ON cr.name = crm.request
        LEFT JOIN `tabRestaurant` r ON r.name = cr.outlet
        WHERE crm.customer_phone=%s
        ORDER BY crm.creation DESC
        LIMIT %s OFFSET %s
        """,
        [phone, limit + 1, offset],
        as_dict=True,
    )

    has_more = len(rows) > limit
    items = rows[:limit]

    result = []
    for row in items:
        formatted = _format_request(row, phone, {row.name}, {row.name: row.my_status})
        formatted["my_member_id"] = row.member_id
        formatted["my_status"] = row.my_status
        result.append(formatted)

    return {"success": True, "data": {"joins": result, "page": page, "has_more": has_more}}


@frappe.whitelist(allow_guest=True)
def cancel_crowd_request(request_id, phone):
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "creator_phone"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.creator_phone != phone:
        frappe.throw(_("Only the creator can cancel this request"), frappe.PermissionError)
    if crowd.status in ("completed", "cancelled"):
        frappe.throw(_("Cannot cancel a request that is already completed or cancelled"))

    frappe.db.set_value("Crowd Request", request_id, "status", "cancelled")
    frappe.db.commit()
    return {"success": True, "data": {"status": "cancelled"}}


# ── Crowd Chat ─────────────────────────────────────────────────────────────────

def _assert_chat_access(request_id, phone):
    """Verify caller is either the creator or an approved member."""
    crowd = frappe.db.get_value(
        "Crowd Request", request_id,
        ["name", "creator_phone", "status"], as_dict=True
    )
    if not crowd:
        frappe.throw(_("Team Up not found"), frappe.DoesNotExistError)
    if crowd.creator_phone == phone:
        return True
    member_status = frappe.db.get_value(
        "Crowd Request Member",
        {"request": request_id, "customer_phone": phone},
        "status"
    )
    if member_status != "approved":
        frappe.throw(_("Access denied — you must be an approved member"), frappe.PermissionError)
    return True


def _format_message(m):
    return {
        "id":               m.name,
        "request_id":       m.request_id,
        "sender_phone":     m.sender_phone,
        "sender_name":      m.sender_name or "",
        "sender_image":     m.sender_image or "",
        "sender_interests": [i.strip() for i in (m.sender_interests or "").split(",") if i.strip()],
        "message_type":     m.message_type,
        "message":          m.message or "",
        "image_url":        m.image_url or "",
        "is_system":        bool(m.is_system),
        "created_at":       str(m.created_at) if m.created_at else str(m.creation),
    }


@frappe.whitelist(allow_guest=True)
def get_messages(request_id, phone=None, before_id=None, limit=40):
    """Paginated message fetch — newest first when before_id given (infinite scroll up)."""
    if not request_id:
        frappe.throw(_("request_id is required"))

    # Guest read allowed for preview; full access requires approved membership
    if phone:
        phone = _require_phone(phone)
        _require_session(phone)
        _assert_chat_access(request_id, phone)

    limit = min(int(limit or 40), 100)
    filters = {"request_id": request_id}

    if before_id:
        before_created = frappe.db.get_value("Crowd Chat Message", before_id, "created_at")
        if before_created:
            filters["created_at"] = ("<", before_created)

    messages = frappe.get_all(
        "Crowd Chat Message",
        filters=filters,
        fields=["name", "request_id", "sender_phone", "sender_name", "sender_image",
                "sender_interests", "message_type", "message", "image_url", "is_system",
                "created_at", "creation"],
        order_by="created_at desc",
        limit_page_length=limit + 1,
    )
    has_more = len(messages) > limit
    messages = messages[:limit]
    messages.reverse()  # return chronological order

    return {
        "success": True,
        "data": {
            "messages": [_format_message(m) for m in messages],
            "has_more": has_more,
        },
    }


@frappe.whitelist(allow_guest=True)
def send_message(request_id, phone, message=None, message_type="text", image_url=None,
                 sender_name=None, sender_image=None, sender_interests=None):
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))
    if message_type == "text" and not (message or "").strip():
        frappe.throw(_("message cannot be empty"))
    if message_type == "image" and not image_url:
        frappe.throw(_("image_url is required for image messages"))

    _assert_chat_access(request_id, phone)

    # Fetch sender profile if not supplied
    if not sender_name:
        sender_name = frappe.db.get_value("Flamezo Member", phone, "customer_name") or ""
    if not sender_image:
        sender_image = frappe.db.get_value("Flamezo Member", phone, "profile_photo") or ""

    doc = frappe.get_doc({
        "doctype":           "Crowd Chat Message",
        "request_id":        request_id,
        "sender_phone":      phone,
        "sender_name":       sender_name,
        "sender_image":      sender_image,
        "sender_interests":  sender_interests or "",
        "message_type":      message_type,
        "message":           (message or "").strip(),
        "image_url":         image_url or "",
        "is_system":         0,
        "created_at":        frappe.utils.now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    payload = _format_message(doc)

    # Push realtime to all members in the room (Socket.IO — polling is the fallback)
    try:
        frappe.publish_realtime(
            event="crowd_message",
            message=payload,
            room=f"crowd:{request_id}",
            after_commit=True,
        )
    except Exception:
        pass

    # Enqueue Expo push notifications (best-effort, non-blocking)
    frappe.enqueue(
        "flamezo_backend.flamezo.api.crowd._send_crowd_chat_push",
        queue="short",
        request_id=request_id,
        sender_phone=phone,
        sender_name=sender_name or "",
        message_preview=message if message_type == "text" else "",
        now=False,
    )

    return {"success": True, "data": payload}


@frappe.whitelist(allow_guest=True)
def upload_chat_image(request_id, phone, file_content, filename, content_type="image/jpeg"):
    """Upload an image to R2 and return the public URL for use in send_message."""
    phone = _require_phone(phone)
    _require_session(phone)
    _assert_chat_access(request_id, phone)

    import base64
    try:
        raw = base64.b64decode(file_content)
    except Exception:
        frappe.throw(_("Invalid base64 file_content"))

    max_bytes = 5 * 1024 * 1024  # 5 MB
    if len(raw) > max_bytes:
        frappe.throw(_("Image too large — max 5 MB"))

    try:
        from flamezo_backend.flamezo.utils.r2 import upload_bytes
        safe_name = f"crowd/{request_id}/{frappe.generate_hash(length=12)}-{filename}"
        url = upload_bytes(raw, safe_name, content_type=content_type)
    except ImportError:
        # Fallback: save decoded bytes as Frappe file (not base64 string)
        import base64 as _b64
        file_doc = frappe.get_doc({
            "doctype":    "File",
            "file_name":  filename,
            "content":    _b64.b64encode(raw).decode("ascii"),  # Frappe File expects b64
            "decode":     True,
            "is_private": 0,
        })
        file_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        url = file_doc.file_url

    return {"success": True, "data": {"url": url}}


# ── Push notifications (Expo) ──────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def save_expo_push_token(phone, token):
    """
    Store the Expo push token for a member so we can send chat push notifications.
    Tokens are stored in Redis with a 30-day TTL — no schema migration needed.
    """
    phone = _require_phone(phone)
    _require_session(phone)
    if not token or not str(token).startswith("ExponentPushToken["):
        frappe.throw(_("Invalid Expo push token format"), frappe.ValidationError)
    frappe.cache().set_value(f"expo_push:{phone}", str(token), expires_in_sec=30 * 24 * 3600)
    return {"success": True}


def _send_crowd_chat_push(request_id, sender_phone, sender_name, message_preview):
    """
    Background-enqueued helper. Sends an Expo push notification to every
    approved member and the creator of this crowd request (except the sender).
    Uses the Expo Push API (free, no Firebase config needed).
    """
    try:
        import requests as http_req

        # Collect all phones that should be notified
        members = frappe.get_all(
            "Crowd Request Member",
            filters={"request": request_id, "status": "approved"},
            fields=["customer_phone"],
        )
        creator_phone = frappe.db.get_value("Crowd Request", request_id, "creator_phone")

        phones = {m.customer_phone for m in members}
        if creator_phone:
            phones.add(creator_phone)
        phones.discard(sender_phone)

        if not phones:
            return

        # Fetch Expo push tokens from Redis
        messages = []
        for phone in phones:
            token = frappe.cache().get_value(f"expo_push:{phone}")
            if not token:
                continue
            body = message_preview[:200] if message_preview and message_preview.strip() else "📷 Photo"
            messages.append({
                "to":    token,
                "title": sender_name or "Crowd Chat",
                "body":  body,
                "data":  {"request_id": request_id, "screen": "crowdChat"},
                "sound": "default",
                "badge": 1,
            })

        if not messages:
            return

        http_req.post(
            "https://exp.host/--/api/v2/push/send",
            json=messages,
            headers={"Accept-Encoding": "gzip, deflate"},
            timeout=8,
        )
    except Exception as e:
        frappe.log_error(f"Crowd chat push failed: {str(e)}", "Crowd Push")


# ── Eligibility gate ───────────────────────────────────────────────────────────

def _check_join_eligibility(phone, customer_name=None):
    """
    Gate before allowing a user to join a Team Up:
    1. Account age >= 7 days
    2. Name not a system-generated placeholder
    3. Reliability score >= 30% (enforced only after 5+ past joins)
    """
    import re

    # 1. Account age — look up the Customer record by phone
    try:
        member_creation = frappe.db.get_value("Customer", {"phone": phone}, "creation")
    except Exception:
        member_creation = None
    if member_creation:
        from frappe.utils import date_diff
        age_days = date_diff(now_datetime(), str(member_creation))
        if age_days < 7:
            frappe.throw(_("Your account must be at least 7 days old to join a Team Up."))

    # 2. Name validation
    if customer_name:
        name = customer_name.strip()
        if len(name) < 2 or not re.search(r'[A-Za-z]', name):
            frappe.throw(_("Please use your real name to join a Team Up."))
        if re.match(r'^(user|guest|anon|test)\d+$', name.lower()):
            frappe.throw(_("Please update your profile name before joining a Team Up."))

    # 3. Reliability gate (only if 5+ past joins)
    stats = frappe.db.sql(
        """
        SELECT COUNT(*) AS total, COALESCE(SUM(attended), 0) AS attended_count
        FROM `tabCrowd Request Member`
        WHERE customer_phone = %s AND status IN ('approved', 'left')
        """,
        [phone],
        as_dict=True,
    )
    total = stats[0].total if stats else 0
    if total >= 5:
        attended = int(stats[0].attended_count) if stats else 0
        if total > 0 and (attended / total) < 0.3:
            frappe.throw(_(
                "Your reliability score is too low. "
                "Please attend your existing Team Ups before joining new ones."
            ))


# ── Edit crowd request ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def edit_crowd_request(request_id, phone, title=None, description=None, max_members=None):
    """Creator can edit a Team Up only if no external members have joined (current_members == 1)."""
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "creator_phone", "current_members"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.creator_phone != phone:
        frappe.throw(_("Only the creator can edit this Team Up"), frappe.PermissionError)
    if crowd.status in ("completed", "cancelled"):
        frappe.throw(_("Cannot edit a completed or cancelled Team Up"))
    if (crowd.current_members or 1) > 1:
        frappe.throw(_("Cannot edit a Team Up after members have joined"))

    updates = {}
    if title is not None:
        updates["title"] = title.strip()
    if description is not None:
        updates["description"] = description.strip()
    if max_members is not None:
        max_members = int(max_members)
        if max_members < 2 or max_members > 20:
            frappe.throw(_("max_members must be between 2 and 20"))
        updates["max_members"] = max_members

    if updates:
        frappe.db.set_value("Crowd Request", request_id, updates)
        frappe.db.commit()

    return {"success": True, "data": {"request_id": request_id}}


# ── Leave crowd request ────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def leave_crowd_request(request_id, phone):
    """Approved member leaves a Team Up — decrements current_members and marks them 'left'."""
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "creator_phone", "current_members"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.creator_phone == phone:
        frappe.throw(_("The creator cannot leave — cancel the Team Up instead"))
    if crowd.status in ("completed", "cancelled"):
        frappe.throw(_("Cannot leave a completed or cancelled Team Up"))

    member = frappe.db.get_value(
        "Crowd Request Member",
        {"request": request_id, "customer_phone": phone, "status": "approved"},
        ["name"],
        as_dict=True,
    )
    if not member:
        frappe.throw(_("You are not an approved member of this Team Up"), frappe.PermissionError)

    # Atomically flip the member out of 'approved' — the WHERE guard protects
    # against a double-tap firing two concurrent leave calls for the same
    # member (would otherwise double-decrement current_members below).
    frappe.db.sql(
        "UPDATE `tabCrowd Request Member` SET status = 'left' WHERE name = %s AND status = 'approved'",
        [member.name],
    )
    if not frappe.db.sql("SELECT ROW_COUNT()")[0][0]:
        frappe.throw(_("You are not an approved member of this Team Up"), frappe.PermissionError)

    # Atomic decrement (same lost-update risk as the approve-side increment
    # this mirrors) — never goes below 1, reopens the crowd if it was closed
    # purely for having been full (see `manage_join_request`).
    frappe.db.sql(
        """
        UPDATE `tabCrowd Request`
        SET current_members = GREATEST(current_members - 1, 1),
            status = IF(status = 'closed', 'open', status)
        WHERE name = %s
        """,
        [request_id],
    )

    frappe.db.commit()
    return {"success": True, "data": {"status": "left"}}


# ── Report crowd message ───────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def report_crowd_message(message_id, phone, reason="other"):
    """Report a chat message for moderator review."""
    phone = _require_phone(phone)
    _require_session(phone)
    if not message_id:
        frappe.throw(_("message_id is required"))

    msg = frappe.db.get_value(
        "Crowd Chat Message",
        message_id,
        ["name", "request_id", "sender_phone"],
        as_dict=True,
    )
    if not msg:
        frappe.throw(_("Message not found"), frappe.DoesNotExistError)
    if msg.sender_phone == phone:
        frappe.throw(_("You cannot report your own message"))

    _assert_chat_access(msg.request_id, phone)

    VALID_REASONS = {"explicit_content", "harassment", "spam", "contact_details", "other"}
    if reason not in VALID_REASONS:
        reason = "other"

    doc = frappe.get_doc({
        "doctype":        "Crowd Report",
        "reporter_phone": phone,
        "message_id":     message_id,
        "request_id":     msg.request_id,
        "reported_phone": msg.sender_phone,
        "reason":         reason,
        "status":         "pending",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": {"report_id": doc.name}}


# ── Complete crowd request ─────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def complete_crowd_request(request_id, phone, attended_phones=None):
    """
    Creator marks the Team Up as completed and records which approved members attended.
    Sets attended=1 for the reliability score calculation.
    """
    phone = _require_phone(phone)
    _require_session(phone)
    if not request_id:
        frappe.throw(_("request_id is required"))

    crowd = frappe.db.get_value(
        "Crowd Request",
        request_id,
        ["name", "status", "creator_phone"],
        as_dict=True,
    )
    if not crowd:
        frappe.throw(_("Request not found"), frappe.DoesNotExistError)
    if crowd.creator_phone != phone:
        frappe.throw(_("Only the creator can complete this Team Up"), frappe.PermissionError)
    if crowd.status in ("completed", "cancelled"):
        frappe.throw(_("This Team Up is already completed or cancelled"))

    if isinstance(attended_phones, str):
        import json
        try:
            attended_phones = json.loads(attended_phones)
        except Exception:
            attended_phones = [p.strip() for p in attended_phones.split(",") if p.strip()]

    attended_set = set(attended_phones or [])

    frappe.db.set_value("Crowd Request", request_id, "status", "completed")

    members = frappe.get_all(
        "Crowd Request Member",
        filters={"request": request_id, "status": "approved"},
        fields=["name", "customer_phone"],
    )
    for m in members:
        frappe.db.set_value(
            "Crowd Request Member", m.name,
            "attended", 1 if m.customer_phone in attended_set else 0,
        )

    frappe.db.commit()
    return {"success": True, "data": {"status": "completed", "attended_count": len(attended_set)}}


# ── Reliability score ──────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_crowd_reliability(phone):
    """Returns the reliability score (0-100) based on past Team Up attendance."""
    phone = _require_phone(phone)
    _require_session(phone)
    stats = frappe.db.sql(
        """
        SELECT COUNT(*) AS total, COALESCE(SUM(attended), 0) AS attended_count
        FROM `tabCrowd Request Member`
        WHERE customer_phone = %s AND status IN ('approved', 'left')
        """,
        [phone],
        as_dict=True,
    )
    total = stats[0].total if stats else 0
    attended = int(stats[0].attended_count) if stats else 0
    score = round((attended / total) * 100) if total > 0 else 100
    return {"success": True, "data": {"total_joins": total, "attended": attended, "score": score}}


# ── Venue Team Ups ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_crowd_requests_for_venue(outlet_id, phone=None, limit=5):
    """Returns active open Team Ups for a venue — shown on the restaurant detail page."""
    if not outlet_id:
        frappe.throw(_("outlet_id is required"))
    limit = min(int(limit or 5), 20)
    phone = _optional_verified_phone(phone)

    rows = frappe.db.sql(
        """
        SELECT name, creator_phone, creator_name, creator_image, title, description,
               category, tier, outlet, venue_name, date, time, max_members, current_members,
               gender_preference, age_range_min, age_range_max, interests, status, expires_at
        FROM `tabCrowd Request`
        WHERE outlet = %s
          AND status = 'open'
          AND (expires_at IS NULL OR expires_at > %s)
        ORDER BY date ASC
        LIMIT %s
        """,
        [outlet_id, now_datetime(), limit],
        as_dict=True,
    )
    for r in rows:
        r.outlet_restaurant_name = ""
    req_ids = [r.name for r in rows]
    requested_set, status_map = _get_requested_set(phone, req_ids)

    return {"success": True, "data": {
        "requests": [_format_request(r, phone, requested_set, status_map) for r in rows]
    }}


# ── Approval push ──────────────────────────────────────────────────────────────

def _send_approval_push(member_phone, request_id):
    """Send push to a member when their join request is approved."""
    try:
        import requests as http_req
        token = frappe.cache().get_value(f"expo_push:{member_phone}")
        if not token:
            return
        req_title = frappe.db.get_value("Crowd Request", request_id, "title") or "Team Up"
        http_req.post(
            "https://exp.host/--/api/v2/push/send",
            json={
                "to":    token,
                "title": "You're In!",
                "body":  f"Your request to join \"{req_title}\" has been approved.",
                "data":  {"request_id": request_id, "screen": "crowdChat"},
                "sound": "default",
            },
            timeout=8,
        )
    except Exception as e:
        frappe.log_error(f"Approval push failed: {str(e)}", "Crowd Push")


# ── Scheduled tasks ────────────────────────────────────────────────────────────

def close_expired_crowd_requests():
    """Close open Team Ups whose expires_at has passed — runs every 30 minutes."""
    frappe.db.sql(
        """
        UPDATE `tabCrowd Request`
        SET status = 'closed'
        WHERE status = 'open'
          AND expires_at IS NOT NULL
          AND expires_at < %s
        """,
        [now_datetime()],
    )
    frappe.db.commit()


def expire_old_chat_messages():
    """
    Delete chat messages for completed/cancelled Team Ups where the event date
    was > 30 days ago (data hygiene). Runs daily at 04:00.
    """
    from frappe.utils import add_days
    cutoff = add_days(now_datetime(), -30)
    frappe.db.sql(
        """
        DELETE m FROM `tabCrowd Chat Message` m
        JOIN `tabCrowd Request` cr ON cr.name = m.request_id
        WHERE cr.status IN ('completed', 'cancelled')
          AND cr.date < %s
        """,
        [cutoff],
    )
    frappe.db.commit()
