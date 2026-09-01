app_name = "flamezo_backend"
app_title = "Flamezo"
app_publisher = "Hetvi Patel"
app_description = "POS and backend for Flamezo"
app_email = "hetvipatel2302@gmail.com"
app_license = "mit"

# CI/CD: Auto-deployment enabled via GitHub Actions
# Last deployment test: 2025-12-24
# Migrated to AWS Lightsail (Mumbai) - 2026-08-20, CI/CD push-trigger test


# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "flamezo_backend",
# 		"logo": "/assets/flamezo_backend/logo.png",
# 		"title": "Flamezo",
# 		"route": "/flamezo_backend",
# 		"has_permission": "flamezo_backend.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/flamezo_backend/css/flamezo_backend.css"
# app_include_js = "/assets/flamezo_backend/js/flamezo_backend.js"

# include js, css files in header of web template
# web_include_css = "/assets/flamezo_backend/css/flamezo_backend.css"
# web_include_js = "/assets/flamezo_backend/js/flamezo_backend.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "flamezo_backend/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "flamezo_backend/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "flamezo_backend.utils.jinja_methods",
# 	"filters": "flamezo_backend.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "flamezo_backend.install.before_install"
# after_install = "flamezo_backend.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "flamezo_backend.uninstall.before_uninstall"
# after_uninstall = "flamezo_backend.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "flamezo_backend.utils.before_app_install"
# after_app_install = "flamezo_backend.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "flamezo_backend.utils.before_app_uninstall"
# after_app_uninstall = "flamezo_backend.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "flamezo_backend.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Outlet": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Outlet Config": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Outlet User": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_user_permission_query_conditions",
	"Outlet Table": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Outlet Loyalty Config": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Outlet Loyalty Entry": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Product": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Category": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",

	"Coupon": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Offer": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Event": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Game": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Table Booking": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Banquet Booking": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Home Feature": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Legacy Content": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Image Extractor": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Customer": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Boost Campaign": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Boost Prerequisite Check": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Boost Coupon Redemption": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Campaign": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Trigger": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Segment": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Event": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Analytics Event": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Coin Transaction": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Monthly Billing Ledger": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Monthly Revenue Ledger": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Plan Change Log": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Media Asset": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Media Upload Session": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Coupon Usage": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"UGC Cashback Config": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"UGC Story Submission": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Catalogue Category": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Catalogue Item": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Service Appointment": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Court": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Court Booking": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Referral Link": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"WhatsApp Lead Unlock": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI credit Transaction": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI Image Generation": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Recommendation Interaction": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",

	"Menu Product Embedding Cache": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Offer Claim": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",

	# Chills / Clubs / Crowd — public consumer doctypes
	"Flamezo Creator": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Chills Reel": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Creator Club": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Creator Club Post": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Crowd Request": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
}

