"""
Personalised Chills Feed Algorithm
=====================================
Two-stage architecture:
  Stage 1 — Global snapshots (shared, periodic refresh):
    • candidates_snapshot  — 500 published Chills (90-day window), 5-min TTL
    • global_scores        — Bayesian engagement + social percentiles, 15-min TTL
    • new_content          — Chills < 48h old (bypasses scoring), 60-sec TTL
    • trending             — National top-30, 5-min TTL

  Stage 2 — Per-user (on demand):
    • filter watched + suppressed outlets
    • score via E×0.35 + A×0.30 + F×0.15 + L×0.12 + S×0.08
    • Thompson Sampling exploration — uncertain tag clusters get occasional boosts
    • outlet diversity pass (max 5 per outlet, no 2-in-a-row cap)
    • inject new content at reserved slots [6, 16, 26]
    • exhaustion fallback: 3-tier (180d → all-time → reset)

Algorithm correctness:
  • Bayesian smoothing (prior mean=45%, weight=50) — prevents 2-view noise domination
  • 7-day rolling percentile rank — prevents viral outlier collapsing other scores to ≈0
  • Correct half-life formula: exp(−age × ln(2) / halflife) → score=0.5 at exactly 7 days
  • Thompson Sampling on UNCERTAINTY (low obs count) — not sample-vs-mean (which is always 50%)
  • not_interested penalises all video tags (−10), not just the outlet
  • Daily 0.99× preference decay — prevents stale taste profile accumulation
  • New content excluded from scored pool → enters ONLY via reserved injection slots
  • Diversity pass: hard outlet cap (DROP not defer), consecutive handled with re-insertion
"""

import json as _json
import math
import random
import time
import frappe
from frappe import _
from frappe.utils import now_datetime, cint

# ── Constants ──────────────────────────────────────────────────────────────────

QUEUE_SIZE              = 30
CANDIDATE_POOL          = 500
CANDIDATE_TTL           = 300       # 5 min
GLOBAL_SCORES_TTL       = 900       # 15 min
QUEUE_TTL               = 900       # 15 min per-user queue
EMPTY_BUILD_BACKOFF_TTL = 60         # don't retry a failed personalised build for this long
WATCHED_MAX             = 12_000    # sliding window, rotate oldest
NEW_CONTENT_HOURS       = 48
NEW_CONTENT_SLOTS       = [6, 16, 26]   # 0-indexed reserved positions

# Outlet diversity caps per 30-item queue
MAX_PER_OUTLET_IN_QUEUE = 5
CONSECUTIVE_OUTLET_CAP  = 2

# Score weights — must sum to 1.0
W_ENGAGEMENT = 0.35
W_AFFINITY   = 0.30
W_FRESHNESS  = 0.15
W_LOCATION   = 0.12
W_SOCIAL     = 0.08

# Bayesian prior for watch completion %
BAYES_PRIOR_MEAN   = 0.45   # 45% average completion
BAYES_PRIOR_WEIGHT = 50     # equivalent prior observations

# Correct half-life: score = exp(−age × ln(2) / HALFLIFE) → score=0.5 when age=HALFLIFE
FRESHNESS_HALFLIFE_HOURS = 168.0    # 7-day half-life

# Thompson Sampling initial state (Beta distribution priors)
THOMPSON_ALPHA_INIT  = 1.0
THOMPSON_BETA_INIT   = 1.0
# Minimum observations before a tag is considered "known" (no exploration needed)
THOMPSON_MIN_OBS     = 8

# Preference deltas per event type (applied per tag in the video)
EVENT_PREF_DELTA = {
    "watch_complete":  10.0,
    "watch_half":       6.0,
    "replay":           8.0,
    "save":            12.0,
    "share":           15.0,
    "profile_tap":      4.0,
    "fast_skip":       -3.0,
    "not_interested": -10.0,
}

DAILY_DECAY     = 0.99      # exponential preference decay applied nightly
SUPPRESS_DAYS   = 14        # outlet suppression window after not_interested

# Cold start thresholds
COLD_THRESHOLD  = 0         # 0 watches → pure trending
WARM_THRESHOLD  = 10        # < 10 watches → blended with trending

# Location scoring
NEAR_DISTANCE_KM     = 2.0
MAX_SCORE_DIST_KM    = 50.0


# ── Redis helpers (fix for Frappe TTL cache bug) ───────────────────────────────
#
# Frappe's set_value(key, val, expires_in_sec=X) only writes to Redis (via SETEX),
# NOT to frappe.local.cache. But get_value() checks local cache first — so if a
# prior get_value() cached None for this key, subsequent reads return None even after
# the TTL-write. Fix: after every set_value with TTL, explicitly update local cache.

def _rk(*parts):
    """Site-safe Redis key via frappe.cache() (auto site-prefixed by make_key)."""
    return "chills_feed:" + ":".join(str(p) for p in parts)


def _cache_set(key, val, ttl):
    """Write to Redis with TTL, AND force-update frappe.local.cache to prevent stale None reads."""
    frappe.cache().set_value(key, val, expires_in_sec=ttl)
    frappe.local.cache[frappe.cache().make_key(key)] = val


_SENTINEL = object()  # marker for "key not in local cache at all"


