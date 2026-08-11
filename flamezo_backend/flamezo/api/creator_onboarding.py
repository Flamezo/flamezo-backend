"""
Creator Onboarding — Instagram OAuth connect flow, self-serve, no manual
review (creator-program-fundamentals-v1-locked.md Section 1).

Uses "Instagram API with Instagram Login" (real endpoints, current as of
2026) — deliberately NOT the older Facebook-Login-based Graph API, which
requires a linked Facebook Page and adds real signup friction for no
benefit at the eligibility-check stage. `instagram_business_basic` is the
only scope needed here: it's fast to get Meta App Review approval for and
returns everything the follower-floor check needs. The richer scope
(`instagram_business_manage_insights`, needed for Phase 2 scoring and
collab reach/impressions) is a separate, later upgrade — see
creator-weekly-score-algorithm.md Section 6.

Real endpoints used (verify against Meta's current docs before going live
— OAuth providers do rev their APIs):
  Authorize:        GET  https://api.instagram.com/oauth/authorize
  Code -> short token: POST https://api.instagram.com/oauth/access_token
  Short -> long token: GET  https://graph.instagram.com/access_token
  Refresh long token:  GET  https://graph.instagram.com/refresh_access_token
  Profile/followers:   GET  https://graph.instagram.com/me

Credentials read from site_config.json — `instagram_client_id`,
`instagram_client_secret`, `instagram_redirect_uri`. NOT set by this code;
your team registers a real Meta Developer App (Business Verification +
App Review for `instagram_business_basic`) and adds these three values.
Until they're set, `get_instagram_auth_url` throws a clear configuration
error rather than silently returning a broken URL — mirrors
`google_business.py`'s pattern for the exact same situation.
"""

from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

FOLLOWER_ELIGIBILITY_FLOOR = 1500  # creator-program-fundamentals-v1-locked.md Section 1
INSTAGRAM_SCOPE = "instagram_business_basic"

AUTHORIZE_URL = "https://api.instagram.com/oauth/authorize"
SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_TOKEN_URL = "https://graph.instagram.com/access_token"
REFRESH_TOKEN_URL = "https://graph.instagram.com/refresh_access_token"
PROFILE_URL = "https://graph.instagram.com/me"


def _oauth_config():
	client_id = frappe.conf.get("instagram_client_id")
	client_secret = frappe.conf.get("instagram_client_secret")
	redirect_uri = frappe.conf.get("instagram_redirect_uri")
	if not client_id or not client_secret or not redirect_uri:
		frappe.throw(
			_(
				"Instagram OAuth is not configured. Add 'instagram_client_id', "
				"'instagram_client_secret', and 'instagram_redirect_uri' to site_config.json "
				"(requires a Meta Developer App with Business Verification + App Review "
				"for the instagram_business_basic scope)."
			),
			frappe.ValidationError,
		)
	return client_id, client_secret, redirect_uri


def _pending_state_cache_key(state: str) -> str:
	return frappe.cache().make_key(f"creator_onboarding:pending:{state}")


@frappe.whitelist(allow_guest=True)
def get_instagram_auth_url(phone: str) -> dict:
	"""Entry point for "Become a Creator" — returns the URL to redirect the
	user to. `phone` must belong to a verified session (caller enforces —
	same pattern as clubs.py's `_require_session`); a random `state` token
	maps back to that phone in the callback, stored server-side (never
	trust a client-roundtripped phone value in the callback itself)."""
	from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session

	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)

	client_id, _secret, redirect_uri = _oauth_config()

	state = frappe.generate_hash(length=32)
	# 10-minute window to complete the OAuth round trip — generous for a
	# real user, short enough that a leaked/stale state can't be replayed
	# much later.
	frappe.cache().set_value(_pending_state_cache_key(state), phone, expires_in_sec=600)

	params = {
		"client_id": client_id,
		"redirect_uri": redirect_uri,
		"scope": INSTAGRAM_SCOPE,
		"response_type": "code",
		"state": state,
	}
	return {"auth_url": f"{AUTHORIZE_URL}?{urlencode(params)}"}


