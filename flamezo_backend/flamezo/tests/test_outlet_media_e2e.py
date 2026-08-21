# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the shared batched outlet media resolver (utils/outlet_media.py)
and its wiring into the consumer-facing card/hero image fields:
  - flamezo.get_all_outlets / get_discovery_feed -> cover_image
  - outlet.get_outlet_detail -> photos[]

Priority under test: curated Gallery (is_selected=1) > food/product photos
(Product Media on active Menu Products) > outlet logo > nothing.
"""

import unittest

import frappe

from flamezo_backend.flamezo.tests.utils import make_restaurant, make_menu_product
from flamezo_backend.flamezo.utils.outlet_media import batch_resolve_outlet_media

_PREFIX = "TEST-OMEDIA"


def _make_rest(suffix, **kwargs):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type="dining", **kwargs)
    return r.name


def _make_gallery_item(restaurant, url, sort_order=0, is_selected=1, source=None):
    doc = frappe.get_doc({
        "doctype": "Restaurant Gallery Item",
        "restaurant": restaurant,
        "media_type": "Image",
        "url": url,
        "title": f"Gallery {sort_order}",
        "is_selected": is_selected,
        "sort_order": sort_order,
        "source": source,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_product_with_media(restaurant, product_id, media_urls, display_order=0):
    product = make_menu_product(restaurant, product_id, display_order=display_order)
    for i, url in enumerate(media_urls):
        product.append("product_media", {
            "media_url": url,
            "media_type": "image",
            "display_order": i,
        })
    product.save(ignore_permissions=True)
    frappe.db.commit()
    return product.name


def _cleanup(restaurant):
    frappe.db.delete("Restaurant Gallery Item", {"restaurant": restaurant})
    for p in frappe.get_all("Menu Product", {"restaurant": restaurant}, pluck="name"):
        frappe.delete_doc("Menu Product", p, force=True, ignore_permissions=True)
    frappe.db.delete("Outlet", restaurant)
    frappe.db.commit()


class TestBatchResolveOutletMedia(unittest.TestCase):
    """Direct unit-level tests of the resolver function itself."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_empty_input_returns_empty(self):
        self.assertEqual(batch_resolve_outlet_media([]), {})

    def test_gallery_takes_priority_over_food_and_logo(self):
        rest = _make_rest("PRI01")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/gallery1.jpg", sort_order=0)
            _make_product_with_media(rest, "prod-pri01", ["https://cdn.example.com/food1.jpg"])
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4, logos={rest: "https://cdn.example.com/logo.jpg"})
            urls = [m["url"] for m in result[rest]]
            self.assertEqual(urls[0], "https://cdn.example.com/gallery1.jpg")
        finally:
            _cleanup(rest)

    def test_gallery_ordered_by_sort_order(self):
        rest = _make_rest("PRI02")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/second.jpg", sort_order=2)
            _make_gallery_item(rest, "https://cdn.example.com/first.jpg", sort_order=1)
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            urls = [m["url"] for m in result[rest]]
            self.assertEqual(urls, ["https://cdn.example.com/first.jpg", "https://cdn.example.com/second.jpg"])
        finally:
            _cleanup(rest)

    def test_unselected_gallery_items_excluded(self):
        rest = _make_rest("PRI03")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/hidden.jpg", sort_order=0, is_selected=0)
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            self.assertEqual(result[rest], [])
        finally:
            _cleanup(rest)

    def test_falls_back_to_food_when_no_gallery(self):
        rest = _make_rest("FOOD01")
        try:
            _make_product_with_media(rest, "prod-food01", ["https://cdn.example.com/dish1.jpg", "https://cdn.example.com/dish2.jpg"])
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            urls = [m["url"] for m in result[rest]]
            self.assertIn("https://cdn.example.com/dish1.jpg", urls)
            self.assertIn("https://cdn.example.com/dish2.jpg", urls)
        finally:
            _cleanup(rest)

    def test_inactive_product_media_excluded_from_fallback(self):
        rest = _make_rest("FOOD02")
        try:
            _make_product_with_media(rest, "prod-food02", ["https://cdn.example.com/inactive.jpg"])
            frappe.db.set_value("Menu Product", {"restaurant": rest}, "is_active", 0)
            frappe.db.commit()
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4, logos={rest: "https://cdn.example.com/logo.jpg"})
            urls = [m["url"] for m in result[rest]]
            self.assertNotIn("https://cdn.example.com/inactive.jpg", urls)
            self.assertEqual(urls, ["https://cdn.example.com/logo.jpg"])
        finally:
            _cleanup(rest)

    def test_falls_back_to_logo_when_nothing_else(self):
        rest = _make_rest("LOGO01")
        try:
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4, logos={rest: "https://cdn.example.com/logo.jpg"})
            self.assertEqual(result[rest], [{"url": "https://cdn.example.com/logo.jpg", "type": "Image", "title": "Logo"}])
        finally:
            _cleanup(rest)

    def test_empty_list_when_nothing_at_all(self):
        rest = _make_rest("NONE01")
        try:
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            self.assertEqual(result[rest], [])
        finally:
            _cleanup(rest)

    def test_gallery_and_food_fill_up_to_cap_combined(self):
        """1 gallery item + cap 4 -> tops up with food photos (across products,
        since a single product allows at most 3 media items), not more."""
        rest = _make_rest("CAP01")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/g1.jpg", sort_order=0)
            _make_product_with_media(rest, "prod-cap01a", [
                "https://cdn.example.com/f1.jpg", "https://cdn.example.com/f2.jpg", "https://cdn.example.com/f3.jpg",
            ], display_order=0)
            _make_product_with_media(rest, "prod-cap01b", ["https://cdn.example.com/f4.jpg"], display_order=1)
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            self.assertEqual(len(result[rest]), 4)
            self.assertEqual(result[rest][0]["url"], "https://cdn.example.com/g1.jpg")
        finally:
            _cleanup(rest)

    def test_batching_does_not_cross_contaminate_outlets(self):
        """Multiple outlets in one call — each gets only its own media, in one
        fixed pair of SQL queries regardless of how many outlets are passed."""
        rest_a = _make_rest("BATCHA")
        rest_b = _make_rest("BATCHB")
        try:
            _make_gallery_item(rest_a, "https://cdn.example.com/a.jpg", sort_order=0)
            _make_product_with_media(rest_b, "prod-batchb", ["https://cdn.example.com/b.jpg"])

            result = batch_resolve_outlet_media([rest_a, rest_b], limit_per_outlet=4)
            self.assertEqual([m["url"] for m in result[rest_a]], ["https://cdn.example.com/a.jpg"])
            self.assertEqual([m["url"] for m in result[rest_b]], ["https://cdn.example.com/b.jpg"])
        finally:
            _cleanup(rest_a)
            _cleanup(rest_b)

    def test_google_places_ranks_first_within_gallery_tier(self):
        """A pre-existing merchant-uploaded gallery row (earlier sort_order)
        must NOT bury a real Google Places photo (later sort_order) — Google
        Places photos rank first within the selected-gallery tier regardless
        of insertion order."""
        rest = _make_rest("GPRANK01")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/menu-upload.jpg", sort_order=1, source="Menu Product")
            _make_gallery_item(rest, "https://cdn.example.com/google-photo.jpg", sort_order=26, source="Google Places")
            result = batch_resolve_outlet_media([rest], limit_per_outlet=4)
            self.assertEqual(result[rest][0]["url"], "https://cdn.example.com/google-photo.jpg")
        finally:
            _cleanup(rest)

    def test_limit_per_outlet_respected(self):
        rest = _make_rest("LIMIT01")
        try:
            for i in range(5):
                _make_gallery_item(rest, f"https://cdn.example.com/g{i}.jpg", sort_order=i)
            result = batch_resolve_outlet_media([rest], limit_per_outlet=1)
            self.assertEqual(len(result[rest]), 1)
            self.assertEqual(result[rest][0]["url"], "https://cdn.example.com/g0.jpg")
        finally:
            _cleanup(rest)


