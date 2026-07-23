# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the non-dining Catalogue API (catalogue.py).

Covers:
  Consumer:
    - get_catalogue: empty, populated, cache hit, cache miss
    - get_catalogue_item: happy path, wrong restaurant, inactive item

  Merchant CRUD:
    - save_catalogue_category: create, update, missing params
    - delete_catalogue_category: success, access denied
    - save_catalogue_item: create with media + sub-items, update, validation
    - delete_catalogue_item: success
    - reorder_catalogue_items: bulk sort_order update

  Cache:
    - Cache populated on get_catalogue
    - Cache invalidated on category update
    - Cache invalidated on item update / trash
"""

import unittest
import json
import frappe
from frappe.utils import now

from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-CAT"


def _make_restaurant(suffix="01", outlet_type="wellness"):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type=outlet_type, whatsapp_number="9876543210")
    return r.name


def _make_category(restaurant, name="Hair Services", sort_order=0):
    doc = frappe.get_doc({
        "doctype": "Catalogue Category",
        "restaurant": restaurant,
        "category_name": name,
        "is_active": 1,
        "sort_order": sort_order,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_item(restaurant, category, name="Haircut", price=500, price_prefix="starts at"):
    doc = frappe.get_doc({
        "doctype": "Catalogue Item",
        "restaurant": restaurant,
        "category": category,
        "item_name": name,
        "price": price,
        "price_prefix": price_prefix,
        "is_active": 1,
        "is_popular": 0,
        "sort_order": 0,
        "item_media": [
            {
                "doctype": "Catalogue Item Media",
                "media_url": "https://cdn.flamezo.in/test/img1.jpg",
                "media_type": "image",
                "is_primary": 1,
                "display_order": 0,
            }
        ],
        "sub_items": [
            {
                "doctype": "Catalogue Sub-item",
                "item_name": "Men Haircut",
                "price": 350,
                "is_available": 1,
                "sort_order": 0,
            },
            {
                "doctype": "Catalogue Sub-item",
                "item_name": "Child Haircut",
                "price": 250,
                "is_available": 1,
                "sort_order": 1,
            },
        ],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup(restaurant):
    for sub in frappe.get_all("Catalogue Sub-item", {"parent": ["like", f"%"]}, ["name", "parent"]):
        pass  # child tables deleted with parent
    for item in frappe.get_all("Catalogue Item", {"restaurant": restaurant}, ["name"]):
        frappe.delete_doc("Catalogue Item", item.name, ignore_permissions=True)
    for cat in frappe.get_all("Catalogue Category", {"restaurant": restaurant}, ["name"]):
        frappe.delete_doc("Catalogue Category", cat.name, ignore_permissions=True)
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestGetCatalogue(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GC01", "wellness")
        self.category   = _make_category(self.restaurant, "Hair Services", sort_order=0)
        self.category2  = _make_category(self.restaurant, "Skin Care", sort_order=1)
        self.item       = _make_item(self.restaurant, self.category, "Haircut", 500, "starts at")

    def tearDown(self):
        # Clear cache first
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        _cleanup(self.restaurant)

    def test_returns_correct_structure(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue(self.restaurant)
        self.assertTrue(res["success"], res)
        data = res["data"]
        self.assertEqual(data["outlet_type"], "wellness")
        self.assertIsInstance(data["categories"], list)
        self.assertEqual(len(data["categories"]), 2)

    def test_category_sort_order(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue(self.restaurant)
        cats = res["data"]["categories"]
        self.assertEqual(cats[0]["name"], "Hair Services")
        self.assertEqual(cats[1]["name"], "Skin Care")

    def test_items_in_category(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue(self.restaurant)
        hair_cat = next(c for c in res["data"]["categories"] if c["name"] == "Hair Services")
        self.assertEqual(len(hair_cat["items"]), 1)
        item = hair_cat["items"][0]
        self.assertEqual(item["name"], "Haircut")
        self.assertEqual(item["price"], 500.0)
        self.assertEqual(item["price_prefix"], "starts at")
        self.assertIn("starts at", item["price_display"])

    def test_sub_items_returned(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue(self.restaurant)
        hair_cat = next(c for c in res["data"]["categories"] if c["name"] == "Hair Services")
        item = hair_cat["items"][0]
        self.assertEqual(len(item["sub_items"]), 2)
        names = [s["name"] for s in item["sub_items"]]
        self.assertIn("Men Haircut", names)
        self.assertIn("Child Haircut", names)

    def test_media_returned(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue(self.restaurant)
        hair_cat = next(c for c in res["data"]["categories"] if c["name"] == "Hair Services")
        item = hair_cat["items"][0]
        self.assertEqual(len(item["media"]), 1)
        self.assertTrue(item["media"][0]["is_primary"])
        self.assertIn("cdn.flamezo.in", item["media"][0]["url"])

    def test_cache_is_populated(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        get_catalogue(self.restaurant)
        cached = frappe.cache().get_value(f"flamezo:catalogue:{self.restaurant}")
        self.assertIsNotNone(cached)
        parsed = json.loads(cached)
        self.assertTrue(parsed["success"])

    def test_cache_invalidated_on_category_update(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        get_catalogue(self.restaurant)
        # Update category — should bust cache
        cat_doc = frappe.get_doc("Catalogue Category", self.category)
        cat_doc.category_name = "Hair & Styling"
        cat_doc.save(ignore_permissions=True)
        frappe.db.commit()
        cached = frappe.cache().get_value(f"flamezo:catalogue:{self.restaurant}")
        self.assertIsNone(cached)

    def test_cache_invalidated_on_item_update(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        get_catalogue(self.restaurant)
        item_doc = frappe.get_doc("Catalogue Item", self.item)
        item_doc.price = 600
        item_doc.save(ignore_permissions=True)
        frappe.db.commit()
        cached = frappe.cache().get_value(f"flamezo:catalogue:{self.restaurant}")
        self.assertIsNone(cached)

    def test_empty_catalogue_returns_empty_list(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        empty_rest = _make_restaurant("GC02", "fashion")
        try:
            res = get_catalogue(empty_rest)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["categories"], [])
        finally:
            frappe.db.delete("Restaurant", empty_rest)
            frappe.db.commit()

    def test_inactive_item_excluded(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        item_doc = frappe.get_doc("Catalogue Item", self.item)
        item_doc.is_active = 0
        item_doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        res = get_catalogue(self.restaurant)
        hair_cat = next(c for c in res["data"]["categories"] if c["name"] == "Hair Services")
        self.assertEqual(len(hair_cat["items"]), 0)

    def test_restaurant_not_found(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        res = get_catalogue("NONEXISTENT-REST-9999")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")


class TestGetCatalogueItem(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GI01", "wellness")
        self.category   = _make_category(self.restaurant, "Hair Services")
        self.item       = _make_item(self.restaurant, self.category)

    def tearDown(self):
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        _cleanup(self.restaurant)

    def test_returns_item_detail(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue_item
        res = get_catalogue_item(self.item, self.restaurant)
        self.assertTrue(res["success"], res)
        data = res["data"]
        self.assertEqual(data["name"], "Haircut")
        self.assertEqual(data["price"], 500.0)
        self.assertEqual(data["outlet_type"], "wellness")
        self.assertEqual(data["whatsapp_number"], "9876543210")

    def test_sub_items_included(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue_item
        res = get_catalogue_item(self.item, self.restaurant)
        self.assertEqual(len(res["data"]["sub_items"]), 2)

    def test_wrong_restaurant_returns_not_found(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue_item
        other = _make_restaurant("GI02", "fashion")
        try:
            res = get_catalogue_item(self.item, other)
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "NOT_FOUND")
        finally:
            frappe.db.delete("Restaurant", other)
            frappe.db.commit()

    def test_inactive_item_returns_not_found(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue_item
        item_doc = frappe.get_doc("Catalogue Item", self.item)
        item_doc.is_active = 0
        item_doc.save(ignore_permissions=True)
        frappe.db.commit()
        res = get_catalogue_item(self.item, self.restaurant)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_nonexistent_item_returns_not_found(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue_item
        res = get_catalogue_item("FAKE-ITEM-XYZ", self.restaurant)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")


class TestCatalogueCategoryMerchantCRUD(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CC01", "fitness")

    def tearDown(self):
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        _cleanup(self.restaurant)

    def test_create_category(self):
        from flamezo_backend.flamezo.api.catalogue import save_catalogue_category
        res = save_catalogue_category(
            restaurant_id=self.restaurant,
            category_name="Group Classes",
            sort_order=0,
            is_active=1,
        )
        self.assertTrue(res["success"], res)
        self.assertIn("name", res["data"])
        # Verify in DB
        self.assertTrue(frappe.db.exists("Catalogue Category", res["data"]["name"]))

    def test_update_category(self):
        from flamezo_backend.flamezo.api.catalogue import save_catalogue_category
        cat_name = _make_category(self.restaurant, "Old Name")
        res = save_catalogue_category(
            restaurant_id=self.restaurant,
            name=cat_name,
            category_name="New Name",
            sort_order=5,
        )
        self.assertTrue(res["success"], res)
        updated = frappe.db.get_value("Catalogue Category", cat_name, ["category_name", "sort_order"], as_dict=True)
        self.assertEqual(updated.category_name, "New Name")
        self.assertEqual(updated.sort_order, 5)

    def test_missing_params_returns_error(self):
        from flamezo_backend.flamezo.api.catalogue import save_catalogue_category
        res = save_catalogue_category(restaurant_id=self.restaurant)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MISSING_PARAM")

    def test_delete_category(self):
        from flamezo_backend.flamezo.api.catalogue import delete_catalogue_category
        cat_name = _make_category(self.restaurant, "To Delete")
        res = delete_catalogue_category(restaurant_id=self.restaurant, name=cat_name)
        self.assertTrue(res["success"], res)
        self.assertFalse(frappe.db.exists("Catalogue Category", cat_name))

    def test_category_name_invalid_restaurant_blocked(self):
        from flamezo_backend.flamezo.api.catalogue import delete_catalogue_category
        other = _make_restaurant("CC02", "fitness")
        cat_name = _make_category(other, "Other Cat")
        try:
            res = delete_catalogue_category(restaurant_id=self.restaurant, name=cat_name)
            # Must not succeed — category belongs to other restaurant
            self.assertFalse(res["success"])
        finally:
            _cleanup(other)


class TestCatalogueItemMerchantCRUD(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CI01", "wellness")
        self.category   = _make_category(self.restaurant, "Hair")

    def tearDown(self):
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        _cleanup(self.restaurant)

    def test_create_item_with_media_and_sub_items(self):
        from flamezo_backend.flamezo.api.catalogue import save_catalogue_item
        res = save_catalogue_item(
            restaurant_id=self.restaurant,
            item_data={
                "item_name": "Keratin Treatment",
                "category": self.category,
                "price": 2000,
                "price_prefix": "starts at",
                "is_popular": 1,
                "badge": "Best Value",
                "item_media": [
                    {"media_url": "https://cdn.flamezo.in/keratin.jpg", "media_type": "image", "is_primary": 1, "display_order": 0}
                ],
                "sub_items": [
                    {"item_name": "Short Hair", "price": 2000, "is_available": 1, "sort_order": 0},
                    {"item_name": "Long Hair",  "price": 3500, "is_available": 1, "sort_order": 1},
                ],
            }
        )
        self.assertTrue(res["success"], res)
        item_name = res["data"]["name"]
        doc = frappe.get_doc("Catalogue Item", item_name)
        self.assertEqual(doc.item_name, "Keratin Treatment")
        self.assertEqual(len(doc.item_media), 1)
        self.assertEqual(len(doc.sub_items), 2)
        self.assertEqual(doc.badge, "Best Value")

    def test_create_item_wrong_category_restaurant_blocked(self):
        from flamezo_backend.flamezo.api.catalogue import save_catalogue_item
        other = _make_restaurant("CI02", "fashion")
        other_cat = _make_category(other, "Clothes")
        try:
            res = save_catalogue_item(
                restaurant_id=self.restaurant,
                item_data={"item_name": "X", "category": other_cat, "price": 100},
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "INVALID_CATEGORY")
        finally:
            _cleanup(other)

    def test_reorder_items(self):
        from flamezo_backend.flamezo.api.catalogue import reorder_catalogue_items
        item1 = _make_item(self.restaurant, self.category, "Item A", 100)
        item2 = _make_item(self.restaurant, self.category, "Item B", 200)
        res = reorder_catalogue_items(
            restaurant_id=self.restaurant,
            item_orders=[
                {"name": item1, "sort_order": 10},
                {"name": item2, "sort_order": 5},
            ],
        )
        self.assertTrue(res["success"], res)
        self.assertEqual(frappe.db.get_value("Catalogue Item", item1, "sort_order"), 10)
        self.assertEqual(frappe.db.get_value("Catalogue Item", item2, "sort_order"), 5)

    def test_delete_item(self):
        from flamezo_backend.flamezo.api.catalogue import delete_catalogue_item
        item_name = _make_item(self.restaurant, self.category, "To Delete", 100)
        res = delete_catalogue_item(restaurant_id=self.restaurant, name=item_name)
        self.assertTrue(res["success"], res)
        self.assertFalse(frappe.db.exists("Catalogue Item", item_name))

    def test_price_display_formatting(self):
        from flamezo_backend.flamezo.api.catalogue import get_catalogue
        _make_item(self.restaurant, self.category, "Facial", 1500, "from")
        frappe.cache().delete_value(f"flamezo:catalogue:{self.restaurant}")
        res = get_catalogue(self.restaurant)
        hair_cat = next(c for c in res["data"]["categories"] if c["name"] == "Hair")
        facial = next(i for i in hair_cat["items"] if i["name"] == "Facial")
        self.assertIn("₹1,500", facial["price_display"])
        self.assertIn("from", facial["price_display"])


if __name__ == "__main__":
    unittest.main()
