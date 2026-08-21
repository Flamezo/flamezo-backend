# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Legacy photo backfill: shrinks full-size photos on our own CDN that were
never run through the resize/compress pipeline, so the app stops downloading
multi-hundred-KB originals for what renders as a small thumbnail/card.

Targets the two doctypes the Media Asset variant pipeline doesn't cover (see
sync_media_asset_to_owner's field_mappings in media/jobs.py):
  - Restaurant Gallery Item.url
  - Product Media.media_url   (only rows with no media_asset link)

Design, safe for a live production DB with real traffic:
  - Never touches or deletes the original object. Compressed output is
    written to a NEW key ("...-opt.webp"); the DB row only flips to point at
    it after the upload is confirmed to be smaller. Trivially reversible.
  - Keyset-paginated (cursor by `name`), not OFFSET-paginated, so it stays
    fast and correct even while rows are being inserted concurrently.
  - Commits after every batch, not once at the end, so a crash/timeout
    partway through a large run keeps whatever progress was already made
    (idempotent — the next run picks up exactly where it left off).
  - A Redis lock stops two invocations from ever running at once.
  - dry_run is a REAL dry run: it downloads + compresses to measure the
    real savings, but does not write anything to R2 or the DB.
  - Every row is wrapped individually — one bad row (corrupt image, network
    blip) is logged via frappe.log_error and skipped; it never aborts the
    whole run.
  - Product list/top-picks/chef-special Redis caches are invalidated for
    every outlet actually touched (Restaurant Gallery Item has no cache in
    front of it — get_outlet_gallery reads straight from the DB).

Usage — always canary a single outlet on a real dry run first:
  bench --site <site> execute flamezo_backend.flamezo.media.legacy_backfill.run \\
      --kwargs "{'dry_run': True, 'restaurant': 'unvind'}"

Then the real run, unrestricted, once you're happy with the numbers:
  bench --site <site> execute flamezo_backend.flamezo.media.legacy_backfill.run \\
      --kwargs "{'dry_run': False}"

