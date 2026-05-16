import frappe
import json

def migrate_tokenizations():
    """
    Migration script: copy existing tokenization Orders into Tokenization Attempt docs.
    - Identifies Orders with order_number starting with 'TOK-' OR notes.type == 'tokenization'
    - Creates Tokenization Attempt docs preserving key fields.
    - Appends migration marker to Order.notes for traceability.
    """
    migrated = []
    try:
        # Find candidate orders
        # Prefer explicit tokenization marker in order_number (TOK-...). As a fallback include tiny orders with a razorpay_order_id.
        rows = frappe.db.sql("""
            SELECT name, restaurant, total, razorpay_order_id, razorpay_payment_id
            FROM `tabOrder`
            WHERE order_number LIKE 'TOK-%%' OR (razorpay_order_id IS NOT NULL AND total <= 1)
        """, as_dict=True)

        for r in rows:
            try:
                amount_paise = int(float(r.get("total") or 0) * 100)
                # original Order.notes column may not exist; keep empty notes JSON
                notes_json = {}

                attempt = frappe.get_doc({
                    "doctype": "Tokenization Attempt",
                    "restaurant": r.get("restaurant"),
                    "order_ref": r.get("name"),
                    "amount": amount_paise if amount_paise > 0 else 100,
                    "currency": "INR",
                    "razorpay_order_id": r.get("razorpay_order_id"),
                    "razorpay_payment_id": r.get("razorpay_payment_id"),
                    "notes": json.dumps(notes_json),
                    "status": "created" if r.get("razorpay_order_id") else "pending"
                })
                attempt.insert(ignore_permissions=True)
                # mark migrated in original order notes for traceability
                migrated_marker = {"migrated_to_tokenization_attempt": attempt.name}
                try:
                    existing_notes = json.loads(r.get("notes") or "{}")
                except Exception:
                    existing_notes = {"original_notes": r.get("notes")}
                existing_notes.update(migrated_marker)
                # set notes (if field exists) and mark order as tokenization for UI filtering
                try:
                    if frappe.db.has_column("tabOrder", "notes"):
                        frappe.db.set_value("Order", r.get("name"), "notes", json.dumps(existing_notes))
                except Exception:
                    # if column doesn't exist or set fails, skip
                    pass
                try:
                    if frappe.db.has_column("tabOrder", "is_tokenization"):
                        frappe.db.set_value("Order", r.get("name"), "is_tokenization", 1)
                except Exception:
                    # if field not present yet, ignore - migration will still record mapping
                    pass
                frappe.db.commit()
                migrated.append({"order": r.get("name"), "attempt": attempt.name})
            except Exception as e:
                frappe.log_error(f"Failed to migrate order {r.get('name')}: {str(e)}", "migrate_tokenizations")
                continue

        return {"success": True, "migrated": migrated, "count": len(migrated)}
    except Exception as e:
        frappe.log_error(f"Tokenization migration failed: {str(e)}", "migrate_tokenizations")
        return {"success": False, "error": str(e)}

