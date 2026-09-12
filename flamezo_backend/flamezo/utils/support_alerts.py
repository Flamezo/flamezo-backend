"""WhatsApp alerts to the internal support team.

The team works from their phones, not Frappe Desk, so every request a customer
or merchant raises is pushed to the numbers in site_config:

	"support_alert_whatsapp_numbers": ["7621014593", "..."]

Sent through the official Meta WhatsApp Cloud API — the same proven path as
the bill-paid and booking messages (whatsapp_utils.send_whatsapp_cloud_message,
credentials from site_config). Meta only allows business-initiated messages
through an APPROVED template, so alerts use the utility template named in
site_config "support_alert_whatsapp_template" (default flamezo_team_request_alert):

	[header] Ticket needs a reply
	Support ticket {{1}} is waiting for a reply. / Raised by: {{2}} / Category: {{3}}
	Subject: {{4}} / Priority: {{5}} / Latest message: "{{6}}"  [footer] Flamezo Support Desk
	[button] Open ticket -> https://backend.flamezo.in/app/support-thread/{{1}}

Template params may not contain newlines, so each detail fills one param.
Every failed send is written to the Error Log ("Support Team Alert") — alerts
never fail silently. Sending only ever goes to the configured team numbers.
Nothing here writes to the database.
"""

import json
import re

import frappe
from frappe.utils import format_datetime

from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone

DEFAULT_TEMPLATE = "flamezo_team_request_alert"

# What the requester picked, in words the team reads at a glance.
_CATEGORY_LABELS = {
	"payment": "Payment",
	"booking": "Booking",
	"offers": "Offers & cashback",
	"account": "Account",
	"creator": "Creator collabs",
	"crowd": "Crowd & Clubs",
	"technical": "App not working",
	"feedback": "Feedback",
	"grievance": "Grievance",
	"settlement": "Settlement / payout",
	"kyc": "KYC & onboarding",
	"commission": "Commission & fees",
	"menu": "Menu & offers",
	"profile": "Outlet profile",
	"other": "Something else",
	"callback": "Call back request",
}

_THREAD_FIELDS = [
	"name", "source", "status", "priority", "category", "app_area", "subject",
	"customer_name", "customer_phone", "requester_user", "outlet",
	"context_doctype", "context_name", "diagnostics_json", "reply_due_at", "assigned_to",
	"callback_requested", "callback_time",
]


def _fmt_phone(p):
	"""'+91 81413 53466' — readable; WhatsApp still makes it tappable."""
	d = normalize_phone(str(p or ""))
	if len(d) == 12 and d.startswith("91"):
		d = d[2:]
	return f"+91 {d[:5]} {d[5:]}" if len(d) == 10 else str(p or "")


def _team_numbers():
	raw = frappe.conf.get("support_alert_whatsapp_numbers") or []
	if isinstance(raw, str):
		raw = [n for n in raw.split(",")]
	out = []
	for n in raw:
		digits = normalize_phone(str(n).strip())
		if len(digits) == 10:
			out.append("91" + digits)
		elif len(digits) == 12 and digits.startswith("91"):
			out.append(digits)
	return out


# ── the facts about a ticket (shared by WhatsApp params and Desk text) ───────

