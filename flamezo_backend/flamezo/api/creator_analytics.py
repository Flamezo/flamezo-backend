"""
Self-serve "Instagram Insights"-style analytics for creators — the
merchant dashboard already has this (api/chills.py::get_chills_outlet_analytics
+ ChillsAnalytics.tsx), creators never had an equivalent. Every function here
is scoped to "my own" content only, same ownership-resolution pattern as
creator_rewards.py's `_require_own_creator`.
"""

import frappe
from frappe import _
from frappe.utils import cint, today, add_days, getdate

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils import redis_counters as rc


def _require_own_creator(phone: str) -> str:
	"""Same resolution as creator_rewards.py::_require_own_creator — kept as
	its own copy rather than a shared import so this module has no
	dependency on creator_rewards.py's internals; the logic is small and
	stable enough that duplication here is cheaper than coupling."""
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)

	creator_name = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
	if not creator_name:
		normalized = normalize_phone(phone)
		for row in frappe.db.get_all("Flamezo Creator", fields=["name", "customer_phone"]):
			if normalize_phone(row.customer_phone or "") == normalized:
				creator_name = row.name
				break

	if not creator_name:
		frappe.throw(_("No creator profile found for this phone."), frappe.DoesNotExistError)
	return creator_name


@frappe.whitelist(allow_guest=True)
def get_my_creator_status(phone):
	"""Non-throwing existence check — lets the app conditionally show a
	"My Insights" entry point only for people who actually have a creator
	profile, without needing a real analytics call (which throws
	DoesNotExistError for everyone else) just to probe for that."""
	if not phone or not has_active_customer_session(phone):
		return {"success": True, "data": {"is_creator": False, "status": None}}

	row = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "status")
	if not row:
		normalized = normalize_phone(phone)
		for r in frappe.db.get_all("Flamezo Creator", fields=["customer_phone", "status"]):
			if normalize_phone(r.customer_phone or "") == normalized:
				row = r.status
				break

	return {"success": True, "data": {"is_creator": bool(row), "status": row}}


