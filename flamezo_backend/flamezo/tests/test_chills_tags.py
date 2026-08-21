"""
E2E test: niche_tags / custom_tags on the Chills doctype.
Run with: bench --site flamezo.localhost run-tests --module flamezo_backend.flamezo.tests.test_chills_tags
"""
import json
import unittest
import unittest.mock as mock

import frappe

from flamezo_backend.flamezo.api.chills import (
    MAX_CUSTOM_TAGS,
    MAX_NICHE_TAGS,
    _format_chills,
    _parse_list,
    _validate_tags,
    get_merchant_chills,
    merchant_update_chills_tags,
)


def _fake_access(outlet, phone=None):
    pass


def _get_outlet():
    name = frappe.db.get_value("Outlet", {}, "name")
    if not name:
        raise RuntimeError("No Restaurant doc in local DB — seed one first.")
    return name


class TestValidateTags(unittest.TestCase):
    # ── _validate_tags ────────────────────────────────────────────────────────

    def test_valid_niche_and_custom(self):
        n, c = _validate_tags(
            json.dumps(["dining-cafe-specialty", "dining-bar-rooftop"]),
            json.dumps(["Rooftop Vibes", "Date Night"]),
        )
        self.assertEqual(n, ["dining-cafe-specialty", "dining-bar-rooftop"])
        self.assertEqual(c, ["Rooftop Vibes", "Date Night"])

    def test_invalid_taxonomy_id_stripped(self):
        n, _ = _validate_tags(json.dumps(["dining-cafe-specialty", "fake-id-xyz"]), None)
        self.assertEqual(n, ["dining-cafe-specialty"])

    def test_deduplication(self):
        n, c = _validate_tags(
            json.dumps(["dining-cafe", "dining-cafe", "dining-cafe"]),
            json.dumps(["tag", "tag"]),
        )
        self.assertEqual(n, ["dining-cafe"])
        self.assertEqual(c, ["tag"])

    def test_accepts_python_list_not_just_json_string(self):
        n, c = _validate_tags(["dining-cafe", "wellness-spa"], ["My Tag"])
        self.assertEqual(n, ["dining-cafe", "wellness-spa"])
        self.assertEqual(c, ["My Tag"])

    def test_none_returns_empty(self):
        n, c = _validate_tags(None, None)
        self.assertEqual(n, [])
        self.assertEqual(c, [])

    def test_empty_string_returns_empty(self):
        n, c = _validate_tags("", "")
        self.assertEqual(n, [])
        self.assertEqual(c, [])

    def test_empty_json_array_returns_empty(self):
        n, c = _validate_tags("[]", "[]")
        self.assertEqual(n, [])
        self.assertEqual(c, [])

    def test_malformed_json_returns_empty(self):
        n, c = _validate_tags("not-json", "[bad")
        self.assertEqual(n, [])
        self.assertEqual(c, [])

    def test_blank_custom_tags_stripped(self):
        _, c = _validate_tags(None, json.dumps(["  ", "valid", ""]))
        self.assertEqual(c, ["valid"])

    def test_niche_cap_enforced(self):
        too_many = [
            "dining-cafe", "dining-bar", "beauty-hair", "fashion-retail",
            "sports-courts", "wellness-spa", "retail-books", "entertainment-gaming",
            "dining-fine",  # 9th — over limit
        ]
        with self.assertRaises(frappe.exceptions.ValidationError) as ctx:
            _validate_tags(json.dumps(too_many), None)
        self.assertIn(str(MAX_NICHE_TAGS), str(ctx.exception))

    def test_custom_cap_enforced(self):
        too_many = ["a", "b", "c", "d", "e", "f"]  # 6 — over limit
        with self.assertRaises(frappe.exceptions.ValidationError) as ctx:
            _validate_tags(None, json.dumps(too_many))
        self.assertIn(str(MAX_CUSTOM_TAGS), str(ctx.exception))