has_permission = {
	"Outlet": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Outlet Config": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Outlet User": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Outlet Table": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Menu Product": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Menu Category": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",

	"Customer": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Marketing Campaign": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Monthly Billing Ledger": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	# All other restaurant-specific doctypes use the base restaurant check
	"Banquet Booking": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Table Booking": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Coupon": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Offer": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Event": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Game": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Home Feature": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Legacy Content": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"AI Image Generation": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Customer": {
		"before_save": "flamezo_backend.flamezo.api.customers.normalize_customer_phone_on_save",
	},

	# Setup Wizard writes logo/tagline/etc. to the Restaurant Onboarding record;
	# push those display fields to the live Restaurant (+ Config) on every save so
	# the logo shows up in the Branding pool / feed / app without a manual sync.
	"Outlet Onboarding": {
		"on_update": "flamezo_backend.flamezo.api.onboarding.auto_sync_onboarding_display",
	},

	# New/reactivated outlets get their Google Places photos + details
	# (rating, review count, price level, hours, facility attributes) fetched
	# automatically — no manual "sync" step needed for merchants onboarding
	# from here on.
	"Outlet": {
		"on_update": [
			"flamezo_backend.flamezo.api.google_places_photos.auto_sync_google_photos_on_activation",
			"flamezo_backend.flamezo.api.google_places_photos.auto_sync_google_details_on_activation",
		],
	},

	"Table Booking": {
		"after_insert": "flamezo_backend.flamezo.api.customers.update_customer_last_visited",
	},
	"Banquet Booking": {
		"after_insert": "flamezo_backend.flamezo.api.customers.update_customer_last_visited",
	},
	"Menu Product": {
		"on_update": [
			"flamezo_backend.flamezo.api.products.invalidate_product_cache",
			"flamezo_backend.flamezo.api.realtime.notify_product_update",
			"flamezo_backend.flamezo.api.google_business.handle_product_update"
		],
	},

	"Menu Category": {
		"on_update": "flamezo_backend.flamezo.api.categories.invalidate_category_cache",
		"after_insert": "flamezo_backend.flamezo.api.categories.invalidate_category_cache",
		"on_trash": "flamezo_backend.flamezo.api.categories.invalidate_category_cache",
	},


	# Media R2 cleanup — when a media-owning doc is trashed, delete its Media
	# Assets and their Cloudflare objects so storage never accumulates orphans.
	# (Menu Product / Menu Category / Menu Image Extractor / UGC Story Submission
	#  already handle their own media in dedicated controllers.)
	"Offer": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Event": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Outlet Config": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Home Feature": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"AI Image Generation": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Legacy Content": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Legacy Member": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Legacy Testimonial": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Legacy Gallery Image": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"Legacy Testimonial Image": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
	"UGC Cashback Config": {"on_trash": "flamezo_backend.flamezo.media.cleanup.cleanup_media_for_owner"},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"30 3 * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.generate_daily_seo_blog",
			# Cash commission engine — drain wallet balance into outstanding
			# ledger entries (03:30 IST, after overnight wallet top-ups settle).
			"flamezo_backend.flamezo.tasks.commission_tasks.retry_wallet_settlements",
			"flamezo_backend.flamezo.tasks.commission_tasks.clear_expired_throttles",
			# Events — once a day, deactivate events whose date/time is over
			# (they drop off the app feed and to the bottom of the list).
			"flamezo_backend.flamezo.api.events.deactivate_past_events",
			# Account deletion — hard-anonymise soft-deleted customers past the
			# 30-day recovery window.
			"flamezo_backend.flamezo.api.otp.purge_deleted_customers",
		],
		# The 23:59 floor-recovery cron was retired when the ₹399 monthly floor
		# was removed from the model. `process_daily_subscription_floors` and
		# `process_legacy_feature_renewals` are now no-ops (kept importable);
		# no monthly minimum / floor is ever charged.
		# Marketing Studio: dispatch scheduled campaigns every 15 minutes
		"*/15 * * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.dispatch_scheduled_campaigns",
			# Chills: recompute Bayesian engagement + social percentile scores
			"flamezo_backend.flamezo.api.chills_feed.recompute_global_scores",
		],
		# Marketing Studio: fire event-based triggers every 30 minutes
		"*/30 * * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.fire_triggers",
			# UGC Cashback — stall recovery: re-enqueue AI verifier for
			# proof_submitted submissions stuck >30 min (capped at 3 retries).
			"flamezo_backend.flamezo.tasks.ugc_tasks.retry_stalled_submissions",
			# Boost — sync Meta campaign performance metrics.
			"flamezo_backend.flamezo.tasks.boost_tasks.sync_boost_performance",
			# Crowd — close Team Ups whose expires_at has passed.
			"flamezo_backend.flamezo.api.crowd.close_expired_crowd_requests",
		],
		# Chills: decay preference scores + persist Redis state to DB
		"0 2 * * *": [
			"flamezo_backend.flamezo.api.chills_feed.sync_preferences_to_db",
		],
		# Google Growth: fetch insights daily
        "0 1 * * *": [
            "flamezo_backend.flamezo.api.google_business.fetch_all_outlet_insights"
        ],
		# Loyalty: grant birthday bonus coins at 08:00 IST daily
		"0 8 * * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.grant_birthday_bonuses"
		],
		# Loyalty: nudge customers whose coins expire within 7 days — 10:00 IST daily
		"0 10 * * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.send_coin_expiry_notifications"
		],
		# Loyalty: reset referral share cycles on 1st of each month at 00:00 IST (18:30 UTC on last day)
		"30 18 28-31 * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.reset_referral_cycles_monthly"
		],
		# Hot Drops: proactive merchant nudge ~2h before real meal-time rush
		# windows — dining/cafe outlets with no active/upcoming Hot Drop and a
		# registered push token get a "post one now" push. 10:30 IST (lunch
		# rush ~12:30) and 17:30 IST (dinner rush ~19:30).
		"30 10 * * *": [
			"flamezo_backend.flamezo.tasks.hot_drops_tasks.nudge_before_lunch_rush"
		],
		"30 17 * * *": [
			"flamezo_backend.flamezo.tasks.hot_drops_tasks.nudge_before_dinner_rush"
		],
		# Recommendations: weekly refresh for all active restaurants (Sunday 02:00)
		"0 2 * * 0": [
			"flamezo_backend.flamezo.tasks.recommendation_tasks.run_weekly_recommendation_refresh"
		],
		# Google Places photo sync — catch-all for any active outlet that
		# slipped past the on-activation hook (bulk import, direct DB flip).
		# Bounded batch per run; see google_places_photos.backfill_missing_google_photos.
		"0 4 * * 0": [
			"flamezo_backend.flamezo.api.google_places_photos.backfill_missing_google_photos"
		],
		# Creator Program — weekly score/payout run, Mondays 03:00 IST (before
		# the 03:45 commission autopay sweep). See creator-weekly-score-
		# algorithm.md and utils/creator_score_engine.py.
		"0 3 * * 1": [
			"flamezo_backend.flamezo.utils.creator_score_engine.run_weekly_payout",
		],
		# Creator Program — monthly follower refresh, 1st of month 05:00 IST.
		# creator-program-fundamentals-v1-locked.md Section 6.
		"0 5 1 * *": [
			"flamezo_backend.flamezo.api.creator_onboarding.monthly_follower_refresh",
		],
		# Creator Program — daily follower-count snapshot (in-app + last-synced
		# Instagram value) that feeds the creator-facing insights trend chart.
		# NOTE: "0 2 * * *" is already used above (chills_feed.sync_preferences_to_db)
		# — a duplicate dict key here would silently drop that entry, so this
		# gets its own distinct slot instead of merging into it.
		"0 6 * * *": [
			"flamezo_backend.flamezo.api.creator_analytics.daily_follower_snapshot",
		],
		# Menu extraction self-heal: sweep docs stuck in 'Processing' for >5min
		# (worker restart / transient failures) and re-aggregate or mark Failed.
		"*/5 * * * *": [
			"flamezo_backend.flamezo.tasks.extraction_recovery.recover_stuck_extractions",
			# Chills: refresh candidate pool + new content + trending caches
			"flamezo_backend.flamezo.api.chills_feed.refresh_candidates_snapshot",
			# Redis-buffered counters (likes/saves/views/shares) — reads are
			# already immediately consistent via Redis; this just keeps the
			# durable MySQL columns in sync for reporting/backups.
			"flamezo_backend.flamezo.utils.redis_counters.flush_all",
			"flamezo_backend.flamezo.tasks.ugc_tasks.dispatch_ugc_cashback_nudges",
			# Boost — self-heal campaigns whose Meta launch job never ran
			# (worker restart / queue drop), capped at 3 retries then Failed + alert.
			"flamezo_backend.flamezo.tasks.boost_tasks.recover_stuck_boost_launches",
		],
		# Cash commission engine — Tier 2 weekly autopay sweep: Mondays
		# 03:45 IST charges any leftover balance via mandate.
		"45 3 * * 1": [
			"flamezo_backend.flamezo.tasks.commission_tasks.weekly_autopay_sweep",
		],
		# Boost — daily health check at 9 AM: alert if guarantee at risk
		"0 9 * * *": [
			"flamezo_backend.flamezo.tasks.boost_tasks.check_boost_campaigns_health",
		],
		# Midnight: finalize expired boost campaigns + reconcile Razorpay KYC
		"0 0 * * *": [
			"flamezo_backend.flamezo.tasks.boost_tasks.finalize_completed_boosts",
			"flamezo_backend.flamezo.api.commission.reconcile_all_pending_kyc",
		],
		# UGC Cashback — hourly: send proof-upload reminders (max 2) and expire
		# claims whose proof window has elapsed.
		# Boost — hourly: WhatsApp reminder ~2hrs before a Boost-linked table
		# reservation, to cut no-shows on guaranteed-visit bookings.
		"15 * * * *": [
			"flamezo_backend.flamezo.tasks.ugc_tasks.send_proof_reminders",
			"flamezo_backend.flamezo.tasks.boost_tasks.send_boost_booking_reminders",
		],
		# UGC Cashback — daily 04:00: purge proof videos older than the retention
		# window (privacy + storage), keeping the submission record for audit.
		# Crowd — delete chat messages for completed/cancelled requests > 30 days old.
		# DPDP Act 2023 — purge OTP Verification Logs older than 90 days.
		"0 4 * * *": [
			"flamezo_backend.flamezo.tasks.ugc_tasks.purge_old_proof_videos",
			"flamezo_backend.flamezo.api.crowd.expire_old_chat_messages",
			"flamezo_backend.flamezo.tasks.privacy_tasks.purge_old_otp_logs",
		],
	}
}