def _cache_get(key):
    """
    Read from frappe.cache(), bypassing potentially-stale local cache Nones.

    Frappe's get_value() caches None in frappe.local.cache on first miss (even with
    expires=False default). If a subsequent set_value(..., expires_in_sec=X) writes to
    Redis but NOT to local cache (the Frappe TTL bug), get_value() returns stale None.

    Fix: if local cache has None for this key, go straight to Redis to verify.
    """
    import pickle as _pickle
    full_key = frappe.cache().make_key(key)
    local_val = frappe.local.cache.get(full_key, _SENTINEL)

    if local_val is not _SENTINEL and local_val is not None:
        return local_val  # Real cached value — trust it

    if local_val is _SENTINEL:
        # Not in local cache yet — standard get_value path
        return frappe.cache().get_value(key)

    # local_val is None — might be stale. Check Redis directly.
    raw = frappe.cache().get(full_key)
    if raw is not None:
        val = _pickle.loads(raw)
        frappe.local.cache[full_key] = val
        return val
    return None


def _cache_del(key):
    frappe.cache().delete_value(key)


# ── JSON parsing helpers ───────────────────────────────────────────────────────

def _parse_list(val):
    if not val:
        return []
    try:
        parsed = _json.loads(val) if isinstance(val, str) else val
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _parse_dict(val):
    if not val:
        return {}
    try:
        parsed = _json.loads(val) if isinstance(val, str) else val
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


# ── Per-user Redis state ───────────────────────────────────────────────────────

def _get_user_prefs(phone):
    """Returns {tag: float_score} dict from cache."""
    return _parse_dict(_cache_get(_rk("prefs", phone)))


def _set_user_prefs(phone, prefs, ttl=86400 * 30):
    _cache_set(_rk("prefs", phone), prefs, ttl)


def _get_thompson_state(phone):
    """Returns flat dict {'{tag}:a': float, '{tag}:b': float}."""
    return _parse_dict(_cache_get(_rk("thompson", phone)))


def _set_thompson_state(phone, state, ttl=86400 * 30):
    _cache_set(_rk("thompson", phone), state, ttl)


def _get_watched_state(phone):
    """Returns (watched_list, watched_set). List is ordered (oldest first)."""
    raw = _cache_get(_rk("watched", phone))
    lst = raw if isinstance(raw, list) else []
    return lst, set(lst)


def _add_to_watched(phone, chills_id):
    """Append to watched list with WATCHED_MAX sliding window."""
    lst, watched_set = _get_watched_state(phone)
    if chills_id in watched_set:
        return
    lst.append(chills_id)
    if len(lst) > WATCHED_MAX:
        lst = lst[len(lst) - WATCHED_MAX:]
    _cache_set(_rk("watched", phone), lst, 86400 * 90)


def _get_suppressed_outlets(phone):
    """Returns {outlet_id: expiry_unix} with expired entries auto-evicted."""
    raw = _parse_dict(_cache_get(_rk("suppress", phone)))
    now_ts = time.time()
    active = {oid: exp for oid, exp in raw.items() if exp > now_ts}
    if len(active) != len(raw):
        _cache_set(_rk("suppress", phone), active, 86400 * 30)
    return active


def _suppress_outlet(phone, outlet_id):
    suppressed = _get_suppressed_outlets(phone)
    suppressed[outlet_id] = time.time() + SUPPRESS_DAYS * 86400
    _cache_set(_rk("suppress", phone), suppressed, 86400 * 30)


# ── Thompson Sampling ──────────────────────────────────────────────────────────

def _thompson_sample(state, tag):
    """Sample from Beta(alpha, beta) for a tag. Returns float in (0, 1)."""
    alpha = state.get(f"{tag}:a", THOMPSON_ALPHA_INIT)
    beta  = state.get(f"{tag}:b", THOMPSON_BETA_INIT)
    try:
        return random.betavariate(max(alpha, 0.01), max(beta, 0.01))
    except Exception:
        return alpha / (alpha + beta)


def _thompson_is_explore(state, niche_tags):
    """
    Return True if this video should get an exploration boost.

    Exploration is triggered when a tag has HIGH UNCERTAINTY — meaning we have
    few actual observations (< THOMPSON_MIN_OBS) on that tag cluster.
    Well-known tags (many observations) are never flagged for exploration.

    This prevents echo chambers: uncertain tag clusters get served occasionally
    even if the user hasn't expressed a preference for them yet.
    """
    for tag in niche_tags:
        alpha = state.get(f"{tag}:a", THOMPSON_ALPHA_INIT)
        beta  = state.get(f"{tag}:b", THOMPSON_BETA_INIT)
        # Actual observations beyond the uniform prior (α=1, β=1)
        total_obs = (alpha - THOMPSON_ALPHA_INIT) + (beta - THOMPSON_BETA_INIT)
        if total_obs < THOMPSON_MIN_OBS:
            # Uncertain tag — sample from Beta to decide exploration
            # Uniform Beta(1,1) fires explore ~60% of the time; Beta with a few
            # obs fires less. Well-known tags (total_obs ≥ 8) never reach here.
            if _thompson_sample(state, tag) > 0.4:
                return True
    return False


def _update_thompson(phone, tags, success):
    if not tags:
        return
    state = _get_thompson_state(phone)
    for tag in tags:
        if success:
            state[f"{tag}:a"] = state.get(f"{tag}:a", THOMPSON_ALPHA_INIT) + 1.0
        else:
            state[f"{tag}:b"] = state.get(f"{tag}:b", THOMPSON_BETA_INIT) + 1.0
    _set_thompson_state(phone, state)


# ── Preference update ──────────────────────────────────────────────────────────

