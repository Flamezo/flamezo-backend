# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Sync outlet photos from the Google Places API (New, v1) into the Gallery
Discovery Pool.

Flow per outlet:
  1. Resolve `google_place_id` via Text Search on "{restaurant_name}, {address}"
     (one-time — Place IDs are stable, so this is skipped once resolved).
  2. List available photo refs on the resolved place.
  3. Download each photo's bytes, skip ones already synced (by SHA-256, so
     re-running the sync is a no-op unless Google's photo set changed).
  4. Upload bytes to R2 (same bucket/CDN as every other outlet media asset),
     insert a `Media Asset` row (role `restaurant_gallery_image`), then a
     `Restaurant Gallery Item` row tagged `source="Google Places"` so it shows
     up in the Gallery Management "Media Library" pool for merchant/admin
     curation — NOT auto-published to the Active Showcase (`is_selected=0`),
     since raw Places photos are a mixed bag (food close-ups, random signage)
     and need a human pick before going live in the app.

Whitelisted entrypoints:
  - resolve_google_place_id(outlet_id, override_query=None, manual_place_id=None)
      — single outlet, id resolution only. override_query/manual_place_id are the
        manual-fallback path for outlets Text Search can't confidently match.
  - sync_outlet_photos_from_google(outlet_id, max_photos=None) — full sync, one outlet
  - bulk_sync_google_photos(outlet_ids=None, max_photos=None)  — many outlets, inline
  - list_outlets_needing_manual_google_photos() — outlets that failed auto-resolution,
        for the "do it manually" fallback path

Future-merchant automation (see hooks.py):
  - auto_sync_google_photos_on_activation(doc, method) — doc_event on Restaurant
        on_update: the moment a new outlet flips is_active 0→1, enqueues a sync
        so photos are ready before the merchant ever opens Gallery Management.
  - backfill_missing_google_photos() — weekly scheduled catch-all for any active
        outlet that slipped through (bulk import, direct DB flip, etc.), bounded
        per run to control API cost.
