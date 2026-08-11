# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Redis-buffered counters for hot-write interactions (likes, saves, views).

The problem: a naive `UPDATE tabX SET n = n + 1` on every like/view is a
synchronous MySQL round-trip that serializes on that row — fine at low
volume, but a viral Chills reel getting many concurrent likes turns that
row into a lock-contention hot spot, and the join-table exists-check before
it is a second round-trip per request.

The fix (same shape real feed products use): Redis becomes the live,
authoritative store for both the counter value and per-user toggle
membership (atomic INCR/DECR, atomic SADD/SREM/SISMEMBER — no
check-then-write race). The durable MySQL row is kept in sync by a
scheduled flush job instead of on every request. This only works without a
"cold vs genuinely zero" ambiguity because every counter is seeded from
MySQL exactly once via `backfill_from_db()` before it's ever trusted as
authoritative — see that function's docstring.

Any request-path code should:
  - read counts via `get_count()` / membership via `is_member()`
  - mutate via `toggle_member()` (returns the new state) + `bump_count()`
  - never touch the DB counter column directly once a scope is migrated here
"""

import redis as _redis_lib

import frappe

# frappe.cache() (RedisWrapper) overrides sadd/srem/sismember/smembers to
# auto-apply make_key() — but a `.pipeline()` object is a plain
# redis.client.Pipeline, NOT a RedisWrapper, so it does NOT go through those
# overrides. Mixing "pre-prefixed key + wrapper's own auto-prefix" (direct
# calls) with "pre-prefixed key + no auto-prefix" (piped calls) silently
# lands writes and batched reads on two different keys. Fix: always call the
# base redis.Redis implementation explicitly (bypassing RedisWrapper's
# overrides) so a manually-applied make_key() is the ONLY prefixing that
# ever happens, identically whether piped or not.
def _sadd(r, key, *values):
    return _redis_lib.Redis.sadd(r, key, *values)


def _srem(r, key, *values):
    return _redis_lib.Redis.srem(r, key, *values)


def _sismember(r, key, value):
    return _redis_lib.Redis.sismember(r, key, value)


def _smembers(r, key):
    return _redis_lib.Redis.smembers(r, key)

# Counter DB commits happen only in the flush job and the backfill — not on
# every request — so requests calling toggle_member/bump_count never block
# on MySQL for the counter itself. (The durable join-table row for likes is
# still written synchronously today — see the module doc in the calling
# file for why that part isn't buffered.)

_SCOPES = {
    # scope_name: (doctype, counter_field, join_doctype_or_None, join_parent_field_or_None)
    "chills_likes": ("Chills", "likes_count", "Chills Like", "chills"),
    "chills_saves": ("Chills", "saves_count", "Chills Save", "chills"),
    "chills_views": ("Chills", "views_count", None, None),
    "chills_shares": ("Chills", "shares_count", None, None),
    "club_post_views": ("Creator Club Post", "views_count", None, None),
}


def _key(*parts):
    raw = "counters:" + ":".join(str(p) for p in parts)
    return frappe.cache().make_key(raw)


def _count_key(scope, item_id):
    return _key(scope, "count", item_id)


def _members_key(scope, item_id):
    return _key(scope, "members", item_id)


def _dirty_key(scope):
    return _key(scope, "dirty")


def get_count(scope, item_id, db_fallback=0):
    """Live count for `item_id` in `scope`. Falls back to `db_fallback`
    (pass the DB column's current value) only if Redis is unreachable or
    this item was never backfilled/touched — both should be rare once
    `backfill_from_db()` has run."""
    r = frappe.cache()
    try:
        val = r.get(_count_key(scope, item_id))
    except Exception:
        return db_fallback
    return int(val) if val is not None else db_fallback


def get_counts(scope, item_ids, db_fallback_map=None):
    """Batched version of `get_count` — one MGET instead of N GETs."""
    db_fallback_map = db_fallback_map or {}
    item_ids = list(item_ids)
    if not item_ids:
        return {}
    r = frappe.cache()
    try:
        vals = r.mget([_count_key(scope, i) for i in item_ids])
    except Exception:
        return {i: db_fallback_map.get(i, 0) for i in item_ids}
    return {
        i: (int(v) if v is not None else db_fallback_map.get(i, 0))
        for i, v in zip(item_ids, vals)
    }


def is_member(scope, item_id, phone):
    if not phone:
        return False
    try:
        return bool(_sismember(frappe.cache(), _members_key(scope, item_id), phone))
    except Exception:
        return False


def members_for(scope, item_ids, phone):
    """Batched membership check across many items for one phone — used by
    feed formatting instead of one SISMEMBER call per item."""
    if not phone or not item_ids:
        return set()
    r = frappe.cache()
    out = set()
    try:
        pipe = r.pipeline()
        for i in item_ids:
            _sismember(pipe, _members_key(scope, i), phone)
        results = pipe.execute()
    except Exception:
        return set()
    for item_id, is_in in zip(item_ids, results):
        if is_in:
            out.add(item_id)
    return out


def toggle_member(scope, item_id, phone):
    """Atomically flips (item_id, phone) membership. Returns the NEW state
    (True = now a member / "liked", False = now removed)."""
    r = frappe.cache()
    key = _members_key(scope, item_id)
    if _sismember(r, key, phone):
        _srem(r, key, phone)
        return False
    _sadd(r, key, phone)
    return True


def bump_count(scope, item_id, delta):
    """Adjusts the live counter and marks the item dirty for the next flush."""
    r = frappe.cache()
    r.incrby(_count_key(scope, item_id), delta)
    _sadd(r, _dirty_key(scope), item_id)


def pop_dirty_items(scope):
    """Returns and clears the dirty-item set for `scope` — flush job only.
    Not perfectly atomic with what follows (a bump landing in the gap just
    gets picked up on the next pass instead of this one — nothing is
    lost, at worst a flush is one cycle late)."""
    r = frappe.cache()
    key = _dirty_key(scope)
    items = _smembers(r, key)
    if items:
        r.delete(key)
    return {i.decode() if isinstance(i, bytes) else i for i in items}


def flush_all():
    """Scheduled job (see hooks.py) — applies each dirty item's current
    Redis count to its real DB column. Writes the absolute value (not a
    delta) so a re-run after a partial failure is a no-op, not a
    double-application."""
    for scope, (doctype, field, _join_doctype, _join_field) in _SCOPES.items():
        dirty = pop_dirty_items(scope)
        if not dirty:
            continue
        for item_id in dirty:
            count = get_count(scope, item_id)
            frappe.db.sql(
                f"UPDATE `tab{doctype}` SET {field} = %s WHERE name = %s",
                (count, item_id),
            )
        frappe.db.commit()


def persist_toggle(join_doctype, join_parent_field, item_id, phone, active):
    """Background job (enqueued per like/save, off the request path) —
    reconciles the Redis toggle decision into the durable join-table row.
    Idempotent: re-running for the same final `active` state is a no-op."""
    filters = {join_parent_field: item_id, "customer_phone": phone}
    exists = frappe.db.exists(join_doctype, filters)
    if active and not exists:
        frappe.get_doc({
            "doctype": join_doctype,
            join_parent_field: item_id,
            "customer_phone": phone,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    elif not active and exists:
        frappe.delete_doc(join_doctype, exists, ignore_permissions=True)
        frappe.db.commit()


def backfill_from_db():
    """ONE-TIME seed — run manually once after deploying this module (e.g.
    `bench --site <site> execute flamezo_backend.flamezo.utils.redis_counters.backfill_from_db`),
    never automatically and never on a request path.

    Establishes the invariant every other function in this module relies
    on: once seeded, an empty Redis membership set means "genuinely zero",
    never "not yet warmed" — copies every existing counter value and
    join-table row into Redis so there's no cold-start ambiguity between
    "nobody liked this" and "Redis hasn't seen this item yet". Safe to
    re-run (SADD/SET are idempotent; re-running just re-asserts the same
    state) but pointless after the first run since `toggle_member` /
    `bump_count` keep Redis ahead of the DB from then on.
    """
    for scope, (doctype, field, join_doctype, join_field) in _SCOPES.items():
        rows = frappe.db.sql(f"SELECT name, {field} FROM `tab{doctype}`", as_dict=True)
        r = frappe.cache()
        for row in rows:
            r.set(_count_key(scope, row.name), row.get(field) or 0)
        if join_doctype:
            members = frappe.db.sql(
                f"SELECT {join_field} AS item_id, customer_phone FROM `tab{join_doctype}`",
                as_dict=True,
            )
            pipe = r.pipeline()
            for m in members:
                if m.item_id and m.customer_phone:
                    _sadd(pipe, _members_key(scope, m.item_id), m.customer_phone)
            if members:
                pipe.execute()
        frappe.logger().info(f"[redis_counters] backfilled {len(rows)} {doctype}.{field} values for scope={scope}")
