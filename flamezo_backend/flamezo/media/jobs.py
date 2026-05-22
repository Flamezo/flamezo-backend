# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

"""
Background jobs for media processing
"""

import frappe
from frappe.utils import now_datetime
from flamezo_backend.flamezo.utils.common import safe_log_error, retry_on_deadlock
from .storage import download_object, upload_object, delete_object, get_cdn_url, calculate_file_hash, generate_object_key
from .processors import process_image, process_video
import os
import tempfile


def process_media_asset(media_asset_name):
	"""
	Process a media asset: generate optimized variants and sync URLs back to owner.

	This job is idempotent and self-healing:
	  - Skips if already `ready`.
	  - The inner DB-touching parts (variant save, owner sync, status flips) each
	    retry transparently on MySQL deadlocks / lock-wait timeouts.
	  - Re-uploading variants to R2 on retry is safe because object keys are
	    deterministic from the asset name + variant name (upsert semantics).
	"""
	from pymysql.err import OperationalError  # local import to avoid hard dep at module load

	def _is_transient(err):
		args = getattr(err, "args", None)
		if args and isinstance(args, tuple) and args and isinstance(args[0], int) and args[0] in (1213, 1205):
			return True
		m = str(err).lower()
		return "deadlock" in m or "lock wait timeout" in m

	max_attempts = 4
	last_err = None

	for attempt in range(max_attempts):
		try:
			asset = frappe.get_doc("Media Asset", media_asset_name)

			# Idempotency: if a previous attempt finished, nothing to do.
			if asset.status == "ready":
				frappe.logger().info(f"Media asset {asset.media_id} already processed")
				return

			asset.mark_as_processing()

			with tempfile.TemporaryDirectory() as temp_dir:
				raw_file_path = os.path.join(temp_dir, asset.source_filename)
				download_object(asset.raw_object_key, raw_file_path)

				if not asset.source_sha256:
					asset.source_sha256 = calculate_file_hash(raw_file_path)

				if asset.media_kind == "image":
					process_image_asset(asset, raw_file_path, temp_dir)
				elif asset.media_kind == "video":
					process_video_asset(asset, raw_file_path, temp_dir)
				else:
					raise Exception(f"Unsupported media kind: {asset.media_kind}")

				asset.mark_as_ready()
				sync_media_asset_to_owner(asset)

			frappe.logger().info(f"Successfully processed media asset {asset.media_id}")
			return

		except OperationalError as e:
			last_err = e
			if not _is_transient(e) or attempt >= max_attempts - 1:
				break
			try:
				frappe.db.rollback()
			except Exception:
				pass
			# Backoff: 0.2s, 0.6s, 1.4s + jitter — gives the contending txn time to drain.
			import time as _t
			import random as _r
			_t.sleep(0.2 + 0.4 * attempt + _r.random() * 0.3)
			continue

		except Exception as e:
			last_err = e
			# Generic deadlock check (wrapped in non-OperationalError sometimes)
			if _is_transient(e) and attempt < max_attempts - 1:
				try:
					frappe.db.rollback()
				except Exception:
					pass
				import time as _t
				import random as _r
				_t.sleep(0.2 + 0.4 * attempt + _r.random() * 0.3)
				continue
			break

	# All retries exhausted (or non-retryable error): mark failed, log, and re-raise.
	safe_log_error(
		"Media Processing Error",
		f"Error processing media asset {media_asset_name}: {str(last_err)}",
	)
	try:
		asset = frappe.get_doc("Media Asset", media_asset_name)
		asset.mark_as_failed(str(last_err))
	except Exception:
		pass
	if last_err is not None:
		raise last_err


