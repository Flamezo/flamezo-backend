# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Centralised media cleanup.

`cleanup_media_for_owner` is registered as an `on_trash` doc-event for every
media-owning DocType (see hooks.py). When such a document is deleted, ALL of
its Media Assets — and their Cloudflare R2 objects (raw + variants + poster) —
are removed, so deleting an Offer / Event / Restaurant Config / Home Feature /
AI image / Legacy record never leaves orphaned files in storage.

It reuses the standard media pipeline (`delete_media_asset` → soft-delete +
async `cleanup_deleted_media`) and falls back to a synchronous hard delete if
that path raises (e.g. permission/restaurant-context edge cases in a job).
"""

import frappe


def cleanup_media_for_owner(doc, method=None):
	"""Delete every Media Asset (and its R2 objects) owned by ``doc``."""
	try:
		assets = frappe.get_all(
			"Media Asset",
			filters={"owner_doctype": doc.doctype, "owner_name": doc.name},
			fields=["name", "media_id", "is_deleted"],
		)
	except Exception:
		return

	for a in assets:
		if a.get("is_deleted"):
			continue
		# Preferred path: standard soft-delete + async R2 cleanup.
		try:
			if a.get("media_id"):
				from flamezo_backend.flamezo.media.api import delete_media_asset
				delete_media_asset(a["media_id"])
				continue
		except Exception:
			pass
		# Fallback: synchronous hard delete of R2 objects + the doc.
		try:
			_hard_delete_asset(a["name"])
		except Exception as e:
			frappe.log_error(
				f"Media cleanup failed for {a['name']} ({doc.doctype} {doc.name}): {e}",
				"Media Cleanup",
			)


def _hard_delete_asset(asset_name):
	"""Delete an asset's raw object + variants + poster from R2, then the doc."""
	from flamezo_backend.flamezo.media.storage import delete_object

	info = frappe.db.get_value(
		"Media Asset", asset_name, ["raw_object_key", "poster_object_key"], as_dict=True
	) or {}

	for variant_key in frappe.get_all("Media Variant", filters={"parent": asset_name}, pluck="object_key"):
		if variant_key:
			try:
				delete_object(variant_key)
			except Exception:
				pass

	for key in (info.get("raw_object_key"), info.get("poster_object_key")):
		if key:
			try:
				delete_object(key)
			except Exception:
				pass

	frappe.delete_doc("Media Asset", asset_name, ignore_permissions=True, force=True)
