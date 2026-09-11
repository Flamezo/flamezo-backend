# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for the Discover Near home-feed sections — flamezo.get_discovery_feed:

  limelight      — only outlets with the Limelight toggle on, inside their
                   date window; never topped up with un-featured outlets
  new_to_flamezo — most recently added (creation) first
  popular        — rated outlets near the viewer, highest rating first;
                   widens 10 km -> 25 km when short; city-wide without GPS
  sections never share an outlet

Every fixture lives in its own made-up city so the site's real outlets never
leak into a section.
"""

import unittest

import frappe
from frappe.utils import add_days, now_datetime, today

from flamezo_backend.flamezo.api import flamezo as flamezo_api
from flamezo_backend.flamezo.tests.utils import make_restaurant


_PREFIX = "TEST-FEEDSEC"
_CITY = "Feedsectionville"

# Viewer location, and points roughly N km due north of it (1° lat ≈ 111 km).
_LAT, _LNG = 21.1702, 72.8311


def _km_north(km):
    return _LAT + km / 111.0


def _make(suffix, rating=4.0, review_count=10, km=1, added_days_ago=30, **fields):
    name = f"{_PREFIX}-{suffix}"
    if frappe.db.exists("Outlet", name):
        frappe.delete_doc("Outlet", name, force=True, ignore_permissions=True)
    make_restaurant(name)
    values = {
        "is_active": 1,
        "is_featured": 0,
        "is_signature": 0,
        "limelight_start_date": None,
        "limelight_end_date": None,
        "rating": rating,
        "review_count": review_count,
        "city": _CITY,
        "latitude": _km_north(km),
        "longitude": _LNG,
        "outlet_type": "cafe",
    }
    values.update(fields)
    frappe.db.set_value("Outlet", name, values, update_modified=False)
    # `creation` is what "New to Flamezo" ranks on — pin it per fixture.
    frappe.db.sql(
        "UPDATE `tabOutlet` SET creation = %s WHERE name = %s",
        (add_days(now_datetime(), -added_days_ago), name),
    )
    frappe.db.commit()
    return name


def _cleanup():
    frappe.db.sql(f"DELETE FROM `tabOutlet` WHERE name LIKE '{_PREFIX}%'")
    for key in frappe.cache().get_keys("flamezo:feed:*") or []:
        frappe.cache().delete_value(key)
    frappe.db.commit()


def _feed(with_location=True, **kwargs):
    if with_location:
        kwargs.setdefault("latitude", _LAT)
        kwargs.setdefault("longitude", _LNG)
    result = flamezo_api.get_discovery_feed(city=_CITY, **kwargs)
    assert result["success"], result
    return result["data"]


def _ids(cards):
    return [c["id"] for c in cards]


class _FeedTestCase(unittest.TestCase):
    def setUp(self):
        _cleanup()

    def tearDown(self):
        _cleanup()


class TestLimelight(_FeedTestCase):
    def test_only_toggled_on_outlets_are_shown(self):
        featured = _make("F1", is_featured=1)
        # More than New + Popular can absorb, so a top-up would have spares.
        plain = [_make(f"P{i}", rating=4.9) for i in range(14)]

        limelight = _ids(_feed()["limelight"])

        self.assertEqual(limelight, [featured])
        for name in plain:
            self.assertNotIn(name, limelight)

    def test_empty_when_nothing_is_toggled_on(self):
        _make("P1", rating=5.0, review_count=5000)

        self.assertEqual(_feed()["limelight"], [])

    def test_respects_limelight_date_window(self):
        live = _make("LIVE", is_featured=1, limelight_start_date=add_days(today(), -1),
                     limelight_end_date=add_days(today(), 1))
        ended = _make("ENDED", is_featured=1, limelight_end_date=add_days(today(), -1))
        upcoming = _make("SOON", is_featured=1, limelight_start_date=add_days(today(), 1))

        limelight = _ids(_feed()["limelight"])

        self.assertIn(live, limelight)
        self.assertNotIn(ended, limelight)
        self.assertNotIn(upcoming, limelight)

    def test_featured_signature_outlet_goes_to_limelight(self):
        both = _make("BOTH", is_featured=1, is_signature=1)

        data = _feed()

        self.assertIn(both, _ids(data["limelight"]))
        self.assertNotIn(both, _ids(data["signature"]))

    def test_best_rated_first_capped_at_six(self):
        names = [_make(f"F{i}", is_featured=1, rating=3.0 + i * 0.2) for i in range(8)]

        limelight = _ids(_feed()["limelight"])

        self.assertEqual(limelight, list(reversed(names))[:6])


class TestNewToFlamezo(_FeedTestCase):
    def test_most_recently_added_first(self):
        old = _make("OLD", added_days_ago=90)
        newest = _make("NEWEST", added_days_ago=1)
        mid = _make("MID", added_days_ago=10)

        self.assertEqual(_ids(_feed()["new_to_flamezo"]), [newest, mid, old])

    def test_capped_at_five_newest(self):
        names = [_make(f"N{i}", added_days_ago=i + 1) for i in range(7)]

        self.assertEqual(_ids(_feed()["new_to_flamezo"]), names[:5])

    def test_independent_of_location(self):
        far = _make("FAR", km=100, added_days_ago=1)

        self.assertEqual(_ids(_feed()["new_to_flamezo"])[0], far)


class TestPopularPicks(_FeedTestCase):
    def setUp(self):
        super().setUp()
        # The five newest outlets are claimed by "New to Flamezo" first;
        # make them unrated so they're never popular candidates themselves.
        self.newest = [_make(f"NEW{i}", rating=0, added_days_ago=i) for i in range(5)]

    def test_nearby_sorted_by_rating(self):
        ok = _make("OK", rating=3.9, km=2)
        best = _make("BEST", rating=4.8, km=8)
        good = _make("GOOD", rating=4.3, km=1)

        self.assertEqual(_ids(_feed()["popular"]), [best, good, ok])

    def test_equal_rating_more_reviews_first(self):
        few = _make("FEW", rating=4.5, review_count=12)
        many = _make("MANY", rating=4.5, review_count=900)

        self.assertEqual(_ids(_feed()["popular"]), [many, few])

    def test_prefers_ten_km_over_higher_rated_farther_away(self):
        near = [_make(f"NEAR{i}", rating=4.0, km=3) for i in range(5)]
        far_star = _make("FARSTAR", rating=5.0, km=20)

        popular = _ids(_feed()["popular"])

        self.assertCountEqual(popular, near)
        self.assertNotIn(far_star, popular)

    def test_widens_to_25_km_when_short(self):
        near = _make("NEAR", rating=4.0, km=3)
        wider = _make("WIDER", rating=4.6, km=20)
        too_far = _make("TOOFAR", rating=4.9, km=40)

        popular = _ids(_feed()["popular"])

        self.assertEqual(popular, [wider, near])
        self.assertNotIn(too_far, popular)

    def test_unrated_and_unpinned_outlets_excluded(self):
        rated = _make("RATED", rating=4.1)
        unrated = _make("UNRATED", rating=0)
        unpinned = _make("NOPIN", rating=4.9, latitude=0, longitude=0)

        popular = _ids(_feed()["popular"])

        self.assertEqual(popular, [rated])
        self.assertNotIn(unrated, popular)
        self.assertNotIn(unpinned, popular)

    def test_without_location_ranks_by_rating_in_city(self):
        low = _make("LOW", rating=3.5, km=100)
        high = _make("HIGH", rating=4.7, km=300)

        popular = _ids(_feed(with_location=False)["popular"])

        self.assertEqual(popular, [high, low])

    def test_returns_distance(self):
        _make("DIST", rating=4.2, km=5)

        card = _feed()["popular"][0]

        self.assertAlmostEqual(card["distance_km"], 5, delta=0.2)


class TestSectionsDoNotOverlap(_FeedTestCase):
    def test_no_outlet_in_two_sections(self):
        for i in range(4):
            _make(f"F{i}", is_featured=1, rating=4.9, added_days_ago=i)
        for i in range(4):
            _make(f"S{i}", is_signature=1, rating=4.8, added_days_ago=i)
        for i in range(12):
            _make(f"X{i}", rating=3.5 + i * 0.1, km=i + 1, added_days_ago=i)

        data = _feed()
        seen = []
        for key in ("limelight", "signature", "new_to_flamezo", "popular"):
            seen += _ids(data[key])

        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(data["popular"]), 5)
