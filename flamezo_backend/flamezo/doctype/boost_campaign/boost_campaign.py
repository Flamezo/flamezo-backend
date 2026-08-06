import frappe
from frappe.model.document import Document
from frappe.utils import flt, today, add_days, now


PACKAGE_CONFIG = {
	"Growth": {"budget": 2000, "ad_spend_pct": 0.70, "fee_pct": 0.30},
	"Boost":  {"budget": 5000, "ad_spend_pct": 0.70, "fee_pct": 0.30},
	"Scale":  {"budget": 10000, "ad_spend_pct": 0.70, "fee_pct": 0.30},
}

GRADE_MULTIPLIERS = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.0}
REDEMPTIONS_PER_1K_SPEND = 12
MIN_DAILY_BUDGET_PAISA = 10000  # ₹100 minimum for Meta optimization


class BoostCampaign(Document):
	def validate(self):
		self._compute_budget_split()
		self._compute_coupon_fields()
		self._validate_coordinates()
		self._validate_daily_budget()
		self._set_first_campaign_flag()
		self._compute_guarantee()

	def _compute_budget_split(self):
		config = PACKAGE_CONFIG.get(self.package_tier)
		if not config:
			return
		self.budget_total = flt(config["budget"])
		self.ad_spend_allocated = flt(self.budget_total * config["ad_spend_pct"])
		self.flamezo_fee = flt(self.budget_total * config["fee_pct"])
		self.gst_on_fee = flt(self.flamezo_fee * 0.18)

	def _compute_coupon_fields(self):
		if not self.coupon_code and self.restaurant:
			self.coupon_code = self._generate_unique_coupon_code()
		self.coupon_discount = flt(self.offer_amount)
		self.coupon_min_order = flt(self.offer_amount) * 2 if flt(self.offer_amount) > 0 else 0
		duration = int(self.campaign_duration or 14)
		self.coupon_valid_days = duration + 7

	def _generate_unique_coupon_code(self):
		"""
		Try the same hyper-local AI coupon-name generator used in Manage
		Offers/Coupons (e.g. SURTNIMAJJA for a Surat restaurant) so Boost codes
		feel local and memorable instead of robotic (BOOST-UNVND-X7K9). Falls
		back silently to the safe random format on any failure — a paid
		campaign must never get blocked by an AI call.
		"""
		ai_code = self._try_ai_coupon_code()
		if ai_code:
			return ai_code
		return self._generate_fallback_code()

	def _try_ai_coupon_code(self):
		"""
		Note: this reuses generate_suggestions() from the Manage Offers/Coupons
		AI feature, which increments the restaurant's monthly free AI-coupon
		quota as a side effect (it does NOT deduct coins — that only happens in
		the merchant-facing wrapper). So each Boost campaign consumes one of the
		restaurant's 10 free monthly AI coupon-suggestion credits, same as if
		they'd generated a suggestion themselves in Manage Offers/Coupons.
		"""
		import re
		try:
			from flamezo_backend.flamezo.services.ai.coupon_generator import generate_suggestions
			result = generate_suggestions(
				restaurant_id=self.restaurant,
				tone="attractive",
				# Boost coupons are always staff-entered/typed codes, never
				# auto-applied or combo deals — "coupon" is the matching
				# offer_type_filter value (OFFER_TYPES in coupon_generator.py),
				# not a discount_type like "flat"/"percent".
				offer_type_filter="coupon",
				count=1,
				# Boost already has a human-set discount amount (offer_amount) —
				# we only want a name, not an AI-invented discount, so the
				# food-cost/margin-safety gate (built for the case where the AI
				# picks the discount itself) doesn't apply here.
				require_food_cost=False,
			)
		except Exception:
			frappe.log_error(
				message=f"Restaurant: {self.restaurant}",
				title="Boost AI Coupon Code Generation Failed"
			)
			return None

		if not result.get("success"):
			return None

		for suggestion in result.get("suggestions") or []:
			code = re.sub(r"[^A-Z0-9_-]", "", (suggestion.get("code") or "").strip().upper())
			if len(code) >= 2 and self._coupon_code_is_unique(code):
				return code
		return None

	def _coupon_code_is_unique(self, code):
		if frappe.db.exists("Boost Campaign", {"coupon_code": code}):
			return False
		if frappe.db.exists("Coupon", {"code": code}):
			return False
		return True

	def _generate_fallback_code(self):
		"""Safe random code, used when AI generation is unavailable/exhausted/fails."""
		import random
		import string
		restaurant_short = (self.restaurant or "XX")[:8].upper().replace("-", "")
		for _ in range(50):
			suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
			candidate = f"BOOST-{restaurant_short}-{suffix}"
			if self._coupon_code_is_unique(candidate):
				return candidate
		frappe.throw("Failed to generate unique coupon code. Please try again.")

	def _validate_coordinates(self):
		"""Ensure restaurant has GPS coordinates set — required for geo-targeting."""
		if self.status == "Draft":
			return  # Don't block draft creation
		if not self.restaurant_lat or not self.restaurant_lng:
			frappe.throw(
				"Restaurant GPS coordinates are required for Boost campaigns. "
				"Please set latitude and longitude in Restaurant settings."
			)

	def _validate_daily_budget(self):
		"""Ensure daily budget meets Meta's minimum for effective optimization."""
		duration = int(self.campaign_duration or 14)
		daily_paisa = int(flt(self.ad_spend_allocated) / duration * 100)
		if daily_paisa < MIN_DAILY_BUDGET_PAISA and self.ad_spend_allocated > 0:
			min_inr = MIN_DAILY_BUDGET_PAISA / 100
			frappe.throw(
				f"Daily ad budget (₹{daily_paisa / 100:.0f}) is below Meta's minimum "
				f"of ₹{min_inr:.0f}/day. Increase the package or reduce duration."
			)

	def _set_first_campaign_flag(self):
		if self.is_new():
			existing = frappe.db.count("Boost Campaign", filters={
				"restaurant": self.restaurant,
				"status": ["not in", ["Draft", "Cancelled", "Failed"]],
			})
			self.is_first_campaign = 1 if existing == 0 else 0

	def _compute_guarantee(self):
		if self.is_first_campaign:
			self.guaranteed_redemptions = 0
			return
		grade = self.location_grade or "A"
		multiplier = GRADE_MULTIPLIERS.get(grade, 1.0)
		ad_spend_k = flt(self.ad_spend_allocated) / 1000
		self.guaranteed_redemptions = int(ad_spend_k * REDEMPTIONS_PER_1K_SPEND * multiplier)

	def get_daily_budget_paisa(self):
		"""Daily budget in paisa for Meta API (Meta uses smallest currency unit)."""
		duration = int(self.campaign_duration or 14)
		daily = flt(self.ad_spend_allocated) / duration
		return int(daily * 100)

	def mark_live(self):
		self.status = "Live"
		self.launch_date = today()
		self.end_date = add_days(today(), int(self.campaign_duration or 14))
		# Activate the linked coupon now that campaign is actually live
		if self.linked_coupon:
			frappe.db.set_value("Coupon", self.linked_coupon, "is_active", 1)
		self.save(ignore_permissions=True)

	def mark_completed(self):
		self.status = "Completed"
		self.completed_at = now()
		self.actual_redemptions = self.coupons_redeemed
		if self.guaranteed_redemptions > 0 and self.actual_redemptions >= self.guaranteed_redemptions:
			self.guarantee_met = 1
		elif self.guaranteed_redemptions > 0:
			deficit = self.guaranteed_redemptions - self.actual_redemptions
			cpr = flt(self.cost_per_redemption) or (flt(self.amount_spent_meta) / max(self.actual_redemptions, 1))
			self.topup_credit_amount = flt(deficit * cpr * 1.2)
		self.save(ignore_permissions=True)

	def apply_pending_guarantee_credit(self):
		"""
		Fold any unclaimed guarantee shortfall credit from this restaurant's past
		completed campaigns into this campaign's actual Meta ad spend — funded by
		Flamezo, not billed to the merchant. Call once, right after payment capture.
		"""
		pending = frappe.get_all("Boost Campaign",
			filters={
				"restaurant": self.restaurant,
				"status": "Completed",
				"guarantee_met": 0,
				"topup_credit_amount": [">", 0],
				"topup_credit_claimed": 0,
				"name": ["!=", self.name],
			},
			fields=["name", "topup_credit_amount"]
		)
		if not pending:
			return

		credit_total = sum(flt(row.topup_credit_amount) for row in pending)
		# Cap the bonus at 100% of this campaign's own ad spend so a large backlog
		# of credit can't silently balloon a single campaign's Meta budget.
		credit_total = min(credit_total, flt(self.ad_spend_allocated))
		if credit_total <= 0:
			return

		self.ad_spend_allocated = flt(self.ad_spend_allocated) + credit_total
		self.credit_topup_applied = credit_total
		self.db_set("ad_spend_allocated", self.ad_spend_allocated, update_modified=False)
		self.db_set("credit_topup_applied", self.credit_topup_applied, update_modified=False)

		remaining = credit_total
		for row in pending:
			claim = min(remaining, flt(row.topup_credit_amount))
			frappe.db.set_value("Boost Campaign", row.name, "topup_credit_claimed", 1, update_modified=False)
			remaining -= claim
			if remaining <= 0:
				break

	def mark_paused(self):
		self.status = "Paused"
		self.paused_at = now()
		self.save(ignore_permissions=True)

	def mark_resumed(self):
		self.status = "Live"
		self.paused_at = ""
		self.save(ignore_permissions=True)
