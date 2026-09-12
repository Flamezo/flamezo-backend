"""Customer & merchant support chat.

A support thread is crowd chat with two things changed: the id is a Support
Thread, and access means "this is your own thread" (or "you are staff")
instead of "you are a member of this crowd". Auth, pagination and the
long-poll mirror crowd.py exactly — see crowd.poll_messages for why this is a
long-poll and not a socket, and why the wait is capped at 8s.

Three front doors, one implementation:
  * customers  — phone + X-Customer-Token, threads keyed by customer_phone
  * merchants  — logged-in Frappe user, threads keyed by outlet, access via the
                 same validate_restaurant_for_api check every merchant API uses
  * agents     — Frappe users holding Support Agent (or System Manager)
The paging, polling, read-receipt and resolve logic is shared below; the
endpoints only differ in who they authenticate and which threads they may see.

Data safety: this module only ever inserts or updates Support Thread and
Support Message rows. It reads Customer / Outlet / User to fill in names and
never writes to them or anything else. Nothing in this module deletes a support
row; deletion is a manual choice left to System Managers in Desk.
"""

import json
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, format_datetime, get_datetime, now_datetime, time_diff_in_seconds

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import (
	has_active_customer_session,
	normalize_phone,
	public_display_name,
)

_ACTIVE = ("open", "awaiting_agent", "awaiting_customer")
_STATUSES = ("open", "awaiting_agent", "awaiting_customer", "resolved", "closed")

# Phase-1 routing: category -> priority. Support Team / Routing Rule doctypes
# replace this in phase 2. Merchant money problems are urgent: a settlement
# that hasn't landed is revenue the merchant is already missing.
_PRIORITY_BY_CATEGORY = {
	"payment": "high",
	"settlement": "urgent",
	"kyc": "urgent",
	"grievance": "high",
	"commission": "high",
	"account": "high",
	"feedback": "low",
	"callback": "high",
}

_POLL_MAX_WAIT_SECONDS = 8  # same cap and reasoning as crowd.poll_messages
_POLL_CHECK_INTERVAL_SECONDS = 1

# Flood guard: a support queue is read by people, so one sender must not be able
# to bury it.
_RATE_LIMIT_PER_MINUTE = 20

_MSG_FIELDS = [
	"name", "thread", "sender_type", "sender_name", "sender_phone", "sender_user",
	"message_type", "message", "image_url", "payload_json", "is_read", "read_at",
	"created_at", "creation",
]
_THREAD_FIELDS = [
	"name", "customer_phone", "requester_user", "outlet", "source", "status",
	"category", "subject", "assigned_to", "app_area", "context_doctype",
	"context_name", "csat_rating", "unread_for_customer", "last_message_at", "creation",
	"customer_name", "priority", "reply_due_at", "escalated_at", "last_update_request_at",
]

# A follow-up gets an automated "got it" only if the team's last reply is older
# than this — mid-conversation, a bot line after every message is noise.
# ponytail: fixed window; tune per channel if it feels chatty in practice.
_FOLLOWUP_ACK_AFTER_SECONDS = 30 * 60

# "Request update" can be pressed once an hour; the team is already alerted.
_UPDATE_REQUEST_COOLDOWN_SECONDS = 60 * 60


# ── auth ──────────────────────────────────────────────────────────────────────

def _require_phone(phone):
	if not phone:
		frappe.throw(_("phone is required"), frappe.AuthenticationError)
	return normalize_phone(phone.strip())


def _customer(phone):
	"""Same contract as crowd._require_session: the token comes from the
	request header, never the body, and must belong to this exact phone."""
	phone = _require_phone(phone)
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
	return phone


def _merchant_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to continue."), frappe.AuthenticationError)
	return user


def _merchant_outlet(outlet_id, user):
	"""The outlet, if this user may act for it. allow_inactive on purpose: the
	dashboard tells deactivated merchants to "contact support to reactivate",
	so the one merchant who most needs support must not be locked out of it."""
	return validate_restaurant_for_api(outlet_id, user=user, allow_inactive=True)


def _not_available():
	# Not-found and not-yours are deliberately indistinguishable, so thread ids
	# cannot be probed.
	frappe.throw(_("This conversation isn't available."), frappe.DoesNotExistError)


def _get_thread_row(thread_id):
	if not thread_id:
		frappe.throw(_("thread_id is required"))
	return frappe.db.get_value("Support Thread", thread_id, _THREAD_FIELDS, as_dict=True)


