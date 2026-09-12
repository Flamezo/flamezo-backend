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
  city / category / Signatures-tab / radius filters and is_active apply to
  every section
  outlets past the old 300-row pool cap still reach their sections
  `seen` (what the app saw last time) — unseen outlets first in every
  section, seen ones only fill, longest-ago seen first; no guest caching

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


def _clone(template, count, tag):
    """`count` SQL copies of `template` (fast — no doc hooks), unique fields
    reset; each copy inherits the template's city, rating, pin and creation."""
    unique_null = {"subdomain", "slug", "referral_code"}
    select = []
    for col in frappe.db.get_table_columns("Outlet"):
        if col in ("name", "outlet_id"):
            select.append("%s")
        elif col in unique_null:
            select.append("NULL")
        else:
            select.append(f"`{col}`")
    cols = ", ".join(f"`{c}`" for c in frappe.db.get_table_columns("Outlet"))
    names = []
    for i in range(count):
        name = f"{_PREFIX}-{tag}-{i:03d}"
        frappe.db.sql(
            f"INSERT INTO `tabOutlet` ({cols}) SELECT {', '.join(select)} FROM `tabOutlet` WHERE name = %s",
            (name, name, template),
        )
        names.append(name)
    frappe.db.commit()
    return names


def _all_ids(data):
    return [c["id"] for key in ("limelight", "signature", "new_to_flamezo", "popular") for c in data[key]]


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

    def test_window_starting_and_ending_today_is_live(self):
        today_only = _make("TODAY", is_featured=1, limelight_start_date=today(),
                           limelight_end_date=today())

        self.assertEqual(_ids(_feed()["limelight"]), [today_only])

    def test_toggled_on_but_inactive_outlet_excluded(self):
        _make("OFF", is_featured=1, is_active=0)

        self.assertEqual(_feed()["limelight"], [])

    def test_not_limited_by_distance(self):
        far = _make("FAR", is_featured=1, km=80)

        self.assertEqual(_ids(_feed()["limelight"]), [far])

    def test_cards_are_marked_featured(self):
        _make("F1", is_featured=1)

        card = _feed()["limelight"][0]

        self.assertTrue(card["is_featured"])


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

    def test_ignores_hand_entered_onboarding_date(self):
        # Onboarding date says "today" but the outlet was added long ago.
        stale = _make("STALE", added_days_ago=200, onboarding_date=today())
        recent = _make("RECENT", added_days_ago=2, onboarding_date=add_days(today(), -400))

        self.assertEqual(_ids(_feed()["new_to_flamezo"]), [recent, stale])

    def test_newest_featured_outlet_stays_in_limelight_only(self):
        featured_newest = _make("FNEW", is_featured=1, added_days_ago=0)
        next_newest = _make("NEXT", added_days_ago=1)

        data = _feed()

        self.assertEqual(_ids(data["limelight"]), [featured_newest])
        self.assertEqual(_ids(data["new_to_flamezo"])[0], next_newest)
        self.assertNotIn(featured_newest, _ids(data["new_to_flamezo"]))


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

    def test_equal_rating_and_reviews_nearest_first(self):
        farther = _make("FARTHER", rating=4.4, review_count=50, km=7)
        nearer = _make("NEARER", rating=4.4, review_count=50, km=2)

        self.assertEqual(_ids(_feed()["popular"]), [nearer, farther])

    def test_explicit_radius_is_a_hard_limit(self):
        inside = _make("INSIDE", rating=4.0, km=3)
        outside = _make("OUTSIDE", rating=4.9, km=8)

        popular = _ids(_feed(radius_km=5)["popular"])

        # Short of 5 results, but an app-sent radius is never widened.
        self.assertEqual(popular, [inside])
        self.assertNotIn(outside, popular)

    def test_inactive_outlet_excluded(self):
        _make("CLOSED", rating=5.0, is_active=0)

        self.assertEqual(_feed()["popular"], [])


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

    def test_sections_respect_their_caps(self):
        for i in range(8):
            _make(f"F{i}", is_featured=1)
        for i in range(12):
            _make(f"S{i}", is_signature=1)
        for i in range(12):
            _make(f"X{i}", added_days_ago=i)

        data = _feed()

        self.assertEqual(len(data["limelight"]), 6)
        self.assertEqual(len(data["signature"]), 10)
        self.assertEqual(len(data["new_to_flamezo"]), 5)
        self.assertEqual(len(data["popular"]), 5)


