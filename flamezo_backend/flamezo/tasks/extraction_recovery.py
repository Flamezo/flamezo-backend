# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Scheduled safety net for Menu Image Extractor.

Worker restarts, OOM kills, or transient DB failures can occasionally leave an
extraction doc in 'Processing' status with no in-flight job to advance it. The
frontend self-heals via recover_extraction when polling sees a 30s stall, but
that only helps users who still have the page open.

This scheduled task sweeps the database every few minutes and calls
recover_extraction() on any doc that:
  - is in 'Processing' status, AND
  - hasn't been modified for >5 minutes (i.e. clearly stalled, not actively
    progressing through batches).

recover_extraction handles both cases:
  - all batches actually finished → re-run aggregation → 'Pending Approval'
  - truly stuck for >5 min → mark 'Failed' so the user can retry
"""

import frappe
from frappe.utils import now_datetime, add_to_date


def recover_stuck_extractions():
	"""Scan for stuck Menu Image Extractor docs and try to recover each one."""
	from flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor import (
		recover_extraction,
	)

	threshold = add_to_date(now_datetime(), minutes=-5)

	stuck = frappe.get_all(
		"Menu Image Extractor",
		filters={
			"extraction_status": "Processing",
			"modified": ["<", threshold],
		},
		fields=["name", "modified", "completed_batches", "total_batches"],
		limit=50,
	)

	if not stuck:
		return

	recovered = 0
	for doc in stuck:
		try:
			result = recover_extraction(doc["name"])
			if isinstance(result, dict) and result.get("recovered"):
				recovered += 1
				frappe.logger().info(
					f"[extraction_recovery] recovered {doc['name']}: {result.get('reason')}"
				)
		except Exception as e:
			frappe.log_error(
				title="Extraction Recovery Sweep Error",
				message=f"Failed to recover {doc['name']}: {str(e)}",
			)

	if recovered:
		frappe.logger().info(
			f"[extraction_recovery] swept {len(stuck)} stuck docs, recovered {recovered}"
		)