@retry_on_deadlock()
def sync_media_asset_to_owner(asset):
	"""Write processed CDN URLs back to the owner doc fields using direct SQL to avoid timestamp conflicts.

	Wrapped with retry_on_deadlock — concurrent media jobs on different assets
	targeting the same owner doctype can interlock on row locks. On deadlock we
	roll back and retry with backoff.
	"""
	try:
		if asset.status != "ready":
			return

		if not asset.owner_doctype or not asset.owner_name:
			return

		field_mappings = {
			"Home Feature": {"home_feature_image": "image_src"},
			"Restaurant Config": {
				"restaurant_config_logo": "logo",
				"restaurant_config_hero_video": "hero_video",
				"apple_touch_icon": "apple_touch_icon",
			},
			"Event": {"event_image": "image_src"},
			"Offer": {"offer_image": "image_src"},
			"Legacy Content": {
				"legacy_hero_media": "hero_media_src",
				"legacy_hero_fallback": "hero_fallback_image",
				"legacy_footer_media": "footer_media_src",
			},
			"Legacy Member": {"legacy_member_image": "image"},
			"Legacy Testimonial": {"legacy_testimonial_avatar": "avatar"},
			"Legacy Gallery Image": {"legacy_gallery_image": "image"},
			"Legacy Testimonial Image": {"legacy_testimonial_dish_image": "image"},
			"Menu Category": {"category_image": "category_image"},
		}

		doctype_map = field_mappings.get(asset.owner_doctype)
		if not doctype_map:
			return

		fieldname = doctype_map.get(asset.media_role)
		if not fieldname:
			return

		frappe.db.sql(
			"""
			UPDATE `tab{doctype}`
			SET `{field}` = %s, `modified` = NOW()
			WHERE `name` = %s
			""".format(doctype=asset.owner_doctype, field=fieldname),
			(asset.primary_url, asset.owner_name),
		)
		frappe.db.commit()

	except Exception as e:
		# Re-raise transient errors so retry_on_deadlock can handle them.
		if "deadlock" in str(e).lower() or "lock wait timeout" in str(e).lower():
			raise
		safe_log_error(
			"Media Owner Sync Error",
			f"Failed to sync media asset {asset.name} to owner {asset.owner_doctype} {asset.owner_name}: {str(e)}",
		)


def process_image_asset(asset, raw_file_path, temp_dir):
	"""Process image: generate variants and blur placeholder"""
	from .storage import get_cdn_url
	
	# Skip processing for SVG and GIF files - use raw file directly
	if asset.source_mime_type in ['image/svg+xml', 'image/gif']:
		cdn_url = get_cdn_url(asset.raw_object_key)
		
		frappe.db.set_value("Media Asset", asset.name, {
			"primary_object_key": asset.raw_object_key,
			"primary_url": cdn_url,
			"status": "ready",
			"processed_at": now_datetime()
		})
		frappe.db.commit()
		
		# Sync to owner document
		sync_media_asset_to_owner(asset)
		return
	
	from .processors import ImageProcessor
	from PIL import Image
	
	processor = ImageProcessor(raw_file_path, temp_dir)
	
	# Determine target sizes based on media role
	variant_configs = get_image_variant_configs(asset.media_role)
	
	# Process variants
	variants_data = []
	
	for config in variant_configs:
		variant_path = processor.create_variant(
			variant_name=config["name"],
			max_size=config["size"],
			quality=config.get("quality", 75)
		)
		
		if variant_path:
			# Generate object key for variant
			variant_object_key = generate_object_key(
				restaurant_id=asset.restaurant,
				owner_doctype=asset.owner_doctype,
				owner_name=asset.owner_name,
				media_role=asset.media_role,
				media_id=asset.media_id,
				filename=f"{config['name']}.webp",
				variant=config['name']
			)
			
			# Upload variant
			variant_url = upload_object(
				variant_path,
				variant_object_key,
				content_type="image/webp"
			)
			
			# Get variant dimensions
			from PIL import Image
			with Image.open(variant_path) as img:
				width, height = img.size
			
			# Get file size
			size_bytes = os.path.getsize(variant_path)
			
			variants_data.append({
				"variant_name": config["name"],
				"object_key": variant_object_key,
				"file_url": variant_url,
				"format": "webp",
				"width": width,
				"height": height,
				"size_bytes": size_bytes,
				"quality": config.get("quality", 75),
				"is_primary": config.get("is_primary", False)
			})
	
	# Get original dimensions
	from PIL import Image
	with Image.open(raw_file_path) as img:
		asset.width, asset.height = img.size
	
	# Generate blur placeholder
	blur_placeholder = processor.generate_blur_placeholder()
	if blur_placeholder:
		asset.blur_placeholder = blur_placeholder
	
	# Set primary URL (use 'md' variant or first variant)
	primary_variant = next((v for v in variants_data if v["is_primary"]), variants_data[0] if variants_data else None)
	if primary_variant:
		asset.primary_url = primary_variant["file_url"]
		asset.primary_object_key = primary_variant["object_key"]
	
	# Clear existing variants and add new ones. Wrapped with retry because
	# concurrent jobs replacing child rows on `tabMedia Variant` can deadlock
	# on InnoDB gap locks. Re-running is safe: variants_data is deterministic
	# and R2 uploads are idempotent (same key overwrites itself).
	@retry_on_deadlock()
	def _save_image_variants():
		asset.reload()
		asset.media_variants = []
		for variant_data in variants_data:
			asset.append("media_variants", variant_data)
		asset.save(ignore_permissions=True)

	_save_image_variants()


