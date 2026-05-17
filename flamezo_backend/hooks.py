app_name = "flamezo_backend"
app_title = "Flamezo"
app_publisher = "Hetvi Patel"
app_description = "POS and backend for Flamezo"
app_email = "hetvipatel2302@gmail.com"
app_license = "mit"

# CI/CD: Auto-deployment enabled via GitHub Actions
# Last deployment test: 2025-12-24


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
	"Restaurant": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Config": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant User": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_user_permission_query_conditions",
	"Restaurant Table": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Loyalty Config": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Loyalty Entry": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Product": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Category": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Order": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Cart Entry": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
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
	"Referral Link": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"WhatsApp Lead Unlock": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI credit Transaction": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI Image Generation": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Recommendation Interaction": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Co Order Event": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Product Embedding Cache": "flamezo_backend.flamezo.utils.permission_helpers.get_restaurant_permission_query_conditions",
}

has_permission = {
	"Restaurant": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Restaurant Config": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Restaurant User": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Restaurant Table": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Menu Product": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Menu Category": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
	"Order": "flamezo_backend.flamezo.utils.permission_helpers.has_restaurant_permission",
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
	"Order": {
		"before_save": "flamezo_backend.flamezo.api.customers.normalize_order_phone_on_save",
		"after_insert": [
			"flamezo_backend.flamezo.api.customers.update_customer_last_visited",
			"flamezo_backend.flamezo.api.realtime.notify_order_update",
			# Push notification to merchant dashboard (free FCM, background-safe)
			"flamezo_backend.flamezo.api.realtime.notify_new_order_to_merchant",
			# Marketing Studio: fire 'On Order Complete' triggers
			"flamezo_backend.flamezo.tasks.marketing_tasks.fire_order_complete_triggers",
			# POS: push confirmed orders to POS provider (Petpooja, etc.)
			"flamezo_backend.flamezo.pos.utils.handle_order_update",
			# Recommendations: log co-ordered product pairs for co-order matrix
			"flamezo_backend.flamezo.tasks.recommendation_tasks.log_co_order_events",
		],
		"on_update": [
			"flamezo_backend.flamezo.api.realtime.notify_order_update",
			"flamezo_backend.flamezo.utils.loyalty.handle_order_cancellation",
			"flamezo_backend.flamezo.utils.loyalty.handle_loyalty_settlement",
			"flamezo_backend.flamezo.pos.utils.handle_order_update"
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
	"Cart Entry": {
		"after_insert": "flamezo_backend.flamezo.api.realtime.notify_cart_update",
		"on_update": "flamezo_backend.flamezo.api.realtime.notify_cart_update",
		"on_trash": "flamezo_backend.flamezo.api.realtime.notify_cart_update",
	},
	"File": {
		"on_update": "flamezo_backend.flamezo.doctype.home_feature.home_feature.update_home_feature_from_file",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"30 3 * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.generate_daily_seo_blog"
		],
		"59 23 * * *": [  # Run daily at 23:59 for floor recovery and lite renewals
			"flamezo_backend.flamezo.tasks.subscription_tasks.process_daily_subscription_floors",
			"flamezo_backend.flamezo.tasks.subscription_tasks.process_silver_feature_renewals",
		],
		"1 0 * * *": [    # Run daily at 00:01 for plan switches
			"flamezo_backend.flamezo.tasks.subscription_tasks.apply_deferred_plan_changes",
		],
		# Marketing Studio: dispatch scheduled campaigns every 15 minutes
		"*/15 * * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.dispatch_scheduled_campaigns",
		],
		# Marketing Studio: fire event-based triggers every 30 minutes
		"*/30 * * * *": [
			"flamezo_backend.flamezo.tasks.marketing_tasks.fire_triggers",
		],
		# Google Growth: fetch insights daily
        "0 1 * * *": [
            "flamezo_backend.flamezo.api.google_business.fetch_all_restaurant_insights"
        ],
		# Loyalty: grant birthday bonus coins at 08:00 IST daily
		"0 8 * * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.grant_birthday_bonuses"
		],
		# Loyalty: nudge customers whose coins expire within 7 days — 10:00 IST daily
		"0 10 * * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.send_coin_expiry_notifications"
		],
		# Loyalty: reset referral share cycles on 1st of each month at 00:00 UTC
		"0 0 1 * *": [
			"flamezo_backend.flamezo.tasks.loyalty_tasks.reset_referral_cycles_monthly"
		],
		# Recommendations: weekly refresh for all active restaurants (Sunday 02:00)
		"0 2 * * 0": [
			"flamezo_backend.flamezo.tasks.recommendation_tasks.run_weekly_recommendation_refresh"
		],
		# Coupons: auto-activate scheduled + deactivate expired offers daily at 00:05
		"5 0 * * *": [
			"flamezo_backend.flamezo.tasks.coupon_tasks.auto_activate_scheduled_coupons",
			"flamezo_backend.flamezo.tasks.coupon_tasks.auto_deactivate_expired_coupons",
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