def _facts(thread_name):
	"""Who, contact, about, subject, linked record, device, priority — each as
	one short string, or "" when unknown."""
	t = frappe.db.get_value("Support Thread", thread_name, _THREAD_FIELDS, as_dict=True)
	if not t:
		return None, {}
	f = {}
	if t.source == "dashboard":
		outlet = frappe.db.get_value("Outlet", t.outlet, "outlet_name") if t.outlet else None
		name = t.customer_name or outlet or t.requester_user or "Unknown"
		f["who"] = f"Merchant · {name}" + (f" ({outlet})" if outlet and outlet != name else "")
		# Contact = the merchant's phone (the number we WhatsApp them on) and
		# their email — the login's email, else the outlet's. Only a fake
		# placeholder (@example.com) is skipped; the team always gets an email.
		email = _merchant_email(t)
		phone = _requester_phone(t)
		f["contact"] = " · ".join(x for x in (_fmt_phone(phone) if phone else None, email) if x)
	else:
		f["who"] = f"Customer · {t.customer_name or 'Unknown'}"
		f["contact"] = _fmt_phone(t.customer_phone) if t.customer_phone else ""
	about = _CATEGORY_LABELS.get(t.category, t.category or "Support")
	if t.app_area:
		about += f" · from the {t.app_area.replace('_', ' ')} screen"
	f["about"] = about
	f["subject"] = t.subject or ""
	f["linked"] = f"{t.context_doctype} {t.context_name}" if t.context_doctype and t.context_name else ""
	f["device"] = _device(t)
	due = f" · reply due {format_datetime(t.reply_due_at, 'h:mm a, d MMM')}" if t.reply_due_at else ""
	f["priority"] = f"{(t.priority or 'normal').upper()}{due}"
	f["callback"] = f"Requested ({t.callback_time or 'anytime'})" if t.get("callback_requested") else ""
	return t, f


def _merchant_email(t):
	def real(e):
		return e if e and "@" in e and not e.endswith("@example.com") else None

	email = real(frappe.db.get_value("User", t.requester_user, "email")) if t.requester_user else None
	if not email and t.outlet:
		meta = frappe.get_meta("Outlet")
		for field in ("owner_email", "email", "contact_email"):
			if meta.has_field(field):
				email = real(frappe.db.get_value("Outlet", t.outlet, field))
				if email:
					break
	return email


def _device(t):
	try:
		d = json.loads(t.diagnostics_json) if t.diagnostics_json else {}
	except Exception:
		return ""
	parts = [
		" ".join(x for x in (d.get("platform"), d.get("os_version")) if x),
		f"app {d['app_version']}" if d.get("app_version") else "",
	]
	return " · ".join(p for p in parts if p)


def _headline(t, first):
	if first and t.category == "feedback":
		return f"💡 New feedback {t.name}"
	if first:
		return f"🆕 New {(t.priority or 'normal').upper()} support request {t.name}"
	return f"💬 {t.customer_name or 'The requester'} wrote again on {t.name}"


def _link(thread_name):
	# The admin dashboard's Support Requests page — the team works there, not Desk.
	return f"{frappe.utils.get_url()}/flamezo_backend/admin/support/{thread_name}"


def _last_from(thread_name, sender_type):
	row = frappe.get_all(
		"Support Message",
		filters={"thread": thread_name, "sender_type": sender_type},
		fields=["message"], order_by="creation desc", limit=1,
	)
	return (row[0].message or "").strip() if row else ""


# ── Desk bell text (multi-line, full picture) ────────────────────────────────

def _detail_lines(f):
	lines = [f"From: {f['who']}"]
	if f.get("contact"):
		lines.append(f"Contact: {f['contact']}")
	lines.append(f"About: {f['about']}")
	for label, key in (("Subject", "subject"), ("Linked record", "linked"), ("Device", "device"), ("Call back", "callback")):
		if f.get(key):
			lines.append(f"{label}: {f[key]}")
	lines.append(f"Priority: {f['priority']}")
	return lines


def build_alert_text(thread_name, message, first):
	"""A new request, or the requester writing again: the full picture."""
	t, f = _facts(thread_name)
	if not t:
		return f"Support request {thread_name}: {(message or '').strip()[:300]}"
	lines = [_headline(t, first), *_detail_lines(f), "", "What they said:", f"\"{(message or '').strip()[:700]}\""]
	if not first:
		last_team = _last_from(t.name, "agent")
		if last_team:
			lines += ["", f"Team's last reply: \"{last_team[:200]}\""]
	lines += ["", f"Open & reply: {_link(t.name)}"]
	return "\n".join(lines)


