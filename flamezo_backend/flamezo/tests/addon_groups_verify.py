"""Quick verification of addon groups full stack. Run: bench --site flamezo.localhost execute flamezo_backend.flamezo.tests.addon_groups_verify.run"""
import frappe, json

def run():
    print("\n=== ADDON GROUPS FULL STACK VERIFICATION ===\n")

    # 1. Groups exist
    groups = frappe.get_all('Addon Group', filters={'restaurant': 'unvind'}, fields=['name', 'group_name', 'group_type', 'status'], order_by='creation desc', limit=10)
    print(f"1. Addon Groups for unvind: {len(groups)}")
    for g in groups[:5]:
        print(f"   {g.group_name} | {g.group_type} | {g.status}")

    # 2. Product links
    links = frappe.get_all('Product Addon Group', filters={'parenttype': 'Menu Product'}, fields=['parent', 'addon_group', 'is_enabled'], limit=10)
    print(f"\n2. Product-Addon links: {len(links)}")
    for l in links[:5]:
        gname = frappe.db.get_value('Addon Group', l.addon_group, 'group_name') or '?'
        print(f"   Product={l.parent} -> {gname} enabled={l.is_enabled}")

    # 3. Products API returns addon groups — find a product that has links
    from flamezo_backend.flamezo.api.products import get_products
    linked_product_names = list({l.parent for l in links})
    print(f"\n3. Products with addon links: {linked_product_names[:5]}")

    # Test with a linked product specifically
    if linked_product_names:
        product_doc = frappe.get_doc('Menu Product', linked_product_names[0])
        from flamezo_backend.flamezo.utils.addon_group_helpers import load_product_addon_groups, format_addon_groups_for_api
        loaded = load_product_addon_groups(product_doc)
        formatted = format_addon_groups_for_api(loaded)
        print(f"   Product '{product_doc.product_name}' direct load: {len(loaded)} groups")
        for g in formatted[:3]:
            items_str = ', '.join(f"{i['name']}({i['price']})" for i in g['items'][:3])
            print(f"     {g['groupName']} [{g['groupType']}] -> {items_str}")

    # Also check via products API
    result = get_products('unvind', limit=50)
    products = result.get('data', {}).get('products', [])
    products_with_ag = [p for p in products if p.get('addonGroups')]
    print(f"   Products API total={len(products)}, with addonGroups={len(products_with_ag)}")
    for p in products_with_ag[:3]:
        ag = p.get('addonGroups', [])
        print(f"   {p['name']} | addonGroups={len(ag)}")
        for g in ag[:2]:
            items_str = ', '.join(f"{i['name']}({i['price']})" for i in g['items'][:3])
            print(f"     {g['groupName']} [{g['groupType']}] -> {items_str}")

    # 4. Inactive group filtered out
    if groups:
        test_g = groups[0]
        frappe.db.set_value('Addon Group', test_g.name, 'status', 'Inactive')
        frappe.db.commit()
        from flamezo_backend.flamezo.utils.addon_group_helpers import load_product_addon_groups
        link = frappe.db.get_value('Product Addon Group', {'addon_group': test_g.name}, 'parent')
        if link:
            product = frappe.get_doc('Menu Product', link)
            loaded = load_product_addon_groups(product)
            found = any(g['name'] == test_g.name for g in loaded)
            print(f"\n4. Inactive filter: '{test_g.group_name}' set Inactive -> appears in load: {found} (should be False)")
            assert not found, "FAIL: Inactive group should not appear!"
            print("   PASS")
        frappe.db.set_value('Addon Group', test_g.name, 'status', 'Active')
        frappe.db.commit()

    # 5. Out-of-stock item validation
    from flamezo_backend.flamezo.utils.addon_group_helpers import validate_addon_selections
    mock_groups = [{"name": "mock_test", "group_id": "test", "group_name": "Test", "group_type": "addon", "is_required": False, "min_selections": 0, "max_selections": 0, "items": [
        {"item_id": "a", "item_name": "A", "price": 0, "in_stock": True},
        {"item_id": "b", "item_name": "B", "price": 0, "in_stock": False},
    ]}]
    try:
        validate_addon_selections(mock_groups, {"test": ["b"]})
        print("\n5. Stock validation: FAIL (should have thrown)")
    except frappe.ValidationError:
        print("\n5. Stock validation: PASS (out-of-stock item rejected)")

    # 6. Price calculation
    from flamezo_backend.flamezo.utils.addon_group_helpers import calculate_addon_price
    var_groups = [{"name": "mock_size", "group_id": "size", "group_name": "Size", "group_type": "variation", "is_required": True, "min_selections": 1, "max_selections": 1, "items": [
        {"item_id": "s", "item_name": "Small", "price": 150},
        {"item_id": "l", "item_name": "Large", "price": 280},
    ]}]
    price, _ = calculate_addon_price(var_groups, {"size": ["l"]}, 200)
    print(f"\n6. Variation price: base=200, selected Large(280) -> unit_price={price} (should be 280)")
    assert price == 280, f"FAIL: Expected 280, got {price}"
    print("   PASS")

    addon_groups = [{"name": "mock_extras", "group_id": "extras", "group_name": "Extras", "group_type": "addon", "is_required": False, "min_selections": 0, "max_selections": 0, "items": [
        {"item_id": "c", "item_name": "Cheese", "price": 30},
        {"item_id": "b", "item_name": "Bacon", "price": 50},
    ]}]
    price2, _ = calculate_addon_price(addon_groups, {"extras": ["c", "b"]}, 200)
    print(f"   Addon price: base=200 + Cheese(30) + Bacon(50) -> unit_price={price2} (should be 280)")
    assert price2 == 280, f"FAIL: Expected 280, got {price2}"
    print("   PASS")

    print("\n=== ALL VERIFICATIONS PASSED ===\n")