@frappe.whitelist(allow_guest=True)
def instagram_callback(code: str, state: str) -> dict:
	"""
	OAuth callback — exchanges the code for tokens, pulls follower count,
	and makes the instant approve/reject decision. No human in this path
	at any point (Section 1 of the fundamentals doc).
	"""
	phone = frappe.cache().get_value(_pending_state_cache_key(state))
	if not phone:
		frappe.throw(_("This connection link has expired. Please try again."), frappe.ValidationError)
	frappe.cache().delete_value(_pending_state_cache_key(state))

	client_id, client_secret, redirect_uri = _oauth_config()

	short_token, ig_user_id = _exchange_code_for_short_token(code, client_id, client_secret, redirect_uri)
	long_token, expires_in_seconds = _exchange_for_long_lived_token(short_token, client_secret)
	profile = _fetch_profile(long_token)

	return _apply_connection_result(phone, ig_user_id, long_token, expires_in_seconds, profile)


def _exchange_code_for_short_token(code, client_id, client_secret, redirect_uri):
	response = requests.post(
		SHORT_TOKEN_URL,
		data={
			"client_id": client_id,
			"client_secret": client_secret,
			"grant_type": "authorization_code",
			"redirect_uri": redirect_uri,
			"code": code,
		},
	)
	if response.status_code != 200:
		frappe.log_error(f"Instagram short-token exchange failed: {response.text}", "Creator Onboarding")
		frappe.throw(_("Couldn't connect to Instagram. Please try again."), frappe.ValidationError)
	data = response.json()
	return data["access_token"], data["user_id"]


def _exchange_for_long_lived_token(short_token, client_secret):
	response = requests.get(
		LONG_TOKEN_URL,
		params={"grant_type": "ig_exchange_token", "client_secret": client_secret, "access_token": short_token},
	)
	if response.status_code != 200:
		frappe.log_error(f"Instagram long-token exchange failed: {response.text}", "Creator Onboarding")
		frappe.throw(_("Couldn't complete the Instagram connection. Please try again."), frappe.ValidationError)
	data = response.json()
	return data["access_token"], data.get("expires_in", 60 * 24 * 60 * 60)  # default 60 days in seconds


def _fetch_profile(access_token):
	response = requests.get(
		PROFILE_URL,
		params={"fields": "user_id,username,followers_count,account_type", "access_token": access_token},
	)
	if response.status_code != 200:
		frappe.log_error(f"Instagram profile fetch failed: {response.text}", "Creator Onboarding")
		frappe.throw(_("Couldn't read your Instagram profile. Please try again."), frappe.ValidationError)
	return response.json()


def _apply_connection_result(phone, ig_user_id, long_token, expires_in_seconds, profile):
	"""The actual instant decision — separated from the HTTP calls above
	so it's independently testable with a fake profile dict, no network
	needed."""
	followers = cint(profile.get("followers_count"))
	username = profile.get("username") or ""
	expires_at = add_to_date(now_datetime(), seconds=cint(expires_in_seconds))

	creator_name = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
	if creator_name:
		creator = frappe.get_doc("Flamezo Creator", creator_name)
	else:
		creator = frappe.new_doc("Flamezo Creator")
		creator.customer_phone = phone

	creator.instagram_handle = username
	creator.meta_user_id = str(ig_user_id)
	creator.meta_followers = followers
	creator.oauth_token = long_token
	creator.oauth_token_expires = expires_at
	creator.follower_count_last_synced = now_datetime()

	approved = followers >= FOLLOWER_ELIGIBILITY_FLOOR
	creator.status = "approved" if approved else "rejected"

	creator.save(ignore_permissions=True)
	frappe.db.commit()

	if approved:
		return {
			"success": True,
			"approved": True,
			"creator_id": creator.name,
			"followers": followers,
			"message": "You're approved! You can create your Club now.",
		}
	return {
		"success": True,
		"approved": False,
		"creator_id": creator.name,
		"followers": followers,
		"message": (
			f"You need at least {FOLLOWER_ELIGIBILITY_FLOOR} followers to join right now "
			f"(you have {followers}). Reconnect anytime once you've crossed that — we check live, no waiting."
		),
	}