def ticket_alert_text(thread_name, headline):
	"""Something the requester did that isn't a message (asked for an update,
	escalated), with the same full picture and what they last said."""
	t, f = _facts(thread_name)
	lines = [headline, *(_detail_lines(f) if t else [])]
	last = _last_from(thread_name, "customer")
	if last:
		lines += ["", f"Their last message: \"{last[:400]}\""]
	lines += ["", f"Open & reply: {_link(thread_name)}"]
	return "\n".join(lines)


# ── WhatsApp (Meta template) ─────────────────────────────────────────────────

def _one_line(s, limit):
	"""Meta rejects template params containing newlines, tabs or 4+ spaces."""
	s = re.sub(r"\s+", " ", str(s or "")).strip()
	if not s:
		return "-"
	return s if len(s) <= limit else s[: limit - 1] + "…"


def _what(t, first, headline):
	"""What just happened, for the Priority line: 'new request', 'escalated…'."""
	if headline:  # e.g. "update requested", "escalated, reply overdue"
		return headline
	if first:
		if t.category == "feedback":
			return "new feedback"
		if t.category == "callback":
			return f"📞 new call request ({t.get('callback_time') or 'anytime'})"
		if t.get("callback_requested"):
			return f"new request · call back requested ({t.get('callback_time') or 'anytime'})"
		return "new request"
	return "merchant wrote again" if t.source == "dashboard" else "customer wrote again"


def _first_from(thread_name, sender_type):
	row = frappe.get_all(
		"Support Message",
		filters={"thread": thread_name, "sender_type": sender_type},
		fields=["message"], order_by="creation asc", limit=1,
	)
	return (row[0].message or "").strip() if row else ""


def alert_params(thread_name, message=None, first=False, headline=None):
	"""The six body params, laid out for a phone screen:
	{{1}} ticket ID · {{2}} "Name (Merchant) · +91 phone · email" ·
	{{3}} category · {{4}} subject ("Not given" when the requester wrote none —
	never a copy of the message) · {{5}} "URGENT · new request · reply due …" ·
	{{6}} their message. The link is the template's "Open ticket" button."""
	t, f = _facts(thread_name)
	if not t:
		return [_one_line(headline or thread_name, 120), "-", "-", "-", "-", _one_line(message, 600)]
	kind = "Merchant" if t.source == "dashboard" else "Customer"
	who = f"{f['who'].split(' · ', 1)[-1]} ({kind})" + (f" · {f['contact']}" if f.get("contact") else "")
	category = " · ".join(x for x in (f["about"], f.get("linked")) if x)
	said = message if message is not None else _last_from(thread_name, "customer")
	# A subject auto-made from the message (support._subject: the first 80
	# characters, for requests sent without one) would just repeat {{6}} — say
	# so plainly. Only an exact auto-copy counts; a typed subject always shows.
	subject = (f.get("subject") or "").strip()
	opening = _first_from(thread_name, "customer")
	if not subject or (opening and subject == opening[:80].strip()):
		subject = "Not given"
	due = f" · reply due {format_datetime(t.reply_due_at, 'h:mm a, d MMM')}" if t.reply_due_at else ""
	return [
		_one_line(t.name, 40),
		_one_line(who, 160),
		_one_line(category, 160),
		_one_line(subject, 140),
		_one_line(f"{(t.priority or 'normal').upper()} · {_what(t, first, headline)}{due}", 120),
		_one_line(said, 600),
	]


def send_team_alert(thread_name, message=None, first=False, headline=None):
	"""WhatsApp every team number about this ticket. Returns [(number, ok, info)].

	Runs as a background job (queued after commit) so a slow WhatsApp API never
	delays the requester, and the alert can't outrun the row it describes.
	"""
	numbers = _team_numbers()
	if not numbers:
		return []
	from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message

	template = frappe.conf.get("support_alert_whatsapp_template") or DEFAULT_TEMPLATE
	params = alert_params(thread_name, message, first, headline)
	results = []
	for number in numbers:
		# The button's URL is fixed in the template; we fill in the ticket ID.
		ok, info = send_whatsapp_cloud_message(number, template, params, button_url_param=thread_name)
		results.append((number, ok, info))
		if not ok:
			# Usual causes: the template isn't approved yet, or the token expired.
			frappe.log_error(title="Support Team Alert", message=f"Support alert {thread_name} to …{number[-4:]} failed ({template}): {info}")
	return results


