import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

# The people who hear about new support messages and may answer them.
SUPPORT_ROLE = "Support Agent"

# Promised reply time (TAT) by priority, in hours. Shown to the requester in
# the automated acknowledgement; missing it unlocks "Escalate" for them.
REPLY_HOURS = {"urgent": 2, "high": 4, "normal": 24, "low": 48}


class SupportMessage(Document):
	def before_insert(self):
		if not self.created_at:
			self.created_at = now_datetime()

	def after_insert(self):
		# Lives on the doctype, not in the API layer, on purpose: an agent
		# replying from Frappe Desk inserts this row directly and never touches
		# the whitelisted API. Anything that must happen on every message —
		# thread state, unread counts, telling the other side — belongs here or
		# the Desk path silently drops it.
		_update_thread(self)
		_notify_other_side(self)
		_notify_staff(self)
		_push_live_update(self)



def _update_thread(msg):
	"""Status follows whoever spoke last, so nobody has to remember to set it.

	Only ever writes to the parent Support Thread — a row this feature owns.
	"""
	thread = frappe.db.get_value(
		"Support Thread",
		msg.thread,
		["status", "priority", "first_response_at", "unread_for_customer", "unread_for_agent"],
		as_dict=True,
	)
	if not thread:
		return

	updates = {"last_message_at": msg.created_at}

	if msg.sender_type == "customer":
		updates["unread_for_agent"] = (thread.unread_for_agent or 0) + 1
		# A customer writing on a resolved/closed thread reopens it — reopening
		# is the customer's right, not an agent favour.
		updates["status"] = "awaiting_agent"
		if thread.status != "awaiting_agent":
			# A new wait starts (first message, reply after the team answered,
			# or a reopen): promise a reply time and reset the escalation state.
			updates["reply_due_at"] = add_to_date(
				msg.created_at, hours=REPLY_HOURS.get(thread.priority or "normal", 24)
			)
			updates["escalated_at"] = None
			updates["last_update_request_at"] = None
	elif msg.sender_type == "agent":
		updates["unread_for_customer"] = (thread.unread_for_customer or 0) + 1
		updates["status"] = "awaiting_customer"
		if not thread.first_response_at:
			updates["first_response_at"] = msg.created_at

	frappe.db.set_value("Support Thread", msg.thread, updates, update_modified=True)


def _notify_other_side(msg):
	"""Tell the customer when an agent replies. Never raises — a failed
	notification must not roll back the message that was just saved."""
	if msg.sender_type != "agent":
		return
	try:
		phone = frappe.db.get_value("Support Thread", msg.thread, "customer_phone")
		if not phone:
			# Merchant threads have no phone; their dashboard badge reads the
			# unread counter updated above instead.
			return
		from flamezo_backend.flamezo.api.notifications_consumer import create_notification

		preview = (msg.message or "").strip()[:120] or _("Sent you an attachment")
		create_notification(
			customer_phone=phone,
			# Never the staff account's name (e.g. "Administrator") — customers see the team.
			title=_("Flamezo Support replied"),
			body=preview,
			notification_type="support",
			reference_doctype="Support Thread",
			reference_name=msg.thread,
			deep_link=f"/support/thread/{msg.thread}",
		)
	except Exception as e:
		frappe.log_error(title="Support Notification", message=f"Support reply notification failed ({msg.thread}): {e}")


def _staff_emails(thread):
	"""Who on the team hears about a new message.

	The assigned agent if the ticket has one; otherwise every enabled System
	Manager. Resolved to EMAILS on purpose: Frappe's make_notification_logs
	looks users up by email, so passing a user name like "Administrator"
	silently notifies nobody.
	"""
	if thread.get("assigned_to"):
		names = [thread.assigned_to]
	else:
		names = frappe.get_all(
			"Has Role", filters={"role": SUPPORT_ROLE, "parenttype": "User"}, pluck="parent"
		)
		if not names:
			# Nobody holds the role yet: tell Administrator only. Never fall back
			# to every System Manager — that list includes sales, contact and test
			# accounts, and Frappe can email notification logs.
			names = ["Administrator"]
	names = [n for n in names if n and n != "Guest"]
	if not names:
		return []
	return [
		e for e in frappe.get_all("User", filters={"name": ["in", names], "enabled": 1}, pluck="email") if e
	]


def _notify_staff(msg):
	"""Ring the Desk bell when a customer or merchant writes.

	Customers aren't Frappe users, so they are notified through Flamezo
	Notification (app inbox + push). Staff ARE Frappe users, so they get
	Frappe's own Notification Log — the bell in Desk, with a live badge. Never
	raises: a missed alert must not roll back the message.
	"""
	if msg.sender_type != "customer":
		return
	try:
		thread = frappe.db.get_value(
			"Support Thread", msg.thread,
			["name", "customer_name", "category", "priority", "assigned_to", "source"],
			as_dict=True,
		)
		if not thread:
			return
		emails = _staff_emails(thread)
		if not emails:
			return
		who = thread.customer_name or _("A customer")
		first = frappe.db.count("Support Message", {"thread": msg.thread, "sender_type": "customer"}) <= 1
		if first:
			where = _("merchant") if thread.source == "dashboard" else _("app")
			subject = _("New {0} request {1} from {2} · {3} ({4})").format(
				thread.priority or "normal", msg.thread, who, thread.category or "support", where
			)
		else:
			subject = _("{0} replied on {1}").format(who, msg.thread)

		# The team works from their phones, not Desk — WhatsApp them too. Queued
		# after commit so the alert can't outrun the row it links to, and a slow
		# WhatsApp server never delays the customer's request.
		from flamezo_backend.flamezo.utils.support_alerts import build_alert_text

		# Who, about what, linked to what, device, priority and reply-due time,
		# plus what they said — the team acts from the alert alone.
		alert_text = build_alert_text(msg.thread, msg.message, first)
		# WhatsApp the team ONCE per request — when it's raised. Follow-ups show
		# on the admin Support Requests page (unread counts) and the Desk bell.
		if first:
			frappe.enqueue(
				"flamezo_backend.flamezo.utils.support_alerts.send_team_alert",
				queue="short",
				enqueue_after_commit=True,
				thread_name=msg.thread,
				message=msg.message,
				first=first,
			)

		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		enqueue_create_notification(emails, {
			"type": "Alert",
			"document_type": "Support Thread",
			"document_name": msg.thread,
			"subject": subject,
			"email_content": frappe.utils.escape_html(alert_text).replace("\n", "<br>"),
			"from_user": msg.sender_user or None,
		})
	except Exception as e:
		frappe.log_error(title="Support Notification", message=f"Support staff notification failed ({msg.thread}): {e}")


def _push_live_update(msg):
	"""Tell any Desk form open on this ticket to redraw, so agents never refresh.

	Staff are real Frappe users with authenticated sockets, so Frappe's own
	realtime is the right tool here (customers, who are not Frappe users, get
	updates by long-poll instead). Sent to the ticket's doc room — only users
	with access to that ticket receive it — and carries ids only, never the
	message text.
	"""
	try:
		frappe.publish_realtime(
			"support_thread_update",
			{"thread": msg.thread, "message_id": msg.name, "sender_type": msg.sender_type},
			doctype="Support Thread",
			docname=msg.thread,
			after_commit=True,
		)
	except Exception:
		# Live refresh is a convenience; the form's timed check still catches it.
		pass
