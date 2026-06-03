# Copyright (c) 2026, Flamezo and contributors
"""
End-to-end exercise of the UGC Cashback flow against the real DB.

Run:
  bench --site flamezo.localhost execute \
      flamezo_backend.flamezo.tests.test_ugc_e2e.run

Drives the full state machine (offer -> shared -> verified -> proof ->
credited / flagged / rejected), the AI auto-approve + manual-review paths,
caps, dedup, idempotency, budget, and the fraud-flag block — asserting each
outcome on its OWN order (the product enforces one active submission per
order) — then cleans up everything it created. Only customer-token auth and
the Gemini OCR are monkeypatched (no HTTP request / no live model in a script).
"""

from collections import defaultdict

import frappe
from frappe.utils import flt, cint, now_datetime

import flamezo_backend.flamezo.api.ugc as ugc
import flamezo_backend.flamezo.services.ai.ugc_verifier as verifier

RESULTS = []
CREATED_SUBMISSIONS = set()
CREATED_CONFIGS = set()
CREATED_FLAGS = set()
TOUCHED_ORDERS = []


def _check(name, cond, detail=""):
	RESULTS.append((bool(cond), name, detail))
	print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _data(res):
	return (res or {}).get("data") or {}


def _ugc_credited(customer):
	rows = frappe.get_all(
		"Restaurant Loyalty Entry",
		filters={"customer": customer, "reason": "UGC Cashback", "transaction_type": "Earn"},
		fields=["coins"],
	)
	return sum(cint(r.coins) for r in rows)


def _setup():
	"""Pick the (restaurant, customer) pair with the most completed orders."""
	rows = frappe.get_all(
		"Order",
		filters={"payment_status": "completed", "platform_customer": ["is", "set"]},
		fields=["name", "restaurant", "platform_customer", "total"],
		limit_page_length=80,
	)
	groups = defaultdict(list)
	for o in rows:
		if flt(o.total) > 0:
			groups[(o.restaurant, o.platform_customer)].append((o.name, flt(o.total)))
	if not groups:
		raise Exception("No completed orders with a platform_customer to test against.")
	(restaurant, customer), orders = max(groups.items(), key=lambda kv: len(kv[1]))
	return restaurant, customer, orders


def _ensure_config(restaurant, **overrides):
	payload = {
		"is_active": 1, "min_order_amount": 0, "max_per_customer_per_month": 50,
		"monthly_budget_coins": 0, "cashback_percent_cap": 100, "absolute_cap_coins": 100000,
		"ai_provider": "Gemini", "ai_confidence_threshold": 0.85,
		"instructions": "Tag us & keep the story live 24h", "terms": "Test terms",
	}
	payload.update(overrides)
	ugc.save_ugc_config(restaurant, payload)
	cfg = frappe.db.get_value("UGC Cashback Config", {"restaurant": restaurant}, "name")
	if cfg:
		CREATED_CONFIGS.add(cfg)
	return cfg