extend_bootinfo = "flamezo_backend.flamezo.utils.boot_helpers.extend_bootinfo"



# Testing
# -------

# before_tests = "flamezo_backend.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "flamezo_backend.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "flamezo_backend.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# CORS Configuration for Frontend Access
before_request = [
    "flamezo_backend.flamezo.utils.cors_helpers.handle_cors_preflight",
    "flamezo_backend.flamezo.utils.auth_hooks.restrict_merchant_desk_access"
]
after_request = ["flamezo_backend.flamezo.utils.cors_helpers.add_cors_headers"]

# Job Events
# ----------
# before_job = ["flamezo_backend.utils.before_job"]
# after_job = ["flamezo_backend.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"flamezo_backend.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Website Route Rules
# -------------------
# URL routing for flamezo_backend UI (similar to Mint)
# Using a catch-all that avoids interfering with system paths
website_route_rules = [
    {"from_route": "/flamezo_backend/<path:app_path>", "to_route": "flamezo_backend"}
]

# Redirect root to flamezo_backend so unauthenticated users land on flamezo_backend login
# (ProtectedRoute then redirects to /flamezo_backend/login)
website_redirects = [
    {"source": "/", "target": "/flamezo_backend"},
    {"source": "/forgot-password", "target": "/flamezo_backend/forgot-password"},
    {"source": "/update-password", "target": "/flamezo_backend/reset-password"}

]


fixtures = [{"dt": "Custom Field", "filters": [["module", "=", "Flamezo"]]}]