def _thread_for_customer(thread_id, phone):
	row = _get_thread_row(thread_id)
	if not row or normalize_phone(row.customer_phone or "") != phone:
		_not_available()
	return row


def _thread_for_merchant(thread_id, user):
	row = _get_thread_row(thread_id)
	if not row or not row.outlet or row.source != "dashboard":
		_not_available()
	try:
		_merchant_outlet(row.outlet, user)
	except (frappe.PermissionError, frappe.DoesNotExistError):
		_not_available()
	return row


def _rate_limit(sender_key):
	key = f"support:rate:{sender_key}"
	count = cint(frappe.cache().get_value(key))
	if count >= _RATE_LIMIT_PER_MINUTE:
		frappe.throw(_("Give us a moment to catch up — try again in a minute."))
	frappe.cache().set_value(key, count + 1, expires_in_sec=60)


# ── formatting ───────────────────────────────────────────────────────────────

def _display_sender(m):
	# Customers and merchants always see the team as "Flamezo Support" — never
	# an internal account name like "Administrator". Desk shows the real agent
	# from sender_user.
	if m.sender_type == "agent":
		return _("Flamezo Support")
	if m.sender_type in ("system", "bot"):
		return _("Flamezo Support")
	return public_display_name(m.sender_name)


# Stand-in sender ids for the team's side, so chat UIs group consecutive team
# (or automated) bubbles under one name instead of treating "" as one sender.
_TEAM_SENDER = {"agent": "flamezo:team", "bot": "flamezo:auto", "system": "flamezo:auto"}


def _format_message(m):
	"""Shaped to be read by the existing Flutter chat model: `request_id`,
	`sender_phone` and `is_system` are what CrowdMessage already parses, so the
	support screen reuses the crowd chat UI unchanged."""
	try:
		payload = json.loads(m.payload_json) if m.get("payload_json") else None
	except Exception:
		payload = None
	return {
		"id": m.name,
		"thread_id": m.thread,
		"request_id": m.thread,
		"sender_type": m.sender_type,
		"sender_phone": m.sender_phone or _TEAM_SENDER.get(m.sender_type, ""),
		"sender_user": m.get("sender_user") or "",
		"sender_name": _display_sender(m),
		"message_type": m.message_type or "text",
		"message": m.message or "",
		"image_url": m.image_url or "",
		"payload": payload,
		"is_read": bool(m.get("is_read")),
		# Automated lines render as chat bubbles from the team (Razorpay-style),
		# not grey status text; `is_automated` tells them apart from a person.
		"is_system": False,
		"is_automated": m.sender_type in ("system", "bot"),
		"created_at": str(m.created_at) if m.created_at else str(m.creation),
	}


def _format_thread(t, last_message=None):
	# Requesters see the team, not the internal account behind it.
	agent_name = _("Flamezo Support") if t.get("assigned_to") else ""
	return {
		"thread_id": t.name,
		"status": t.status,
		"category": t.category,
		"subject": t.subject or "",
		"app_area": t.get("app_area") or "",
		"outlet": t.get("outlet") or "",
		"agent_name": agent_name,
		"unread_count": cint(t.get("unread_for_customer")),
		"csat_rating": t.get("csat_rating"),
		"context": (
			{"doctype": t.context_doctype, "name": t.context_name}
			if t.get("context_doctype") and t.get("context_name") else None
		),
		"last_message_at": str(t.last_message_at) if t.get("last_message_at") else str(t.get("creation") or ""),
		"last_message_preview": (last_message or "")[:120],
		"created_at": str(t.get("creation") or ""),
		**_wait_state(t),
	}


def _wait_state(t):
	"""Razorpay-style TAT: while the team owes a reply, show when it's due.
	"Request update" only unlocks once that time has passed (once per wait) —
	before then the requester just sees the promised time."""
	waiting = t.status in ("open", "awaiting_agent") and t.get("category") != "feedback"
	due = get_datetime(t.reply_due_at) if t.get("reply_due_at") else None
	overdue = bool(waiting and due and now_datetime() > due)
	escalated = bool(t.get("escalated_at"))
	return {
		"reply_due_at": str(due) if waiting and due else "",
		"escalated": waiting and escalated,
		"can_escalate": overdue and not escalated,
		"can_request_update": overdue and not escalated,
	}


