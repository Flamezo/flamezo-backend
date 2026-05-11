app_name = "dinematters"
app_title = "Dinematters"
app_publisher = "Hetvi Patel"
app_description = "POS and backend for Dinematters"
app_email = "hetvipatel2302@gmail.com"
app_license = "mit"

# CI/CD: Auto-deployment enabled via GitHub Actions
# Last deployment test: 2025-12-24


# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "dinematters",
# 		"logo": "/assets/dinematters/logo.png",
# 		"title": "Dinematters",
# 		"route": "/dinematters",
# 		"has_permission": "dinematters.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/dinematters/css/dinematters.css"
# app_include_js = "/assets/dinematters/js/dinematters.js"

# include js, css files in header of web template
# web_include_css = "/assets/dinematters/css/dinematters.css"
# web_include_js = "/assets/dinematters/js/dinematters.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "dinematters/public/scss/website"

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
# app_include_icons = "dinematters/public/icons.svg"

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
# 	"methods": "dinematters.utils.jinja_methods",
# 	"filters": "dinematters.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "dinematters.install.before_install"
# after_install = "dinematters.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "dinematters.uninstall.before_uninstall"
# after_uninstall = "dinematters.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "dinematters.utils.before_app_install"
# after_app_install = "dinematters.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "dinematters.utils.before_app_uninstall"
# after_app_uninstall = "dinematters.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "dinematters.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Restaurant": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Config": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant User": "dinematters.dinematters.utils.permission_helpers.get_restaurant_user_permission_query_conditions",
	"Restaurant Table": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Loyalty Config": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Restaurant Loyalty Entry": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Product": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Category": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Order": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Cart Entry": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Coupon": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Offer": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Event": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Game": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Table Booking": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Banquet Booking": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Home Feature": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Legacy Content": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Menu Image Extractor": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Customer": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Campaign": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Trigger": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Segment": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Marketing Event": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Analytics Event": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Coin Transaction": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Monthly Billing Ledger": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Monthly Revenue Ledger": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Plan Change Log": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Media Asset": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Media Upload Session": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Coupon Usage": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"Referral Link": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"WhatsApp Lead Unlock": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI credit Transaction": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
	"AI Image Generation": "dinematters.dinematters.utils.permission_helpers.get_restaurant_permission_query_conditions",
}

