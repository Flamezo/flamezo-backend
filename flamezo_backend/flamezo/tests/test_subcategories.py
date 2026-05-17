# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Production-grade tests for the subcategory feature.

Covers:
  MenuCategory doctype (menu_category.py)
  ─────────────────────────────────────────
  - Creating a parent category and a sub-category linked to it
  - Sub-category inherits the same restaurant as its parent
  - Circular reference prevention (self-reference)
  - Circular reference prevention (deep cycle)
  - Max depth enforcement: cannot create a sub-sub-category
  - Cross-restaurant parent rejection
  - Cascade delete: deleting a parent also deletes its sub-categories and their products

  get_categories API (categories.py)
  ─────────────────────────────────────────
  - Flat category appears at top level with subcategories=[]
  - Parent category appears at top level with sub inside subcategories[]
  - Sub-category NOT present at top level
  - productCount on parent = own products + sub products
  - isParent flag correct

  get_products API (products.py)
  ─────────────────────────────────────────
  - Filtering by parent category name returns own + sub products
  - Filtering by sub-category name returns only sub products
  - include_inactive=0 still works correctly with hierarchy

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_subcategories
"""

import unittest
import frappe
from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
)
from flamezo_backend.flamezo.api.categories import get_categories
from flamezo_backend.flamezo.api.products import get_products

TEST_PREFIX = "TEST-SUBCAT-"


def make_category(restaurant, category_name, parent_category=None, is_active=1):
    """Create a Menu Category and return the doc."""
    doc = frappe.get_doc({
        "doctype": "Menu Category",
        "restaurant": restaurant,
        "category_name": category_name,
        "is_active": is_active,
        "parent_category": parent_category,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def make_product(restaurant, product_name, category_docname, is_active=1):
    """Create a Menu Product linked to a category (by docname)."""
    doc = frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": restaurant,
        "product_name": product_name,
        "category": category_docname,
        "price": 100.0,
        "is_active": is_active,
        "is_vegetarian": 1,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


class TestMenuCategorySubcategoryDoctype(unittest.TestCase):

    def setUp(self):
        self.restaurant = make_restaurant(f"{TEST_PREFIX}DOCTYPE").name
        frappe.set_user("Administrator")
        for name in frappe.get_all("Menu Product", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Product", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Menu Category", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Category", name, force=True, ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self):
        cleanup_restaurant(self.restaurant)
        frappe.db.commit()

    # ── Creation ──────────────────────────────────────────────────────────────

    def test_create_parent_and_sub(self):
        parent = make_category(self.restaurant, "Starters")
        sub = make_category(self.restaurant, "Veg Starters", parent_category=parent.name)

        self.assertIsNotNone(parent.name)
        self.assertEqual(sub.parent_category, parent.name)
        self.assertEqual(sub.restaurant, self.restaurant)

    def test_sub_category_id_generated(self):
        parent = make_category(self.restaurant, "Main Course")
        sub = make_category(self.restaurant, "Biryani", parent_category=parent.name)
        self.assertTrue(sub.category_id)
        self.assertIn("biryani", sub.category_id)

    def test_plain_category_has_no_parent(self):
        cat = make_category(self.restaurant, "Beverages")
        self.assertFalse(cat.parent_category)

    # ── Validation errors ─────────────────────────────────────────────────────

    def test_self_reference_rejected(self):
        cat = make_category(self.restaurant, "Deserts")
        with self.assertRaises(frappe.ValidationError):
            cat.parent_category = cat.name
            cat.save(ignore_permissions=True)

    def test_max_depth_two_levels_enforced(self):
        """Creating a sub-sub-category must be rejected."""
        parent = make_category(self.restaurant, "NonVeg")
        sub = make_category(self.restaurant, "Chicken", parent_category=parent.name)

        with self.assertRaises(frappe.ValidationError):
            make_category(self.restaurant, "Grilled Chicken", parent_category=sub.name)

    def test_cross_restaurant_parent_rejected(self):
        other_restaurant = make_restaurant(f"{TEST_PREFIX}OTHER").name
        other_parent = make_category(other_restaurant, "Foreign Parent")

        try:
            with self.assertRaises(frappe.ValidationError):
                make_category(self.restaurant, "My Sub", parent_category=other_parent.name)
        finally:
            cleanup_restaurant(other_restaurant)
            frappe.db.commit()

    def test_circular_reference_rejected(self):
        """A → B → A should be rejected when trying to set B as parent of A."""
        a = make_category(self.restaurant, "Cat A")
        b = make_category(self.restaurant, "Cat B", parent_category=a.name)

        with self.assertRaises(frappe.ValidationError):
            # Trying to set a's parent to b would create: b → a → b
            a.parent_category = b.name
            a.save(ignore_permissions=True)

    # ── Cascade delete ────────────────────────────────────────────────────────

    def test_delete_parent_cascades_to_sub_and_products(self):
        parent = make_category(self.restaurant, "Cascade Parent")
        sub = make_category(self.restaurant, "Cascade Sub", parent_category=parent.name)
        product_in_parent = make_product(self.restaurant, "Parent Product", parent.name)
        product_in_sub = make_product(self.restaurant, "Sub Product", sub.name)

        frappe.delete_doc("Menu Category", parent.name, force=True, ignore_permissions=True)
        frappe.db.commit()

        self.assertFalse(frappe.db.exists("Menu Category", parent.name))
        self.assertFalse(frappe.db.exists("Menu Category", sub.name))
        self.assertFalse(frappe.db.exists("Menu Product", product_in_parent.name))
        self.assertFalse(frappe.db.exists("Menu Product", product_in_sub.name))

    def test_delete_sub_does_not_delete_parent(self):
        parent = make_category(self.restaurant, "Safe Parent")
        sub = make_category(self.restaurant, "Deletable Sub", parent_category=parent.name)

        frappe.delete_doc("Menu Category", sub.name, force=True, ignore_permissions=True)
        frappe.db.commit()

        self.assertFalse(frappe.db.exists("Menu Category", sub.name))
        self.assertTrue(frappe.db.exists("Menu Category", parent.name))


class TestGetCategoriesAPI(unittest.TestCase):

    def setUp(self):
        self.restaurant = make_restaurant(f"{TEST_PREFIX}API").name
        frappe.set_user("Administrator")
        for name in frappe.get_all("Menu Product", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Product", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Menu Category", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Category", name, force=True, ignore_permissions=True)
        frappe.db.commit()

        # Build: parent "Starters" → sub "Veg Starters" + sub "Nonveg Starters"
        #        plain "Beverages" (no subs)
        self.parent = make_category(self.restaurant, "Starters")
        self.sub_veg = make_category(self.restaurant, "Veg Starters", parent_category=self.parent.name)
        self.sub_nonveg = make_category(self.restaurant, "Nonveg Starters", parent_category=self.parent.name)
        self.plain = make_category(self.restaurant, "Beverages")

        # Products
        make_product(self.restaurant, "Paneer Tikka", self.sub_veg.name)
        make_product(self.restaurant, "Chicken 65", self.sub_nonveg.name)
        make_product(self.restaurant, "Nachos", self.parent.name)  # direct product on parent
        make_product(self.restaurant, "Mango Lassi", self.plain.name)

    def tearDown(self):
        cleanup_restaurant(self.restaurant)
        frappe.db.commit()

    def _get_cats(self, include_inactive=0):
        result = get_categories(self.restaurant, include_inactive=include_inactive)
        self.assertTrue(result.get("success"), f"API failed: {result}")
        return result["data"]["categories"]

    def _find(self, cats, name):
        return next((c for c in cats if c["name"] == name), None)

    # ── Structure tests ───────────────────────────────────────────────────────

    def test_parent_appears_at_top_level(self):
        cats = self._get_cats()
        found = self._find(cats, "Starters")
        self.assertIsNotNone(found, "Parent category must be in top-level list")

    def test_sub_not_at_top_level(self):
        cats = self._get_cats()
        names = [c["name"] for c in cats]
        self.assertNotIn("Veg Starters", names, "Sub-category must NOT appear at top level")
        self.assertNotIn("Nonveg Starters", names, "Sub-category must NOT appear at top level")

    def test_sub_appears_inside_parent(self):
        cats = self._get_cats()
        parent_data = self._find(cats, "Starters")
        self.assertIsNotNone(parent_data)
        sub_names = [s["name"] for s in parent_data.get("subcategories", [])]
        self.assertIn("Veg Starters", sub_names)
        self.assertIn("Nonveg Starters", sub_names)

    def test_plain_category_has_empty_subcategories(self):
        cats = self._get_cats()
        plain_data = self._find(cats, "Beverages")
        self.assertIsNotNone(plain_data)
        self.assertEqual(plain_data.get("subcategories", []), [])
        self.assertFalse(plain_data.get("isParent", False))

    def test_parent_is_parent_flag(self):
        cats = self._get_cats()
        parent_data = self._find(cats, "Starters")
        self.assertTrue(parent_data.get("isParent"), "isParent must be True on a parent category")

    def test_sub_has_parent_id(self):
        cats = self._get_cats()
        parent_data = self._find(cats, "Starters")
        for sub in parent_data.get("subcategories", []):
            self.assertEqual(sub.get("parentId"), parent_data["id"], "subcategory must have correct parentId")

    # ── Product count tests ───────────────────────────────────────────────────

    def test_parent_product_count_includes_subs(self):
        """Parent count = own (1 Nachos) + sub_veg (1) + sub_nonveg (1) = 3."""
        cats = self._get_cats()
        parent_data = self._find(cats, "Starters")
        self.assertEqual(parent_data["productCount"], 3)

    def test_plain_product_count(self):
        cats = self._get_cats()
        plain_data = self._find(cats, "Beverages")
        self.assertEqual(plain_data["productCount"], 1)

    def test_sub_product_count(self):
        cats = self._get_cats()
        parent_data = self._find(cats, "Starters")
        sub_veg_data = next(s for s in parent_data["subcategories"] if s["name"] == "Veg Starters")
        self.assertEqual(sub_veg_data["productCount"], 1)

    # ── include_inactive ──────────────────────────────────────────────────────

    def test_inactive_category_excluded_by_default(self):
        inactive = make_category(self.restaurant, "Hidden Cat", is_active=0)
        try:
            cats = self._get_cats(include_inactive=0)
            names = [c["name"] for c in cats]
            self.assertNotIn("Hidden Cat", names)
        finally:
            frappe.delete_doc("Menu Category", inactive.name, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_inactive_category_included_when_flag_set(self):
        inactive = make_category(self.restaurant, "Hidden Cat", is_active=0)
        try:
            cats = self._get_cats(include_inactive=1)
            names = [c["name"] for c in cats]
            self.assertIn("Hidden Cat", names)
        finally:
            frappe.delete_doc("Menu Category", inactive.name, force=True, ignore_permissions=True)
            frappe.db.commit()


class TestGetProductsWithSubcategories(unittest.TestCase):

    def setUp(self):
        self.restaurant = make_restaurant(f"{TEST_PREFIX}PROD").name
        frappe.set_user("Administrator")
        # Clean any leftover data from previous runs (make_restaurant reuses the same name)
        for name in frappe.get_all("Menu Product", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Product", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Menu Category", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Category", name, force=True, ignore_permissions=True)
        frappe.db.commit()

        self.parent = make_category(self.restaurant, "Mains")
        self.sub_veg = make_category(self.restaurant, "Veg Mains", parent_category=self.parent.name)
        self.sub_nonveg = make_category(self.restaurant, "Nonveg Mains", parent_category=self.parent.name)
        self.plain = make_category(self.restaurant, "Soups")

        self.p_direct = make_product(self.restaurant, "Dal Makhani", self.parent.name)
        self.p_veg = make_product(self.restaurant, "Paneer Butter Masala", self.sub_veg.name)
        self.p_nonveg = make_product(self.restaurant, "Butter Chicken", self.sub_nonveg.name)
        self.p_soup = make_product(self.restaurant, "Tomato Soup", self.plain.name)

    def tearDown(self):
        # Explicitly delete Menu Products and Categories before restaurant cleanup
        for name in frappe.get_all("Menu Product", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Product", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Menu Category", filters={"restaurant": self.restaurant}, pluck="name"):
            frappe.delete_doc("Menu Category", name, force=True, ignore_permissions=True)
        cleanup_restaurant(self.restaurant)
        frappe.db.commit()

    def _get_products(self, category=None, **kwargs):
        result = get_products(self.restaurant, category=category, include_inactive=1, **kwargs)
        self.assertTrue(result.get("success"), f"API failed: {result}")
        return result["data"]["products"]

    def test_filter_by_parent_returns_own_and_sub_products(self):
        """Filtering by 'Mains' should return Dal Makhani + Paneer Butter Masala + Butter Chicken."""
        products = self._get_products(category="Mains")
        names = {p["name"] for p in products}
        self.assertIn("Dal Makhani", names)
        self.assertIn("Paneer Butter Masala", names)
        self.assertIn("Butter Chicken", names)
        self.assertNotIn("Tomato Soup", names)

    def test_filter_by_sub_returns_only_sub_products(self):
        products = self._get_products(category="Veg Mains")
        names = {p["name"] for p in products}
        self.assertIn("Paneer Butter Masala", names)
        self.assertNotIn("Dal Makhani", names)
        self.assertNotIn("Butter Chicken", names)

    def test_filter_by_plain_category(self):
        products = self._get_products(category="Soups")
        names = {p["name"] for p in products}
        self.assertIn("Tomato Soup", names)
        self.assertEqual(len(names), 1)

    def test_no_category_returns_all(self):
        products = self._get_products(limit=500)
        names = {p["name"] for p in products}
        # All 4 products we inserted must be present
        self.assertIn("Dal Makhani", names)
        self.assertIn("Paneer Butter Masala", names)
        self.assertIn("Butter Chicken", names)
        self.assertIn("Tomato Soup", names)

    def test_inactive_products_excluded_by_default(self):
        inactive_p = make_product(self.restaurant, "Hidden Dish", self.sub_veg.name, is_active=0)
        try:
            result = get_products(self.restaurant, category="Veg Mains", include_inactive=0)
            products = result["data"]["products"]
            names = {p["name"] for p in products}
            self.assertNotIn("Hidden Dish", names)
        finally:
            frappe.delete_doc("Menu Product", inactive_p.name, force=True, ignore_permissions=True)
            frappe.db.commit()