def get_valid_access_token(creator_name: str):
	"""Returns a usable access token for this creator, refreshing it first
	if it's old enough to need it (Instagram allows refresh after 24h,
	tokens are valid 60 days) — used by the monthly follower-refresh job
	and anything else that needs to call the Graph API on this creator's
	behalf. Returns None if never connected or the token is unrecoverably
	expired (caller should treat that as "reconnect needed", matching
	Section 6 of the fundamentals doc)."""
	creator = frappe.db.get_value(
		"Flamezo Creator", creator_name, ["oauth_token", "oauth_token_expires"], as_dict=True
	)
	if not creator or not creator.oauth_token:
		return None

	token = creator.oauth_token  # Password fields decrypt automatically on ORM read
	if not creator.oauth_token_expires:
		return token

	expires_at = frappe.utils.get_datetime(creator.oauth_token_expires)
	now = now_datetime()
	if expires_at <= now:
		return None  # unrecoverably expired — needs a fresh OAuth connect, not a refresh

	# Refresh proactively once within 7 days of expiry, so a slow-moving
	# monthly job never hands back a token that expires mid-use.
	if (expires_at - now).days <= 7:
		return _refresh_token(creator_name, token)
	return token


def monthly_follower_refresh():
	"""
	Scheduled job (register in hooks.py, monthly) — creator-program-
	fundamentals-v1-locked.md Section 6. For every connected creator:
	re-pull their real follower count, flag (not instantly cut off) any
	who've dropped below the eligibility floor, and pause posting/reward
	for anyone whose token has lapsed past recovery. No human review in
	the normal path — flagging just means the monthly-refresh receipt
	notes it, doesn't reject/suspend automatically on a single dip.
	"""
	creators = frappe.db.get_all(
		"Flamezo Creator",
		filters={"status": "approved"},
		fields=["name", "meta_followers"],
	)

	refreshed, lapsed, below_floor = 0, 0, 0
	for creator in creators:
		token = get_valid_access_token(creator.name)
		if not token:
			# Token unrecoverably expired (or never connected) — pause
			# posting rights + weekly reward eligibility until they
			# reconnect. Club stays active either way (Section 6).
			frappe.db.set_value("Flamezo Creator", creator.name, "status", "suspended")
			lapsed += 1
			continue

		try:
			profile = _fetch_profile(token)
		except Exception:
			# A transient API failure shouldn't suspend a real creator —
			# skip this cycle, try again next month.
			frappe.log_error(f"monthly_follower_refresh: profile fetch failed for {creator.name}", "Creator Onboarding")
			continue

		followers = cint(profile.get("followers_count"))
		frappe.db.set_value("Flamezo Creator", creator.name, {
			"meta_followers": followers,
			"follower_count_last_synced": now_datetime(),
		})
		refreshed += 1
		if followers < FOLLOWER_ELIGIBILITY_FLOOR:
			below_floor += 1

	frappe.db.commit()
	frappe.logger().info(
		f"[creator_onboarding] monthly follower refresh: {refreshed} refreshed, "
		f"{lapsed} suspended (token lapsed), {below_floor} now below the eligibility floor"
	)
	return {"refreshed": refreshed, "lapsed": lapsed, "below_floor": below_floor}


def _refresh_token(creator_name, current_token):
	response = requests.get(REFRESH_TOKEN_URL, params={"grant_type": "ig_refresh_token", "access_token": current_token})
	if response.status_code != 200:
		frappe.log_error(f"Instagram token refresh failed for {creator_name}: {response.text}", "Creator Onboarding")
		return current_token  # fall back to the still-valid-for-now token rather than failing the caller

	data = response.json()
	new_token = data["access_token"]
	expires_at = add_to_date(now_datetime(), seconds=cint(data.get("expires_in", 60 * 24 * 60 * 60)))
	frappe.db.set_value("Flamezo Creator", creator_name, {
		"oauth_token": new_token,
		"oauth_token_expires": expires_at,
	})
	frappe.db.commit()
	return new_token