def _update_user_prefs(phone, tags, event_type):
    """Update in-cache tag preference scores and Thompson state."""
    if not tags:
        return
    delta = EVENT_PREF_DELTA.get(event_type, 0.0)
    if delta == 0.0:
        return
    prefs = _get_user_prefs(phone)
    for tag in tags:
        prefs[tag] = prefs.get(tag, 0.0) + delta
    _set_user_prefs(phone, prefs)
    _update_thompson(phone, tags, success=(delta > 0))


# ── Global candidate + score snapshots ────────────────────────────────────────

def _get_candidates_snapshot():
    """
    500 published Chills (90-day window) sorted by engagement.
    Cached globally, 5-min TTL.
    """
    cache_key = _rk("candidates_snapshot")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    rows = frappe.db.sql(
        """
        SELECT
            c.name                                          AS chills_id,
            c.outlet,
            c.outlet_lat,
            c.outlet_lng,
            c.niche_tags,
            c.custom_tags,
            c.views_count,
            c.likes_count,
            c.saves_count,
            c.shares_count,
            TIMESTAMPDIFF(HOUR, c.published_at, NOW())     AS age_hours
        FROM `tabChills` c
        WHERE c.status = 'published'
          AND c.published_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        ORDER BY
            (c.likes_count + c.saves_count * 2 + c.shares_count * 3) DESC,
            c.published_at DESC
        LIMIT %s
        """,
        [CANDIDATE_POOL],
        as_dict=True,
    )

    candidates = []
    for r in rows:
        niche = _parse_list(r.niche_tags)
        custom = _parse_list(r.custom_tags)
        candidates.append({
            "id":         r.chills_id,
            "outlet":     r.outlet or "",
            "lat":        float(r.outlet_lat or 0),
            "lng":        float(r.outlet_lng or 0),
            "niche_tags": niche,
            "tags":       niche + custom,
            "views":      cint(r.views_count),
            "likes":      cint(r.likes_count),
            "saves":      cint(r.saves_count),
            "shares":     cint(r.shares_count),
            "age_hours":  float(r.age_hours or 0),
        })

    _cache_set(cache_key, candidates, CANDIDATE_TTL)
    return candidates


def _compute_global_scores():
    """
    Bayesian engagement percentile + social proof percentile for all active Chills.

    Engagement: Bayesian smoothed watch_pct (prior mean=45%, weight=50 views).
    Social:     (saves×2 + shares×3) / max(views, 1) — saves/shares rate.
    Both: 7-day rolling window, percentile-ranked [0, 1].
    Chills with no watch events default to 50th percentile (neutral).
    """
    watch_agg = frappe.db.sql(
        """
        SELECT
            chills_id,
            SUM(watch_pct)  AS watch_pct_sum,
            COUNT(*)        AS watch_events
        FROM `tabChills Watch Event`
        WHERE creation >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          AND event_type IN ('watch_complete', 'watch_half', 'fast_skip', 'replay')
        GROUP BY chills_id
        """,
        as_dict=True,
    )

    social_rows = frappe.db.sql(
        """
        SELECT name AS chills_id, saves_count, shares_count, views_count
        FROM `tabChills`
        WHERE status = 'published'
          AND published_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        """,
        as_dict=True,
    )

    watch_map = {r.chills_id: r for r in watch_agg}
    eng_raw    = {}
    social_raw = {}

    for r in social_rows:
        cid = r.chills_id
        wa  = watch_map.get(cid)
        if wa and (wa.watch_events or 0) > 0:
            smoothed = (
                (wa.watch_pct_sum or 0) + BAYES_PRIOR_MEAN * 100 * BAYES_PRIOR_WEIGHT
            ) / ((wa.watch_events or 0) + BAYES_PRIOR_WEIGHT)
        else:
            smoothed = BAYES_PRIOR_MEAN * 100
        eng_raw[cid] = smoothed

        views          = cint(r.views_count) or 1
        social_raw[cid] = (cint(r.saves_count) * 2 + cint(r.shares_count) * 3) / views

    def _percentile_rank(raw_dict):
        if not raw_dict:
            return {}
        values = sorted(raw_dict.values())
        n = len(values)
        ranked = {}
        for cid, val in raw_dict.items():
            lo, hi = 0, n
            while lo < hi:
                mid = (lo + hi) // 2
                if values[mid] < val:
                    lo = mid + 1
                else:
                    hi = mid
            ranked[cid] = lo / n
        return ranked

    eng_pct = _percentile_rank(eng_raw)
    soc_pct = _percentile_rank(social_raw)

    return {
        cid: {
            "eng":    round(eng_pct.get(cid, 0.5), 4),
            "social": round(soc_pct.get(cid, 0.5), 4),
        }
        for cid in eng_raw
    }


def _get_global_scores_snapshot():
    """Returns pre-computed {chills_id: {eng, social}} snapshot (15-min TTL)."""
    cache_key = _rk("global_scores")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    scores = _compute_global_scores()
    _cache_set(cache_key, scores, GLOBAL_SCORES_TTL)
    return scores


# ── Scoring sub-functions ──────────────────────────────────────────────────────

def _score_engagement(candidate, global_scores):
    gs = global_scores.get(candidate["id"])
    return gs["eng"] if gs else 0.5     # new item → neutral prior