# ── WhatsApp to the requester (customer or merchant) ─────────────────────────
#
# The requester hears on their own WhatsApp, even with the app closed, when
# their request is created and when it's resolved. Team replies reach them by
# app notification only (no WhatsApp) — deliberately, to avoid noise. Same Meta Cloud path and
# approved UTILITY templates; names overridable in site_config.

_REQUESTER_TEMPLATES = {
	# Same wording as the in-app messages:
	# Hi {{1}}, your request has been forwarded ... Subject: {{2}} ... by {{3}} ... ID is *{{4}}*
	"created": "flamezo_support_created",
	# Hi {{1}}, we've marked your request *{{2}}* as resolved. Subject: {{3}} ...
	"resolved": "flamezo_support_resolved",
}


def _outlet_phone(outlet, fields):
	for field in fields:
		v = frappe.db.get_value("Outlet", outlet, field)
		if v:
			return v
	return None


def _requester_phone(t):
	"""Customer: the phone they raised it from. Merchant: the outlet's WhatsApp
	number, else their own mobile, else the outlet owner / contact phone."""
	if t.source == "dashboard":
		return (
			(_outlet_phone(t.outlet, ("whatsapp_number",)) if t.outlet else None)
			or (frappe.db.get_value("User", t.requester_user, "mobile_no") if t.requester_user else None)
			or (_outlet_phone(t.outlet, ("owner_phone", "contact_phone")) if t.outlet else None)
		)
	return t.customer_phone


def _first_name(t):
	name = (t.customer_name or "").strip()
	return name.split()[0] if name else "there"


def _due_words(t):
	"""'4:28 PM today' / '4:28 PM, 11 Sep' — same as the in-app message. If no
	due time is stored yet, work it out from the priority."""
	from frappe.utils import add_to_date, get_datetime, now_datetime

	from flamezo_backend.flamezo.doctype.support_message.support_message import REPLY_HOURS

	due = get_datetime(t.reply_due_at) if t.reply_due_at else add_to_date(
		now_datetime(), hours=REPLY_HOURS.get(t.priority or "normal", 24)
	)
	if due.date() == now_datetime().date():
		return f"{format_datetime(due, 'h:mm a')} today"
	return format_datetime(due, "h:mm a, d MMM")


def notify_requester(thread_name, kind, text=None):
	"""WhatsApp the requester about `kind` ("created" | "resolved").

	Not called `event`: frappe.enqueue reserves that keyword for itself and
	never passes it to the job, which made every call fail. Background job; every failure lands in the Error Log."""
	template = frappe.conf.get(f"support_{kind}_whatsapp_template") or _REQUESTER_TEMPLATES.get(kind)
	t, f = _facts(thread_name)
	if not t or not template:
		return None
	if kind == "created" and t.category == "feedback":
		# "You'll hear back by ..." doesn't fit feedback; the team is still alerted.
		return None
	phone = _requester_phone(t)
	if not phone:
		frappe.log_error(title="Support Requester WhatsApp", message=f"No WhatsApp number for the requester of {thread_name}")
		return None
	# The requester's own subject line (falls back to the category).
	subject = _one_line(f.get("subject") or f["about"].split(" · ")[0], 140)
	if kind == "created":
		params = [_first_name(t), subject, _due_words(t), t.name]
	else:
		params = [_first_name(t), t.name, subject]
	params = [_one_line(p, 600) for p in params]

	from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message

	ok, info = send_whatsapp_cloud_message(phone, template, params)
	if not ok:
		frappe.log_error(title="Support Requester WhatsApp", message=f"Requester WhatsApp '{kind}' for {thread_name} failed ({template}): {info}")
	return ok, info