has_permission = {
	"Restaurant": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Restaurant Config": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Restaurant User": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Restaurant Table": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Menu Product": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Menu Category": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Order": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Customer": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Marketing Campaign": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Monthly Billing Ledger": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	# All other restaurant-specific doctypes use the base restaurant check
	"Banquet Booking": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Table Booking": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Coupon": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Offer": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Event": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Game": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Home Feature": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"Legacy Content": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
	"AI Image Generation": "dinematters.dinematters.utils.permission_helpers.has_restaurant_permission",
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
		"before_save": "dinematters.dinematters.api.customers.normalize_customer_phone_on_save",
	},
	"Order": {
		"before_save": "dinematters.dinematters.api.customers.normalize_order_phone_on_save",
		"after_insert": [
			"dinematters.dinematters.api.customers.update_customer_last_visited",
			"dinematters.dinematters.api.realtime.notify_order_update",
			# Push notification to merchant dashboard (free FCM, background-safe)
			"dinematters.dinematters.api.realtime.notify_new_order_to_merchant",
			# Marketing Studio: fire 'On Order Complete' triggers
			"dinematters.dinematters.tasks.marketing_tasks.fire_order_complete_triggers"
		],
		"on_update": [
			"dinematters.dinematters.api.realtime.notify_order_update",
			"dinematters.dinematters.utils.loyalty.handle_order_cancellation",
			"dinematters.dinematters.utils.loyalty.handle_loyalty_settlement",
			"dinematters.dinematters.pos.utils.handle_order_update"
		],
	},
	"Table Booking": {
		"after_insert": "dinematters.dinematters.api.customers.update_customer_last_visited",
	},
	"Banquet Booking": {
		"after_insert": "dinematters.dinematters.api.customers.update_customer_last_visited",
	},
	"Menu Product": {
		"on_update": [
			"dinematters.dinematters.api.products.invalidate_product_cache",
			"dinematters.dinematters.api.realtime.notify_product_update",
			"dinematters.dinematters.api.google_business.handle_product_update"
		],
	},
	"Cart Entry": {
		"after_insert": "dinematters.dinematters.api.realtime.notify_cart_update",
		"on_update": "dinematters.dinematters.api.realtime.notify_cart_update",
		"on_trash": "dinematters.dinematters.api.realtime.notify_cart_update",
	},
	"File": {
		"on_update": "dinematters.dinematters.doctype.home_feature.home_feature.update_home_feature_from_file",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"30 3 * * *": [
			"dinematters.dinematters.tasks.marketing_tasks.generate_daily_seo_blog"
		],
		"59 23 * * *": [  # Run daily at 23:59 for floor recovery and lite renewals
			"dinematters.dinematters.tasks.subscription_tasks.process_daily_subscription_floors",
			"dinematters.dinematters.tasks.subscription_tasks.process_silver_feature_renewals",
		],
		"1 0 * * *": [    # Run daily at 00:01 for plan switches
			"dinematters.dinematters.tasks.subscription_tasks.apply_deferred_plan_changes",
		],
		# Marketing Studio: dispatch scheduled campaigns every 15 minutes
		"*/15 * * * *": [
			"dinematters.dinematters.tasks.marketing_tasks.dispatch_scheduled_campaigns",
		],
		# Marketing Studio: fire event-based triggers every 30 minutes
		"*/30 * * * *": [
			"dinematters.dinematters.tasks.marketing_tasks.fire_triggers",
		],
		# Google Growth: fetch insights daily
        "0 1 * * *": [
            "dinematters.dinematters.api.google_business.fetch_all_restaurant_insights"
        ],
		# Loyalty: grant birthday bonus coins at 08:00 IST daily
		"0 8 * * *": [
			"dinematters.dinematters.tasks.loyalty_tasks.grant_birthday_bonuses"
		],
		# Loyalty: nudge customers whose coins expire within 7 days — 10:00 IST daily
		"0 10 * * *": [
			"dinematters.dinematters.tasks.loyalty_tasks.send_coin_expiry_notifications"
		],
		# Loyalty: reset referral share cycles on 1st of each month at 00:00 UTC
		"0 0 1 * *": [
			"dinematters.dinematters.tasks.loyalty_tasks.reset_referral_cycles_monthly"
		],
	}
}

extend_bootinfo = "dinematters.dinematters.utils.boot_helpers.extend_bootinfo"



# Testing
# -------

# before_tests = "dinematters.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "dinematters.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "dinematters.task.get_dashboard_data"
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
    "dinematters.dinematters.utils.cors_helpers.handle_cors_preflight",
    "dinematters.dinematters.utils.auth_hooks.restrict_merchant_desk_access"
]
after_request = ["dinematters.dinematters.utils.cors_helpers.add_cors_headers"]

# Job Events
# ----------
# before_job = ["dinematters.utils.before_job"]
# after_job = ["dinematters.utils.after_job"]

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
# 	"dinematters.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Website Route Rules
# -------------------
# URL routing for dinematters UI (similar to Mint)
# Using a catch-all that avoids interfering with system paths
website_route_rules = [
    {"from_route": "/dinematters/<path:app_path>", "to_route": "dinematters"}
]

# Redirect root to dinematters so unauthenticated users land on dinematters login
# (ProtectedRoute then redirects to /dinematters/login)
website_redirects = [{"source": "/", "target": "/dinematters"}]

fixtures = [{"dt": "Custom Field", "filters": [["module", "=", "Dinematters"]]}]
