# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
UGC proof verifier
==================
Reads the Instagram/Facebook story view-count from the diner's uploaded
screen-recording and decides whether to auto-credit cashback or route the
claim to staff review.

Pipeline (per submission):
  1. Guard       — only run on freshly `proof_submitted` claims.
  2. Dedup       — reject claims whose proof video re-uses an already-seen hash.
  3. AI OCR      — read the view count + tamper signals from a video frame.
  4. Decision    — confident & clean  → auto-credit (credit_ugc_cashback)
                   otherwise          → flag for staff review.

NOTE (rollout): P1 ships steps 1-2 live and leaves the AI OCR (step 3) stubbed
so every claim lands in the staff `flagged` queue — a safe, fully-working manual
path. Flipping on auto-approve in P4 only means implementing `_read_view_count`
with Gemini 2.5 Flash (config.ai_provider) and frame extraction; the decision
logic below already consumes its output.
"""

import os
import json
import time
import tempfile

import frappe
from frappe.utils import cint, flt

# Prompt the vision model gets for each proof video.
_OCR_PROMPT = (
	"You are verifying a screen recording a diner submitted to claim cashback. "
	"The video should show THEIR OWN Instagram or Facebook STORY's view list / insights "
	"(the 'Seen by' / viewer count screen). Watch the whole clip and read the HIGHEST "
	"story view/seen count number that is clearly shown.\n\n"
	"Return STRICT JSON only, no prose:\n"
	"{\n"
	'  "view_count": <integer, 0 if no story view count is clearly visible>,\n'
	'  "confidence": <float 0.0-1.0, how sure you are of the number>,\n'
	'  "is_story_insights": <true only if this clearly shows a story\'s own viewer/seen list>,\n'
	'  "tamper_signals": [<zero or more of: "edited_number", "screenshot_of_screenshot", '
	'"not_a_story", "feed_post_not_story", "number_unreadable", "inconsistent_numbers">]\n'
	"}\n"
	"Be conservative: if you cannot clearly read a genuine story view count, set view_count to 0 "
	"and confidence below 0.5."
)


def verify_submission(submission_name):
	"""Entry point (enqueued from submit_ugc_proof)."""
	try:
		sub = frappe.get_doc("UGC Story Submission", submission_name)
	except frappe.DoesNotExistError:
		return

	# 1. Guard — idempotent: only process claims awaiting verification.
	if sub.status != "proof_submitted":
		return

	from flamezo_backend.flamezo.api.ugc import _get_active_config, credit_ugc_cashback

	config = _get_active_config(sub.restaurant)
	provider = (config.ai_provider if config else "Gemini") or "Gemini"
	threshold = flt(config.ai_confidence_threshold) if config else 0.85
	sub.ai_provider = provider

	# 2. Dedup — same proof video used on another live/credited claim = fraud.
	if sub.proof_video_hash:
		dup = frappe.db.exists(
			"UGC Story Submission",
			{
				"name": ["!=", sub.name],
				"proof_video_hash": sub.proof_video_hash,
				"status": ["in", ("credited", "proof_submitted", "flagged")],
			},
		)
		if dup:
			sub.status = "rejected"
			sub.rejection_reason = "Duplicate proof video (already used on another claim)."
			sub.ai_tamper_signals = "duplicate_video_hash"
			sub.save(ignore_permissions=True)
			frappe.db.commit()
			return

	# 3. AI OCR — read the view count.
	result = _read_view_count(sub, provider)

	sub.ai_view_count = cint(result.get("view_count"))
	sub.ai_confidence = flt(result.get("confidence"))
	sub.ai_tamper_signals = result.get("tamper_signals") or ""
	sub.ai_raw = result.get("raw") or ""

	# 4. Decision.
	clean = not result.get("tamper_signals")
	confident = flt(result.get("confidence")) >= threshold
	has_views = cint(result.get("view_count")) > 0

	if result.get("ready") and clean and confident and has_views:
		sub.save(ignore_permissions=True)
		frappe.db.commit()
		credit_ugc_cashback(sub, view_count=cint(result["view_count"]), source="ai")
	else:
		sub.status = "flagged"
		sub.save(ignore_permissions=True)
		frappe.db.commit()


def _read_view_count(submission, provider):
	"""
	Read the story view count from the proof video.

	Returns {ready, view_count, confidence, tamper_signals, raw}. ``ready=False``
	routes the claim to the staff queue — used whenever anything is missing,
	errors, or the provider can't process video (so auto-approve never fires on
	an unverified claim).

	Gemini 2.5 Flash reads the video directly via the Files API (no ffmpeg).
	"""
	# Only Gemini handles video natively here; OpenAI/GPT-4o would need frame
	# extraction, so it falls through to manual review for now.
	if (provider or "Gemini") != "Gemini":
		return _not_ready("Provider has no video reader — manual review.")

	object_key = None
	if submission.proof_video:
		object_key = frappe.db.get_value("Media Asset", submission.proof_video, "raw_object_key")
	if not object_key:
		return _not_ready("Proof video object not found — manual review.")

	tmp_path = None
	uploaded = None
	try:
		import google.generativeai as genai
		from flamezo_backend.flamezo.media.storage import download_object
		from flamezo_backend.flamezo.services.ai.base import get_gemini_client

		# 1. Pull the video to a temp file.
		fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
		os.close(fd)
		download_object(object_key, tmp_path)

		# 2. Configure Gemini + upload via Files API, wait until ACTIVE.
		model = get_gemini_client()  # also runs genai.configure(api_key=...)
		uploaded = genai.upload_file(path=tmp_path, mime_type="video/mp4")
		for _ in range(30):  # up to ~60s for the file to finish processing
			if uploaded.state.name == "ACTIVE":
				break
			if uploaded.state.name == "FAILED":
				return _not_ready("Gemini could not process the video — manual review.")
			time.sleep(2)
			uploaded = genai.get_file(uploaded.name)
		if uploaded.state.name != "ACTIVE":
			return _not_ready("Gemini video processing timed out — manual review.")

		# 3. Ask for the view count as strict JSON.
		resp = model.generate_content(
			[_OCR_PROMPT, uploaded],
			generation_config={"response_mime_type": "application/json", "temperature": 0},
		)
		raw = (resp.text or "").strip()
		parsed = json.loads(raw)

		tamper = list(parsed.get("tamper_signals") or [])
		if not parsed.get("is_story_insights", False):
			tamper.append("not_story_insights")

		return {
			"ready": True,
			"view_count": cint(parsed.get("view_count")),
			"confidence": flt(parsed.get("confidence")),
			"tamper_signals": ",".join(sorted(set(tamper))),
			"raw": raw[:2000],
		}
	except Exception as e:
		frappe.log_error(f"UGC view-count OCR failed for {submission.name}: {e}", "UGC")
		return _not_ready(f"OCR error — manual review. ({str(e)[:120]})")
	finally:
		try:
			if uploaded is not None:
				import google.generativeai as genai
				genai.delete_file(uploaded.name)
		except Exception:
			pass
		if tmp_path and os.path.exists(tmp_path):
			try:
				os.remove(tmp_path)
			except Exception:
				pass


def _not_ready(reason):
	return {"ready": False, "view_count": 0, "confidence": 0.0, "tamper_signals": "", "raw": reason}