class TestFiltersApplyToEverySection(_FeedTestCase):
    """An outlet that would win every section — featured, newest, best rated,
    nearest — must still stay out of all of them when a filter excludes it."""

    def _star(self, suffix, **fields):
        return _make(suffix, is_featured=1, is_signature=1, rating=5.0,
                     review_count=9999, km=0.5, added_days_ago=0, **fields)

    def test_other_city_excluded(self):
        elsewhere = self._star("ELSEWHERE", city="Othertown")
        _make("LOCAL", rating=4.0)

        self.assertNotIn(elsewhere, _all_ids(_feed()))

    def test_category_tab_excluded(self):
        dining = self._star("DINING", outlet_type="dining")
        cafe = _make("CAFE", is_featured=1, rating=4.0)

        data = _feed(outlet_type="cafe")

        self.assertNotIn(dining, _all_ids(data))
        self.assertEqual(_ids(data["limelight"]), [cafe])

    def test_signatures_tab_shows_only_signature_outlets(self):
        plain = _make("PLAIN", is_featured=1, rating=5.0, added_days_ago=0)
        sig = [_make(f"SIG{i}", is_signature=1, rating=4.0) for i in range(3)]

        ids = _all_ids(_feed(is_signature=1))

        self.assertNotIn(plain, ids)
        self.assertCountEqual(ids, sig)

    def test_inactive_excluded(self):
        closed = self._star("CLOSED", is_active=0)

        self.assertNotIn(closed, _all_ids(_feed()))

    def test_radius_limits_every_section(self):
        far = self._star("FAR", latitude=_km_north(30))
        near = _make("NEAR", is_featured=1, rating=4.0, km=2)

        data = _feed(radius_km=10)

        self.assertNotIn(far, _all_ids(data))
        self.assertEqual(_ids(data["limelight"]), [near])


class TestBeyondOldPoolCap(_FeedTestCase):
    """The old feed read one arbitrary 300-row pool, so with more outlets than
    that, the featured / newest / best-rated ones could never be picked. The
    winners here sort AFTER 310 filler rows by primary key, i.e. outside what
    an un-ordered LIMIT 300 scan returns."""

    def setUp(self):
        super().setUp()
        filler = _make("BULK-TEMPLATE", rating=3.0, km=1, added_days_ago=60)
        _clone(filler, 310, "BULK")
        self.featured = _make("ZZZ-FEATURED", is_featured=1, rating=3.0, added_days_ago=60)
        self.newest = _make("ZZZ-NEWEST", rating=3.0, added_days_ago=0)
        # Older than the filler, so New to Flamezo doesn't claim it first.
        self.top_rated = _make("ZZZ-TOPRATED", rating=4.9, km=2, added_days_ago=90)

    def test_featured_outlet_reaches_limelight(self):
        self.assertEqual(_ids(_feed()["limelight"]), [self.featured])

    def test_newest_outlet_reaches_new_to_flamezo(self):
        self.assertEqual(_ids(_feed()["new_to_flamezo"])[0], self.newest)

    def test_top_rated_nearby_outlet_reaches_popular(self):
        self.assertEqual(_ids(_feed()["popular"])[0], self.top_rated)