def _score_affinity(candidate, prefs):
    """Sigmoid-squashed tag affinity."""
    if not prefs:
        return 0.5
    tags = candidate["tags"]
    if not tags:
        return 0.3
    total_pref = sum(prefs.get(tag, 0.0) for tag in tags)
    norm  = total_pref / (len(tags) * 15.0)
    score = 1.0 / (1.0 + math.exp(-norm))
    return round(score, 4)


def _score_freshness(candidate):
    """
    Exponential decay with correct half-life formula:
    score = exp(−age × ln(2) / halflife)
    Score = 1.0 at age=0, 0.5 at age=7d (168h), 0.25 at age=14d.
    """
    age = float(candidate.get("age_hours", 0))
    return round(math.exp(-age * math.log(2) / FRESHNESS_HALFLIFE_HOURS), 4)


def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _score_location(candidate, user_lat, user_lng):
    """Linear [0,1] by distance. 0.5 when GPS unavailable on either side."""
    if not user_lat or not user_lng:
        return 0.5
    c_lat = candidate.get("lat", 0)
    c_lng = candidate.get("lng", 0)
    if not c_lat or not c_lng:
        return 0.5
    dist = _haversine_km(user_lat, user_lng, c_lat, c_lng)
    if dist <= NEAR_DISTANCE_KM:
        return 1.0
    if dist >= MAX_SCORE_DIST_KM:
        return 0.0
    return round(1.0 - (dist - NEAR_DISTANCE_KM) / (MAX_SCORE_DIST_KM - NEAR_DISTANCE_KM), 4)


def _score_social(candidate, global_scores):
    gs = global_scores.get(candidate["id"])
    return gs["social"] if gs else 0.3  # new content → lower default


def _final_score(candidate, global_scores, prefs, thompson_state, user_lat, user_lng):
    e = _score_engagement(candidate, global_scores)
    a = _score_affinity(candidate, prefs)
    f = _score_freshness(candidate)
    l = _score_location(candidate, user_lat, user_lng)
    s = _score_social(candidate, global_scores)
    score = W_ENGAGEMENT * e + W_AFFINITY * a + W_FRESHNESS * f + W_LOCATION * l + W_SOCIAL * s

    # Thompson exploration boost (+0.08 for uncertain tag clusters, capped at 1.0)
    if thompson_state and candidate["niche_tags"]:
        if _thompson_is_explore(thompson_state, candidate["niche_tags"]):
            score = min(1.0, score + 0.08)

    return round(score, 5)


# ── Diversity pass ─────────────────────────────────────────────────────────────

def _diversity_pass(scored_candidates):
    """
    Enforce outlet diversity constraints on a scored candidate list:
      1. Hard cap: any outlet exceeding MAX_PER_OUTLET_IN_QUEUE is DROPPED.
      2. Consecutive cap: no more than CONSECUTIVE_OUTLET_CAP consecutive
         from the same outlet; items violating this are deferred and
         re-inserted at the next valid position.

    Items are processed in score order. Outlet cap violations are dropped
    (not appended to end), ensuring the returned list strictly respects the cap.
    """
    outlet_counts = {}
    result  = []
    deferred = []  # items deferred due to consecutive constraint

    for item in scored_candidates:
        outlet = item["outlet"]
        count  = outlet_counts.get(outlet, 0)

        # Hard cap: drop items beyond the per-outlet limit
        if count >= MAX_PER_OUTLET_IN_QUEUE:
            continue

        # Before placing this item, try to re-insert any deferred items
        still_deferred = []
        for d in deferred:
            d_outlet = d["outlet"]
            d_count  = outlet_counts.get(d_outlet, 0)
            # Drop if cap was reached while it was waiting
            if d_count >= MAX_PER_OUTLET_IN_QUEUE:
                continue
            # Try inserting: check consecutive constraint with current result tail
            if result and len(result) >= CONSECUTIVE_OUTLET_CAP:
                recent = [r["outlet"] for r in result[-CONSECUTIVE_OUTLET_CAP:]]
                if len(set(recent)) == 1 and recent[0] == d_outlet:
                    still_deferred.append(d)
                    continue
            result.append(d)
            outlet_counts[d_outlet] = d_count + 1
        deferred = still_deferred

        # Check consecutive constraint for the current item
        if result and len(result) >= CONSECUTIVE_OUTLET_CAP:
            recent = [r["outlet"] for r in result[-CONSECUTIVE_OUTLET_CAP:]]
            if len(set(recent)) == 1 and recent[0] == outlet:
                deferred.append(item)
                continue

        result.append(item)
        outlet_counts[outlet] = count + 1

    # Drain deferred items (respecting both caps)
    for d in deferred:
        d_outlet = d["outlet"]
        d_count  = outlet_counts.get(d_outlet, 0)
        if d_count >= MAX_PER_OUTLET_IN_QUEUE:
            continue  # Drop
        if result and len(result) >= CONSECUTIVE_OUTLET_CAP:
            recent = [r["outlet"] for r in result[-CONSECUTIVE_OUTLET_CAP:]]
            if len(set(recent)) == 1 and recent[0] == d_outlet:
                continue  # Skip (no valid insertion point)
        result.append(d)
        outlet_counts[d_outlet] = d_count + 1

    return result


# ── Outlet round-robin interleave ────────────────────────────────────────────────

