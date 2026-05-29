"""
Migration: Convert old Customization Questions → Addon Groups

Run:
  bench --site <site> execute flamezo_backend.flamezo.migrations.migrate_customizations_to_addon_groups.run

This script:
1. Scans all Menu Products with customization_questions
2. Groups identical customization question sets (deduplication)
3. Creates Addon Group docs from unique question groups
4. Links them to products via Product Addon Group child table
5. Does NOT delete old customization_questions (backwards compat)
"""
import frappe
import json
import re
from frappe.utils import flt, cint
from collections import defaultdict


def run(dry_run=False):
    print("\n" + "=" * 60)
    print("  MIGRATION: Customization Questions → Addon Groups")
    print("=" * 60)

    # Get all products with customization questions
    products_with_questions = frappe.get_all(
        "Customization Question",
        filters={"parenttype": "Menu Product", "parentfield": "customization_questions"},
        fields=["parent"],
        group_by="parent"
    )
    product_names = [p.parent for p in products_with_questions]
    print(f"\n  Products with customizations: {len(product_names)}")

    if not product_names:
        print("  Nothing to migrate.")
        return

    # Load all questions
    questions = frappe.get_all(
        "Customization Question",
        filters={"parent": ["in", product_names], "parenttype": "Menu Product"},
        fields=["name", "parent", "question_id", "title", "subtitle",
                "question_type", "is_required", "display_order"],
        order_by="parent asc, display_order asc"
    )

    # Load all options
    question_names = [q.name for q in questions]
    options = frappe.get_all(
        "Customization Option",
        filters={"parent": ["in", question_names], "parenttype": "Customization Question"},
        fields=["parent", "option_id", "label", "price", "is_default",
                "is_vegetarian", "display_order"],
        order_by="display_order asc"
    )
    options_by_question = defaultdict(list)
    for opt in options:
        options_by_question[opt.parent].append(opt)

    # Group questions by product
    questions_by_product = defaultdict(list)
    for q in questions:
        q["options"] = options_by_question.get(q.name, [])
        questions_by_product[q.parent].append(q)

    # Deduplicate: create a fingerprint for each question to find reusable groups
    # Fingerprint = (title, type, options_labels_sorted)
    fingerprint_to_group = {}
    groups_created = 0
    links_created = 0

    for product_name, product_questions in questions_by_product.items():
        restaurant = frappe.db.get_value("Menu Product", product_name, "restaurant")
        if not restaurant:
            continue

        for q in product_questions:
            option_labels = tuple(sorted([opt.label for opt in q["options"]]))
            fingerprint = (restaurant, q.title, q.question_type, option_labels)

            if fingerprint not in fingerprint_to_group:
                # Determine group_type: single-select with price → variation
                is_variation = (
                    q.question_type == "single"
                    and any(flt(opt.price) > 0 for opt in q["options"])
                )
                group_type = "variation" if is_variation else "addon"
                max_sel = 1 if q.question_type == "single" else 0

                # Generate slug
                slug = re.sub(r'[^a-z0-9]+', '-', q.title.lower()).strip('-')

                group_data = {
                    "doctype": "Addon Group",
                    "group_name": q.title,
                    "group_id": slug,
                    "group_type": group_type,
                    "restaurant": restaurant,
                    "is_required": cint(q.is_required),
                    "min_selections": 1 if q.is_required else 0,
                    "max_selections": max_sel,
                    "display_order": cint(q.display_order),
                    "status": "Active",
                    "items": []
                }

                for idx, opt in enumerate(q["options"]):
                    label = (opt.label or "").strip()
                    if not label:
                        continue
                    item_slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-') or f"opt-{idx}"
                    group_data["items"].append({
                        "item_name": label,
                        "item_id": f"{slug}--{item_slug}",
                        "price": flt(opt.price),
                        "is_default": cint(opt.is_default),
                        "is_vegetarian": cint(opt.is_vegetarian),
                        "in_stock": 1,
                        "display_order": idx
                    })

                if not group_data["items"]:
                    print(f"  Skipping '{q.title}' — no options found")
                    continue

                if dry_run:
                    print(f"  [DRY] Would create Addon Group: {q.title} ({group_type}) with {len(group_data['items'])} items for {restaurant}")
                    fingerprint_to_group[fingerprint] = f"DRY_{slug}"
                else:
                    doc = frappe.get_doc(group_data)
                    doc.insert(ignore_permissions=True)
                    fingerprint_to_group[fingerprint] = doc.name
                    groups_created += 1
                    print(f"  Created: {doc.group_name} ({group_type}) → {doc.name}")

            # Link to product
            group_doc_name = fingerprint_to_group[fingerprint]

            if not dry_run:
                product_doc = frappe.get_doc("Menu Product", product_name)
                already_linked = any(
                    link.addon_group == group_doc_name
                    for link in (product_doc.addon_groups or [])
                )
                if not already_linked:
                    product_doc.append("addon_groups", {
                        "addon_group": group_doc_name,
                        "is_enabled": 1,
                        "display_order": cint(q.display_order)
                    })
                    product_doc.save(ignore_permissions=True)
                    links_created += 1

    if not dry_run:
        frappe.db.commit()

    print(f"\n  Summary:")
    print(f"    Addon Groups created: {groups_created}")
    print(f"    Product links created: {links_created}")
    print(f"    Products processed: {len(product_names)}")
    print("  Migration complete!" if not dry_run else "  [DRY RUN] No changes made.")
    print("=" * 60)