class TestParseSeenIds(unittest.TestCase):
    def test_drops_blanks_and_keeps_a_repeat_at_its_latest_position(self):
        self.assertEqual(flamezo_api._parse_seen_ids(" a, ,b,a ,c"), ["b", "a", "c"])

    def test_accepts_a_list(self):
        self.assertEqual(flamezo_api._parse_seen_ids(["x", " y "]), ["x", "y"])

    def test_keeps_only_the_newest_ids(self):
        ids = [f"o{i}" for i in range(250)]

        self.assertEqual(flamezo_api._parse_seen_ids(",".join(ids)), ids[-200:])

    def test_empty(self):
        self.assertEqual(flamezo_api._parse_seen_ids(None), [])
        self.assertEqual(flamezo_api._parse_seen_ids(""), [])

    def test_drops_ids_longer_than_an_outlet_name_can_be(self):
        self.assertEqual(flamezo_api._parse_seen_ids(f"ok,{'x' * 141}"), ["ok"])


class TestSeenRotation(_FeedTestCase):
    """The app sends `seen` — outlets already looked at in these sections,
    oldest first — and every section shows unseen outlets before them."""

    def test_limelight_unseen_first(self):
        names = [_make(f"F{i}", is_featured=1, rating=3.0 + i * 0.2) for i in range(8)]

        limelight = _ids(_feed(seen=f"{names[7]},{names[6]}")["limelight"])

        # The two best were seen last time; the other six take the section.
        self.assertEqual(limelight, list(reversed(names[:6])))

    def test_seen_ones_fill_longest_ago_seen_first(self):
        top = _make("TOP", is_featured=1, rating=4.9)
        mid = _make("MID", is_featured=1, rating=4.5)
        low = _make("LOW", is_featured=1, rating=4.0)

        # MID was seen longest ago, TOP most recently.
        limelight = _ids(_feed(seen=f"{mid},{top}")["limelight"])

        self.assertEqual(limelight, [low, mid, top])

    def test_signature_unseen_first(self):
        best = _make("SBEST", is_signature=1, rating=4.9)
        other = _make("SOTHER", is_signature=1, rating=4.0)

        self.assertEqual(_ids(_feed(seen=best)["signature"]), [other, best])

    def test_new_to_flamezo_unseen_first(self):
        names = [_make(f"N{i}", added_days_ago=i + 1) for i in range(7)]

        new = _ids(_feed(seen=f"{names[0]},{names[1]}")["new_to_flamezo"])

        self.assertEqual(new, names[2:7])

    def test_new_to_flamezo_seen_fill(self):
        names = [_make(f"N{i}", added_days_ago=i + 1) for i in range(5)]

        new = _ids(_feed(seen=names[0])["new_to_flamezo"])

        self.assertEqual(new, names[1:] + [names[0]])

    def test_new_to_flamezo_rotates_only_inside_its_window(self):
        recent = _make("RECENT", added_days_ago=5)
        old = _make("OLD", added_days_ago=120)

        # RECENT was seen, but a four-month-old outlet still isn't "new".
        self.assertEqual(_ids(_feed(seen=recent)["new_to_flamezo"]), [recent, old])

    def test_unknown_and_messy_ids_are_ignored(self):
        best = _make("BEST", is_featured=1, rating=4.9)
        other = _make("OTHER", is_featured=1, rating=4.0)

        limelight = _ids(_feed(seen=f" , nope ,{best}, ,")["limelight"])

        self.assertEqual(limelight, [other, best])

    def test_sections_stay_full_and_separate_when_everything_was_seen(self):
        names = [_make(f"F{i}", is_featured=1) for i in range(8)]
        names += [_make(f"S{i}", is_signature=1) for i in range(12)]
        names += [_make(f"X{i}", added_days_ago=i) for i in range(12)]

        data = _feed(seen=",".join(names))
        ids = _all_ids(data)

        self.assertEqual(len(data["limelight"]), 6)
        self.assertEqual(len(data["signature"]), 10)
        self.assertEqual(len(data["new_to_flamezo"]), 5)
        self.assertEqual(len(data["popular"]), 5)
        self.assertEqual(len(ids), len(set(ids)))