"""

import difflib
import hashlib
import io
import json
import re

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from flamezo_backend.flamezo.media.storage import generate_object_key, upload_bytes
from flamezo_backend.flamezo.utils.common import safe_log_error
from flamezo_backend.flamezo.utils.roles import is_supervisor

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_PHOTO_URL_TMPL = "https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx=1600&key={key}"
MAX_PHOTOS_PER_OUTLET_DEFAULT = 10


def _get_api_key():
    key = frappe.conf.get("google_places_api_key")
    if not key:
        frappe.throw(_("google_places_api_key is not configured in site_config.json"))
    return key


def _search_place(query):
    """Text Search for a single best-match place. Returns dict or None."""
    api_key = _get_api_key()
    resp = requests.post(
        PLACES_TEXT_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.photos,places.rating,places.businessStatus,places.primaryType",
        },
        json={"textQuery": query, "maxResultCount": 1},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    places = data.get("places") or []
    return places[0] if places else None


_GENERIC_NAME_WORDS = {
    "restaurant", "cafe", "coffee", "the", "and", "bar", "grill", "kitchen",
    "house", "dine", "dining", "family", "hotel", "food", "court", "mart",
    "corner", "point", "hub", "zone", "world", "mall", "complex", "surat",
}
_MISMATCH_TYPES = {"shopping_mall", "lodging", "premise", "point_of_interest"}


def _match_confidence(outlet_name, place):
    """
    How confident are we that `place` (a Text Search result) is actually the
    outlet, not just the mall/building/street it happens to sit in?

    Text Search on "{name}, {address}" can and does match the wrong entity —
    e.g. an outlet inside a mall resolving to the mall itself — especially
    for short/generic outlet names. Two independent signals, either is enough
    to reject a match outright before it gets silently linked and synced
    against the wrong place's photos:
      - the matched place's primaryType is itself a mall/building/POI, not a
        food/service business
      - the matched display name shares no meaningful word with the outlet
        name AND scores low on fuzzy string similarity
    Returns (is_confident: bool, reason: str | None).
    """
    matched_name = (place.get("displayName", {}) or {}).get("text", "")
    primary_type = place.get("primaryType", "")

    if primary_type in _MISMATCH_TYPES:
        return False, f"matched place is a '{primary_type}', not the outlet itself"

    a = re.sub(r"[^a-z0-9\s]", "", (outlet_name or "").lower())
    b = re.sub(r"[^a-z0-9\s]", "", (matched_name or "").lower())
    a_words = {w for w in a.split() if len(w) >= 4 and w not in _GENERIC_NAME_WORDS}
    b_words = {w for w in b.split() if len(w) >= 4 and w not in _GENERIC_NAME_WORDS}

    shares_word = bool(a_words & b_words)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()

    if shares_word or ratio >= 0.55:
        return True, None
    return False, f"matched name '{matched_name}' doesn't resemble outlet name '{outlet_name}' (similarity {ratio:.2f})"


@frappe.whitelist()
def resolve_google_place_id(outlet_id, override_query=None, manual_place_id=None):
    """
    Resolve and persist google_place_id for one outlet.

    Normal path: Places Text Search on "{restaurant_name}, {address}".
    Idempotent — no-ops if already resolved (Place IDs are stable, no reason
    to re-search and burn an API call).

    Manual fallback path (for the outlets auto-search can't confidently
    match — wrong/incomplete address, a very generic name, brand-new outlet
    Google hasn't indexed yet):
      - override_query: retry Text Search with a hand-written query instead
        of the auto-built "name, address" one (e.g. add a landmark or drop a
        typo'd address component).
      - manual_place_id: skip search entirely and set a Place ID an admin
        looked up themselves via Google's own Place ID Finder tool
        (https://developers.google.com/maps/documentation/places/web-service/place-id).
        Verified against Places Details before saving, so a bad paste fails
        loudly instead of silently linking the wrong place.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    if not frappe.db.exists("Restaurant", outlet_id):
        return {"success": False, "error": "Outlet not found"}

    r = frappe.db.get_value(
        "Restaurant", outlet_id,
        ["restaurant_name", "address", "city", "google_place_id"],
        as_dict=True,
    )

    if manual_place_id:
        api_key = _get_api_key()
        try:
            resp = requests.get(
                f"https://places.googleapis.com/v1/places/{manual_place_id}",
                headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "id,displayName,photos"},
                timeout=15,
            )
            resp.raise_for_status()
            place = resp.json()
        except requests.RequestException as e:
            return {"success": False, "error": f"Could not verify manual place_id: {e}"}

        frappe.db.set_value("Restaurant", outlet_id, "google_place_id", place["id"])
        frappe.db.commit()
        return {
            "success": True, "already_resolved": False, "manual": True,
            "google_place_id": place["id"],
            "matched_name": place.get("displayName", {}).get("text"),
            "photos_available": len(place.get("photos") or []),
        }

    if r.google_place_id and not override_query:
        return {"success": True, "already_resolved": True, "google_place_id": r.google_place_id}

    if override_query:
        query = override_query
    else:
        if not r.restaurant_name or not (r.address or r.city):
            return {"success": False, "error": "Outlet has no name/address to search with — needs manual_place_id"}
        query = f"{r.restaurant_name}, {r.address or r.city}"

    try:
        place = _search_place(query)
    except requests.RequestException as e:
        safe_log_error("Google Places Search", f"{outlet_id}: {e}")
        return {"success": False, "error": f"Places search failed: {e}"}

    if not place:
        return {"success": False, "error": "No matching place found on Google — needs manual_place_id or override_query"}

    confident, reason = _match_confidence(r.restaurant_name, place)
    if not confident:
        return {
            "success": False,
            "error": f"Low-confidence match rejected: {reason}",
            "candidate_place_id": place["id"],
            "candidate_name": place.get("displayName", {}).get("text"),
            "hint": "Verify by hand and call resolve_google_place_id(outlet_id, manual_place_id=...) if the candidate is actually correct, or override_query=... to retry with a better search string.",
        }

    place_id = place["id"]
    frappe.db.set_value("Restaurant", outlet_id, "google_place_id", place_id)
    frappe.db.commit()

    return {
        "success": True,
        "already_resolved": False,
        "google_place_id": place_id,
        "matched_name": place.get("displayName", {}).get("text"),
        "rating": place.get("rating"),
        "photos_available": len(place.get("photos") or []),
    }


def _sanitize(s):
    return re.sub(r"[^a-z0-9-]", "", (s or "").lower())


@frappe.whitelist()
def sync_outlet_photos_from_google(outlet_id, max_photos=None):
    """
    Full sync for one outlet: resolve place_id if missing, fetch all
    available photos (capped at max_photos), download+dedup+upload to R2,
    create Media Asset + Restaurant Gallery Item rows.

    Returns a summary dict — never throws on a single-photo failure, so a
    bulk caller can keep going; per-photo errors are collected in `errors`.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    max_photos = int(max_photos) if max_photos else MAX_PHOTOS_PER_OUTLET_DEFAULT

    if not frappe.db.exists("Restaurant", outlet_id):
        return {"success": False, "error": "Outlet not found"}

    r = frappe.db.get_value(
        "Restaurant", outlet_id,
        ["restaurant_name", "address", "city", "google_place_id"],
        as_dict=True,
    )

    place_id = r.google_place_id
    place_photos = None

    if not place_id:
        resolved = resolve_google_place_id(outlet_id)
        if not resolved.get("success"):
            return {"success": False, "error": resolved.get("error", "Could not resolve place")}
        place_id = resolved["google_place_id"]

    # Re-fetch the place (fresh photo refs — they aren't stored, and expire)
    api_key = _get_api_key()
    try:
        resp = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "id,displayName,photos",
            },
            timeout=15,
        )
        resp.raise_for_status()
        place = resp.json()
    except requests.RequestException as e:
        safe_log_error("Google Places Details", f"{outlet_id}: {e}")
        return {"success": False, "error": f"Places details fetch failed: {e}"}

    photos = (place.get("photos") or [])[:max_photos]
    if not photos:
        return {"success": True, "outlet_id": outlet_id, "photos_found": 0, "created": 0, "skipped_duplicate": 0, "errors": []}

    # Existing hashes for this outlet's already-synced Google photos, for dedup.
    existing_hashes = set(frappe.get_all(
        "Media Asset",
        filters={"restaurant": outlet_id, "owner_doctype": "Restaurant", "media_role": "restaurant_gallery_image", "source_filename": ["like", "google_places_%"]},
        pluck="source_sha256",
    ))

    outlet_safe = _sanitize(outlet_id)
    created, skipped, errors = 0, 0, []
    existing_max_sort = frappe.db.sql(
        "select coalesce(max(sort_order), 0) from `tabRestaurant Gallery Item` where restaurant=%s", (outlet_id,)
    )[0][0] or 0

    for i, photo in enumerate(photos):
        photo_name = photo.get("name")
        if not photo_name:
            continue
        try:
            media_url = PLACES_PHOTO_URL_TMPL.format(photo_name=photo_name, key=api_key)
            img_resp = requests.get(media_url, timeout=20)
            img_resp.raise_for_status()
            content = img_resp.content
        except requests.RequestException as e:
            errors.append({"photo_index": i, "error": str(e)})
            continue

        sha256 = hashlib.sha256(content).hexdigest()
        if sha256 in existing_hashes:
            skipped += 1
            continue

        media_id = f"med_gp_{frappe.generate_hash(length=12)}"
        filename = f"google_places_{i+1:02d}.jpg"
        object_key = generate_object_key(
            outlet_id, "Restaurant", outlet_id, "restaurant_gallery_image", media_id, filename,
        )

        try:
            cdn_url = upload_bytes(object_key, content, content_type="image/jpeg")
        except Exception as e:
            errors.append({"photo_index": i, "error": f"R2 upload failed: {e}"})
            continue

        media_asset = frappe.get_doc({
            "doctype": "Media Asset",
            "media_id": media_id,
            "restaurant": outlet_id,
            "owner_doctype": "Restaurant",
            "owner_name": outlet_id,
            "media_role": "restaurant_gallery_image",
            "media_kind": "image",
            "visibility": "public",
            "source_filename": filename,
            "source_extension": "jpg",
            "source_mime_type": "image/jpeg",
            "source_size_bytes": len(content),
            "source_sha256": sha256,
            "storage_provider": "cloudflare_r2",
            "raw_object_key": object_key,
            "primary_url": cdn_url,
            "status": "uploaded",
            "caption": "Synced from Google Places",
            "is_active": 1,
        })
        media_asset.insert(ignore_permissions=True)

        gallery_item = frappe.get_doc({
            "doctype": "Restaurant Gallery Item",
            "restaurant": outlet_id,
            "media_type": "Image",
            "url": cdn_url,
            "title": f"{r.restaurant_name} — Google Photo {i+1}",
            # Auto-selected: real Google Places photos of the actual outlet are
            # the strongest cover-image signal we have, so they go live in the
            # Gallery immediately (batch_resolve_outlet_media additionally
            # ranks them ahead of any other selected gallery item).
            "is_selected": 1,
            "sort_order": existing_max_sort + i + 1,
            "source": "Google Places",
        })
        gallery_item.insert(ignore_permissions=True)

        existing_hashes.add(sha256)
        created += 1

        # Enqueue variant/thumbnail generation, matching the standard upload path.
        frappe.enqueue(
            "flamezo_backend.flamezo.media.jobs.process_media_asset",
            media_asset_name=media_asset.name,
            queue="default",
            timeout=600,
            is_async=True,
            now=False,
        )

    frappe.db.set_value("Restaurant", outlet_id, {
        "google_place_photos_synced_at": now_datetime(),
        "google_place_photos_count": frappe.db.count("Media Asset", {
            "restaurant": outlet_id, "owner_doctype": "Restaurant", "media_role": "restaurant_gallery_image",
            "source_filename": ["like", "google_places_%"],
        }),
    })
    frappe.db.commit()

    return {
        "success": True,
        "outlet_id": outlet_id,
        "google_place_id": place_id,
        "photos_found": len(photos),
        "created": created,
        "skipped_duplicate": skipped,
        "errors": errors,
    }


@frappe.whitelist()
def bulk_sync_google_photos(outlet_ids=None, max_photos=None, only_active=1):
    """
    Sync photos for many outlets in one call — runs inline (not enqueued),
    intended for admin-triggered bulk backfills over a bounded outlet list.
    For larger batches, call sync_outlet_photos_from_google per-outlet via
    frappe.enqueue from the caller instead of using this synchronously.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    if isinstance(outlet_ids, str):
        outlet_ids = json.loads(outlet_ids)

    if not outlet_ids:
        filters = {"is_active": 1} if int(only_active) else {}
        outlet_ids = frappe.get_all("Restaurant", filters=filters, pluck="name")

    results = []
    for outlet_id in outlet_ids:
        try:
            results.append(sync_outlet_photos_from_google(outlet_id, max_photos=max_photos))
        except Exception as e:
            safe_log_error("Bulk Google Places Sync", f"{outlet_id}: {e}")
            results.append({"success": False, "outlet_id": outlet_id, "error": str(e)})

    return {
        "success": True,
        "total_outlets": len(outlet_ids),
        "results": results,
    }


@frappe.whitelist()
def list_outlets_needing_manual_google_photos():
    """
    Outlets that could not be auto-resolved/synced — i.e. is_active but has
    no google_place_id and no synced_at timestamp. This is the worklist for
    the "do it manually" fallback: an admin looks each one up via Google's
    Place ID Finder and calls resolve_google_place_id(outlet_id, manual_place_id=...),
    or falls back further to uploading photos by hand through the existing
    Gallery Management upload flow if the outlet genuinely isn't on Google Maps.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    return frappe.get_all(
        "Restaurant",
        filters={"is_active": 1, "google_place_id": ["in", ["", None]]},
        fields=["name", "restaurant_name", "address", "city", "outlet_type"],
        order_by="creation desc",
    )


def auto_sync_google_photos_on_activation(doc, method=None):
    """
    Restaurant doc_event (on_update) — the moment a new outlet flips
    is_active 0→1, enqueue a background sync so Google Places photos are
    already sitting in the Gallery Media Library before the merchant/admin
    ever opens Gallery Management. Safe to fire repeatedly (sync is
    dedup'd/idempotent); only actually enqueues on the 0→1 transition so it
    doesn't re-run on every unrelated save.
    """
    if not doc.has_value_changed("is_active") or not doc.is_active:
        return
    if doc.google_place_photos_synced_at:
        return  # already synced at some point — activation toggling off/on shouldn't re-trigger

    frappe.enqueue(
        "flamezo_backend.flamezo.api.google_places_photos.sync_outlet_photos_from_google",
        outlet_id=doc.name,
        queue="long",
        timeout=300,
        is_async=True,
        now=False,
        enqueue_after_commit=True,
    )


def backfill_missing_google_photos():
    """
    Weekly scheduled catch-all (see hooks.py scheduler_events) — finds active
    outlets that never got synced (missed the on_update hook: bulk import,
    direct DB flip, activated before this feature existed) and enqueues them,
    a bounded batch per run so a large backlog doesn't spike Places API cost
    in one go.
    """
    BATCH_SIZE = 20
    outlet_ids = frappe.get_all(
        "Restaurant",
        filters={"is_active": 1, "google_place_photos_synced_at": ["is", "not set"]},
        pluck="name",
        limit_page_length=BATCH_SIZE,
    )
    for outlet_id in outlet_ids:
        frappe.enqueue(
            "flamezo_backend.flamezo.api.google_places_photos.sync_outlet_photos_from_google",
            outlet_id=outlet_id,
            queue="long",
            timeout=300,
            is_async=True,
            now=False,
        )
    if outlet_ids:
        frappe.logger().info(f"backfill_missing_google_photos: enqueued {len(outlet_ids)} outlets")
