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

Also fetches outlet *details* (rating, review count, price level, hours,
facility attributes) into the existing Restaurant fields — see
sync_outlet_details_from_google() below.

Future-merchant automation (see hooks.py):
  - auto_sync_google_photos_on_activation(doc, method) — doc_event on Restaurant
        on_update: the moment a new outlet flips is_active 0→1, enqueues a sync
        so photos are ready before the merchant ever opens Gallery Management.
  - auto_sync_google_details_on_activation(doc, method) — same trigger, enqueues
        sync_outlet_details_from_google() so rating/hours/price/facilities are
        live on the outlet detail screen from day one.
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


def _search_place(query, max_results=1):
    """Text Search for the best-match place(s). Returns a list (possibly empty)."""
    api_key = _get_api_key()
    resp = requests.post(
        PLACES_TEXT_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.photos,places.rating,places.businessStatus,places.primaryType,places.location",
        },
        json={"textQuery": query, "maxResultCount": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("places") or []


def _distance_meters(lat1, lng1, lat2, lng2):
    """Haversine distance in meters."""
    import math
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(a ** 0.5, (1 - a) ** 0.5)


# Within this radius of the outlet's own stored coordinates, treat a candidate
# as confidently matched regardless of name similarity — two branches of the
# same chain effectively never sit this close together, but easily share the
# exact same display name (the MMV multi-branch case).
GEO_MATCH_RADIUS_METERS = 150


_GENERIC_NAME_WORDS = {
    "restaurant", "cafe", "coffee", "the", "and", "bar", "grill", "kitchen",
    "house", "dine", "dining", "family", "hotel", "food", "court", "mart",
    "corner", "point", "hub", "zone", "world", "mall", "complex", "surat",
}
_MISMATCH_TYPES = {"shopping_mall", "lodging", "premise", "point_of_interest"}


def _match_confidence(outlet_name, place, outlet_lat=None, outlet_lng=None):
    """
    How confident are we that `place` (a Text Search result) is actually the
    outlet, not just the mall/building/street it happens to sit in — or, for
    a multi-branch chain, a *different branch* that happens to share the
    exact same name?

    Two ways to earn confidence, either is enough:
      - geo match: the place's coordinates are within GEO_MATCH_RADIUS_METERS
        of the outlet's own stored latitude/longitude. Strictly more reliable
        than name matching for chains — two branches of the same chain
        essentially never sit this close together.
      - name match: the matched display name shares a meaningful word with
        the outlet name, or scores well on fuzzy string similarity.

    Either way, a matched place whose primaryType is itself a mall/building/
    POI (not a food/service business) is rejected outright first — a geo-close
    match against the mall the outlet sits inside is still the wrong entity.

    Returns (is_confident: bool, reason: str | None).
    """
    matched_name = (place.get("displayName", {}) or {}).get("text", "")
    primary_type = place.get("primaryType", "")

    if primary_type in _MISMATCH_TYPES:
        return False, f"matched place is a '{primary_type}', not the outlet itself"

    if outlet_lat and outlet_lng and place.get("location"):
        dist = _distance_meters(
            float(outlet_lat), float(outlet_lng),
            place["location"]["latitude"], place["location"]["longitude"],
        )
        if dist <= GEO_MATCH_RADIUS_METERS:
            return True, None

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

    if not frappe.db.exists("Outlet", outlet_id):
        return {"success": False, "error": "Outlet not found"}

    r = frappe.db.get_value(
        "Outlet", outlet_id,
        ["outlet_name", "address", "city", "google_place_id", "latitude", "longitude"],
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

        frappe.db.set_value("Outlet", outlet_id, "google_place_id", place["id"], update_modified=False)
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
        if not r.outlet_name or not (r.address or r.city):
            return {"success": False, "error": "Outlet has no name/address to search with — needs manual_place_id"}
        query = f"{r.outlet_name}, {r.address or r.city}"

    try:
        # Ask for several candidates, not just the top hit — chains return
        # multiple branches under the identical name, and only a geo check
        # against the outlet's own coordinates can tell them apart.
        candidates = _search_place(query, max_results=5)
    except requests.RequestException as e:
        safe_log_error("Google Places Search", f"{outlet_id}: {e}")
        return {"success": False, "error": f"Places search failed: {e}"}

    if not candidates:
        return {"success": False, "error": "No matching place found on Google — needs manual_place_id or override_query"}

    # Prefer any candidate that passes on geo distance over the raw top hit —
    # Text Search ranks by relevance/popularity, not proximity to our outlet.
    place, confident, reason = None, False, None
    for candidate in candidates:
        is_confident, why = _match_confidence(r.outlet_name, candidate, r.latitude, r.longitude)
        if is_confident:
            place, confident, reason = candidate, True, None
            break
    if not confident:
        place, reason = candidates[0], (
            _match_confidence(r.outlet_name, candidates[0], r.latitude, r.longitude)[1]
        )

    if not confident:
        return {
            "success": False,
            "error": f"Low-confidence match rejected: {reason}",
            "candidate_place_id": place["id"],
            "candidate_name": place.get("displayName", {}).get("text"),
            "candidates_checked": len(candidates),
            "hint": "Verify by hand and call resolve_google_place_id(outlet_id, manual_place_id=...) if the candidate is actually correct, or override_query=... to retry with a better search string.",
        }

    place_id = place["id"]
    frappe.db.set_value("Outlet", outlet_id, "google_place_id", place_id, update_modified=False)
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

    if not frappe.db.exists("Outlet", outlet_id):
        return {"success": False, "error": "Outlet not found"}

    r = frappe.db.get_value(
        "Outlet", outlet_id,
        ["outlet_name", "address", "city", "google_place_id"],
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
        filters={"outlet": outlet_id, "owner_doctype": "Outlet", "media_role": "restaurant_gallery_image", "source_filename": ["like", "google_places_%"]},
        pluck="source_sha256",
    ))

    outlet_safe = _sanitize(outlet_id)
    created, skipped, errors = 0, 0, []
    existing_max_sort = frappe.db.sql(
        "select coalesce(max(sort_order), 0) from `tabOutlet Gallery Item` where outlet=%s", (outlet_id,)
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
            outlet_id, "Outlet", outlet_id, "restaurant_gallery_image", media_id, filename,
        )

        try:
            cdn_url = upload_bytes(object_key, content, content_type="image/jpeg")
        except Exception as e:
            errors.append({"photo_index": i, "error": f"R2 upload failed: {e}"})
            continue

        media_asset = frappe.get_doc({
            "doctype": "Media Asset",
            "media_id": media_id,
            "outlet": outlet_id,
            "owner_doctype": "Outlet",
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
            "doctype": "Outlet Gallery Item",
            "outlet": outlet_id,
            "media_type": "Image",
            "url": cdn_url,
            "title": f"{r.outlet_name} — Google Photo {i+1}",
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

    frappe.db.set_value("Outlet", outlet_id, {
        "google_place_photos_synced_at": now_datetime(),
        "google_place_photos_count": frappe.db.count("Media Asset", {
            "outlet": outlet_id, "owner_doctype": "Outlet", "media_role": "restaurant_gallery_image",
            "source_filename": ["like", "google_places_%"],
        }),
    }, update_modified=False)
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
        outlet_ids = frappe.get_all("Outlet", filters=filters, pluck="name")

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
        "Outlet",
        filters={"is_active": 1, "google_place_id": ["in", ["", None]]},
        fields=["name", "outlet_name", "address", "city", "outlet_type"],
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
        "Outlet",
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


# ---------------------------------------------------------------------------
# Outlet details sync — rating, review count, price level, hours, facilities.
# Same resolved google_place_id as the photo sync; writes straight onto the
# existing Restaurant fields (rating/review_count/price_range/hours_json/
# amenities_mask/google_review_url) — no new doctype fields needed.
# ---------------------------------------------------------------------------

_PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": "",
    "PRICE_LEVEL_INEXPENSIVE": "₹",
    "PRICE_LEVEL_MODERATE": "₹₹",
    "PRICE_LEVEL_EXPENSIVE": "₹₹₹",
    "PRICE_LEVEL_VERY_EXPENSIVE": "₹₹₹₹",
}

# Google day index: 0=Sunday..6=Saturday. hours_json keys are the 3-letter
# lowercase abbreviations get_outlet_detail's _is_open_now_inline already
# expects (Python's now.strftime("%a").lower()).
_DAY_ABBR = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat"}

# Google attribute field -> our Amenity bitmask flag. Only ever OR these in
# when Google explicitly says true — an absent/false field means "Google has
# no data", not "this outlet doesn't have it", so merchant-set bits are never
# cleared by a sync.
_ATTRIBUTE_TO_FLAG = {
    "dineIn": 1 << 0,
    "takeout": 1 << 1,
    "delivery": 1 << 2,
    "reservable": 1 << 3,
    "outdoorSeating": 1 << 4,
    "servesBreakfast": 1 << 5,
    "servesLunch": 1 << 6,
    "servesDinner": 1 << 7,
    "servesBrunch": 1 << 8,
    "servesVegetarianFood": 1 << 9,
    "servesCoffee": 1 << 10,
    "servesCocktails": 1 << 11,
    "servesDessert": 1 << 12,
    "liveMusic": 1 << 13,
    "goodForChildren": 1 << 14,
    "goodForGroups": 1 << 15,
    "goodForWatchingSports": 1 << 16,
    "restroom": 1 << 17,
}
_PAYMENT_ATTRIBUTE_TO_FLAG = {
    "acceptsCreditCards": 1 << 18,
    "acceptsDebitCards": 1 << 19,
    "acceptsNfc": 1 << 20,
    "acceptsCashOnly": 1 << 21,
}
_PARKING_ATTRIBUTE_TO_FLAG = {
    "freeParkingLot": 1 << 22,
    "paidParkingLot": 1 << 23,
    "valetParking": 1 << 24,
    "freeStreetParking": 1 << 25,
    "paidStreetParking": 1 << 25,
}

_DETAILS_FIELD_MASK = ",".join([
    "id", "rating", "userRatingCount", "priceLevel", "regularOpeningHours",
    "googleMapsUri", "businessStatus",
    "dineIn", "takeout", "delivery", "reservable", "outdoorSeating",
    "servesBreakfast", "servesLunch", "servesDinner", "servesBrunch",
    "servesVegetarianFood", "servesCoffee", "servesCocktails", "servesDessert",
    "liveMusic", "goodForChildren", "goodForGroups", "goodForWatchingSports",
    "restroom", "paymentOptions", "parkingOptions",
])


def _build_hours_json(regular_opening_hours):
    """Google periods -> {"mon": "11:00 AM - 1:00 AM", ...} matching the
    format get_outlet_detail's _is_open_now_inline already parses. Only the
    first period per day is used (a second split shift, if any, is dropped —
    good enough for display; merchants can hand-edit for exact split hours)."""
    if not regular_opening_hours:
        return {}
    hours = {}
    for period in regular_opening_hours.get("periods") or []:
        open_t, close_t = period.get("open"), period.get("close")
        if not open_t or not close_t:
            continue
        day = _DAY_ABBR.get(open_t.get("day"))
        if not day or day in hours:
            continue
        def _fmt(t):
            h, m = t.get("hour", 0), t.get("minute", 0)
            suffix = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {suffix}"
        hours[day] = f"{_fmt(open_t)} - {_fmt(close_t)}"
    return hours


def _build_amenities_bits(place):
    bits = 0
    for attr, flag in _ATTRIBUTE_TO_FLAG.items():
        if place.get(attr) is True:
            bits |= flag
    payment = place.get("paymentOptions") or {}
    for attr, flag in _PAYMENT_ATTRIBUTE_TO_FLAG.items():
        if payment.get(attr) is True:
            bits |= flag
    parking = place.get("parkingOptions") or {}
    for attr, flag in _PARKING_ATTRIBUTE_TO_FLAG.items():
        if parking.get(attr) is True:
            bits |= flag
    return bits


@frappe.whitelist()
def sync_outlet_details_from_google(outlet_id):
    """
    Fetch rating, review count, price level, hours, and facility attributes
    from Google Places and store them straight onto the Restaurant record —
    no new doctype fields, all six (rating, review_count, price_range,
    hours_json, amenities_mask, google_review_url) already exist and are
    simply empty until a merchant fills them in by hand.

    Facility bits (amenities_mask) are only ever OR'd in when Google
    explicitly reports true — never overwrites/clears a bit a merchant
    already set, since an absent Google field means "no data", not "no".

    Idempotent to call repeatedly (safe on the same on_update/backfill
    triggers as sync_outlet_photos_from_google); cheap — one Details call,
    no downloads/uploads.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    if not frappe.db.exists("Outlet", outlet_id):
        return {"success": False, "error": "Outlet not found"}

    r = frappe.db.get_value(
        "Outlet", outlet_id,
        ["google_place_id", "amenities_mask"],
        as_dict=True,
    )

    place_id = r.google_place_id
    if not place_id:
        resolved = resolve_google_place_id(outlet_id)
        if not resolved.get("success"):
            return {"success": False, "error": resolved.get("error", "Could not resolve place")}
        place_id = resolved["google_place_id"]

    api_key = _get_api_key()
    try:
        resp = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _DETAILS_FIELD_MASK},
            timeout=15,
        )
        resp.raise_for_status()
        place = resp.json()
    except requests.RequestException as e:
        safe_log_error("Google Places Details (sync)", f"{outlet_id}: {e}")
        return {"success": False, "error": f"Places details fetch failed: {e}"}

    new_bits = _build_amenities_bits(place)
    merged_mask = (r.amenities_mask or 0) | new_bits

    updates = {
        "amenities_mask": merged_mask,
    }
    if place.get("rating") is not None:
        updates["rating"] = place["rating"]
    if place.get("userRatingCount") is not None:
        updates["review_count"] = place["userRatingCount"]
    if place.get("priceLevel") in _PRICE_LEVEL_MAP:
        updates["price_range"] = _PRICE_LEVEL_MAP[place["priceLevel"]]
    if place.get("googleMapsUri"):
        updates["google_review_url"] = place["googleMapsUri"]
    hours = _build_hours_json(place.get("regularOpeningHours"))
    if hours:
        updates["hours_json"] = json.dumps(hours)

    frappe.db.set_value("Outlet", outlet_id, updates, update_modified=False)
    frappe.db.commit()
    frappe.cache().delete_value(f"flamezo:outlet_detail:{outlet_id}")

    return {"success": True, "outlet_id": outlet_id, "google_place_id": place_id, **updates}


@frappe.whitelist()
def bulk_sync_google_details(outlet_ids=None, only_active=1):
    """
    Sync details (rating/review_count/price_range/hours_json/amenities_mask/
    google_review_url) for many outlets in one call — runs inline, for a
    one-time backfill over currently-live outlets. Mirrors bulk_sync_google_photos.
    """
    if not is_supervisor():
        frappe.throw(_("Permission denied"), frappe.PermissionError)

    if isinstance(outlet_ids, str):
        outlet_ids = json.loads(outlet_ids)

    if not outlet_ids:
        filters = {"is_active": 1} if int(only_active) else {}
        outlet_ids = frappe.get_all("Outlet", filters=filters, pluck="name")

    results = []
    for outlet_id in outlet_ids:
        try:
            results.append(sync_outlet_details_from_google(outlet_id))
        except Exception as e:
            safe_log_error("Bulk Google Places Details Sync", f"{outlet_id}: {e}")
            results.append({"success": False, "outlet_id": outlet_id, "error": str(e)})

    return {
        "success": True,
        "total_outlets": len(outlet_ids),
        "succeeded": sum(1 for r in results if r.get("success")),
        "results": results,
    }


def auto_sync_google_details_on_activation(doc, method=None):
    """
    Restaurant doc_event (on_update) — same 0→1 activation trigger as the
    photo sync, enqueued alongside it so a new merchant's outlet page shows
    real rating/hours/price/facilities from day one, no manual entry needed.
    """
    if not doc.has_value_changed("is_active") or not doc.is_active:
        return

    frappe.enqueue(
        "flamezo_backend.flamezo.api.google_places_photos.sync_outlet_details_from_google",
        outlet_id=doc.name,
        queue="short",
        timeout=60,
        is_async=True,
        now=False,
        enqueue_after_commit=True,
    )
