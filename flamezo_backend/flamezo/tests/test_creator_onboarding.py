# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for api/creator_onboarding.py. HTTP calls to Instagram's real
endpoints are mocked throughout (no live Meta app exists yet) — what's
under test is the connect/callback/approve-reject FLOW LOGIC, the
config-missing guard, and the token-refresh decision logic, not whether
Meta's servers respond a certain way.
"""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_to_date, now_datetime

from flamezo_backend.flamezo.api import creator_onboarding as onboarding

_PHONE = "9300000601"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


@contextmanager
def _with_conf(values: dict):
	"""frappe.conf is a werkzeug LocalProxy over a dict-like `_dict` — it
	doesn't support `patch.object(frappe.conf, "get", ...)` (no real
	`__dict__` entry for a proxy to patch), so this mutates the underlying
	dict directly and restores it afterward instead."""
	saved = {k: frappe.conf.get(k) for k in values}
	try:
		frappe.conf.update(values)
		yield
	finally:
		for k, v in saved.items():
			if v is None:
				frappe.conf.pop(k, None)
			else:
				frappe.conf[k] = v


@contextmanager
def _without_conf(*keys):
	"""Ensures the given config keys are absent for the duration — used by
	the missing-config guard test."""
	saved = {k: frappe.conf.get(k) for k in keys}
	try:
		for k in keys:
			frappe.conf.pop(k, None)
		yield
	finally:
		for k, v in saved.items():
			if v is not None:
				frappe.conf[k] = v


class TestOAuthConfigGuard(unittest.TestCase):
	def test_missing_config_throws_clear_error(self):
		with _without_conf("instagram_client_id", "instagram_client_secret", "instagram_redirect_uri"):
			with self.assertRaises(frappe.exceptions.ValidationError):
				onboarding._oauth_config()


class TestGetInstagramAuthUrl(unittest.TestCase):
	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	def test_requires_verified_session(self):
		with patch(
			"flamezo_backend.flamezo.utils.customer_helpers.has_active_customer_session",
			return_value=False,
		):
			with self.assertRaises(frappe.exceptions.AuthenticationError):
				onboarding.get_instagram_auth_url(_PHONE)

	def test_returns_real_authorize_url_with_state(self):
		fake_conf = {
			"instagram_client_id": "test_client_id",
			"instagram_client_secret": "test_secret",
			"instagram_redirect_uri": "https://flamezo.in/callback",
		}
		with patch(
			"flamezo_backend.flamezo.utils.customer_helpers.has_active_customer_session",
			return_value=True,
		), _with_conf(fake_conf):
			result = onboarding.get_instagram_auth_url(_PHONE)
		self.assertIn(onboarding.AUTHORIZE_URL, result["auth_url"])
		self.assertIn("client_id=test_client_id", result["auth_url"])
		self.assertIn("state=", result["auth_url"])
		self.assertIn(f"scope={onboarding.INSTAGRAM_SCOPE}", result["auth_url"])


class TestApplyConnectionResult(unittest.TestCase):
	"""The actual approve/reject decision — pure enough to test directly
	with a fake profile dict, no HTTP involved."""

	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	def test_above_floor_auto_approved(self):
		profile = {"followers_count": 5000, "username": "bigcreator"}
		result = onboarding._apply_connection_result(_PHONE, "IG123", "tok_abc", 5184000, profile)
		self.assertTrue(result["approved"])
		creator = frappe.get_doc("Flamezo Creator", result["creator_id"])
		self.assertEqual(creator.status, "approved")
		self.assertEqual(creator.meta_followers, 5000)
		self.assertEqual(creator.instagram_handle, "bigcreator")

	def test_below_floor_auto_rejected(self):
		profile = {"followers_count": 400, "username": "smallcreator"}
		result = onboarding._apply_connection_result(_PHONE, "IG124", "tok_def", 5184000, profile)
		self.assertFalse(result["approved"])
		creator = frappe.get_doc("Flamezo Creator", result["creator_id"])
		self.assertEqual(creator.status, "rejected")
		self.assertIn(str(onboarding.FOLLOWER_ELIGIBILITY_FLOOR), result["message"])

	def test_exactly_at_floor_approved(self):
		profile = {"followers_count": onboarding.FOLLOWER_ELIGIBILITY_FLOOR, "username": "edgecase"}
		result = onboarding._apply_connection_result(_PHONE, "IG125", "tok_ghi", 5184000, profile)
		self.assertTrue(result["approved"])

	def test_reconnect_re_evaluates_live_not_cached(self):
		"""A previously-rejected creator crossing the floor later should
		auto-approve on reconnect — no queue, no waiting, matches the
		're-checked live on every reconnect' promise in the fundamentals
		doc."""
		onboarding._apply_connection_result(_PHONE, "IG126", "tok1", 5184000, {"followers_count": 500, "username": "x"})
		result = onboarding._apply_connection_result(_PHONE, "IG126", "tok2", 5184000, {"followers_count": 3000, "username": "x"})
		self.assertTrue(result["approved"])
		creator = frappe.get_doc("Flamezo Creator", result["creator_id"])
		self.assertEqual(creator.status, "approved")
		self.assertEqual(creator.meta_followers, 3000)

	def test_stores_long_lived_token_and_expiry(self):
		before = now_datetime()
		result = onboarding._apply_connection_result(_PHONE, "IG127", "secret_tok", 5184000, {"followers_count": 2000, "username": "y"})
		creator = frappe.get_doc("Flamezo Creator", result["creator_id"])
		self.assertEqual(creator.get_password("oauth_token"), "secret_tok")
		self.assertIsNotNone(creator.oauth_token_expires)
		self.assertGreater(frappe.utils.get_datetime(creator.oauth_token_expires), before)


class TestInstagramCallback(unittest.TestCase):
	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	def test_unknown_state_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			onboarding.instagram_callback("some_code", "nonexistent_state_token")

	def test_full_flow_with_mocked_http(self):
		state = "test_state_123"
		frappe.cache().set_value(onboarding._pending_state_cache_key(state), _PHONE, expires_in_sec=600)

		fake_conf = {
			"instagram_client_id": "cid",
			"instagram_client_secret": "csecret",
			"instagram_redirect_uri": "https://flamezo.in/cb",
		}

		short_resp = MagicMock(status_code=200)
		short_resp.json.return_value = {"access_token": "short_tok", "user_id": "998877"}

		long_resp = MagicMock(status_code=200)
		long_resp.json.return_value = {"access_token": "long_tok", "expires_in": 5184000}

		profile_resp = MagicMock(status_code=200)
		profile_resp.json.return_value = {"followers_count": 9000, "username": "mockcreator"}

		with _with_conf(fake_conf), \
			patch("flamezo_backend.flamezo.api.creator_onboarding.requests.post", return_value=short_resp), \
			patch(
				"flamezo_backend.flamezo.api.creator_onboarding.requests.get",
				side_effect=[long_resp, profile_resp],
			):
			result = onboarding.instagram_callback("auth_code_xyz", state)

		self.assertTrue(result["approved"])
		self.assertEqual(result["followers"], 9000)
		# state is single-use — replaying it should now fail
		with self.assertRaises(frappe.exceptions.ValidationError):
			onboarding.instagram_callback("auth_code_xyz", state)

	def test_short_token_exchange_failure_throws_friendly_error(self):
		state = "test_state_fail"
		frappe.cache().set_value(onboarding._pending_state_cache_key(state), _PHONE, expires_in_sec=600)
		fake_conf = {
			"instagram_client_id": "cid", "instagram_client_secret": "csecret", "instagram_redirect_uri": "https://x/cb",
		}
		bad_resp = MagicMock(status_code=400, text="invalid_grant")
		with _with_conf(fake_conf), \
			patch("flamezo_backend.flamezo.api.creator_onboarding.requests.post", return_value=bad_resp):
			with self.assertRaises(frappe.exceptions.ValidationError):
				onboarding.instagram_callback("bad_code", state)


class TestUnwrapIgResponse(unittest.TestCase):
	"""Meta's own live docs render the short-token-exchange and /me example
	responses inconsistently — flat in some places, nested under
	`data: [{...}]` in others (verified ambiguous Aug 2026, both against a
	live doc fetch). _unwrap_ig_response must handle both without the caller
	having to guess which shape a given response actually is."""

	def test_flat_shape_passed_through_unchanged(self):
		flat = {"access_token": "tok", "user_id": "123"}
		self.assertEqual(onboarding._unwrap_ig_response(flat), flat)

	def test_nested_data_array_shape_unwrapped(self):
		nested = {"data": [{"access_token": "tok", "user_id": "123", "permissions": "instagram_business_basic"}]}
		self.assertEqual(
			onboarding._unwrap_ig_response(nested),
			{"access_token": "tok", "user_id": "123", "permissions": "instagram_business_basic"},
		)

	def test_empty_data_array_falls_back_to_original(self):
		# An empty `data: []` isn't a valid unwrap target — pass the original
		# dict through so the caller's own "field missing" check catches it
		# with a clear error, rather than this silently returning {}.
		empty = {"data": []}
		self.assertEqual(onboarding._unwrap_ig_response(empty), empty)

	def test_non_dict_input_passed_through(self):
		self.assertEqual(onboarding._unwrap_ig_response("not a dict"), "not a dict")


class TestExchangeCodeForShortToken(unittest.TestCase):
	def test_flat_response_shape(self):
		resp = MagicMock(status_code=200)
		resp.json.return_value = {"access_token": "short_tok", "user_id": "998877"}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.post", return_value=resp):
			token, user_id = onboarding._exchange_code_for_short_token("code", "cid", "secret", "https://x/cb")
		self.assertEqual(token, "short_tok")
		self.assertEqual(user_id, "998877")

	def test_nested_data_array_response_shape(self):
		resp = MagicMock(status_code=200)
		resp.json.return_value = {"data": [{"access_token": "short_tok", "user_id": "998877"}]}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.post", return_value=resp):
			token, user_id = onboarding._exchange_code_for_short_token("code", "cid", "secret", "https://x/cb")
		self.assertEqual(token, "short_tok")
		self.assertEqual(user_id, "998877")

	def test_unrecognized_shape_throws_friendly_error_not_keyerror(self):
		resp = MagicMock(status_code=200, text='{"unexpected": "shape"}')
		resp.json.return_value = {"unexpected": "shape"}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.post", return_value=resp):
			with self.assertRaises(frappe.exceptions.ValidationError):
				onboarding._exchange_code_for_short_token("code", "cid", "secret", "https://x/cb")


class TestFetchProfile(unittest.TestCase):
	def test_flat_response_shape(self):
		resp = MagicMock(status_code=200)
		resp.json.return_value = {"followers_count": 9000, "username": "mockcreator"}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.get", return_value=resp):
			profile = onboarding._fetch_profile("tok")
		self.assertEqual(profile["followers_count"], 9000)

	def test_nested_data_array_response_shape(self):
		resp = MagicMock(status_code=200)
		resp.json.return_value = {"data": [{"followers_count": 9000, "username": "mockcreator"}]}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.get", return_value=resp):
			profile = onboarding._fetch_profile("tok")
		self.assertEqual(profile["followers_count"], 9000)


class TestGetValidAccessToken(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "TokenTestCreator",
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)

	def tearDown(self):
		_cleanup()

	def test_never_connected_returns_none(self):
		self.assertIsNone(onboarding.get_valid_access_token(self.creator.name))

	def test_valid_far_from_expiry_returned_as_is(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"oauth_token": "still_good",
			"oauth_token_expires": add_to_date(now_datetime(), days=45),
		})
		self.assertEqual(onboarding.get_valid_access_token(self.creator.name), "still_good")

	def test_expired_returns_none(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"oauth_token": "stale",
			"oauth_token_expires": add_to_date(now_datetime(), days=-1),
		})
		self.assertIsNone(onboarding.get_valid_access_token(self.creator.name))

	def test_near_expiry_triggers_refresh(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"oauth_token": "about_to_expire",
			"oauth_token_expires": add_to_date(now_datetime(), days=3),
		})
		refresh_resp = MagicMock(status_code=200)
		refresh_resp.json.return_value = {"access_token": "refreshed_tok", "expires_in": 5184000}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.get", return_value=refresh_resp):
			token = onboarding.get_valid_access_token(self.creator.name)
		self.assertEqual(token, "refreshed_tok")


class TestMonthlyFollowerRefresh(unittest.TestCase):
	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	def test_lapsed_token_gets_suspended(self):
		creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "LapsedCreator",
			"status": "approved",
			"oauth_token": "expired_tok",
			"oauth_token_expires": add_to_date(now_datetime(), days=-5),
		})
		creator.insert(ignore_permissions=True)

		onboarding.monthly_follower_refresh()

		self.assertEqual(frappe.db.get_value("Flamezo Creator", creator.name, "status"), "suspended")

	def test_refreshed_follower_count_updates(self):
		creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "RefreshCreator",
			"status": "approved",
			"meta_followers": 1000,
			"oauth_token": "good_tok",
			"oauth_token_expires": add_to_date(now_datetime(), days=45),
		})
		creator.insert(ignore_permissions=True)

		profile_resp = MagicMock(status_code=200)
		profile_resp.json.return_value = {"followers_count": 1800}
		with patch("flamezo_backend.flamezo.api.creator_onboarding.requests.get", return_value=profile_resp):
			result = onboarding.monthly_follower_refresh()

		self.assertEqual(frappe.db.get_value("Flamezo Creator", creator.name, "meta_followers"), 1800)
		self.assertEqual(result["refreshed"], 1)
