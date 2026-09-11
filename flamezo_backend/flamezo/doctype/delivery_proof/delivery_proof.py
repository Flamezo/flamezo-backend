# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

NATIVE_TYPES = {"native_chills", "native_club_post"}
INSTAGRAM_TYPES = {"instagram_reel", "instagram_story"}


class DeliveryProof(Document):
	def validate(self):
		self._validate_evidence_matches_type()

	def _validate_evidence_matches_type(self):
		if self.deliverable_type in NATIVE_TYPES:
			if not self.native_post_id:
				frappe.throw(_("A native deliverable needs native_post_id."), frappe.ValidationError)
			if self.verification_method != "native_first_party" and self.verification_method != "manual":
				frappe.throw(_("A native deliverable can't be verified via graph_api."), frappe.ValidationError)
		elif self.deliverable_type in INSTAGRAM_TYPES:
			if not self.instagram_media_id:
				frappe.throw(_("An Instagram deliverable needs instagram_media_id."), frappe.ValidationError)
			if self.deliverable_type == "instagram_story" and not self.screenshot_backup:
				frappe.throw(
					_("Stories expire in 24h and aren't always API-visible after — attach a screenshot backup."),
					frappe.ValidationError,
				)
		if not self.verified_at:
			self.verified_at = now_datetime()