def _purge_order(order_id):
	"""Remove any prior UGC submissions + ledger entries for an order (clean slate)."""
	for s in frappe.get_all("UGC Story Submission", filters={"order": order_id}, fields=["name"]):
		frappe.db.delete("Restaurant Loyalty Entry",
						 {"reference_doctype": "UGC Story Submission", "reference_name": s.name})
		frappe.delete_doc("UGC Story Submission", s.name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _to_proof(restaurant, order_id, hash_val):
	"""Fresh submission driven to proof_submitted on its own order."""
	_purge_order(order_id)
	r = ugc.start_ugc_offer(restaurant, order_id)
	sub_id = _data(r).get("submission_id")
	CREATED_SUBMISSIONS.add(sub_id)
	ugc.mark_story_shared(restaurant, sub_id)
	ugc.verify_ugc_story(restaurant, sub_id, "approve")
	sub = frappe.get_doc("UGC Story Submission", sub_id)
	sub.status = "proof_submitted"; sub.proof_video_hash = hash_val; sub.proof_submitted_at = now_datetime()
	sub.save(ignore_permissions=True); frappe.db.commit()
	return sub_id


def run():
	try:
		_run()
	finally:
		_summary()
		_cleanup()


def _run():
	restaurant, customer, orders = _setup()
	TOUCHED_ORDERS.extend([o[0] for o in orders])
	ugc.get_customer_token = lambda: "test-token"
	ugc.get_customer_from_token = lambda t: customer
	print(f"\n=== UGC E2E  restaurant={restaurant}  customer={customer}  orders={len(orders)} ===\n")

	cfg = _ensure_config(restaurant)
	for oid, _ in orders:
		_purge_order(oid)

	# ── Scenario A: happy path on order[0] ───────────────────────────────────
	o0, amt0 = orders[0]
	r = ugc.get_ugc_eligibility(restaurant, o0)
	_check("eligible when config active", _data(r).get("eligible") is True)
	_check("max_cashback capped at order amount", cint(_data(r).get("max_cashback")) == int(amt0))

	r = ugc.start_ugc_offer(restaurant, o0)
	sub0 = _data(r).get("submission_id"); CREATED_SUBMISSIONS.add(sub0)
	_check("start creates submission (offer_shown)",
		   frappe.db.get_value("UGC Story Submission", sub0, "status") == "offer_shown")
	_check("start is idempotent", _data(ugc.start_ugc_offer(restaurant, o0)).get("submission_id") == sub0)

	ugc.mark_story_shared(restaurant, sub0)
	_check("mark_shared → story_shared",
		   frappe.db.get_value("UGC Story Submission", sub0, "status") == "story_shared")
	_check("in story-verification queue",
		   sub0 in [s["name"] for s in _data(ugc.list_pending_story_verifications(restaurant)).get("submissions", [])])

	ugc.verify_ugc_story(restaurant, sub0, "approve")
	_check("staff verify → story_verified",
		   frappe.db.get_value("UGC Story Submission", sub0, "status") == "story_verified")

	# proof gate: requests before verify should be blocked
	blocked = ugc.request_ugc_video_upload(restaurant, sub0, "x.mp4", "video/mp4", 1000)
	_check("upload allowed once verified", blocked.get("success") is True or blocked.get("error") != "STORY_NOT_VERIFIED")

	sub = frappe.get_doc("UGC Story Submission", sub0)
	sub.status = "proof_submitted"; sub.proof_video_hash = "hash-A"; sub.proof_submitted_at = now_datetime()
	sub.save(ignore_permissions=True); frappe.db.commit()

	start_credited = _ugc_credited(customer)
	verifier._read_view_count = lambda s, p: {"ready": True, "view_count": 250, "confidence": 0.95, "tamper_signals": "", "raw": "{}"}
	verifier.verify_submission(sub0)
	sub = frappe.get_doc("UGC Story Submission", sub0)
	_check("AI auto-approve → credited", sub.status == "credited", f"status={sub.status}")
	_check("cashback = min(views, order)", cint(sub.cashback_coins) == min(250, int(amt0)), f"coins={sub.cashback_coins}")
	_check("loyalty entry linked", bool(sub.reward_entry))
	_check("wallet grew by cashback", _ugc_credited(customer) == start_credited + cint(sub.cashback_coins))
	after = _ugc_credited(customer)
	verifier.verify_submission(sub0)  # re-run
	_check("idempotent — no double credit", _ugc_credited(customer) == after)

	# ── Scenario B: low confidence → flagged → manual review credits ─────────
	if len(orders) > 1:
		o1, _ = orders[1]
		sub1 = _to_proof(restaurant, o1, "hash-B")
		verifier._read_view_count = lambda s, p: {"ready": True, "view_count": 300, "confidence": 0.40, "tamper_signals": "", "raw": "{}"}
		verifier.verify_submission(sub1)
		_check("low confidence → flagged", frappe.db.get_value("UGC Story Submission", sub1, "status") == "flagged")
		_check("in flagged queue", sub1 in [s["name"] for s in _data(ugc.list_flagged_ugc(restaurant)).get("submissions", [])])
		before = _ugc_credited(customer)
		ugc.review_ugc(restaurant, sub1, "approve", view_count=180)
		s1 = frappe.get_doc("UGC Story Submission", sub1)
		_check("manual review credits 180", s1.status == "credited" and cint(s1.cashback_coins) == 180)
		_check("wallet grew by manual 180", _ugc_credited(customer) == before + 180)

	# ── Scenario C: tamper signal → flagged even if confident ────────────────
	if len(orders) > 2:
		sub2 = _to_proof(restaurant, orders[2][0], "hash-C")
		verifier._read_view_count = lambda s, p: {"ready": True, "view_count": 500, "confidence": 0.99, "tamper_signals": "edited_number", "raw": "{}"}
		verifier.verify_submission(sub2)
		_check("tamper → flagged", frappe.db.get_value("UGC Story Submission", sub2, "status") == "flagged")

	# ── Scenario D: duplicate proof hash → rejected ──────────────────────────
	if len(orders) > 4:
		_to_proof(restaurant, orders[3][0], "dup-hash")           # A stays proof_submitted
		subB = _to_proof(restaurant, orders[4][0], "dup-hash")    # B reuses the hash
		verifier._read_view_count = lambda s, p: {"ready": True, "view_count": 100, "confidence": 0.99, "tamper_signals": "", "raw": "{}"}
		verifier.verify_submission(subB)
		_check("duplicate proof hash → rejected", frappe.db.get_value("UGC Story Submission", subB, "status") == "rejected")

	# ── Scenario E: fraud-flagged customer blocked (fresh order) ─────────────
	if len(orders) > 5:
		o5, _ = orders[5]; _purge_order(o5)
		flag = frappe.get_doc({"doctype": "UGC Fraud Flag", "customer": customer, "is_active": 1, "reason": "test"}).insert(ignore_permissions=True)
		CREATED_FLAGS.add(flag.name); frappe.db.commit()
		_check("fraud-flagged → not eligible", _data(ugc.get_ugc_eligibility(restaurant, o5)).get("eligible") is False)
		frappe.db.set_value("UGC Fraud Flag", flag.name, "is_active", 0); frappe.db.commit()

	# ── Scenario F: budget exhausted (fresh order) ───────────────────────────
	if len(orders) > 6:
		o6, _ = orders[6]; _purge_order(o6)
		frappe.db.set_value("UGC Cashback Config", cfg, {"monthly_budget_coins": 5, "coins_issued_this_month": 5})
		frappe.db.commit()
		r = ugc.get_ugc_eligibility(restaurant, o6)
		_check("budget exhausted → not eligible", _data(r).get("eligible") is False, _data(r).get("reason", ""))
		frappe.db.set_value("UGC Cashback Config", cfg, {"monthly_budget_coins": 0, "coins_issued_this_month": 0}); frappe.db.commit()

	# ── Scenario G: test R2 storage cleanup on rejection/expiration ──────────
	if len(orders) > 7:
		o7, _ = orders[7]; _purge_order(o7)
		sub_id = _to_proof(restaurant, o7, "cleanup-test-hash")
		
		# Force schema reload to pick up select options
		frappe.reload_doc("flamezo", "doctype", "media_asset", force=True)
		
		# Create a dummy Media Asset to represent the proof video
		asset = frappe.get_doc({
			"doctype": "Media Asset",
			"media_id": "test_cleanup_media",
			"restaurant": restaurant,
			"owner_doctype": "UGC Story Submission",
			"owner_name": sub_id,
			"media_role": "ugc_proof_video",
			"media_kind": "video",
			"source_filename": "proof.mp4",
			"source_mime_type": "video/mp4",
			"source_size_bytes": 100,
			"storage_provider": "cloudflare_r2",
			"raw_object_key": "restaurants/test/menu_product/test/test_cleanup_media/raw.mp4",
			"primary_url": "http://localhost/proof.mp4",
			"status": "uploaded",
			"is_active": 1,
		})
		asset.insert(ignore_permissions=True)
		frappe.db.commit()
		
		# Link proof video to submission
		frappe.db.set_value("UGC Story Submission", sub_id, "proof_video", asset.name)
		frappe.db.commit()
		
		# Mock delete_object to avoid live network call
		import flamezo_backend.flamezo.doctype.ugc_story_submission.ugc_story_submission as doc_module
		orig_delete = doc_module.delete_object
		deleted_keys = []
		doc_module.delete_object = lambda key: deleted_keys.append(key)
		
		try:
			# Modify status to rejected
			sub_doc = frappe.get_doc("UGC Story Submission", sub_id)
			sub_doc.status = "rejected"
			sub_doc.save(ignore_permissions=True)
			frappe.db.commit()
			
			# Assertions
			_check("cleanup: Media Asset deleted from DB", not frappe.db.exists("Media Asset", asset.name))
			_check("cleanup: proof_video field cleared on submission", sub_doc.proof_video is None)
			_check("cleanup: delete_object called with raw key", len(deleted_keys) == 1 and deleted_keys[0] == asset.raw_object_key)
		finally:
			doc_module.delete_object = orig_delete

	# ── Analytics sanity ─────────────────────────────────────────────────────
	ad = _data(ugc.get_ugc_analytics(restaurant, days=30))
	_check("analytics counts credited + reach", cint(ad.get("coins_issued")) > 0 and cint(ad.get("reach_impressions")) > 0,
		   f"issued={ad.get('coins_issued')} reach={ad.get('reach_impressions')} approval={ad.get('approval_rate')}%")


def _summary():
	passed = sum(1 for ok, _, _ in RESULTS if ok)
	print(f"\n=== {passed}/{len(RESULTS)} checks passed ===")
	for ok, name, _ in RESULTS:
		if not ok:
			print(f"   ✗ {name}")


def _cleanup():
	print("\n--- cleanup ---")
	try:
		for oid in TOUCHED_ORDERS:
			for s in frappe.get_all("UGC Story Submission", filters={"order": oid}, fields=["name"]):
				frappe.db.delete("Restaurant Loyalty Entry",
								 {"reference_doctype": "UGC Story Submission", "reference_name": s.name})
				frappe.delete_doc("UGC Story Submission", s.name, force=True, ignore_permissions=True)
		for flag in list(CREATED_FLAGS):
			frappe.delete_doc("UGC Fraud Flag", flag, force=True, ignore_permissions=True)
		for cfg in list(CREATED_CONFIGS):
			frappe.delete_doc("UGC Cashback Config", cfg, force=True, ignore_permissions=True)
		frappe.db.commit()
		print("cleanup done.")
	except Exception as e:
		print(f"cleanup warning: {e}")