def _interleave_by_outlet(ids, shuffle_outlets=True):
    """
    Round-robin an ordered list of chills_ids across their outlets so the feed
    never shows one merchant's clips back-to-back and EVERY merchant surfaces
    near the top of the very first batch.

    Nothing is dropped — every id in `ids` is returned exactly once. Within a
    single outlet the incoming relative order (recency / engagement) is kept.

    This is the light-weight counterpart to `_diversity_pass` (which needs
    fully-scored candidates). It exists for the cold-start / trending / fallback
    paths, where the source query orders purely by an engagement score. Freshly
    uploaded content all ties at score 0, so MySQL hands it back in physical
    (upload) order — i.e. grouped merchant-by-merchant. This restores mixing.
    """
    if not ids or len(ids) < 3:
        return list(ids)

    placeholders = ",".join(["%s"] * len(ids))
    rows = frappe.db.sql(
        "SELECT name, outlet FROM `tabChills` WHERE name IN ({})".format(placeholders),
        list(ids),
        as_dict=True,
    )
    outlet_of = {r.name: (r.outlet or r.name) for r in rows}

    buckets = {}
    order   = []   # outlet visitation order (first-seen)
    for cid in ids:
        outlet = outlet_of.get(cid, cid)
        if outlet not in buckets:
            buckets[outlet] = []
            order.append(outlet)
        buckets[outlet].append(cid)

    # Only one merchant → nothing to interleave; preserve original order.
    if len(order) < 2:
        return list(ids)

    if shuffle_outlets:
        random.shuffle(order)

    result = []
    while any(buckets[o] for o in order):
        for o in order:
            if buckets[o]:
                result.append(buckets[o].pop(0))
    return result


# ── New content injection ──────────────────────────────────────────────────────

def _get_new_content_ids(watched_set):
    """Chills < NEW_CONTENT_HOURS old, not yet watched. 60-sec global cache."""
    cache_key = _rk("new_content")
    cached = _cache_get(cache_key)
    if cached is not None:
        return [cid for cid in cached if cid not in watched_set]

    rows = frappe.db.sql(
        """
        SELECT name FROM `tabChills`
        WHERE status = 'published'
          AND published_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
        ORDER BY published_at DESC
        LIMIT 60
        """,
        [NEW_CONTENT_HOURS],
        as_dict=True,
    )
    all_new = [r.name for r in rows]
    _cache_set(cache_key, all_new, 60)
    return [cid for cid in all_new if cid not in watched_set]


def _inject_new_content(queue_ids, new_ids, watched_set):
    """Insert new content at reserved slots, pushing displaced items back."""
    if not new_ids:
        return queue_ids

    queue    = list(queue_ids)
    in_queue = set(queue)
    new_ptr  = 0

    for slot in NEW_CONTENT_SLOTS:
        while new_ptr < len(new_ids) and new_ids[new_ptr] in in_queue:
            new_ptr += 1
        if new_ptr >= len(new_ids):
            break
        nid = new_ids[new_ptr]
        if slot < len(queue):
            queue.insert(slot, nid)
        else:
            queue.append(nid)
        in_queue.add(nid)
        new_ptr += 1

    return queue[:QUEUE_SIZE]


# ── Exhaustion fallback ────────────────────────────────────────────────────────

def _exhaustion_fallback(watched_set):
    """
    3-tier fallback when user has seen everything in 90-day pool.
    Tier 1 → 180-day   Tier 2 → all-time   Tier 3 → reset (allow rewatches)
    """
    for interval in [180, None]:
        where = f"AND published_at >= DATE_SUB(NOW(), INTERVAL {interval} DAY)" if interval else ""
        rows = frappe.db.sql(
            f"""
            SELECT name FROM `tabChills`
            WHERE status = 'published' {where}
            ORDER BY (likes_count + saves_count * 2 + shares_count * 3) DESC
            LIMIT 500
            """,
            as_dict=True,
        )
        unwatched = [r.name for r in rows if r.name not in watched_set]
        if unwatched:
            return _interleave_by_outlet(unwatched[:QUEUE_SIZE])

    # Tier 3: allow rewatches
    rows = frappe.db.sql(
        """
        SELECT name FROM `tabChills`
        WHERE status = 'published'
        ORDER BY (likes_count + saves_count * 2 + shares_count * 3) DESC
        LIMIT %s
        """,
        [QUEUE_SIZE],
        as_dict=True,
    )
    return _interleave_by_outlet([r.name for r in rows])


# ── Trending (cold start) ──────────────────────────────────────────────────────