@frappe.whitelist(allow_guest=True)
def get_my_chills_analytics(phone):
	"""Aggregate Chills performance for this creator — identical shape/query
	pattern to get_chills_outlet_analytics, scoped by `creator` instead of
	`outlet`."""
	creator_name = _require_own_creator(phone)

	agg = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS total_videos,
			COALESCE(SUM(views_count), 0)  AS total_views,
			COALESCE(SUM(likes_count), 0)  AS total_likes,
			COALESCE(SUM(saves_count), 0)  AS total_saves,
			COALESCE(SUM(shares_count), 0) AS total_shares
		FROM `tabChills`
		WHERE creator = %s AND status = 'published'
		""",
		creator_name,
		as_dict=True,
	)
	a = agg[0] if agg else {}

	total_videos = cint(a.get("total_videos"))
	total_views  = cint(a.get("total_views"))
	total_likes  = cint(a.get("total_likes"))
	total_saves  = cint(a.get("total_saves"))
	total_shares = cint(a.get("total_shares"))
	avg_views    = round(total_views / total_videos, 1) if total_videos else 0
	engagement   = round((total_likes + total_saves) / total_views * 100, 1) if total_views else 0

	top_rows = frappe.db.sql(
		"""
		SELECT name, video_url, thumbnail_url, description,
		       views_count, likes_count, saves_count, shares_count, published_at
		FROM `tabChills`
		WHERE creator = %s AND status = 'published'
		ORDER BY views_count DESC
		LIMIT 1
		""",
		creator_name,
		as_dict=True,
	)
	top_video = None
	if top_rows:
		t = top_rows[0]
		top_video = {
			"id": t.name,
			"thumbnail": t.thumbnail_url or t.video_url or "",
			"description": t.description or "",
			"views": cint(t.views_count),
			"likes": cint(t.likes_count),
			"saves": cint(t.saves_count),
			"shares": cint(t.shares_count),
			"published_at": str(t.published_at) if t.published_at else "",
		}

	return {
		"success": True,
		"data": {
			"total_videos": total_videos,
			"total_views": total_views,
			"total_likes": total_likes,
			"total_saves": total_saves,
			"total_shares": total_shares,
			"avg_views_per_video": avg_views,
			"engagement_rate": engagement,
			"top_video": top_video,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_my_chills(phone, cursor=None, limit=20):
	"""Paginated list of this creator's own Chills with per-video stats —
	same cursor shape as get_merchant_chills."""
	creator_name = _require_own_creator(phone)
	limit = min(int(limit), 50)

	conditions = ["creator = %s", "status != 'removed'"]
	params = [creator_name]

	if cursor:
		try:
			cur_ts, cur_name = cursor.split("|", 1)
			conditions.append("(published_at < %s OR (published_at = %s AND name < %s))")
			params += [cur_ts, cur_ts, cur_name]
		except ValueError:
			pass

	where = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT name, video_url, thumbnail_url, description,
		       views_count, likes_count, saves_count, shares_count,
		       status, published_at
		FROM `tabChills`
		WHERE {where}
		ORDER BY published_at DESC, name DESC
		LIMIT %s
		""",
		params + [limit + 1],
		as_dict=True,
	)

	has_more = len(rows) > limit
	items = rows[:limit]

	next_cursor = None
	if has_more and items:
		last = items[-1]
		next_cursor = f"{last.published_at}|{last.name}"

	return {
		"success": True,
		"data": {
			"videos": [
				{
					"id": r.name,
					"videoUrl": r.video_url or "",
					"thumbnail": r.thumbnail_url or "",
					"description": r.description or "",
					"views": cint(r.views_count),
					"likes": cint(r.likes_count),
					"saves": cint(r.saves_count),
					"shares": cint(r.shares_count),
					"status": r.status,
					"published_at": str(r.published_at) if r.published_at else "",
				}
				for r in items
			],
			"next_cursor": next_cursor,
			"has_more": has_more,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_my_club_analytics(phone):
	"""Aggregate Club Talks performance across every club post this creator
	has authored (no per-creator equivalent existed for merchants either —
	clubs.py only ever exposed per-post/per-comment CRUD)."""
	creator_name = _require_own_creator(phone)

	post_rows = frappe.db.sql(
		"""
		SELECT name, likes_count, comments_count, views_count
		FROM `tabCreator Club Post`
		WHERE creator = %s
		""",
		creator_name,
		as_dict=True,
	)

	total_posts = len(post_rows)
	post_ids = [p.name for p in post_rows]
	views_map = rc.get_counts(
		"club_post_views", post_ids,
		{p.name: p.views_count or 0 for p in post_rows},
	)

	total_views = sum(views_map.get(p.name, 0) for p in post_rows)
	total_likes = sum(cint(p.likes_count) for p in post_rows)
	total_comments = sum(cint(p.comments_count) for p in post_rows)
	avg_views = round(total_views / total_posts, 1) if total_posts else 0
	engagement = round((total_likes + total_comments) / total_views * 100, 1) if total_views else 0

	top_post = None
	if post_rows:
		top = max(post_rows, key=lambda p: views_map.get(p.name, 0))
		top_full = frappe.db.get_value(
			"Creator Club Post", top.name,
			["club", "post_type", "content", "image_url", "reel", "creation"],
			as_dict=True,
		)
		thumbnail = top_full.image_url or ""
		if top_full.post_type == "chills" and top_full.reel:
			thumbnail = frappe.db.get_value("Chills", top_full.reel, "thumbnail_url") or thumbnail
		top_post = {
			"id": top.name,
			"club_id": top_full.club,
			"post_type": top_full.post_type,
			"content": top_full.content or "",
			"thumbnail": thumbnail,
			"views": views_map.get(top.name, 0),
			"likes": cint(top.likes_count),
			"comments": cint(top.comments_count),
			"created_at": str(top_full.creation) if top_full.creation else "",
		}

	return {
		"success": True,
		"data": {
			"total_posts": total_posts,
			"total_views": total_views,
			"total_likes": total_likes,
			"total_comments": total_comments,
			"avg_views_per_post": avg_views,
			"engagement_rate": engagement,
			"top_post": top_post,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_my_club_posts(phone, cursor=None, limit=20):
	"""Paginated list of this creator's own Club Talks posts, across every
	club they've posted in, with per-post stats."""
	creator_name = _require_own_creator(phone)
	limit = min(int(limit), 50)

	conditions = ["cp.creator = %s"]
	params = [creator_name]

	if cursor:
		cursor_row = frappe.db.get_value("Creator Club Post", cursor, "creation")
		if cursor_row:
			conditions.append("(cp.creation < %s OR (cp.creation = %s AND cp.name < %s))")
			params += [cursor_row, cursor_row, cursor]

	where = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT cp.name, cp.club, cp.post_type, cp.content, cp.image_url, cp.reel,
		       cp.likes_count, cp.comments_count, cp.views_count, cp.creation,
		       cc.club_name
		FROM `tabCreator Club Post` cp
		JOIN `tabCreator Club` cc ON cc.name = cp.club
		WHERE {where}
		ORDER BY cp.creation DESC, cp.name DESC
		LIMIT %s
		""",
		params + [limit + 1],
		as_dict=True,
	)

	has_more = len(rows) > limit
	posts = rows[:limit]
	post_ids = [p.name for p in posts]

	views_map = rc.get_counts(
		"club_post_views", post_ids,
		{p.name: p.views_count or 0 for p in posts},
	)

	chills_ids = [p.reel for p in posts if p.post_type == "chills" and p.reel]
	thumb_map = {}
	if chills_ids:
		placeholders = ",".join(["%s"] * len(chills_ids))
		thumb_rows = frappe.db.sql(
			f"SELECT name, thumbnail_url FROM `tabChills` WHERE name IN ({placeholders})",
			chills_ids, as_dict=True,
		)
		thumb_map = {t.name: t.thumbnail_url for t in thumb_rows}

	next_cursor = None
	if has_more and posts:
		next_cursor = posts[-1].name

	return {
		"success": True,
		"data": {
			"posts": [
				{
					"id": p.name,
					"club_id": p.club,
					"club_name": p.club_name or "",
					"post_type": p.post_type,
					"content": p.content or "",
					"thumbnail": (p.image_url or thumb_map.get(p.reel, "")) or "",
					"views": views_map.get(p.name, 0),
					"likes": cint(p.likes_count),
					"comments": cint(p.comments_count),
					"created_at": str(p.creation) if p.creation else "",
				}
				for p in posts
			],
			"next_cursor": next_cursor,
			"has_more": has_more,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_my_follower_trend(phone, days=90):
	"""Daily-snapshotted follower history for a trend chart. In-app followers
	move daily (real Creator Follow COUNT at snapshot time); Instagram
	followers move in a staircase since the underlying value only refreshes
	monthly (creator_onboarding.monthly_follower_refresh) — both are real
	numbers, just different granularity, which the chart legend should make
	clear rather than interpolating a fake smooth line."""
	creator_name = _require_own_creator(phone)
	days = min(int(days), 365)
	since = add_days(today(), -days)

	rows = frappe.db.get_all(
		"Creator Follower Snapshot",
		filters={"creator": creator_name, "snapshot_date": [">=", since]},
		fields=["snapshot_date", "in_app_followers", "ig_followers"],
		order_by="snapshot_date asc",
	)

	current_in_app = frappe.db.count("Creator Follow", {"creator": creator_name})
	current_ig = cint(frappe.db.get_value("Flamezo Creator", creator_name, "meta_followers"))

	return {
		"success": True,
		"data": {
			"current_in_app_followers": current_in_app,
			"current_ig_followers": current_ig,
			"history": [
				{
					"date": str(r.snapshot_date),
					"in_app_followers": cint(r.in_app_followers),
					"ig_followers": cint(r.ig_followers),
				}
				for r in rows
			],
		},
	}


def daily_follower_snapshot():
	"""Scheduled job (register in hooks.py, daily). One row per creator per
	day — idempotent, safe to re-run same-day (skips creators who already
	have today's snapshot rather than inserting a duplicate)."""
	snapshot_date = getdate(today())

	creators = frappe.db.get_all(
		"Flamezo Creator",
		filters={"status": "approved"},
		fields=["name", "meta_followers"],
	)
	if not creators:
		return {"snapshotted": 0}

	already = set(frappe.db.get_all(
		"Creator Follower Snapshot",
		filters={"snapshot_date": snapshot_date, "creator": ["in", [c.name for c in creators]]},
		pluck="creator",
	))

	snapshotted, failed = 0, 0
	for creator in creators:
		if creator.name in already:
			continue
		try:
			in_app = frappe.db.count("Creator Follow", {"creator": creator.name})
			doc = frappe.new_doc("Creator Follower Snapshot")
			doc.creator = creator.name
			doc.snapshot_date = snapshot_date
			doc.in_app_followers = in_app
			doc.ig_followers = cint(creator.meta_followers)
			doc.insert(ignore_permissions=True)
			snapshotted += 1
		except Exception:
			# One bad row (rare DB hiccup, unexpected data) must never stop
			# every other creator in this run from getting snapshotted —
			# same resilience pattern as monthly_follower_refresh.
			failed += 1
			frappe.log_error(frappe.get_traceback(), f"daily_follower_snapshot: {creator.name}")
			continue

	frappe.db.commit()
	frappe.logger().info(f"[creator_analytics] daily_follower_snapshot: {snapshotted} snapshotted, {failed} failed")
	return {"snapshotted": snapshotted, "failed": failed}