class TestSeenRotationPopular(_FeedTestCase):
    def setUp(self):
        super().setUp()
        # Unrated, so New to Flamezo claims them and they never compete here.
        self.newest = [_make(f"NEW{i}", rating=0, added_days_ago=i) for i in range(5)]

    def test_unseen_farther_away_before_seen_nearby(self):
        near = _make("NEAR", rating=4.9, km=2)
        far = _make("FAR", rating=4.0, km=20)

        self.assertEqual(_ids(_feed(seen=near)["popular"]), [far, near])

    def test_unseen_still_prefer_ten_km(self):
        near = [_make(f"NEAR{i}", rating=4.0, km=3) for i in range(5)]
        _make("FARSTAR", rating=5.0, km=20)
        seen_one = _make("SEEN", rating=4.5, km=1)

        popular = _ids(_feed(seen=seen_one)["popular"])

        self.assertCountEqual(popular, near)

    def test_seen_fill_longest_ago_seen_first(self):
        best = _make("BEST", rating=4.9, km=1)
        other = _make("OTHER", rating=4.2, km=1)

        self.assertEqual(_ids(_feed(seen=f"{other},{best}")["popular"]), [other, best])

    def test_without_location_unseen_first(self):
        high = _make("HIGH", rating=4.7, km=300)
        low = _make("LOW", rating=3.5, km=100)

        popular = _ids(_feed(with_location=False, seen=high)["popular"])

        self.assertEqual(popular, [low, high])