class TestParseList(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(_parse_list(json.dumps(["a", "b"])), ["a", "b"])

    def test_none(self):
        self.assertEqual(_parse_list(None), [])

    def test_empty_string(self):
        self.assertEqual(_parse_list(""), [])

    def test_malformed(self):
        self.assertEqual(_parse_list("not json"), [])

    def test_empty_array(self):
        self.assertEqual(_parse_list("[]"), [])

    def test_passthrough_list(self):
        self.assertEqual(_parse_list(["x", "y"]), ["x", "y"])


class TestChillsTagsE2E(unittest.TestCase):
    """Full DB-backed E2E tests — create, read, update, clean up."""

    @classmethod
    def setUpClass(cls):
        cls.outlet_id = _get_outlet()
        niche_list, custom_list = _validate_tags(
            json.dumps(["dining-cafe-specialty", "dining-bar-rooftop"]),
            json.dumps(["Rooftop Vibes", "Date Night"]),
        )
        doc = frappe.get_doc({
            "doctype": "Chills",
            "outlet": cls.outlet_id,
            "video_url": "https://cdn.example.com/test.mp4",
            "thumbnail_url": "https://cdn.example.com/thumb.jpg",
            "description": "E2E tag test",
            "niche_tags": json.dumps(niche_list),
            "custom_tags": json.dumps(custom_list),
            "status": "published",
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        cls.chills_id = doc.name

    @classmethod
    def tearDownClass(cls):
        frappe.delete_doc("Chills", cls.chills_id, ignore_permissions=True, force=True)
        frappe.db.commit()

    # ── A: Persistence ────────────────────────────────────────────────────────

    def test_A1_niche_tags_stored_as_json_string(self):
        val = frappe.db.get_value("Chills", self.chills_id, "niche_tags")
        self.assertIsInstance(val, str)
        self.assertTrue(val.startswith("["))

    def test_A2_niche_tags_round_trip(self):
        val = frappe.db.get_value("Chills", self.chills_id, "niche_tags")
        self.assertEqual(_parse_list(val), ["dining-cafe-specialty", "dining-bar-rooftop"])

    def test_A3_custom_tags_round_trip(self):
        val = frappe.db.get_value("Chills", self.chills_id, "custom_tags")
        self.assertEqual(_parse_list(val), ["Rooftop Vibes", "Date Night"])

    # ── B: get_merchant_chills payload ────────────────────────────────────────

    def _get_merchant_resp(self):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            return get_merchant_chills(outlet_id=self.outlet_id, limit=50)

    def test_B1_response_success(self):
        resp = self._get_merchant_resp()
        self.assertTrue(resp.get("success"))

    def test_B2_videos_is_list(self):
        resp = self._get_merchant_resp()
        self.assertIsInstance(resp["data"]["videos"], list)

    def test_B3_test_doc_in_list(self):
        resp = self._get_merchant_resp()
        ids = [v["id"] for v in resp["data"]["videos"]]
        self.assertIn(self.chills_id, ids)

    def test_B4_nicheTags_is_list(self):
        resp = self._get_merchant_resp()
        match = next(v for v in resp["data"]["videos"] if v["id"] == self.chills_id)
        self.assertIsInstance(match["nicheTags"], list)

    def test_B5_nicheTags_correct_values(self):
        resp = self._get_merchant_resp()
        match = next(v for v in resp["data"]["videos"] if v["id"] == self.chills_id)
        self.assertEqual(match["nicheTags"], ["dining-cafe-specialty", "dining-bar-rooftop"])

    def test_B6_customTags_is_list(self):
        resp = self._get_merchant_resp()
        match = next(v for v in resp["data"]["videos"] if v["id"] == self.chills_id)
        self.assertIsInstance(match["customTags"], list)

    def test_B7_customTags_correct_values(self):
        resp = self._get_merchant_resp()
        match = next(v for v in resp["data"]["videos"] if v["id"] == self.chills_id)
        self.assertEqual(match["customTags"], ["Rooftop Vibes", "Date Night"])

    def test_B8_legacy_fields_intact(self):
        resp = self._get_merchant_resp()
        match = next(v for v in resp["data"]["videos"] if v["id"] == self.chills_id)
        for key in ["videoUrl", "thumbnail", "views", "likes", "saves", "shares", "status", "published_at"]:
            self.assertIn(key, match, f"Missing field: {key}")

    # ── C: _format_chills (customer feed) ────────────────────────────────────

    def _get_raw(self):
        return frappe.db.get_value(
            "Chills", self.chills_id,
            ["name", "outlet", "outlet_name", "outlet_city", "outlet_logo",
             "outlet_lat", "outlet_lng", "video_url", "thumbnail_url",
             "description", "audio", "niche_tags", "custom_tags",
             "likes_count", "saves_count", "shares_count", "views_count", "published_at"],
            as_dict=True,
        )

    def test_C1_nicheTags_in_feed_format(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        self.assertIn("nicheTags", fmt)

    def test_C2_customTags_in_feed_format(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        self.assertIn("customTags", fmt)

    def test_C3_nicheTags_correct(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        self.assertEqual(fmt["nicheTags"], ["dining-cafe-specialty", "dining-bar-rooftop"])

    def test_C4_customTags_correct(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        self.assertEqual(fmt["customTags"], ["Rooftop Vibes", "Date Night"])

    def test_C5_outlet_nested_dict_present(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        self.assertIsInstance(fmt.get("outlet"), dict)

    def test_C6_all_feed_fields_present(self):
        fmt = _format_chills(self._get_raw(), set(), set(), set(), {})
        for key in ["id", "videoUrl", "description", "likes", "saves", "isLiked", "isSaved", "nicheTags", "customTags"]:
            self.assertIn(key, fmt, f"Missing feed field: {key}")

    # ── D: merchant_update_chills_tags ────────────────────────────────────────

    def _update(self, niche=None, custom=None):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            return merchant_update_chills_tags(
                self.outlet_id, self.chills_id,
                niche_tags=niche, custom_tags=custom,
            )

    def test_D1_update_returns_success(self):
        res = self._update(niche=json.dumps(["beauty-hair-salon"]), custom=json.dumps(["Updated"]))
        self.assertTrue(res["success"])

    def test_D2_update_returns_new_values(self):
        res = self._update(niche=json.dumps(["beauty-hair-salon"]), custom=json.dumps(["Updated"]))
        self.assertEqual(res["data"]["nicheTags"], ["beauty-hair-salon"])
        self.assertEqual(res["data"]["customTags"], ["Updated"])

    def test_D3_update_persisted_to_db(self):
        self._update(niche=json.dumps(["wellness-spa"]), custom=json.dumps(["Persist Test"]))
        row = frappe.db.get_value("Chills", self.chills_id, ["niche_tags", "custom_tags"], as_dict=True)
        self.assertEqual(_parse_list(row.niche_tags), ["wellness-spa"])
        self.assertEqual(_parse_list(row.custom_tags), ["Persist Test"])

    def test_D4_clear_tags(self):
        self._update(niche="[]", custom="[]")
        row = frappe.db.get_value("Chills", self.chills_id, ["niche_tags", "custom_tags"], as_dict=True)
        self.assertEqual(_parse_list(row.niche_tags), [])
        self.assertEqual(_parse_list(row.custom_tags), [])

    def test_D5_rejects_empty_chills_id(self):
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=self.outlet_id):
            with self.assertRaises(frappe.exceptions.ValidationError):
                merchant_update_chills_tags(self.outlet_id, chills_id="", niche_tags="[]")

    def test_D6_ownership_check(self):
        other = frappe.db.sql(
            "SELECT name FROM `tabOutlet` WHERE name != %s LIMIT 1",
            self.outlet_id, as_dict=True,
        )
        if not other:
            self.skipTest("Only one outlet in local DB")
        other_id = other[0]["name"]
        with mock.patch("flamezo_backend.flamezo.api.chills._assert_outlet_access", _fake_access), \
             mock.patch("flamezo_backend.flamezo.api.chills._resolve_outlet", return_value=other_id):
            with self.assertRaises(frappe.PermissionError):
                merchant_update_chills_tags(other_id, self.chills_id, niche_tags="[]")

    def test_D7_rejects_over_niche_cap_on_update(self):
        too_many = ["dining-cafe","dining-bar","beauty-hair","fashion-retail","sports-courts",
                    "wellness-spa","retail-books","entertainment-gaming","dining-fine"]
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._update(niche=json.dumps(too_many))

    def test_D8_rejects_over_custom_cap_on_update(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._update(custom=json.dumps(["a", "b", "c", "d", "e", "f"]))