def _get_trending_ids(limit=QUEUE_SIZE):
    """National trending: top engagement, last 30 days. 5-min global cache."""
    cache_key = _rk("trending", limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    rows = frappe.db.sql(
        """
        SELECT name FROM `tabChills`
        WHERE status = 'published'
          AND published_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        ORDER BY (views_count + likes_count * 3 + saves_count * 5 + shares_count * 7) DESC
        LIMIT %s
        """,
        [limit * 2],
        as_dict=True,
    )
    ids = [r.name for r in rows][:limit]
    _cache_set(cache_key, ids, 300)
    return ids


# ── Core queue builder ─────────────────────────────────────────────────────────

def _build_and_cache_queue(phone, lat, lng):
    """
    Build a QUEUE_SIZE personalised queue for `phone` and cache it.
    Returns list of chills_ids (ordered by relevance, diversified).

    New content (< 48h) is excluded from the scored pool and injected
    at reserved slots [6, 16, 26] — ensures new content always gets impressions
    regardless of engagement score.
    """
    lat = float(lat) if lat else 0.0
    lng = float(lng) if lng else 0.0

    watched_list, watched_set = _get_watched_state(phone)
    total_watches = len(watched_list)

    new_ids     = _get_new_content_ids(watched_set)
    new_ids_set = set(new_ids)

    # ── Cold start: 0 watches → pure trending (still filter suppressed outlets)
    if total_watches <= COLD_THRESHOLD:
        suppressed  = _get_suppressed_outlets(phone)
        now_ts      = time.time()
        trending_all = _get_trending_ids(QUEUE_SIZE * 3)
        if suppressed:
            sup_outlet_ids = {oid for oid, exp in suppressed.items() if exp > now_ts}
            if sup_outlet_ids:
                cands_for_sup = frappe.db.sql(
                    "SELECT name, outlet FROM `tabChills` WHERE name IN ({})".format(
                        ",".join(["%s"] * len(trending_all))
                    ),
                    trending_all,
                    as_dict=True,
                )
                sup_map = {r.name: r.outlet for r in cands_for_sup}
                trending_all = [cid for cid in trending_all if sup_map.get(cid) not in sup_outlet_ids]
        # Round-robin across merchants FIRST (the trending query orders purely
        # by engagement, so 0-engagement fresh uploads come back grouped by
        # merchant), THEN inject new content at its reserved slots.
        trending = _interleave_by_outlet(trending_all[:QUEUE_SIZE])
        queue    = _inject_new_content(trending, new_ids, watched_set)
        _cache_set(_rk("queue", phone), queue, QUEUE_TTL)
        return queue

    candidates     = _get_candidates_snapshot()
    global_scores  = _get_global_scores_snapshot()
    suppressed     = _get_suppressed_outlets(phone)
    prefs          = _get_user_prefs(phone)
    thompson_state = _get_thompson_state(phone)
    now_ts         = time.time()

    # ── Filter: remove watched + suppressed + new content (injected separately)
    filtered = [
        c for c in candidates
        if c["id"] not in watched_set
        and suppressed.get(c["outlet"], 0) < now_ts
        and c["id"] not in new_ids_set  # new content enters only via reserved slots
    ]

    # ── Exhaustion check ───────────────────────────────────────────────────────
    if len(filtered) < 10:
        fallback = _exhaustion_fallback(watched_set)
        _cache_set(_rk("queue", phone), fallback, QUEUE_TTL)
        return fallback

    # ── Score ──────────────────────────────────────────────────────────────────
    scored = []
    for c in filtered:
        score = _final_score(c, global_scores, prefs, thompson_state, lat, lng)
        scored.append({**c, "score": score})

    # ── Warm start blend: < WARM_THRESHOLD watches ─────────────────────────────
    if total_watches < WARM_THRESHOLD:
        trending_set = set(_get_trending_ids(100))
        warm_weight  = total_watches / WARM_THRESHOLD   # 0 → 1 as watches accumulate
        for item in scored:
            if item["id"] in trending_set:
                item["score"] = item["score"] * warm_weight + 0.7 * (1 - warm_weight)

    scored.sort(key=lambda x: x["score"], reverse=True)

    # ── Diversity pass ─────────────────────────────────────────────────────────
    diversified = _diversity_pass(scored)

    # ── Build queue + inject new content ──────────────────────────────────────
    queue_ids = [item["id"] for item in diversified[:QUEUE_SIZE]]
    queue_ids = _inject_new_content(queue_ids, new_ids, watched_set)

    _cache_set(_rk("queue", phone), queue_ids, QUEUE_TTL)
    return queue_ids


# ── Hydration ──────────────────────────────────────────────────────────────────

def _hydrate_chills_ids(chills_ids, phone):
    """Convert ordered list of chills_ids → full Chills dicts (preserves order)."""
    from flamezo_backend.flamezo.api.chills import (
        _format_chills, _fetch_interaction_sets,
        _get_outlet_follow_set, _get_offers_count_map,
        _get_outlet_ratings_map, _get_outlet_followers_map,
    )
    if not chills_ids:
        return []

    placeholders = ",".join(["%s"] * len(chills_ids))
    rows = frappe.db.sql(
        f"""
        SELECT
            c.name, c.outlet, c.outlet_name, c.outlet_city, c.outlet_logo,
            c.outlet_lat, c.outlet_lng, c.video_url, c.thumbnail_url,
            c.description, c.audio, c.niche_tags, c.custom_tags,
            c.location_name, c.location_lat, c.location_lng, c.location_radius,
            c.likes_count, c.saves_count, c.shares_count, c.views_count,
            c.published_at
        FROM `tabChills` c
        WHERE c.name IN ({placeholders}) AND c.status = 'published'
        """,
        chills_ids,
        as_dict=True,
    )

    row_map = {r.name: r for r in rows}
    ordered = [row_map[cid] for cid in chills_ids if cid in row_map]

    outlet_ids           = list({r.outlet for r in ordered if r.outlet})
    liked_set, saved_set = _fetch_interaction_sets(phone, [r.name for r in ordered])
    follow_set           = _get_outlet_follow_set(phone) if phone else set()
    offers_map           = _get_offers_count_map(outlet_ids)
    rating_map           = _get_outlet_ratings_map(outlet_ids)
    followers_map        = _get_outlet_followers_map(outlet_ids)

    return [_format_chills(r, liked_set, saved_set, follow_set, offers_map, rating_map, followers_map) for r in ordered]


# ── General-feed fallback (when personalisation has nothing) ──────────────────

def _build_general_fallback_queue(phone):
    """
    Last-resort content source for a phone whose personalised queue came back
    empty (thin catalogue, empty trending/candidate pools, or content that's
    all outside `_get_trending_ids`'s 30-day window).

    Deliberately sources from `get_chills_feed`'s plain recency query, NOT
    `_get_trending_ids` — the latter is itself scoped to the last 30 days and
    can be the very thing that's empty (e.g. a dev/staging catalogue seeded
    once, weeks ago), whereas the guest-facing recency feed has no such
    window and is confirmed to return content in that case. Still excludes
    what this phone has already watched, with a final unfiltered fallback so
    a user is never shown a hard-empty feed even if they've watched
    everything currently published.
    """
    from flamezo_backend.flamezo.api.chills import get_chills_feed
    _, watched_set = _get_watched_state(phone)

    general = get_chills_feed(phone=phone, limit=QUEUE_SIZE * 3)
    reels = ((general or {}).get("data") or {}).get("reels") or []
    ids = [r["id"] for r in reels if r.get("id")]

    fresh = [cid for cid in ids if cid not in watched_set]
    return _interleave_by_outlet((fresh or ids)[:QUEUE_SIZE])


# ── Public API endpoints ───────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_personalised_feed(phone=None, lat=None, lng=None, batch_size=10):
    """
    Main Chills feed endpoint.
    Authenticated users get personalised queue; anonymous users get trending.
    Returns next `batch_size` items and triggers async queue rebuild when low.

    Falls back to general (still watched-filtered, still paginated through
    the same per-phone queue) content whenever personalisation has nothing to
    offer, so a phone with an empty queue never sees a blank screen.
    """
    batch_size = min(int(batch_size or 10), 20)

    if not phone:
        from flamezo_backend.flamezo.api.chills import get_chills_feed
        return get_chills_feed(phone=None, limit=batch_size)

    phone = phone.strip()
    queue = _cache_get(_rk("queue", phone)) or []

    if not queue and not _cache_get(_rk("empty_backoff", phone)):
        # Skip this fairly expensive rebuild (candidate snapshot, scoring,
        # global-scores lookup) if we already know it failed very recently —
        # avoids re-running it on every single request from a user stuck
        # with no personalised content.
        queue = _build_and_cache_queue(phone, lat, lng)
        if not queue:
            _cache_set(_rk("empty_backoff", phone), True, EMPTY_BUILD_BACKOFF_TTL)

    if not queue:
        queue = _build_general_fallback_queue(phone)

    batch     = queue[:batch_size]
    remaining = queue[batch_size:]
    _cache_set(_rk("queue", phone), remaining, QUEUE_TTL)

    # Proactively rebuild in background when < 5 items remain
    if len(remaining) < 5:
        frappe.enqueue(
            "flamezo_backend.flamezo.api.chills_feed._bg_rebuild_queue",
            queue="short",
            phone=phone,
            lat=lat,
            lng=lng,
            enqueue_after_commit=True,
        )

    reels = _hydrate_chills_ids(batch, phone)

    # Same safety net at the batch level: if this specific slice hydrated to
    # nothing (e.g. cached ids that are no longer published) and there's no
    # more queue behind it, rebuild the general fallback immediately rather
    # than returning an empty reels list.
    if not reels and not remaining:
        fallback_queue = _build_general_fallback_queue(phone)
        fallback_batch = fallback_queue[:batch_size]
        fallback_remaining = fallback_queue[batch_size:]
        _cache_set(_rk("queue", phone), fallback_remaining, QUEUE_TTL)
        reels = _hydrate_chills_ids(fallback_batch, phone)
        remaining = fallback_remaining

    return {
        "success": True,
        "data": {
            "reels":           reels,
            "queue_remaining": len(remaining),
            "has_more":        len(remaining) > 0,
        },
    }


@frappe.whitelist(allow_guest=True)
def record_chills_event(
    phone, chills_id, event_type,
    watch_pct=0, watch_sec=0,
    source="feed", session_id=None,
):
    """
    Hot-path event recording. Cache-first, async DB write via frappe.enqueue.
    Drives preference learning and watched-set membership.
    """
    if not phone or not chills_id or not event_type:
        return {"success": False, "error": "phone, chills_id, event_type required"}

    phone     = phone.strip()
    watch_pct = max(0, min(100, cint(watch_pct)))

    # Fetch video metadata (outlet + tags) — 1-hour cache per video
    meta_key = _rk("meta", chills_id)
    meta = _cache_get(meta_key)
    if meta is None:
        row = frappe.db.sql(
            "SELECT outlet, niche_tags, custom_tags FROM `tabChills` WHERE name=%s",
            chills_id,
            as_dict=True,
        )
        if row:
            r = row[0]
            meta = {
                "outlet":      r.outlet or "",
                "niche_tags":  _parse_list(r.niche_tags),
                "custom_tags": _parse_list(r.custom_tags),
            }
        else:
            meta = {"outlet": "", "niche_tags": [], "custom_tags": []}
        _cache_set(meta_key, meta, 3600)

    all_tags  = meta["niche_tags"] + meta["custom_tags"]
    outlet_id = meta["outlet"]

    # Mark as watched (any event = seen, never repeat)
    _add_to_watched(phone, chills_id)

    # Update preferences + Thompson state
    _update_user_prefs(phone, all_tags, event_type)

    # not_interested: suppress outlet AND penalize tags (pref delta applied above)
    if event_type == "not_interested" and outlet_id:
        _suppress_outlet(phone, outlet_id)

    # Invalidate cached queue so next request builds fresh
    _cache_del(_rk("queue", phone))

    # Async DB write (fire-and-forget)
    frappe.enqueue(
        "flamezo_backend.flamezo.api.chills_feed._persist_watch_event_to_db",
        queue="short",
        phone=phone,
        chills_id=chills_id,
        event_type=event_type,
        watch_pct=watch_pct,
        watch_sec=cint(watch_sec),
        source=source or "feed",
        outlet_id=outlet_id,
        tags_snapshot=_json.dumps(all_tags),
        session_id=session_id or "",
        enqueue_after_commit=True,
    )

    return {"success": True, "data": {"ok": True}}


@frappe.whitelist(allow_guest=True)
def refresh_chills_queue(phone, lat=None, lng=None):
    """Force-rebuild a user's personalised queue (e.g. after preference change)."""
    if not phone:
        return {"success": False, "error": "phone required"}
    phone = phone.strip()
    _cache_del(_rk("queue", phone))
    queue = _build_and_cache_queue(phone, lat, lng)
    return {"success": True, "data": {"queue_size": len(queue)}}


@frappe.whitelist(allow_guest=True)
def seed_interest_preferences(phone, categories):
    """
    Onboarding: pre-seed preference scores for selected niche taxonomy IDs.
    Ensures first feed is personalised, not cold.
    """
    if not phone:
        return {"success": False, "error": "phone required"}
    phone = phone.strip()

    cats = _parse_list(categories) if isinstance(categories, str) else (categories or [])
    if not cats:
        return {"success": False, "error": "categories required"}

    prefs = _get_user_prefs(phone)
    for tag in cats:
        if isinstance(tag, str) and tag.strip():
            prefs[tag] = max(prefs.get(tag, 0.0), 25.0)

    _set_user_prefs(phone, prefs)
    _cache_del(_rk("queue", phone))

    return {"success": True, "data": {"seeded_tags": len(cats)}}


# ── Background helpers ─────────────────────────────────────────────────────────

def _bg_rebuild_queue(phone, lat=None, lng=None):
    """Async queue rebuild — called via frappe.enqueue when queue runs low."""
    try:
        _build_and_cache_queue(phone, lat, lng)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chills_feed:bg_rebuild_queue")


def _persist_watch_event_to_db(
    phone, chills_id, event_type, watch_pct, watch_sec,
    source, outlet_id, tags_snapshot, session_id,
):
    """Persist a watch event to `Chills Watch Event` doctype (called via enqueue)."""
    try:
        doc = frappe.get_doc({
            "doctype":             "Chills Watch Event",
            "user_phone":          phone,
            "chills_id":           chills_id,
            "event_type":          event_type,
            "watch_pct":           watch_pct,
            "watch_sec":           watch_sec,
            "source":              source,
            "outlet_id":           outlet_id,
            "niche_tags_snapshot": tags_snapshot,
            "session_id":          session_id,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chills_feed:persist_watch_event")


# ── Scheduler tasks ────────────────────────────────────────────────────────────

def recompute_global_scores():
    """Every 15 min: recompute Bayesian engagement + social percentile scores."""
    try:
        scores = _compute_global_scores()
        _cache_set(_rk("global_scores"), scores, GLOBAL_SCORES_TTL)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chills_feed:recompute_global_scores")


def refresh_candidates_snapshot():
    """Every 5 min: refresh candidate pool + new content + trending caches."""
    try:
        _cache_del(_rk("candidates_snapshot"))
        _cache_del(_rk("new_content"))
        _cache_del(_rk("trending", QUEUE_SIZE))
        _get_candidates_snapshot()
        _get_trending_ids(QUEUE_SIZE)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chills_feed:refresh_candidates_snapshot")


def sync_preferences_to_db():
    """
    Daily 02:00: persist Redis preferences to UserChillsPreference doctype
    and apply exponential decay (×0.99) to all tag preference scores.
    """
    try:
        phones = frappe.db.sql(
            """
            SELECT DISTINCT user_phone
            FROM `tabChills Watch Event`
            WHERE creation >= DATE_SUB(NOW(), INTERVAL 90 DAY)
            """,
            as_dict=True,
        )
        for row in phones:
            _sync_one_user_prefs(row.user_phone)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chills_feed:sync_preferences_to_db")


def _sync_one_user_prefs(phone):
    """Decay + upsert a single user's cache state to DB."""
    prefs          = _get_user_prefs(phone)
    thompson_state = _get_thompson_state(phone)
    suppressed     = _get_suppressed_outlets(phone)
    watched_list, _ = _get_watched_state(phone)

    # Decay and prune near-zero scores
    decayed = {
        tag: round(score * DAILY_DECAY, 4)
        for tag, score in prefs.items()
        if abs(score * DAILY_DECAY) > 0.1
    }
    if decayed != prefs:
        _set_user_prefs(phone, decayed)

    # Upsert to UserChillsPreference
    try:
        doc = frappe.get_doc("User Chills Preference", phone)
    except frappe.DoesNotExistError:
        doc = frappe.get_doc({
            "doctype":    "User Chills Preference",
            "user_phone": phone,
        })

    doc.tag_scores         = _json.dumps(decayed)
    doc.thompson_state     = _json.dumps(thompson_state)
    doc.suppressed_outlets = _json.dumps(suppressed)
    doc.total_watches      = len(watched_list)
    doc.last_active        = now_datetime()

    try:
        doc.save(ignore_permissions=True)
    except Exception:
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "chills_feed:sync_one_user_prefs")
