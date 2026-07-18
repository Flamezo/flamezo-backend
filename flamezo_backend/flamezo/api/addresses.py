import frappe
from frappe import _
from flamezo_backend.flamezo.api.otp import _resolve_customer_from_token


@frappe.whitelist(allow_guest=True)
def save_customer_address(
    label: str,
    address_line_1: str,
    area: str,
    city: str,
    address_type: str = "home",
    pincode: str = "",
    latitude: float = None,
    longitude: float = None,
    delivery_notes: str = "",
    is_default: bool = False,
    address_id: str = None,  # present = update, absent = create
) -> dict:
    """
    Create or update a saved address for the authenticated customer.
    Returns the saved address object.
    """
    customer_id = _resolve_customer_from_token()

    if not all([label, address_line_1, area, city]):
        frappe.throw(_("label, address_line_1, area, and city are required."), frappe.MandatoryError)

    if address_type not in ("home", "work", "other"):
        frappe.throw(_("address_type must be one of: home, work, other"))

    if pincode and len(pincode.strip()) not in (0, 6):
        frappe.throw(_("Pincode must be 6 digits."))

    # ── Update existing ────────────────────────────────────────────────────────
    if address_id:
        doc = frappe.get_doc("Customer Address", address_id)
        if doc.customer != customer_id:
            frappe.throw(_("Not authorised."), frappe.PermissionError)
        doc.label = label
        doc.address_line_1 = address_line_1
        doc.area = area
        doc.city = city
        doc.address_type = address_type
        doc.pincode = pincode or ""
        doc.latitude = latitude
        doc.longitude = longitude
        doc.delivery_notes = delivery_notes or ""
        doc.is_default = 1 if is_default else 0
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "data": _serialize_address(doc)}

    # ── Create new ─────────────────────────────────────────────────────────────
    doc = frappe.get_doc({
        "doctype": "Customer Address",
        "customer": customer_id,
        "label": label,
        "address_line_1": address_line_1,
        "area": area,
        "city": city,
        "address_type": address_type,
        "pincode": pincode or "",
        "latitude": latitude,
        "longitude": longitude,
        "delivery_notes": delivery_notes or "",
        "is_default": 1 if is_default else 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "data": _serialize_address(doc)}


@frappe.whitelist(allow_guest=True)
def get_customer_addresses() -> dict:
    """
    Return all saved addresses for the authenticated customer,
    default address first.
    """
    customer_id = _resolve_customer_from_token()

    rows = frappe.get_all(
        "Customer Address",
        filters={"customer": customer_id},
        fields=[
            "name", "label", "address_type", "address_line_1",
            "area", "city", "pincode", "latitude", "longitude",
            "is_default", "delivery_notes", "creation", "modified",
        ],
        order_by="is_default desc, creation asc",
    )

    return {
        "success": True,
        "data": {
            "addresses": [_serialize_address_row(r) for r in rows],
            "count": len(rows),
        },
    }


@frappe.whitelist(allow_guest=True)
def delete_customer_address(address_id: str) -> dict:
    """
    Delete a saved address. If the deleted address was the default,
    promote the most recently created remaining address to default.
    """
    customer_id = _resolve_customer_from_token()

    if not address_id:
        frappe.throw(_("address_id is required."), frappe.MandatoryError)

    doc = frappe.get_doc("Customer Address", address_id)
    if doc.customer != customer_id:
        frappe.throw(_("Not authorised."), frappe.PermissionError)

    was_default = bool(doc.is_default)
    doc.delete(ignore_permissions=True)
    frappe.db.commit()

    if was_default:
        # Promote the next address to default
        remaining = frappe.get_all(
            "Customer Address",
            filters={"customer": customer_id},
            fields=["name"],
            order_by="creation asc",
            limit=1,
        )
        if remaining:
            frappe.db.set_value("Customer Address", remaining[0].name, "is_default", 1)
            frappe.db.commit()

    return {"success": True, "data": {"deleted": address_id}}


@frappe.whitelist(allow_guest=True)
def set_default_address(address_id: str) -> dict:
    """
    Mark one address as the default; clears default on all others for this customer.
    """
    customer_id = _resolve_customer_from_token()

    if not address_id:
        frappe.throw(_("address_id is required."), frappe.MandatoryError)

    doc = frappe.get_doc("Customer Address", address_id)
    if doc.customer != customer_id:
        frappe.throw(_("Not authorised."), frappe.PermissionError)

    # Clear all others
    frappe.db.set_value(
        "Customer Address",
        {"customer": customer_id, "name": ("!=", address_id)},
        "is_default",
        0,
    )
    frappe.db.set_value("Customer Address", address_id, "is_default", 1)
    frappe.db.commit()

    return {"success": True, "data": {"default_address_id": address_id}}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_address(doc) -> dict:
    return {
        "id": doc.name,
        "label": doc.label,
        "address_type": doc.address_type,
        "address_line_1": doc.address_line_1,
        "area": doc.area,
        "city": doc.city,
        "pincode": doc.pincode or "",
        "latitude": doc.latitude,
        "longitude": doc.longitude,
        "is_default": bool(doc.is_default),
        "delivery_notes": doc.delivery_notes or "",
    }


def _serialize_address_row(row) -> dict:
    return {
        "id": row.get("name"),
        "label": row.get("label"),
        "address_type": row.get("address_type"),
        "address_line_1": row.get("address_line_1"),
        "area": row.get("area"),
        "city": row.get("city"),
        "pincode": row.get("pincode") or "",
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "is_default": bool(row.get("is_default")),
        "delivery_notes": row.get("delivery_notes") or "",
    }


def get_addresses_for_customer(customer_id: str) -> list:
    """
    Internal helper — used by get_my_profile to embed addresses in the auth response.
    No auth check; caller must have already verified the customer_id.
    """
    rows = frappe.get_all(
        "Customer Address",
        filters={"customer": customer_id},
        fields=[
            "name", "label", "address_type", "address_line_1",
            "area", "city", "pincode", "latitude", "longitude",
            "is_default", "delivery_notes",
        ],
        order_by="is_default desc, creation asc",
    )
    return [_serialize_address_row(r) for r in rows]
