"""Test addon group save on product. bench --site flamezo.localhost execute flamezo_backend.flamezo.tests.test_addon_save.run"""
import frappe, json

def run():
    product_name = "farm-fresh"
    group_name = "2hn3ic8uls"  # Patty Type

    print(f"\n=== Testing addon group save on {product_name} ===")

    # Check current state
    doc = frappe.get_doc("Menu Product", product_name)
    print(f"Before: addon_groups = {len(doc.addon_groups or [])}")
    for link in (doc.addon_groups or []):
        print(f"  {link.addon_group} -> {link.addon_group_name} enabled={link.is_enabled}")

    # Clear existing links
    doc.addon_groups = []
    doc.save(ignore_permissions=True)
    doc.reload()
    print(f"After clear: {len(doc.addon_groups)}")

    # Add a link via doc.append
    doc.append("addon_groups", {
        "addon_group": group_name,
        "is_enabled": 1,
        "display_order": 0
    })
    doc.save(ignore_permissions=True)
    doc.reload()
    print(f"After append+save: {len(doc.addon_groups)}")
    for link in doc.addon_groups:
        print(f"  addon_group={link.addon_group} name_fetched={link.addon_group_name} type={link.addon_group_type} enabled={link.is_enabled}")

    # Now test via update_document API (same as frontend)
    from flamezo_backend.flamezo.api.documents import update_document
    result = update_document("Menu Product", product_name, {
        "addon_groups": [
            {"addon_group": group_name, "is_enabled": 1, "display_order": 0},
            {"addon_group": "2hnlse3kck", "is_enabled": 1, "display_order": 1},  # Add Extras
        ]
    })
    print(f"\nupdate_document result: success={result.get('success')}")
    if not result.get("success"):
        print(f"  Error: {result.get('error')}")

    doc.reload()
    print(f"After update_document: {len(doc.addon_groups)}")
    for link in doc.addon_groups:
        print(f"  addon_group={link.addon_group} name={link.addon_group_name} type={link.addon_group_type} enabled={link.is_enabled}")

    # Verify persistence
    doc2 = frappe.get_doc("Menu Product", product_name)
    print(f"\nFresh reload: {len(doc2.addon_groups)}")
    for link in doc2.addon_groups:
        print(f"  addon_group={link.addon_group} name={link.addon_group_name} type={link.addon_group_type}")

    assert len(doc2.addon_groups) == 2, f"Expected 2, got {len(doc2.addon_groups)}"
    assert doc2.addon_groups[0].addon_group == group_name
    print("\n=== PASS ===")