class TestSeenSkipsGuestCache(_FeedTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_guest_request_with_seen_is_not_cached(self):
        featured = _make("F1", is_featured=1)
        frappe.set_user("Guest")

        _feed(seen=featured)

        self.assertFalse(frappe.cache().get_keys("flamezo:feed:*"))

    def test_guest_request_without_seen_is_still_cached(self):
        _make("F1", is_featured=1)
        frappe.set_user("Guest")

        _feed()

        self.assertTrue(frappe.cache().get_keys("flamezo:feed:*"))


class TestSeenWithFilters(_FeedTestCase):
    def test_signatures_tab_unseen_first(self):
        top = _make("STOP", is_signature=1, rating=4.9)
        mid = _make("SMID", is_signature=1, rating=4.5)
        low = _make("SLOW", is_signature=1, rating=4.0)
        plain = _make("PLAIN", rating=5.0, added_days_ago=0)

        data = _feed(is_signature=1, seen=top)

        self.assertEqual(_ids(data["signature"]), [mid, low, top])
        self.assertNotIn(plain, _all_ids(data))

    def test_explicit_radius_stays_a_hard_limit(self):
        for i in range(5):
            _make(f"NEW{i}", rating=0, added_days_ago=i)
        seen_near = _make("SEENNEAR", rating=4.9, km=3)
        unseen_near = _make("UNSEENNEAR", rating=4.0, km=4)
        _make("OUTSIDE", rating=5.0, km=8)

        popular = _ids(_feed(radius_km=5, seen=seen_near)["popular"])

        self.assertEqual(popular, [unseen_near, seen_near])

    def test_seen_ids_from_another_city_change_nothing(self):
        elsewhere = _make("ELSEWHERE", is_featured=1, city="Othertown")
        best = _make("BEST", is_featured=1, rating=4.9)
        other = _make("OTHER", is_featured=1, rating=4.0)

        self.assertEqual(_ids(_feed(seen=elsewhere)["limelight"]), [best, other])

    def test_new_to_flamezo_window_edge(self):
        inside = _make("DAY59", added_days_ago=59)
        outside = _make("DAY61", added_days_ago=61)

        # DAY59 was seen but is still "new"; DAY61 isn't, so it only tops up.
        self.assertEqual(_ids(_feed(seen=inside)["new_to_flamezo"]), [inside, outside])


class TestRotationAcrossOpens(_FeedTestCase):
    """Open after open, the way the app does it: what the viewer saw goes
    back as `seen` — here every card shown, the most the app could send."""

    def _open(self, history, **kwargs):
        data = _feed(seen=",".join(history), **kwargs)
        for outlet_id in _all_ids(data):
            if outlet_id in history:
                history.remove(outlet_id)
            history.append(outlet_id)
        return data

    def _fresh_five(self):
        # Newest and unrated: New to Flamezo takes them every time, Popular
        # never does — so the other sections' outlets stay where they are.
        for i in range(5):
            _make(f"NEW{i}", rating=0, added_days_ago=i)

    def test_limelight_new_outlets_each_open_then_starts_over(self):
        # Older than New to Flamezo's window and unrated: Limelight only.
        featured = [_make(f"F{i:02d}", is_featured=1, rating=0, added_days_ago=90) for i in range(12)]
        self._fresh_five()
        history = []

        first = _ids(self._open(history)["limelight"])
        second = _ids(self._open(history)["limelight"])
        third = _ids(self._open(history)["limelight"])

        self.assertEqual(len(first), 6)
        self.assertEqual(len(second), 6)
        self.assertCountEqual(first + second, featured)
        # All twelve seen: the ones seen longest ago come back first.
        self.assertCountEqual(third, first)

    def test_signature_new_outlets_each_open(self):
        signature = [_make(f"S{i:02d}", is_signature=1, rating=0, added_days_ago=90) for i in range(20)]
        self._fresh_five()
        history = []

        first = _ids(self._open(history)["signature"])
        second = _ids(self._open(history)["signature"])

        self.assertEqual(len(first), 10)
        self.assertCountEqual(first + second, signature)

    def test_new_to_flamezo_new_outlets_each_open(self):
        new = [_make(f"N{i:02d}", rating=0, added_days_ago=i + 1) for i in range(10)]
        history = []

        self.assertEqual(_ids(self._open(history)["new_to_flamezo"]), new[:5])
        self.assertEqual(_ids(self._open(history)["new_to_flamezo"]), new[5:])
        self.assertEqual(_ids(self._open(history)["new_to_flamezo"]), new[:5])

    def test_popular_new_nearby_outlets_each_open(self):
        self._fresh_five()
        # Ratings are stored to one decimal, so step by 0.1 to avoid ties.
        near = [_make(f"P{i:02d}", rating=round(4.0 + i * 0.1, 1), km=2, added_days_ago=90) for i in range(10)]
        best_first = list(reversed(near))
        history = []

        first = _ids(self._open(history)["popular"])
        second = _ids(self._open(history)["popular"])
        third = _ids(self._open(history)["popular"])

        self.assertEqual(first, best_first[:5])
        self.assertEqual(second, best_first[5:])
        self.assertCountEqual(third, first)

    def test_all_four_sections_change_between_opens(self):
        for i in range(12):
            _make(f"F{i:02d}", is_featured=1, rating=0, added_days_ago=90)
        for i in range(20):
            _make(f"S{i:02d}", is_signature=1, rating=0, added_days_ago=90)
        for i in range(10):
            _make(f"N{i:02d}", rating=0, added_days_ago=i + 1)
        for i in range(10):
            _make(f"P{i:02d}", rating=4.0, km=2, added_days_ago=90)
        history = []

        first = self._open(history)
        second = self._open(history)

        for key, size in (("limelight", 6), ("signature", 10), ("new_to_flamezo", 5), ("popular", 5)):
            with self.subTest(section=key):
                self.assertEqual(len(first[key]), size)
                self.assertEqual(len(second[key]), size)
                self.assertFalse(set(_ids(first[key])) & set(_ids(second[key])))
        for data in (first, second):
            ids = _all_ids(data)
            self.assertEqual(len(ids), len(set(ids)))

    def test_only_cards_really_seen_are_pushed_back(self):
        # The app reports just the cards that were on screen; loaded-but-
        # unseen ones keep their place at the front next time.
        featured = [_make(f"F{i}", is_featured=1, rating=4.9 - i * 0.1) for i in range(8)]

        first = _ids(_feed()["limelight"])
        second = _ids(_feed(seen=",".join(first[:2]))["limelight"])

        self.assertEqual(first, featured[:6])
        self.assertEqual(second, featured[2:8])
