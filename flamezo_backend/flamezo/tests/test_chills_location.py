"""
E2E test: location fields on the Chills doctype.
Run with: bench --site flamezo.localhost run-tests --module flamezo_backend.flamezo.tests.test_chills_location
"""
import unittest
import unittest.mock as mock

import frappe

from flamezo_backend.flamezo.api.chills import (
    _format_chills,
    get_merchant_chills,
    merchant_publish_chills,
    merchant_update_chills_location,
)


def _fake_access(outlet, phone=None):
    pass


def _get_outlet():
    name = frappe.db.get_value("Restaurant", {}, "name")
    if not name:
        raise RuntimeError("No Restaurant doc in local DB — seed one first.")
    return name


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chills(outlet, location_name="", location_lat=0.0, location_lng=0.0, location_radius=0):
    doc = frappe.get_doc({
        "doctype": "Chills",
        "outlet": outlet,
        "video_url": "https://cdn.example.com/loc_test.mp4",
        "thumbnail_url": "https://cdn.example.com/loc_thumb.jpg",
        "description": "Location E2E test",
        "location_name": location_name,
        "location_lat": location_lat,
        "location_lng": location_lng,
        "location_radius": location_radius,
        "status": "published",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


# ── A: DB persistence ────────────────────────────────────────────────────────

class TestLocationPersistence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.outlet_id = _get_outlet()
        cls.chills_id = _make_chills(
            cls.outlet_id,
            location_name="Adajan, Surat",
            location_lat=21.1855,
            location_lng=72.7997,
            location_radius=300,
        )

    @classmethod
    def tearDownClass(cls):
        frappe.delete_doc("Chills", cls.chills_id, ignore_permissions=True, force=True)
        frappe.db.commit()

    def _row(self):
        return frappe.db.get_value(
            "Chills", self.chills_id,
            ["location_name", "location_lat", "location_lng", "location_radius"],
            as_dict=True,
        )

    def test_A1_location_name_stored(self):
        self.assertEqual(self._row().location_name, "Adajan, Surat")

    def test_A2_location_lat_stored(self):
        self.assertAlmostEqual(float(self._row().location_lat), 21.1855, places=3)

    def test_A3_location_lng_stored(self):
        self.assertAlmostEqual(float(self._row().location_lng), 72.7997, places=3)

    def test_A4_location_radius_stored(self):
        self.assertEqual(int(self._row().location_radius), 300)


# ── B: _format_chills (feed format) ──────────────────────────────────────────

class TestLocationFeedFormat(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.outlet_id = _get_outlet()
        cls.chills_id_pinned = _make_chills(
            cls.outlet_id,
            location_name="City Light, Surat",
            location_lat=21.1567,
            location_lng=72.8243,
            location_radius=300,
        )
        cls.chills_id_no_loc = _make_chills(cls.outlet_id)

    @classmethod
    def tearDownClass(cls):
        for cid in (cls.chills_id_pinned, cls.chills_id_no_loc):
            frappe.delete_doc("Chills", cid, ignore_permissions=True, force=True)
        frappe.db.commit()

    def _raw(self, chills_id):
        return frappe.db.get_value(
            "Chills", chills_id,
            ["name", "outlet", "outlet_name", "outlet_city", "outlet_logo",
             "outlet_lat", "outlet_lng", "video_url", "thumbnail_url",
             "description", "audio", "niche_tags", "custom_tags",
             "location_name", "location_lat", "location_lng", "location_radius",
             "likes_count", "saves_count", "shares_count", "views_count", "published_at"],
            as_dict=True,
        )

    def test_B1_pinned_location_in_feed(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        self.assertIsNotNone(fmt.get("location"))

    def test_B2_location_name_correct(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        self.assertEqual(fmt["location"]["name"], "City Light, Surat")

    def test_B3_location_lat_correct(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        self.assertAlmostEqual(fmt["location"]["lat"], 21.1567, places=3)

    def test_B4_location_lng_correct(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        self.assertAlmostEqual(fmt["location"]["lng"], 72.8243, places=3)

    def test_B5_location_radius_correct(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        self.assertEqual(fmt["location"]["radius"], 300)

    def test_B6_no_location_returns_none(self):
        fmt = _format_chills(self._raw(self.chills_id_no_loc), set(), set(), set(), {})
        self.assertIsNone(fmt.get("location"))

    def test_B7_all_expected_fields_present(self):
        fmt = _format_chills(self._raw(self.chills_id_pinned), set(), set(), set(), {})
        for key in ["id", "videoUrl", "description", "location", "nicheTags", "customTags"]:
            self.assertIn(key, fmt, f"Missing: {key}")


# ── C: get_merchant_chills payload ───────────────────────────────────────────

class TestMerchantChillsLocationPayload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.outlet_id = _get_outlet()
        cls.chills_id = _make_chills(
            cls.outlet_id,
            location_name="Vesu, Surat",
            location_lat=21.1347,
            location_lng=72.7944,
            location_radius=3000,
        )

    @classmethod
    def tearDownClass(cls):
        frappe.delete_doc("Chills", cls.chills_id, ignore_permissions=True, force=True)
        frappe.db.commit()

    def _resp(self):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            return get_merchant_chills(outlet_id=self.outlet_id, limit=50)

    def test_C1_response_success(self):
        self.assertTrue(self._resp().get("success"))

    def test_C2_test_doc_in_list(self):
        ids = [v["id"] for v in self._resp()["data"]["videos"]]
        self.assertIn(self.chills_id, ids)

    def test_C3_location_dict_present(self):
        match = next(v for v in self._resp()["data"]["videos"] if v["id"] == self.chills_id)
        self.assertIsNotNone(match.get("location"))

    def test_C4_location_name_correct(self):
        match = next(v for v in self._resp()["data"]["videos"] if v["id"] == self.chills_id)
        self.assertEqual(match["location"]["name"], "Vesu, Surat")

    def test_C5_location_radius_correct(self):
        match = next(v for v in self._resp()["data"]["videos"] if v["id"] == self.chills_id)
        self.assertEqual(match["location"]["radius"], 3000)

    def test_C6_location_coords_correct(self):
        match = next(v for v in self._resp()["data"]["videos"] if v["id"] == self.chills_id)
        self.assertAlmostEqual(match["location"]["lat"], 21.1347, places=3)
        self.assertAlmostEqual(match["location"]["lng"], 72.7944, places=3)


# ── D: merchant_update_chills_location ───────────────────────────────────────

class TestUpdateChillsLocation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.outlet_id = _get_outlet()
        cls.chills_id = _make_chills(cls.outlet_id)

    @classmethod
    def tearDownClass(cls):
        frappe.delete_doc("Chills", cls.chills_id, ignore_permissions=True, force=True)
        frappe.db.commit()

    def _update(self, **kwargs):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            return merchant_update_chills_location(
                outlet_id=self.outlet_id,
                chills_id=self.chills_id,
                **kwargs,
            )

    def _row(self):
        return frappe.db.get_value(
            "Chills", self.chills_id,
            ["location_name", "location_lat", "location_lng", "location_radius"],
            as_dict=True,
        )

    def test_D1_update_returns_success(self):
        res = self._update(
            location_name="Pal, Surat",
            location_lat=21.1952,
            location_lng=72.8096,
            location_radius=300,
        )
        self.assertTrue(res["success"])

    def test_D2_update_returns_location_dict(self):
        res = self._update(
            location_name="Pal, Surat",
            location_lat=21.1952,
            location_lng=72.8096,
            location_radius=300,
        )
        self.assertIsNotNone(res["data"]["location"])
        self.assertEqual(res["data"]["location"]["name"], "Pal, Surat")

    def test_D3_update_persisted_to_db(self):
        self._update(
            location_name="Dumas, Surat",
            location_lat=21.0788,
            location_lng=72.7189,
            location_radius=300,
        )
        row = self._row()
        self.assertEqual(row.location_name, "Dumas, Surat")
        self.assertAlmostEqual(float(row.location_lat), 21.0788, places=3)

    def test_D4_clear_location(self):
        # Set first
        self._update(location_name="Test Area", location_lat=21.1, location_lng=72.8, location_radius=300)
        # Clear by passing empty string
        res = self._update(location_name="", location_lat=0, location_lng=0, location_radius=0)
        self.assertIsNone(res["data"]["location"])
        row = self._row()
        self.assertEqual(row.location_name or "", "")

    def test_D5_rejects_empty_chills_id(self):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            with self.assertRaises(frappe.exceptions.ValidationError):
                merchant_update_chills_location(
                    outlet_id=self.outlet_id, chills_id="",
                    location_name="X", location_lat=21.0, location_lng=72.8, location_radius=300,
                )

    def test_D6_ownership_check(self):
        other = frappe.db.sql(
            "SELECT name FROM `tabRestaurant` WHERE name != %s LIMIT 1",
            self.outlet_id, as_dict=True,
        )
        if not other:
            self.skipTest("Only one outlet in local DB")
        other_id = other[0]["name"]
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=other_id):
            with self.assertRaises(frappe.PermissionError):
                merchant_update_chills_location(
                    outlet_id=other_id, chills_id=self.chills_id,
                    location_name="Evil", location_lat=0.0, location_lng=0.0, location_radius=300,
                )

    def test_D7_invalid_coords_raises(self):
        with self.assertRaises(Exception):
            self._update(
                location_name="Bad",
                location_lat="not-a-float",
                location_lng=72.8,
                location_radius=300,
            )

    def test_D8_city_radius_saved(self):
        self._update(
            location_name="Surat",
            location_lat=21.1702,
            location_lng=72.8311,
            location_radius=20000,
        )
        row = self._row()
        self.assertEqual(int(row.location_radius), 20000)

    def test_D9_neighbourhood_radius_saved(self):
        self._update(
            location_name="Athwa, Surat",
            location_lat=21.1700,
            location_lng=72.8100,
            location_radius=3000,
        )
        row = self._row()
        self.assertEqual(int(row.location_radius), 3000)


# ── E: merchant_publish_chills with location ─────────────────────────────────

class TestPublishChillsWithLocation(unittest.TestCase):
    """Verify that location fields survive the full publish path."""

    _created: list = []

    @classmethod
    def tearDownClass(cls):
        for cid in cls._created:
            try:
                frappe.delete_doc("Chills", cid, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def _publish(self, **extra):
        outlet_id = _get_outlet()
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=outlet_id), \
             mock.patch("flamezo_backend.flamezo.utils.r2_storage.public_url", return_value="https://cdn.example.com/v.mp4"):
            res = merchant_publish_chills(
                outlet_id=outlet_id,
                object_key="chills/merchant/test/uuid.mp4",
                description="E2E publish with location",
                **extra,
            )
        cid = res["data"]["chills_id"]
        self.__class__._created.append(cid)
        return cid

    def test_E1_publish_with_location_creates_doc(self):
        cid = self._publish(
            location_name="Katargam, Surat",
            location_lat=21.2312,
            location_lng=72.8448,
            location_radius=300,
        )
        row = frappe.db.get_value(
            "Chills", cid,
            ["location_name", "location_lat", "location_radius"],
            as_dict=True,
        )
        self.assertEqual(row.location_name, "Katargam, Surat")
        self.assertAlmostEqual(float(row.location_lat), 21.2312, places=3)
        self.assertEqual(int(row.location_radius), 300)

    def test_E2_publish_without_location_stores_empty(self):
        cid = self._publish()
        row = frappe.db.get_value("Chills", cid, "location_name")
        self.assertFalse(row)  # None or ""

    def test_E3_publish_city_radius(self):
        cid = self._publish(
            location_name="Surat",
            location_lat=21.1702,
            location_lng=72.8311,
            location_radius=20000,
        )
        row = frappe.db.get_value("Chills", cid, "location_radius")
        self.assertEqual(int(row), 20000)