class TestDiscoveryFeedCoverImage(unittest.TestCase):
    """cover_image field on flamezo.get_all_outlets / get_discovery_feed."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_cover_image_from_gallery(self):
        from flamezo_backend.flamezo.api.flamezo import get_all_outlets
        rest = _make_rest("FEED01")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/feed-gallery.jpg", sort_order=0)
            result = get_all_outlets(search=f"{_PREFIX}-FEED01")
            card = next(o for o in result["data"]["outlets"] if o["id"] == rest)
            self.assertEqual(card["cover_image"], "https://cdn.example.com/feed-gallery.jpg")
        finally:
            _cleanup(rest)

    def test_cover_image_falls_back_to_food_then_logo(self):
        from flamezo_backend.flamezo.api.flamezo import get_all_outlets
        rest = _make_rest("FEED02")
        try:
            frappe.db.set_value("Outlet", rest, "logo", "https://cdn.example.com/feed-logo.jpg")
            frappe.db.commit()
            result = get_all_outlets(search=f"{_PREFIX}-FEED02")
            card = next(o for o in result["data"]["outlets"] if o["id"] == rest)
            self.assertEqual(card["cover_image"], "https://cdn.example.com/feed-logo.jpg")

            _make_product_with_media(rest, "prod-feed02", ["https://cdn.example.com/feed-food.jpg"])
            result2 = get_all_outlets(search=f"{_PREFIX}-FEED02")
            card2 = next(o for o in result2["data"]["outlets"] if o["id"] == rest)
            self.assertEqual(card2["cover_image"], "https://cdn.example.com/feed-food.jpg")
        finally:
            _cleanup(rest)


class TestOutletDetailPhotosFallback(unittest.TestCase):
    """photos[] field on outlet.get_outlet_detail now falls back to food
    photos (not just logo) when the merchant hasn't curated a Gallery."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_detail_photos_gallery_priority(self):
        from flamezo_backend.flamezo.api.outlet import get_outlet_detail
        rest = _make_rest("DET01")
        try:
            _make_gallery_item(rest, "https://cdn.example.com/det-gallery.jpg", sort_order=0)
            result = get_outlet_detail(rest)
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["photos"][0]["url"], "https://cdn.example.com/det-gallery.jpg")
        finally:
            _cleanup(rest)

    def test_detail_photos_food_fallback(self):
        from flamezo_backend.flamezo.api.outlet import get_outlet_detail
        rest = _make_rest("DET02")
        try:
            _make_product_with_media(rest, "prod-det02", ["https://cdn.example.com/det-food.jpg"])
            result = get_outlet_detail(rest)
            self.assertTrue(result["success"])
            urls = [p["url"] for p in result["data"]["photos"]]
            self.assertIn("https://cdn.example.com/det-food.jpg", urls)
        finally:
            _cleanup(rest)

    def test_detail_photos_logo_fallback_when_nothing_else(self):
        from flamezo_backend.flamezo.api.outlet import get_outlet_detail
        rest = _make_rest("DET03")
        try:
            frappe.db.set_value("Outlet", rest, "logo", "https://cdn.example.com/det-logo.jpg")
            frappe.db.commit()
            result = get_outlet_detail(rest)
            self.assertTrue(result["success"])
            urls = [p["url"] for p in result["data"]["photos"]]
            self.assertEqual(urls, ["https://cdn.example.com/det-logo.jpg"])
        finally:
            _cleanup(rest)

    def test_detail_photos_capped_at_twelve(self):
        # Was capped at 4 (far below the discovery card's 6 and the full
        # gallery viewer's 25, and below what HeroCollage was actually built
        # to display) — raised to 12. Create more than that so this test
        # still actually exercises the cap, not just "return everything".
        from flamezo_backend.flamezo.api.outlet import get_outlet_detail
        rest = _make_rest("DET12")
        try:
            for i in range(15):
                _make_gallery_item(rest, f"https://cdn.example.com/det-{i}.jpg", sort_order=i)
            result = get_outlet_detail(rest)
            self.assertEqual(len(result["data"]["photos"]), 12)
        finally:
            _cleanup(rest)


if __name__ == "__main__":
    unittest.main()
