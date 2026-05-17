# Copyright (c) 2025, Flamezo and contributors
# Staff Management API — invite, list, remove, toggle staff
#
# All endpoints require the calling user to be a Restaurant Admin
# for the target restaurant (except get_staff_members which also works for Staff).

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.permissions import validate_restaurant_access
from flamezo_backend.flamezo.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES
from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import get_staff_seat_limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_admin(restaurant_id):
	"""Throw if the current user is NOT a Restaurant Admin for this restaurant."""
	user = frappe.session.user
	user_roles = frappe.get_roles(user)
	if (
		user == "Administrator" or 
		any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles) or
		"Restaurant Admin" in user_roles
	):
		return

	role = frappe.db.get_value(
		"Restaurant User",
		{"user": user, "restaurant": restaurant_id, "is_active": 1},
		"role"
	)
	if role != "Restaurant Admin":
		frappe.throw(_("Only a Restaurant Admin can perform this action."), frappe.PermissionError)


def _resolve_restaurant(restaurant_id):
	"""Normalise restaurant_id → docname (handles both restaurant_id slug and name)."""
	from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
	# validate_restaurant_access expects the docname
	doc_name = frappe.db.get_value("Restaurant", restaurant_id, "name")
	if not doc_name:
		doc_name = get_restaurant_from_id(restaurant_id)
	if not doc_name:
		frappe.throw(_("Restaurant not found"), frappe.DoesNotExistError)
	return doc_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_staff_members(restaurant_id):
	"""
	GET – return all staff for this restaurant plus seat-quota info.

	Returns:
	  {
	    success: true,
	    data: {
	      members: [...],
	      seat_limit: 3,
	      seats_used: 1,       # non-admin only
	      seats_remaining: 2,
	      plan_type: "GOLD",
	      can_add_staff: true
	    }
	  }
	"""
	try:
		restaurant = _resolve_restaurant(restaurant_id)

		if not validate_restaurant_access(frappe.session.user, restaurant):
			frappe.throw(_("Access denied"), frappe.PermissionError)

		members_raw = frappe.get_all(
			"Restaurant User",
			filters={"restaurant": restaurant},
			fields=["name", "user", "role", "is_active", "is_default", "creation"],
			order_by="creation asc"
		)

		# Enrich with display name and email from User doctype
		members = []
		for m in members_raw:
			user_info = frappe.db.get_value(
				"User", m.user, ["full_name", "email", "user_image"], as_dict=True
			) or {}
			
			# Role priority: if they have Restaurant Admin or System Manager role in Frappe, they are an Admin
			actual_role = m.role
			if "Restaurant Admin" in frappe.get_roles(m.user) or "System Manager" in frappe.get_roles(m.user):
				actual_role = "Restaurant Admin"
				# Auto-sync to database if there's a mismatch (perfect fix)
				if m.role != "Restaurant Admin":
					frappe.db.set_value("Restaurant User", m.name, "role", "Restaurant Admin")
			
			members.append({
				"name": m.name,
				"user": m.user,
				"full_name": user_info.get("full_name") or m.user,
				"email": user_info.get("email") or m.user,
				"user_image": user_info.get("user_image"),
				"role": actual_role,
				"is_active": bool(m.is_active),
				"is_default": bool(m.is_default),
				"creation": str(m.creation),
			})

		limit, plan_type = get_staff_seat_limit(restaurant)
		# Count only active non-admin staff toward the quota
		seats_used = sum(1 for m in members if m["role"] == "Restaurant Staff" and m["is_active"])
		seats_remaining = max(0, limit - seats_used)

		return {
			"success": True,
			"data": {
				"members": members,
				"seat_limit": limit,
				"seats_used": seats_used,
				"seats_remaining": seats_remaining,
				"plan_type": plan_type,
				"can_add_staff": seats_remaining > 0,
			}
		}
	except Exception as e:
		frappe.log_error(f"get_staff_members error: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def invite_staff_member(restaurant_id, email, full_name, role="Restaurant Staff"):
	"""
	POST – invite a staff member by email.

	Flow:
	  1. Validate caller is Restaurant Admin
	  2. Find or create Frappe User (disabled until they set password via welcome email)
	  3. Create Restaurant User record (seat limit is enforced by the DocType)
	  4. Send welcome / invite email

	Returns:
	  { success: true, data: { restaurant_user: "...", user: "...", is_new_user: true } }
	"""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_admin(restaurant)

		email = (email or "").strip().lower()
		full_name = (full_name or "").strip()
		role = role if role in ("Restaurant Admin", "Restaurant Staff") else "Restaurant Staff"

		if not email:
			frappe.throw(_("Email is required"))
		if not full_name:
			frappe.throw(_("Full name is required"))

		# --- Find or create Frappe User ---
		is_new_user = False
		if not frappe.db.exists("User", email):
			user_doc = frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": full_name.split()[0],
				"last_name": " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else "",
				"full_name": full_name,
				"enabled": 1,
				"send_welcome_email": 0,  # We send our own invite email below
			})
			user_doc.insert(ignore_permissions=True)
			is_new_user = True
		else:
			# Update full_name if given user doesn't have one yet
			existing = frappe.get_doc("User", email)
			if not existing.full_name and full_name:
				frappe.db.set_value("User", email, "full_name", full_name)

		# --- Check not already added ---
		if frappe.db.exists("Restaurant User", {"user": email, "restaurant": restaurant}):
			frappe.throw(_("{0} is already a member of this restaurant.").format(email))

		# --- Create Restaurant User (seat limit enforced in DocType.validate) ---
		ru = frappe.get_doc({
			"doctype": "Restaurant User",
			"user": email,
			"restaurant": restaurant,
			"role": role,
			"is_active": 1,
			"is_default": 0,
		})
		ru.insert(ignore_permissions=True)

		# --- Send invite email ---
		_send_staff_invite_email(
			email=email,
			full_name=full_name,
			restaurant_name=frappe.db.get_value("Restaurant", restaurant, "restaurant_name") or restaurant,
			is_new_user=is_new_user,
		)

		return {
			"success": True,
			"data": {
				"restaurant_user": ru.name,
				"user": email,
				"full_name": full_name,
				"role": role,
				"is_new_user": is_new_user,
			}
		}
	except frappe.ValidationError as e:
		return {"success": False, "error": str(e)}
	except frappe.PermissionError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(f"invite_staff_member error: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def remove_staff_member(restaurant_id, restaurant_user_name):
	"""
	DELETE – remove a staff member from this restaurant.

	Admins cannot remove themselves this way.
	"""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_admin(restaurant)

		ru = frappe.get_doc("Restaurant User", restaurant_user_name)

		# Safety: ensure the record belongs to this restaurant
		if ru.restaurant != restaurant:
			frappe.throw(_("This staff record does not belong to this restaurant."), frappe.PermissionError)

		# Admins cannot remove themselves
		if ru.user == frappe.session.user:
			frappe.throw(_("You cannot remove yourself from the restaurant."))

		frappe.delete_doc("Restaurant User", restaurant_user_name, ignore_permissions=True)

		return {"success": True, "message": _("Staff member removed successfully.")}
	except frappe.ValidationError as e:
		return {"success": False, "error": str(e)}
	except frappe.PermissionError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(f"remove_staff_member error: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_staff_member(restaurant_id, restaurant_user_name, is_active=None, role=None):
	"""
	PATCH – update staff member status or role.
	"""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_admin(restaurant)

		ru = frappe.get_doc("Restaurant User", restaurant_user_name)
		if ru.restaurant != restaurant:
			frappe.throw(_("This staff record does not belong to this restaurant."), frappe.PermissionError)

		# Update active status if provided
		if is_active is not None:
			# Cannot deactivate yourself
			if ru.user == frappe.session.user and not is_active:
				frappe.throw(_("You cannot deactivate your own account."))
			ru.is_active = 1 if is_active else 0

		# Update role if provided
		if role:
			if role not in ("Restaurant Admin", "Restaurant Staff"):
				frappe.throw(_("Invalid role: {0}").format(role))
			ru.role = role

		ru.save(ignore_permissions=True)

		# Bust Redis cache
		redis_key = f"flamezo_backend:user_restaurants:{ru.user}"
		frappe.cache().delete_value(redis_key)

		return {"success": True, "message": _("Staff member updated.")}
	except frappe.ValidationError as e:
		return {"success": False, "error": str(e)}
	except frappe.PermissionError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(f"update_staff_member error: {str(e)}")
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _send_staff_invite_email(email, full_name, restaurant_name, is_new_user):
	"""Send a welcome/invite email to the newly added staff member."""
	try:
		site_url = frappe.utils.get_url()
		login_url = f"{site_url}/flamezo_backend/login"

		if is_new_user:
			# Generate a password reset link so they can set their own password
			reset_key = frappe.generate_hash(length=32)
			frappe.cache().set_value(f"password_reset:{reset_key}", email, expires_in_sec=86400)

			# Use Frappe's built-in reset password mechanism
			try:
				from frappe.core.doctype.user.user import reset_password
				reset_password(email)
			except Exception:
				pass  # Non-fatal – they can use "forgot password"

			subject = f"You've been invited to {restaurant_name} on Flamezo!"
			message_body = f"""
			<p>Hi {full_name},</p>
			<p>You have been added as a staff member for <strong>{restaurant_name}</strong> on Flamezo.</p>
			<p>Please <a href="{site_url}/update-password?key={reset_key}">click here to set your password</a> and get started.</p>
			<p>Once logged in, visit: <a href="{login_url}">{login_url}</a></p>
			<p>— The Flamezo Team</p>
			"""
		else:
			subject = f"You've been added to {restaurant_name} on Flamezo"
			message_body = f"""
			<p>Hi {full_name},</p>
			<p>You have been added as a staff member for <strong>{restaurant_name}</strong> on Flamezo.</p>
			<p><a href="{login_url}">Log in to your dashboard</a> to start managing orders.</p>
			<p>— The Flamezo Team</p>
			"""

		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=message_body,
			now=True
		)
	except Exception as e:
		# Non-fatal: staff is added even if email fails
		frappe.log_error(f"Failed to send staff invite email to {email}: {str(e)}", "Staff Invite Email")