Safe to stop (Ctrl+C) and re-run at any time — already-optimized and
already-skipped rows are never reprocessed.
"""

import os
import tempfile
import time

import frappe

from flamezo_backend.flamezo.media.config import get_cdn_config
from flamezo_backend.flamezo.media.storage import download_object, upload_bytes, verify_object_exists
from flamezo_backend.flamezo.media.processors import compress_image_bytes
from flamezo_backend.flamezo.api.products import invalidate_product_cache

SKIP_ABOVE_BYTES = 60 * 1024  # already small enough, not worth reprocessing
MAX_DIM = 900
QUALITY = 78
BATCH_SIZE = 25
LOCK_KEY = "legacy_photo_backfill:lock"
LOCK_TTL = 3600  # 1 hour — well above any realistic single-batch stall


def _cdn_base():
	return get_cdn_config()["base_url"].rstrip("/")


def _object_key_from_url(url):
	base = _cdn_base()
	if not url or not url.startswith(base + "/"):
		return None
	return url[len(base) + 1:]


def _acquire_lock():
	# NX-style: only set if not already held. expires=True is required here —
	# without it, get_value() can serve a stale value from frappe's
	# per-request local cache instead of asking Redis, which is exactly
	# wrong for a lock (see frappe.utils.redis_wrapper.RedisWrapper.get_value).
	if frappe.cache().get_value(LOCK_KEY, expires=True):
		return False
	frappe.cache().set_value(LOCK_KEY, "1", expires_in_sec=LOCK_TTL)
	return True


def _release_lock():
	frappe.cache().delete_key(LOCK_KEY)


def _gallery_batch(after_name, limit, restaurant=None):
	base = _cdn_base()
	conditions = ["url like %s", "url not like %s", "name > %s"]
	params = [f"{base}/%", "%-opt.webp", after_name or ""]
	if restaurant:
		conditions.append("restaurant = %s")
		params.append(restaurant)
	params.append(limit)
	return frappe.db.sql(
		f"""
		select name, restaurant, url
		from `tabOutlet Gallery Item`
		where {" and ".join(conditions)}
		order by name
		limit %s
		""",
		params,
		as_dict=True,
	)


def _product_media_batch(after_name, limit, restaurant=None):
	base = _cdn_base()
	conditions = [
		"pm.media_url like %s", "pm.media_url not like %s", "pm.name > %s",
		"(pm.media_asset is null or pm.media_asset = '')",
	]
	params = [f"{base}/%", "%-opt.webp", after_name or ""]
	if restaurant:
		conditions.append("mp.restaurant = %s")
		params.append(restaurant)
	params.append(limit)
	return frappe.db.sql(
		f"""
		select pm.name, pm.parent, pm.media_url, mp.restaurant as outlet_id
		from `tabProduct Media` pm
		left join `tabMenu Product` mp on mp.name = pm.parent
		where {" and ".join(conditions)}
		order by pm.name
		limit %s
		""",
		params,
		as_dict=True,
	)


def _process_one(object_key, dry_run):
	"""Download + maybe-compress + maybe-upload one object.

	Returns (new_url_or_none, old_size, new_size) or None if skipped.
	In dry_run mode nothing is written to R2 — new_url is the key that
	WOULD be written, purely for visibility in the report.
	"""
	if object_key.lower().endswith((".svg", ".gif", ".mp4", ".mov", ".webm")):
		return None

	info = verify_object_exists(object_key)
	if not info.get("exists"):
		return None
	old_size = info.get("size") or 0
	if old_size and old_size <= SKIP_ABOVE_BYTES:
		return None

	with tempfile.TemporaryDirectory() as tmp:
		local_path = os.path.join(tmp, "raw")
		download_object(object_key, local_path)
		with open(local_path, "rb") as f:
			raw = f.read()

	compressed, content_type, ext = compress_image_bytes(raw, max_dim=MAX_DIM, quality=QUALITY)
	if not content_type:
		return None  # compression failed (corrupt/unsupported), leave original untouched

	new_size = len(compressed)
	if new_size >= old_size:
		return None  # no win, skip

	base, _old_ext = object_key.rsplit(".", 1) if "." in object_key else (object_key, "")
	new_key = f"{base}-opt.{ext}"

	if dry_run:
		from flamezo_backend.flamezo.media.storage import get_cdn_url
		return get_cdn_url(new_key), old_size, new_size

	new_url = upload_bytes(new_key, compressed, content_type=content_type)
	return new_url, old_size, new_size


def run(dry_run=True, restaurant=None, batch_size=BATCH_SIZE, max_rows=None):
	"""Process every eligible legacy row across both doctypes, in batches,
	committing progress after each batch. Safe to re-run / resume anytime.

	Args:
		dry_run: if True, downloads+compresses to report real savings but
			writes nothing to R2 or the DB.
		restaurant: optional outlet_id to restrict to (canary a single
			outlet before running unrestricted).
		batch_size: rows fetched per query per doctype per iteration.
		max_rows: optional cap on total rows scanned this invocation
			(across both doctypes combined) — leave unset to drain fully.
	"""
	if not dry_run and not _acquire_lock():
		msg = "Another backfill run is already in progress (lock held) — skipping."
		frappe.logger().warning(msg)
		return {"summary": {"aborted": True, "reason": msg}}

	summary = {
		"dry_run": dry_run, "restaurant": restaurant,
		"gallery_updated": 0, "product_media_updated": 0,
		"skipped": 0, "errors": 0, "bytes_saved": 0, "rows_scanned": 0,
	}
	touched_outlets = set()
	samples = {"gallery": [], "product_media": []}

	try:
		# ── Restaurant Gallery Item ──
		cursor = None
		while True:
			if max_rows and summary["rows_scanned"] >= max_rows:
				break
			rows = _gallery_batch(cursor, batch_size, restaurant=restaurant)
			if not rows:
				break
			for row in rows:
				cursor = row.name
				summary["rows_scanned"] += 1
				key = _object_key_from_url(row.url)
				if not key:
					continue
				try:
					out = _process_one(key, dry_run)
				except Exception as e:
					summary["errors"] += 1
					frappe.log_error(
						title="legacy_photo_backfill: gallery row failed",
						message=f"row={row.name} key={key} error={e}",
					)
					continue
				if not out:
					summary["skipped"] += 1
					continue
				new_url, old_size, new_size = out
				summary["gallery_updated"] += 1
				summary["bytes_saved"] += old_size - new_size
				if len(samples["gallery"]) < 10:
					samples["gallery"].append(
						{"row": row.name, "restaurant": row.restaurant,
						 "old_url": row.url, "new_url": new_url,
						 "old_size": old_size, "new_size": new_size}
					)
				if not dry_run:
					frappe.db.set_value("Outlet Gallery Item", row.name, "url", new_url)
			if not dry_run:
				frappe.db.commit()
			if len(rows) < batch_size:
				break

		# ── Product Media ──
		cursor = None
		while True:
			if max_rows and summary["rows_scanned"] >= max_rows:
				break
			rows = _product_media_batch(cursor, batch_size, restaurant=restaurant)
			if not rows:
				break
			for row in rows:
				cursor = row.name
				summary["rows_scanned"] += 1
				key = _object_key_from_url(row.media_url)
				if not key:
					continue
				try:
					out = _process_one(key, dry_run)
				except Exception as e:
					summary["errors"] += 1
					frappe.log_error(
						title="legacy_photo_backfill: product media row failed",
						message=f"row={row.name} key={key} error={e}",
					)
					continue
				if not out:
					summary["skipped"] += 1
					continue
				new_url, old_size, new_size = out
				summary["product_media_updated"] += 1
				summary["bytes_saved"] += old_size - new_size
				if len(samples["product_media"]) < 10:
					samples["product_media"].append(
						{"row": row.name, "product": row.parent, "old_url": row.media_url,
						 "new_url": new_url, "old_size": old_size, "new_size": new_size}
					)
				if not dry_run:
					frappe.db.set_value("Product Media", row.name, "media_url", new_url)
					if row.outlet_id:
						touched_outlets.add(row.outlet_id)
			if not dry_run:
				frappe.db.commit()
			if len(rows) < batch_size:
				break

		if not dry_run:
			for outlet_id in touched_outlets:
				invalidate_product_cache({"restaurant": outlet_id})
			frappe.db.commit()
	finally:
		if not dry_run:
			_release_lock()

	result = {"summary": summary, "samples": samples}
	print(frappe.as_json(summary))
	return result
