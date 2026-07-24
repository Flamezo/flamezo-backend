import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_days


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


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
def get_crowd_requests(phone=None, category=None, page=1, limit=20):
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

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.outlet, cr.venue_name,
               cr.date, cr.time, cr.max_members, cr.current_members,
               cr.gender_preference, cr.age_range_min, cr.age_range_max,
               cr.interests, cr.status, cr.expires_at,
               r.restaurant_name AS outlet_restaurant_name
        FROM `tabCrowd Request` cr
        LEFT JOIN `tabRestaurant` r ON r.name = cr.outlet
        WHERE {where}
        ORDER BY cr.date ASC, cr.creation ASC
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
def create_crowd_request(phone, title, date, category=None, description=None,
                         outlet_id=None, venue_name=None, time=None,
                         max_members=4, gender_preference="any",
                         age_range_min=None, age_range_max=None, interests=None,
                         creator_name=None, creator_image=None):
    phone = _require_phone(phone)
    if not title:
        frappe.throw(_("title is required"))
    if not date:
        frappe.throw(_("date is required"))

    if outlet_id and not frappe.db.exists("Restaurant", outlet_id):
        frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)

    # expires_at = 48h after event date
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
        ["name", "status", "request"],
        as_dict=True,
    )
    if not member or member.request != request_id:
        frappe.throw(_("Member record not found"), frappe.DoesNotExistError)
    if member.status != "pending":
        frappe.throw(_("This join request has already been processed"))

    new_status = "approved" if action == "approve" else "rejected"
    frappe.db.set_value("Crowd Request Member", member_id, {
        "status": new_status,
        "responded_at": now_datetime(),
    })

    if action == "approve":
        new_count = (crowd.current_members or 1) + 1
        update = {"current_members": new_count}
        if new_count >= (crowd.max_members or 4):
            update["status"] = "closed"
        frappe.db.set_value("Crowd Request", request_id, update)

    frappe.db.commit()
    return {"success": True, "data": {"member_id": member_id, "status": new_status}}


# ── my requests / joins ───────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_crowd_requests(phone, page=1, limit=20):
    phone = _require_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    rows = frappe.db.sql(
        """
        SELECT cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.outlet, cr.venue_name,
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

    # Attach member list to each request
    result = []
    for req in requests:
        members = frappe.db.sql(
            """
            SELECT name AS id, customer_phone, customer_name, customer_image, intro_message, status, responded_at
            FROM `tabCrowd Request Member`
            WHERE request=%s
            ORDER BY creation DESC
            """,
            req.name,
            as_dict=True,
        )
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
            for m in members
        ]
        result.append(formatted)

    return {"success": True, "data": {"requests": result, "page": page, "has_more": has_more}}


@frappe.whitelist(allow_guest=True)
def get_my_crowd_joins(phone, page=1, limit=20):
    phone = _require_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    rows = frappe.db.sql(
        """
        SELECT crm.name AS member_id, crm.status AS my_status, crm.intro_message,
               cr.name, cr.creator_phone, cr.creator_name, cr.creator_image,
               cr.title, cr.description, cr.category, cr.outlet, cr.venue_name,
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