def _fmt_due(dt):
	"""'4:30 PM today' / '4:28 PM, 11 Sep' — the promised time, in words."""
	dt = get_datetime(dt)
	if dt.date() == now_datetime().date():
		return _("{0} today").format(format_datetime(dt, "h:mm a"))
	return "{0}, {1}".format(format_datetime(dt, "h:mm a"), format_datetime(dt, "d MMM"))


def _reply_promise(thread_id):
	due = frappe.db.get_value("Support Thread", thread_id, "reply_due_at")
	if not due:
		return _("We'll reply right here as soon as we can.")
	return _("You'll hear back right here by {0}.").format(_fmt_due(due))


# ── shared implementation (used by every front door) ─────────────────────────

def _insert_message(thread_id, sender_type, message="", **extra):
	doc = frappe.get_doc({
		"doctype": "Support Message",
		"thread": thread_id,
		"sender_type": sender_type,
		"message": message or "",
		**extra,
	})
	doc.insert(ignore_permissions=True)
	return doc


def _reject_abuse(*texts):
	"""No abusive language in support conversations — customers, merchants and
	staff alike (utils/abuse_filter). The sender sees why and can rephrase."""
	from flamezo_backend.flamezo.utils.abuse_filter import contains_abuse

	if any(contains_abuse(t) for t in texts if t):
		frappe.throw(
			_("Please keep it respectful — your message has words we can't send. "
			  "Rephrase it and our team will help you right away."),
			title=_("Message not sent"),
		)


def _clean_message(message, image_url=None):
	message = (message or "").strip()
	if not message and not image_url:
		frappe.throw(_("Message is empty."))
	return message