def process_video_asset(asset, source_path, temp_dir):
	"""Process video asset - generate optimized video and poster"""
	from .processors import VideoProcessor
	
	processor = VideoProcessor(source_path, temp_dir)
	
	# Get video metadata
	metadata = processor.get_metadata()
	asset.width = metadata.get("width")
	asset.height = metadata.get("height")
	asset.duration_seconds = metadata.get("duration")
	
	# Generate 720p video
	video_720p_path = processor.create_720p_variant()
	
	if video_720p_path:
		# Upload video variant
		video_object_key = generate_object_key(
			restaurant_id=asset.restaurant,
			owner_doctype=asset.owner_doctype,
			owner_name=asset.owner_name,
			media_role=asset.media_role,
			media_id=asset.media_id,
			filename="video_720p.mp4",
			variant="video_720p"
		)
		
		video_url = upload_object(
			video_720p_path,
			video_object_key,
			content_type="video/mp4"
		)
		
		video_size = os.path.getsize(video_720p_path)
		
		asset.append("media_variants", {
			"variant_name": "video_720p",
			"object_key": video_object_key,
			"file_url": video_url,
			"format": "mp4",
			"width": 1280,
			"height": 720,
			"size_bytes": video_size,
			"is_primary": True
		})
		
		asset.primary_url = video_url
		asset.primary_object_key = video_object_key
	
	# Generate poster image
	poster_path = processor.create_poster()
	
	if poster_path:
		# Upload poster
		poster_object_key = generate_object_key(
			restaurant_id=asset.restaurant,
			owner_doctype=asset.owner_doctype,
			owner_name=asset.owner_name,
			media_role=asset.media_role,
			media_id=asset.media_id,
			filename="poster.webp",
			variant="poster"
		)
		
		poster_url = upload_object(
			poster_path,
			poster_object_key,
			content_type="image/webp"
		)
		
		from PIL import Image
		with Image.open(poster_path) as img:
			poster_width, poster_height = img.size
		
		poster_size = os.path.getsize(poster_path)
		
		asset.append("media_variants", {
			"variant_name": "poster",
			"object_key": poster_object_key,
			"file_url": poster_url,
			"format": "webp",
			"width": poster_width,
			"height": poster_height,
			"size_bytes": poster_size,
			"is_primary": False
		})
		
		asset.poster_url = poster_url

	# Save with retry: child-table replacement on `tabMedia Variant` can
	# deadlock when concurrent video jobs collide on InnoDB gap locks.
	@retry_on_deadlock()
	def _save_video_asset():
		asset.save(ignore_permissions=True)

	_save_video_asset()


def cleanup_deleted_media(media_asset_name):
	"""Cleanup deleted media from storage"""
	try:
		asset = frappe.get_doc("Media Asset", media_asset_name)
		
		if not asset.is_deleted:
			frappe.logger().warning(f"Media asset {asset.media_id} is not marked as deleted")
			return
		
		# Delete raw object
		if asset.raw_object_key:
			delete_object(asset.raw_object_key)
		
		# Delete variants
		for variant in asset.media_variants:
			if variant.object_key:
				delete_object(variant.object_key)
		
		# Delete poster if exists
		if asset.poster_url and hasattr(asset, 'poster_object_key'):
			delete_object(asset.poster_object_key)
		
		frappe.logger().info(f"Cleaned up deleted media asset {asset.media_id}")
		
	except Exception as e:
		safe_log_error("Media Cleanup Error", f"Error cleaning up media asset {media_asset_name}: {str(e)}")


def get_image_variant_configs(media_role):
	"""Get variant configurations based on media role"""
	
	# Canonical frontend-facing variants only.
	# These map directly to current UI usage and srcset breakpoints.
	base_variants = [
		{"name": "small", "size": 400, "quality": 75, "is_primary": False},
		{"name": "medium", "size": 800, "quality": 75, "is_primary": True},
		{"name": "large", "size": 1200, "quality": 80, "is_primary": False}
	]
	
	# Role-specific adjustments
	if media_role in ["restaurant_logo", "restaurant_config_logo", "apple_touch_icon"]:
		return [
			{"name": "small", "size": 128, "quality": 75, "is_primary": False},
			{"name": "medium", "size": 256, "quality": 80, "is_primary": True},
			{"name": "large", "size": 512, "quality": 85, "is_primary": False}
		]
	else:
		return base_variants
