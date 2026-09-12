import frappe
from frappe import _
from frappe.model.document import Document
import secrets

# Every part of a request ID means something: TOPIC-YYMMDD-XXX, e.g.
# PAY-260911-K7Q = a payment issue raised on 11 Sep 2026. The 3-character tail
# is random (not a running number), so IDs can't be guessed and don't reveal
# ticket volume; no 0/O/1/I, so they read out cleanly on a call.
# Older tickets keep their SUP- ids.
_ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_ID_PREFIX = {
	"payment": "PAY",
	"booking": "BKG",
	"offers": "OFR",
	"account": "ACC",
	"creator": "CRT",
	"crowd": "CRW",
	"technical": "TEC",
	"feedback": "FDB",
	"grievance": "GRV",
	"settlement": "STL",
	"kyc": "KYC",
	"commission": "COM",
	"menu": "MNU",
	"profile": "PRF",
	"callback": "CAL",
}


class SupportThread(Document):
	def autoname(self):
		prefix = _ID_PREFIX.get(self.category, "GEN")
		day = frappe.utils.getdate().strftime("%y%m%d")
		# 32,768 codes per topic per day; the exists() check rules out a clash.
		while True:
			name = f"{prefix}-{day}-{''.join(secrets.choice(_ID_ALPHABET) for _ in range(3))}"
			if not frappe.db.exists("Support Thread", name):
				self.name = name
				return

	def validate(self):
		# A thread belongs to either an app customer (phone + session token) or a
		# dashboard merchant (Frappe user). Exactly one identity must be present,
		# or the thread can't be routed back to whoever raised it.
		if not self.customer_phone and not self.requester_user:
			frappe.throw(_("A support thread needs a customer phone or a requester user."))

		if not self.subject:
			self.subject = _("{0} request").format((self.category or "support").replace("_", " ").title())