def _page_threads(filters, page, limit):
	page = max(1, cint(page))
	limit = min(cint(limit) or 20, 50)
	rows = frappe.get_all(
		"Support Thread", filters=filters, fields=_THREAD_FIELDS,
		order_by="last_message_at desc",
		limit_start=(page - 1) * limit, limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	out = []
	# ponytail: one preview query per thread; fine at limit<=50, batch with a
	# window query if an inbox ever needs to be larger.
	for t in rows[:limit]:
		preview = frappe.db.get_value(
			"Support Message", {"thread": t.name}, "message", order_by="created_at desc, creation desc"
		)
		out.append(_format_thread(t, preview))
	return {"success": True, "data": {"threads": out, "has_more": has_more}}


def _messages_page(thread_id, before_id, limit):
	"""Scroll-up pagination, same contract as crowd.get_messages."""
	limit = min(cint(limit) or 30, 100)
	filters = {"thread": thread_id}
	if before_id:
		# `created_at` is when the message happened (set in before_insert);
		# `creation` can be stamped seconds late on a slow request, which put a
		# "resolved" line below the reply that followed it. Clients re-sort
		# live-polled messages by created_at too, so a reload looks the same.
		before = frappe.db.get_value("Support Message", before_id, "created_at")
		if before:
			filters["created_at"] = ("<", before)
	rows = frappe.get_all(
		"Support Message", filters=filters, fields=_MSG_FIELDS,
		order_by="created_at desc, creation desc", limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	rows = rows[:limit]
	rows.reverse()
	return {"success": True, "data": {"messages": [_format_message(m) for m in rows], "has_more": has_more}}


def _poll(thread_id, after_id):
	"""8-second long-poll. Returns as soon as anything newer than `after_id`
	exists, or empty on timeout; the client re-issues immediately."""
	after_creation = None
	if after_id:
		after_creation = frappe.db.get_value("Support Message", after_id, "creation")
	if not after_creation:
		after_creation = now_datetime()

	deadline = time.monotonic() + _POLL_MAX_WAIT_SECONDS
	while True:
		rows = frappe.get_all(
			"Support Message",
			filters={"thread": thread_id, "creation": (">", after_creation)},
			fields=_MSG_FIELDS, order_by="creation asc", limit_page_length=100,
		)
		if rows:
			status = frappe.db.get_value("Support Thread", thread_id, "status")
			return {"success": True, "data": {
				"messages": [_format_message(m) for m in rows], "status": status, "timed_out": False,
			}}
		if time.monotonic() >= deadline:
			return {"success": True, "data": {"messages": [], "timed_out": True}}
		frappe.db.commit()
		time.sleep(_POLL_CHECK_INTERVAL_SECONDS)


def _mark_read_by_requester(thread_id):
	"""The requester (customer or merchant) has seen everything staff sent."""
	now = now_datetime()
	for name in frappe.get_all(
		"Support Message",
		filters={"thread": thread_id, "sender_type": ["in", ["agent", "system", "bot"]], "is_read": 0},
		pluck="name",
	):
		frappe.db.set_value("Support Message", name, {"is_read": 1, "read_at": now}, update_modified=False)
	frappe.db.set_value("Support Thread", thread_id, "unread_for_customer", 0, update_modified=False)
	frappe.db.commit()
	return {"success": True}


def _send_as_requester(thread, sender_name, message, message_type, image_url, **sender):
	if thread.status == "closed":
		# Closed is terminal; the client starts a fresh thread instead.
		frappe.throw(_("This conversation is closed. Start a new one and we'll pick it up."))
	message = _clean_message(message, image_url)
	_reject_abuse(message)
	# Same shape as _open_or_join: caller fields win over the defaults, so no
	# caller can collide on a keyword by passing it inside **sender.
	fields = {
		"sender_name": sender_name,
		"message_type": message_type if message_type in ("text", "image", "video") else "text",
		"image_url": image_url or "",
		**sender,
	}
	doc = _insert_message(thread.name, "customer", message, **fields)
	_followup_ack(thread.name, thread.status)
	frappe.db.commit()
	doc.reload()
	return {"success": True, "data": _format_message(doc)}


def _followup_ack(thread_id, prev_status):
	"""Automated reply to a requester's follow-up, so nobody writes into silence.

	Reopening a resolved request always gets one. Otherwise only when the team
	last spoke a while ago (see _FOLLOWUP_ACK_AFTER_SECONDS) — never after every
	line of a live back-and-forth, and never twice before the team answers.
	"""
	if prev_status == "resolved":
		_insert_message(thread_id, "bot", _(
			"Reopened {0} — your message has gone back to the Flamezo team. {1}"
		).format(thread_id, _reply_promise(thread_id)), message_type="system")
		return
	last = frappe.get_all(
		"Support Message",
		filters={"thread": thread_id, "sender_type": ["in", ["agent", "bot"]]},
		fields=["sender_type", "created_at"],
		order_by="creation desc",
		limit=1,
	)
	if (
		last
		and last[0].sender_type == "agent"
		and time_diff_in_seconds(now_datetime(), last[0].created_at) > _FOLLOWUP_ACK_AFTER_SECONDS
	):
		_insert_message(thread_id, "bot", _(
			"Got it — added to {0}, no need to raise a new request. {1}"
		).format(thread_id, _reply_promise(thread_id)), message_type="system")


def _alert_staff(thread_id, text, label=None):
	"""Alert the team (WhatsApp + Desk bell) about something the requester did
	that isn't a message — asking for an update, escalating. Never raises."""
	try:
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		from flamezo_backend.flamezo.doctype.support_message.support_message import _staff_emails
		from flamezo_backend.flamezo.utils.support_alerts import ticket_alert_text

		# Desk bell only: the team is WhatsApped once per request (when it's
		# raised); updates like this show on the admin Support Requests page.
		full = ticket_alert_text(thread_id, text)
		thread = frappe.db.get_value("Support Thread", thread_id, ["name", "assigned_to"], as_dict=True)
		emails = _staff_emails(thread)
		if emails:
			enqueue_create_notification(emails, {
				"type": "Alert",
				"document_type": "Support Thread",
				"document_name": thread_id,
				"subject": text,
				"email_content": frappe.utils.escape_html(full).replace("\n", "<br>"),
			})
	except Exception as e:
		frappe.log_error(title="Support Notification", message=f"Support staff alert failed ({thread_id}): {e}")


def _request_update(thread):
	"""Request update — or Escalate, once the promised reply time has passed.

	Escalating makes the ticket urgent, promises a reply within the urgent
	TAT, and alerts the whole team. Both answer with an automated message.
	"""
	from flamezo_backend.flamezo.doctype.support_message.support_message import REPLY_HOURS

	state = _wait_state(thread)
	if not state["can_escalate"]:
		if thread.status in ("open", "awaiting_agent") and not thread.get("escalated_at"):
			frappe.throw(_("You can request an update once the promised reply time has passed."))
		frappe.throw(_("The team already has this — they'll reply right here."))
	who = thread.customer_name or _("The requester")
	now = now_datetime()
	if state["can_escalate"]:
		due = add_to_date(now, hours=REPLY_HOURS["urgent"])
		frappe.db.set_value("Support Thread", thread.name, {
			"priority": "urgent", "escalated_at": now, "reply_due_at": due,
		})
		text = _(
			"Escalated. {0} is now top priority and the whole Flamezo team has been alerted. "
			"You'll hear back right here by {1}."
		).format(thread.name, _fmt_due(due))
		alert = f"🚨 ESCALATED {thread.name}: {who} waited past the promised reply time."
		label = "escalated, reply overdue"
	else:
		last = thread.get("last_update_request_at")
		if last and time_diff_in_seconds(now, last) < _UPDATE_REQUEST_COOLDOWN_SECONDS:
			frappe.throw(_("You asked for an update less than an hour ago — the team has it."))
		frappe.db.set_value("Support Thread", thread.name, "last_update_request_at", now)
		text = _("We've asked the team for an update on {0}. {1}").format(
			thread.name, _reply_promise(thread.name))
		alert = f"⏰ {who} asked for an update on {thread.name}."
		label = "update requested"
	_insert_message(thread.name, "bot", text, message_type="system")
	_alert_staff(thread.name, alert, label)
	frappe.db.commit()
	return {"success": True, "data": _format_thread(_get_thread_row(thread.name))}


def _open_or_join(match, new_doc, first_message, sender):
	"""A request with its own subject is its own ticket (Razorpay-style).
	`match` is only passed for requests without a subject (older app builds):
	those join the requester's open ticket in the same category, as before."""
	existing = match and frappe.db.get_value(
		"Support Thread", {**match, "status": ["in", list(_ACTIVE)]}, "name",
		order_by="last_message_at desc",
	)
	if existing:
		thread_id = existing
		prev_status = frappe.db.get_value("Support Thread", thread_id, "status")
	else:
		doc = frappe.get_doc({"doctype": "Support Thread", **new_doc})
		doc.insert(ignore_permissions=True)
		thread_id = doc.name
	# The caller's sender fields win over the default name. The merchant path
	# passes its own sender_name (the person, not the outlet); passing a
	# default *and* spreading **sender raised "multiple values for keyword
	# argument 'sender_name'" and failed every merchant request before saving.
	fields = {"sender_name": frappe.db.get_value("Support Thread", thread_id, "customer_name"), **sender}
	_insert_message(thread_id, "customer", first_message, **fields)
	if not existing:
		# Without this the requester sends into silence and has no sign anyone
		# received it. A bot message: it changes no status, pings no one, and
		# carries the ticket number they can quote.
		_insert_message(thread_id, "bot", _acknowledgement(thread_id), message_type="system")
		# ...and on their WhatsApp, so they have the ID even with the app closed.
		frappe.enqueue(
			"flamezo_backend.flamezo.utils.support_alerts.notify_requester",
			queue="short", enqueue_after_commit=True,
			thread_name=thread_id, kind="created",
		)
	else:
		_followup_ack(thread_id, prev_status)
	frappe.db.commit()
	return {
		"success": True,
		"data": {
			"thread_id": thread_id,
			"status": frappe.db.get_value("Support Thread", thread_id, "status"),
			"joined_existing": bool(existing),
		},
	}


def _subject(subject, message):
	"""The requester's own subject line if they wrote one, else the start of
	their message — so older app versions without the field still work."""
	return (subject or "").strip()[:140] or message[:80]


def _acknowledgement(thread_id):
	"""The first thing a requester sees after sending — honest about timing."""
	# Two parts, like a ticket confirmation: what happened and when to expect a
	# reply, then the request ID on its own line so it's easy to find and quote.
	if frappe.db.get_value("Support Thread", thread_id, "category") == "feedback":
		return _(
			"Thanks for your feedback — it has gone straight to the Flamezo team. We read "
			"every note, and if we need more detail we'll ask right here.\n\n"
			"Your feedback ID is {0}."
		).format(thread_id)
	return _(
		"Your request has been forwarded to the Flamezo team. {0}\n\n"
		"Your request ID is {1} — mention it if you contact us anywhere else."
	).format(_reply_promise(thread_id), thread_id)


# ── customer endpoints (app) ─────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def start_thread(phone, category, message, app_area=None, subject=None, context_doctype=None,
                 context_name=None, app_version=None, platform=None, os_version=None,
                 callback=None, callback_time=None):
	"""Open a support request, or add to the one already open in this category."""
	phone = _customer(phone)
	_rate_limit(phone)
	message = _clean_message(message)
	_reject_abuse(message, subject)
	if not category:
		frappe.throw(_("category is required"))
	name = public_display_name(frappe.db.get_value("Customer", {"phone": phone}, "customer_name"))
	return _open_or_join(
		match=None if (subject or "").strip() else {"customer_phone": phone, "category": category},
		new_doc={
			"customer_phone": phone,
			"customer_name": name,
			"category": category,
			"app_area": app_area or "",
			"subject": _subject(subject, message),
			"priority": _PRIORITY_BY_CATEGORY.get(category, "normal"),
			"source": "app",
			"status": "open",
			"context_doctype": context_doctype or "",
			"context_name": context_name or "",
			"callback_requested": 1 if cint(callback) else 0,
			"callback_time": (callback_time or "").strip()[:40] if cint(callback) else "",
			"diagnostics_json": json.dumps(
				{"app_version": app_version, "platform": platform, "os_version": os_version}
			),
		},
		first_message=message,
		sender={"sender_phone": phone},
	)


@frappe.whitelist(allow_guest=True)
def list_my_threads(phone, status=None, page=1, limit=20):
	phone = _customer(phone)
	filters = {"customer_phone": phone}
	if status:
		filters["status"] = status
	return _page_threads(filters, page, limit)


@frappe.whitelist(allow_guest=True)
def get_thread(phone, thread_id):
	phone = _customer(phone)
	return {"success": True, "data": _format_thread(_thread_for_customer(thread_id, phone))}


@frappe.whitelist(allow_guest=True)
def get_messages(phone, thread_id, before_id=None, limit=30):
	phone = _customer(phone)
	_thread_for_customer(thread_id, phone)
	return _messages_page(thread_id, before_id, limit)


@frappe.whitelist(allow_guest=True)
def poll_messages(phone, thread_id, after_id=None):
	phone = _customer(phone)
	_thread_for_customer(thread_id, phone)
	return _poll(thread_id, after_id)


@frappe.whitelist(allow_guest=True)
def send_message(phone, thread_id, message=None, message_type="text", image_url=None):
	phone = _customer(phone)
	_rate_limit(phone)
	thread = _thread_for_customer(thread_id, phone)
	return _send_as_requester(
		thread, frappe.db.get_value("Support Thread", thread_id, "customer_name"),
		message, message_type, image_url, sender_phone=phone,
	)


@frappe.whitelist(allow_guest=True)
def mark_thread_read(phone, thread_id):
	phone = _customer(phone)
	_thread_for_customer(thread_id, phone)
	return _mark_read_by_requester(thread_id)


@frappe.whitelist(allow_guest=True)
def request_update(phone, thread_id):
	phone = _customer(phone)
	_rate_limit(phone)
	return _request_update(_thread_for_customer(thread_id, phone))


@frappe.whitelist(allow_guest=True)
def submit_csat(phone, thread_id, rating, comment=None):
	phone = _customer(phone)
	thread = _thread_for_customer(thread_id, phone)
	if thread.status not in ("resolved", "closed"):
		frappe.throw(_("You can rate this once it's resolved."))
	rating = cint(rating)
	if rating < 1 or rating > 5:
		frappe.throw(_("Rating must be between 1 and 5."))
	frappe.db.set_value("Support Thread", thread_id, {
		"csat_rating": rating, "csat_comment": (comment or "").strip()[:500],
	})
	frappe.db.commit()
	return {"success": True}


# ── merchant endpoints (dashboard) ───────────────────────────────────────────
# Authenticated as the logged-in Frappe user; every thread is scoped to an
# outlet, and access is exactly validate_restaurant_for_api's — so any admin or
# staff who can act for an outlet can see and answer its tickets.

@frappe.whitelist()
def merchant_start_thread(outlet_id, category, message, app_area=None, subject=None,
                          context_doctype=None, context_name=None, callback=None, callback_time=None):
	user = _merchant_user()
	outlet = _merchant_outlet(outlet_id, user)
	_rate_limit(user)
	message = _clean_message(message)
	_reject_abuse(message, subject)
	if not category:
		frappe.throw(_("category is required"))
	outlet_name = frappe.db.get_value("Outlet", outlet, "outlet_name") or outlet
	user_name = frappe.db.get_value("User", user, "full_name") or user
	return _open_or_join(
		match=None if (subject or "").strip() else {"outlet": outlet, "source": "dashboard", "category": category},
		new_doc={
			"requester_user": user,
			"outlet": outlet,
			# Agents see the outlet first — that is who the ticket is about.
			"customer_name": outlet_name,
			"category": category,
			"app_area": app_area or "",
			"subject": _subject(subject, message),
			"priority": _PRIORITY_BY_CATEGORY.get(category, "normal"),
			"source": "dashboard",
			"status": "open",
			"context_doctype": context_doctype or "",
			"context_name": context_name or "",
			# "Request a call back" in the merchant's New request form.
			"callback_requested": 1 if cint(callback) else 0,
			"callback_time": (callback_time or "").strip()[:40] if cint(callback) else "",
		},
		first_message=message,
		sender={"sender_user": user, "sender_name": user_name},
	)


@frappe.whitelist()
def merchant_list_threads(outlet_id, status=None, page=1, limit=20):
	user = _merchant_user()
	outlet = _merchant_outlet(outlet_id, user)
	filters = {"outlet": outlet, "source": "dashboard"}
	if status:
		filters["status"] = status
	return _page_threads(filters, page, limit)


@frappe.whitelist()
def merchant_get_thread(thread_id):
	user = _merchant_user()
	return {"success": True, "data": _format_thread(_thread_for_merchant(thread_id, user))}


@frappe.whitelist()
def merchant_get_messages(thread_id, before_id=None, limit=30):
	user = _merchant_user()
	_thread_for_merchant(thread_id, user)
	return _messages_page(thread_id, before_id, limit)


@frappe.whitelist()
def merchant_poll_messages(thread_id, after_id=None):
	user = _merchant_user()
	_thread_for_merchant(thread_id, user)
	return _poll(thread_id, after_id)


@frappe.whitelist()
def merchant_send_message(thread_id, message=None, message_type="text", image_url=None):
	user = _merchant_user()
	_rate_limit(user)
	thread = _thread_for_merchant(thread_id, user)
	return _send_as_requester(
		thread, frappe.db.get_value("User", user, "full_name") or user,
		message, message_type, image_url, sender_user=user,
	)


@frappe.whitelist()
def merchant_mark_read(thread_id):
	user = _merchant_user()
	_thread_for_merchant(thread_id, user)
	return _mark_read_by_requester(thread_id)


@frappe.whitelist()
def merchant_request_update(thread_id):
	user = _merchant_user()
	return _request_update(_thread_for_merchant(thread_id, user))


@frappe.whitelist()
def merchant_unread_count(outlet_id):
	"""Sidebar badge: staff replies this outlet hasn't read yet."""
	user = _merchant_user()
	outlet = _merchant_outlet(outlet_id, user)
	total = frappe.db.sql(
		"""SELECT COALESCE(SUM(unread_for_customer), 0) FROM `tabSupport Thread`
		   WHERE outlet = %s AND source = 'dashboard'""",
		outlet,
	)[0][0]
	return {"success": True, "data": {"unread_count": cint(total)}}


# ── agent endpoints (internal team) ──────────────────────────────────────────
# Real Frappe users holding Support Agent (or System Manager).

def _require_agent():
	# Same people as the admin dashboard (admin.check_admin_access), plus the
	# Support Agent role. Customers and merchants can never reach these.
	frappe.only_for(["System Manager", "Flamezo Supervisor", "Flamezo Admin", "Support Agent"])
	return frappe.session.user


@frappe.whitelist()
def agent_list_threads(status=None, category=None, assigned_to=None, priority=None,
                       source=None, page=1, limit=30):
	"""`source` separates the merchant queue (dashboard) from the customer one
	(app) — they must not share a queue."""
	_require_agent()
	page = max(1, cint(page))
	limit = min(cint(limit) or 30, 100)
	if status == "all":
		filters = {}
	elif status == "done":
		filters = {"status": ["in", ["resolved", "closed"]]}
	else:
		filters = {"status": status if status else ["in", list(_ACTIVE)]}
	for field, value in (("category", category), ("assigned_to", assigned_to),
	                     ("priority", priority), ("source", source)):
		if value:
			filters[field] = value
	rows = frappe.get_all(
		"Support Thread",
		filters=filters,
		fields=["name", "customer_name", "customer_phone", "requester_user", "outlet",
		        "source", "status", "priority", "category", "app_area", "subject",
		        "assigned_to", "unread_for_agent", "last_message_at", "first_response_at", "creation",
		        "reply_due_at", "callback_requested", "callback_time", "escalated_at"],
		order_by="last_message_at desc",
		limit_start=(page - 1) * limit,
		limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	return {"success": True, "data": {"threads": rows[:limit], "has_more": has_more}}


@frappe.whitelist()
def agent_get_thread(thread_id):
	"""Thread plus its full history. Opening it clears the agent's unread
	count — the agent equivalent of mark_thread_read."""
	_require_agent()
	thread = frappe.get_doc("Support Thread", thread_id)
	rows = frappe.get_all(
		"Support Message", filters={"thread": thread_id}, fields=_MSG_FIELDS,
		order_by="created_at asc, creation asc", limit_page_length=500,
	)
	frappe.db.set_value("Support Thread", thread_id, "unread_for_agent", 0, update_modified=False)
	frappe.db.commit()
	info = thread.as_dict()
	if thread.source == "dashboard":
		# The team needs a way to reach the merchant beyond the dashboard.
		from flamezo_backend.flamezo.utils.support_alerts import _merchant_email, _requester_phone

		info["requester_email"] = _merchant_email(thread)
		info["requester_phone"] = _requester_phone(thread)
	return {"success": True, "data": {
		"thread": info,
		"messages": [_format_message(m) for m in rows],
	}}


@frappe.whitelist()
def agent_assign(thread_id, user=None):
	"""Claim a thread (no user = the caller), or hand it to a colleague. Writes an
	automated line so the requester knows someone has picked it up."""
	agent = _require_agent()
	target = user or agent
	frappe.db.set_value("Support Thread", thread_id, "assigned_to", target)
	_insert_message(thread_id, "system", _("A member of the Flamezo team is now looking into your request."),
	                message_type="system")
	frappe.db.commit()
	return {"success": True, "data": {"assigned_to": target}}


@frappe.whitelist()
def agent_send_message(thread_id, message, message_type="text", payload_json=None):
	agent = _require_agent()
	message = _clean_message(message)
	_reject_abuse(message)
	thread = frappe.db.get_value("Support Thread", thread_id, ["status", "assigned_to"], as_dict=True)
	if not thread:
		frappe.throw(_("Thread not found."), frappe.DoesNotExistError)
	if not thread.assigned_to:
		# Replying is an implicit claim — the first agent to answer owns it.
		frappe.db.set_value("Support Thread", thread_id, "assigned_to", agent)
	# after_insert on Support Message updates status/counters and notifies the
	# requester, so this path and a reply typed into Desk behave identically.
	doc = _insert_message(
		thread_id, "agent", message,
		sender_user=agent,
		sender_name=frappe.db.get_value("User", agent, "full_name") or _("Flamezo Support"),
		message_type=message_type if message_type in ("text", "quick_reply", "card") else "text",
		payload_json=payload_json or "",
	)
	frappe.db.commit()
	doc.reload()
	return {"success": True, "data": _format_message(doc)}


@frappe.whitelist()
def agent_update_thread(thread_id, status=None, priority=None, category=None):
	# Only the team resolves a request — customers and merchants have no "mark
	# sorted" option. A requester replying to a resolved request reopens it.
	_require_agent()
	updates = {}
	if status:
		if status not in _STATUSES:
			frappe.throw(_("Invalid status."))
		updates["status"] = status
		if status == "resolved":
			updates["resolved_at"] = now_datetime()
		elif status == "closed":
			updates["closed_at"] = now_datetime()
	if priority:
		updates["priority"] = priority
	if category:
		updates["category"] = category
	if not updates:
		return {"success": True}
	frappe.db.set_value("Support Thread", thread_id, updates)
	if status == "resolved":
		frappe.enqueue(
			"flamezo_backend.flamezo.utils.support_alerts.notify_requester",
			queue="short", enqueue_after_commit=True,
			thread_name=thread_id, kind="resolved",
		)
		_insert_message(thread_id, "system", _(
			"We've marked {0} as resolved. Not sorted? Just reply here — it reopens and goes "
			"straight back to the team."
		).format(thread_id), message_type="system")
	frappe.db.commit()
	return {"success": True, "data": updates}
