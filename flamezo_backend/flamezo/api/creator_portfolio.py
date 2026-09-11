"""
Creator Portfolio — public pages, self-serve settings, QR generation
(creator-marketplace-blueprint.html §15, §16, §19 Phase 7).

Public surface:
  get_public_portfolio(slug)  — the /c/<slug> page reads this; allow_guest=True,
                                rate-limited by IP, records a portfolio view.
  report_portfolio(slug)      — viewer flags a profile for ops review.

Creator self-serve:
  get_my_portfolio(phone)             — slug, visibility, headline, featured posts.
  update_my_portfolio(phone, ...)     — headline / visibility / featured_posts_json.
  get_my_qr_code(phone)               — base64 PNG QR for /c/<slug>?source=qr.
  get_my_portfolio_analytics(phone)   — view counts by source + day, last 30 days.

Slug rules:
  Auto-generated from display_name at portfolio creation: slugify, then make
  unique with a numeric suffix if needed.  Creators cannot change their own slug
  (slug stability = link stability).  Ops can rename with a direct DB write if
  needed (e.g. account takeover, brand change).

Visibility:
  public    — indexed by search engines, appears in the directory + leaderboard.
  unlisted  — /c/<slug> and QR both work; not in directory.  Default for new creators.
  private   — 404 for everyone, including the creator on the public URL.
"""

import base64
import io
import json
import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today

from flamezo_backend.flamezo.utils.creator_badges import _compute_badge_details
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.api.creator_collabs import (
    WEEKLY_ACCEPT_CAP,
    _accepted_this_week_count,
)

_VIEW_HOURLY_CAP_PER_IP = 20  # Redis key expires every hour; >20 views/IP/hr → skip DB write
_STALE_DAYS = 30              # days after which a follower count is flagged as stale


# ── slug helpers ──────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "", text.lower().replace(" ", ""))
    return text[:40] or "creator"


def _make_unique_slug(base_slug: str) -> str:
    slug = base_slug[:40]
    if not frappe.db.exists("Creator Portfolio", {"slug": slug}):
        return slug
    for i in range(2, 200):
        candidate = f"{slug[:37]}-{i}"
        if not frappe.db.exists("Creator Portfolio", {"slug": candidate}):
            return candidate
    return frappe.generate_hash(length=12)


def _ensure_portfolio(creator_name: str, display_name: str = "") -> str:
    """Returns the Creator Portfolio doc name, creating it (unlisted) if missing."""
    existing = frappe.db.get_value("Creator Portfolio", {"creator": creator_name}, "name")
    if existing:
        return existing

    slug = _make_unique_slug(_slugify(display_name or creator_name))
    portfolio = frappe.get_doc({
        "doctype": "Creator Portfolio",
        "creator": creator_name,
        "slug": slug,
        "visibility": "unlisted",
    })
    portfolio.insert(ignore_permissions=True)
    frappe.db.commit()
    return portfolio.name


def _require_own_creator(phone: str) -> str:
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


# ── public endpoint ───────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_public_portfolio(slug: str) -> dict:
    """
    Everything the /c/<slug> portfolio page renders.  All data is sourced from
    existing doctypes — no numbers are creator-editable except headline, bio,
    and which posts they feature.  Stale follower counts are flagged honestly
    rather than silently presented as current (blueprint §15 design principle).
    """
    portfolio = frappe.db.get_value(
        "Creator Portfolio", {"slug": slug},
        ["name", "creator", "visibility", "headline", "featured_posts_json"],
        as_dict=True,
    )
    if not portfolio:
        frappe.throw(_("Creator not found"), frappe.DoesNotExistError)
    if portfolio.visibility == "private":
        frappe.throw(_("This portfolio is not public"), frappe.PermissionError)

    creator = frappe.db.get_value(
        "Flamezo Creator",
        portfolio.creator,
        [
            "name", "display_name", "instagram_handle", "profile_image", "bio",
            "city", "status", "meta_followers", "meta_avg_views",
            "follower_count_last_synced", "approved_at",
        ],
        as_dict=True,
    )
    if not creator or creator.status != "approved":
        frappe.throw(_("Creator not found"), frappe.DoesNotExistError)

    tier, criteria = _compute_badge_details(portfolio.creator)

    # Follower staleness
    sync_date = creator.follower_count_last_synced
    sync_age_days = (getdate(today()) - getdate(sync_date)).days if sync_date else 9999
    is_stale = sync_age_days > _STALE_DAYS

    in_app_followers = frappe.db.count("Creator Follow", {"creator": portfolio.creator})

    # 90-day follower trend from daily snapshots
    trend_rows = frappe.db.get_all(
        "Creator Follower Snapshot",
        filters={
            "creator": portfolio.creator,
            "snapshot_date": [">=", frappe.utils.add_days(today(), -90)],
        },
        fields=["snapshot_date", "in_app_followers", "ig_followers"],
        order_by="snapshot_date asc",
    )
    trend = [
        {"date": str(r.snapshot_date), "in_app": cint(r.in_app_followers), "ig": cint(r.ig_followers)}
        for r in trend_rows
    ]

    # Collab history — two completion paths (legacy invites + marketplace deals)
    invite_count = cint(frappe.db.count(
        "Creator Collab Invite", {"creator": portfolio.creator, "status": "completed"}
    ))
    deal_count = cint(frappe.db.count(
        "Collab Deal", {"creator": portfolio.creator, "status": "released"}
    ))
    collabs_done = invite_count + deal_count

    rating_row = frappe.db.sql(
        "SELECT AVG(merchant_rating) AS avg_r, COUNT(*) AS cnt "
        "FROM `tabCreator Collab Invite` WHERE creator=%s AND merchant_rating > 0",
        portfolio.creator,
        as_dict=True,
    )
    avg_rating = round(flt(rating_row[0].avg_r), 1) if rating_row and rating_row[0].avg_r else None
    rating_count = cint(rating_row[0].cnt) if rating_row else 0

    total_earned = flt(frappe.db.sql(
        """
        SELECT COALESCE(SUM(et.creator_net_inr), 0)
        FROM `tabEscrow Transaction` et
        JOIN `tabCollab Deal` d ON d.name = et.deal
        WHERE d.creator = %s AND et.state = 'released'
        """,
        portfolio.creator,
    )[0][0] or 0)

    # "Worked with" — distinct outlets from both completion paths
    worked_with_rows = frappe.db.sql(
        """
        SELECT DISTINCT r.name AS outlet_id, r.outlet_name, r.logo
        FROM `tabOutlet` r
        WHERE r.name IN (
            SELECT outlet FROM `tabCollab Deal`
            WHERE creator = %(c)s AND status = 'released'
            UNION
            SELECT outlet FROM `tabCreator Collab Invite`
            WHERE creator = %(c)s AND status = 'completed'
        )
        LIMIT 12
        """,
        {"c": portfolio.creator},
        as_dict=True,
    )
    worked_with = [
        {"outlet_id": r.outlet_id, "outlet_name": r.outlet_name, "logo": r.logo or ""}
        for r in worked_with_rows
    ]

    # Rate cards — public pricing
    rate_cards = frappe.db.get_all(
        "Creator Rate Card",
        filters={"creator": portfolio.creator, "is_active": 1},
        fields=["deliverable_type", "price_inr", "accepts_barter", "barter_min_value_inr"],
        order_by="deliverable_type asc",
    )

    # Featured posts (creator-curated, falls back to top-viewed chills)
    featured_posts = _resolve_featured_posts(
        portfolio.creator,
        json.loads(portfolio.featured_posts_json or "[]"),
    )

    # Club card shown on portfolio
    club = frappe.db.get_value(
        "Creator Club",
        {"creator": portfolio.creator, "is_active": 1},
        ["name", "club_name", "category", "niche", "description", "cover_image", "followers_count"],
        as_dict=True,
    )

    # Weekly availability (for CTA "Send an invite" state)
    available_this_week = _accepted_this_week_count(portfolio.creator) < WEEKLY_ACCEPT_CAP

    _record_view(portfolio.creator)

    return {
        "success": True,
        "data": {
            "creator_id": creator.name,
            "display_name": creator.display_name or "",
            "instagram_handle": creator.instagram_handle or "",
            "profile_image": creator.profile_image or "",
            "bio": creator.bio or "",
            "headline": portfolio.headline or "",
            "city": creator.city or "",
            "badge_tier": tier,
            "badge_criteria": criteria,
            "slug": slug,
            "visibility": portfolio.visibility,
            "club": (
                {
                    "id": club.name,
                    "club_name": club.club_name,
                    "category": club.category,
                    "niche": club.niche or "",
                    "description": club.description or "",
                    "cover_image": club.cover_image or "",
                    "followers_count": cint(club.followers_count),
                }
                if club else None
            ),
            "verified_reach": {
                "meta_followers": cint(creator.meta_followers),
                "meta_avg_views": round(flt(creator.meta_avg_views)),
                "in_app_followers": in_app_followers,
                "last_synced": str(getdate(sync_date)) if sync_date else None,
                "sync_age_days": sync_age_days,
                "is_stale": is_stale,
            },
            "follower_trend": trend,
            "collabs_done": collabs_done,
            "avg_rating": avg_rating,
            "rating_count": rating_count,
            "total_earned_inr": total_earned,
            "worked_with": worked_with,
            "featured_posts": featured_posts,
            "rate_cards": [
                {
                    "deliverable_type": r.deliverable_type,
                    "price_inr": flt(r.price_inr),
                    "accepts_barter": bool(r.accepts_barter),
                    "barter_min_value_inr": flt(r.barter_min_value_inr),
                }
                for r in rate_cards
            ],
            "available_this_week": available_this_week,
        },
    }


def _resolve_featured_posts(creator_name: str, pinned: list) -> list:
    """
    Resolves a creator's featured_posts_json into real post rows, then fills
    any remaining slots (up to 6) with top-viewed published Chills.
    """
    posts = []
    seen_ids: set = set()

    for item in pinned[:6]:
        post_type = item.get("type")
        post_id = item.get("id")
        if not post_type or not post_id or post_id in seen_ids:
            continue

        if post_type == "native_chills":
            row = frappe.db.get_value(
                "Chills", post_id,
                ["name", "video_url", "thumbnail_url", "description", "views_count", "likes_count", "creator"],
                as_dict=True,
            )
            if row and row.creator == creator_name:
                seen_ids.add(post_id)
                posts.append({
                    "type": "chills", "id": row.name,
                    "thumbnail": row.thumbnail_url or row.video_url or "",
                    "description": row.description or "",
                    "views": cint(row.views_count), "likes": cint(row.likes_count),
                })

        elif post_type == "native_club_post":
            row = frappe.db.get_value(
                "Creator Club Post", post_id,
                ["name", "image_url", "content", "likes_count", "views_count", "creator"],
                as_dict=True,
            )
            if row and row.creator == creator_name:
                seen_ids.add(post_id)
                posts.append({
                    "type": "club_post", "id": row.name,
                    "thumbnail": row.image_url or "",
                    "description": row.content or "",
                    "views": cint(row.views_count), "likes": cint(row.likes_count),
                })

    # Backfill from top-viewed published Chills
    fill_needed = 6 - len(posts)
    if fill_needed > 0:
        exclusions = list(seen_ids) if seen_ids else ["__none__"]
        placeholders = ",".join(["%s"] * len(exclusions))
        top_chills = frappe.db.sql(
            f"""
            SELECT name, thumbnail_url, video_url, description, views_count, likes_count
            FROM `tabChills`
            WHERE creator = %s AND status = 'published' AND name NOT IN ({placeholders})
            ORDER BY views_count DESC
            LIMIT %s
            """,
            [creator_name] + exclusions + [fill_needed],
            as_dict=True,
        )
        for r in top_chills:
            posts.append({
                "type": "chills", "id": r.name,
                "thumbnail": r.thumbnail_url or r.video_url or "",
                "description": r.description or "",
                "views": cint(r.views_count), "likes": cint(r.likes_count),
            })

    return posts[:6]


def _record_view(creator_name: str) -> None:
    """Inserts one Creator Portfolio View, rate-limited to 20 per IP per hour
    so the analytics table can't be inflated by a bot hitting the endpoint."""
    try:
        client_ip = (
            frappe.request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if frappe.request else "server"
        ) or "unknown"
        cache_key = frappe.cache().make_key(f"portfolio_view_ip:{client_ip}")
        current = cint(frappe.cache().get_value(cache_key) or 0)
        if current >= _VIEW_HOURLY_CAP_PER_IP:
            return
        frappe.cache().set_value(cache_key, current + 1, expires_in_sec=3600)

        # Viewer outlet — only set when a logged-in merchant is looking
        viewer_outlet = None
        if frappe.session and frappe.session.user and frappe.session.user != "Guest":
            viewer_outlet = frappe.db.get_value("Outlet", {"owner": frappe.session.user}, "name")

        source = (frappe.form_dict.get("source") or "direct") if frappe.form_dict else "direct"

        frappe.get_doc({
            "doctype": "Creator Portfolio View",
            "creator": creator_name,
            "view_date": getdate(today()),
            "source": source if source in ("link", "qr", "directory", "bill_signal", "direct") else "direct",
            "viewer_outlet": viewer_outlet,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        # View tracking must never break the portfolio page load
        try:
            frappe.log_error(title="creator_portfolio.record_view", message=frappe.get_traceback())
        except Exception:
            pass


# ── creator self-management ───────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_my_portfolio(phone: str) -> dict:
    """Returns this creator's portfolio settings — slug, URL, visibility,
    headline, and which posts are currently pinned."""
    creator_name = _require_own_creator(phone)
    display_name = frappe.db.get_value("Flamezo Creator", creator_name, "display_name") or ""
    portfolio_name = _ensure_portfolio(creator_name, display_name)

    p = frappe.db.get_value(
        "Creator Portfolio", portfolio_name,
        ["slug", "visibility", "headline", "featured_posts_json"],
        as_dict=True,
    )
    return {
        "success": True,
        "data": {
            "slug": p.slug,
            "portfolio_url": f"https://flamezo.in/c/{p.slug}",
            "visibility": p.visibility,
            "headline": p.headline or "",
            "featured_posts": json.loads(p.featured_posts_json or "[]"),
        },
    }


@frappe.whitelist(allow_guest=True)
def update_my_portfolio(phone: str, headline=None, visibility=None, featured_posts_json=None) -> dict:
    """Creator updates their own portfolio — headline, visibility, featured posts.
    Slug is read-only from here (see module docstring)."""
    creator_name = _require_own_creator(phone)
    display_name = frappe.db.get_value("Flamezo Creator", creator_name, "display_name") or ""
    portfolio_name = _ensure_portfolio(creator_name, display_name)
    portfolio = frappe.get_doc("Creator Portfolio", portfolio_name)

    if headline is not None:
        portfolio.headline = (headline or "").strip()[:200]

    if visibility is not None:
        if visibility not in ("public", "unlisted", "private"):
            frappe.throw(_("visibility must be public, unlisted, or private"), frappe.ValidationError)
        portfolio.visibility = visibility

    if featured_posts_json is not None:
        if isinstance(featured_posts_json, str):
            try:
                posts = json.loads(featured_posts_json)
            except json.JSONDecodeError:
                frappe.throw(_("featured_posts_json must be valid JSON"), frappe.ValidationError)
        else:
            posts = featured_posts_json
        if not isinstance(posts, list):
            frappe.throw(_("featured_posts must be a list"), frappe.ValidationError)
        valid = [
            {"type": p["type"], "id": p["id"]}
            for p in posts[:6]
            if isinstance(p, dict)
            and p.get("type") in ("native_chills", "native_club_post")
            and p.get("id")
        ]
        portfolio.featured_posts_json = json.dumps(valid)

    portfolio.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "success": True,
        "data": {
            "slug": portfolio.slug,
            "portfolio_url": f"https://flamezo.in/c/{portfolio.slug}",
            "visibility": portfolio.visibility,
            "headline": portfolio.headline or "",
        },
    }


@frappe.whitelist(allow_guest=True)
def get_my_qr_code(phone: str) -> dict:
    """
    Returns a base64-encoded PNG QR code pointing to this creator's portfolio
    URL with ?source=qr so scans are tracked separately from link traffic.
    The QR fill color matches the Flamezo brand red (#E23744).
    """
    creator_name = _require_own_creator(phone)
    display_name = frappe.db.get_value("Flamezo Creator", creator_name, "display_name") or ""
    portfolio_name = _ensure_portfolio(creator_name, display_name)
    slug = frappe.db.get_value("Creator Portfolio", portfolio_name, "slug")

    portfolio_url = f"https://flamezo.in/c/{slug}?source=qr"

    import qrcode

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(portfolio_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#E23744", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "success": True,
        "data": {
            "qr_code_base64": qr_b64,
            "portfolio_url": portfolio_url,
            "slug": slug,
        },
    }


@frappe.whitelist(allow_guest=True)
def get_my_portfolio_analytics(phone: str) -> dict:
    """View counts by source + daily trend for the last 30 days — the portfolio
    analytics panel visible to the creator in the 'You' tab / creator dashboard."""
    creator_name = _require_own_creator(phone)

    since = frappe.utils.add_days(today(), -30)
    rows = frappe.db.get_all(
        "Creator Portfolio View",
        filters={"creator": creator_name, "view_date": [">=", since]},
        fields=["view_date", "source"],
        order_by="view_date asc",
    )

    total = len(rows)
    by_source: dict = {}
    by_day: dict = {}
    for r in rows:
        src = r.source or "direct"
        by_source[src] = by_source.get(src, 0) + 1
        day = str(r.view_date)
        by_day[day] = by_day.get(day, 0) + 1

    daily_trend = [{"date": d, "views": v} for d, v in sorted(by_day.items())]

    return {
        "success": True,
        "data": {
            "total_views_30d": total,
            "by_source": by_source,
            "daily_trend": daily_trend,
        },
    }


@frappe.whitelist(allow_guest=True)
def report_portfolio(slug: str) -> dict:
    """Any viewer can flag a profile for ops review.  Increments report_count;
    no automatic action — ops review at threshold.  Rate-limited the same way
    view recording is so a single user can't spam-report a creator."""
    portfolio = frappe.db.get_value("Creator Portfolio", {"slug": slug}, ["name", "report_count"], as_dict=True)
    if not portfolio:
        frappe.throw(_("Creator not found"), frappe.DoesNotExistError)

    client_ip = (
        frappe.request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if frappe.request else "server"
    ) or "unknown"
    report_key = frappe.cache().make_key(f"portfolio_report_ip:{client_ip}:{portfolio.name}")
    if frappe.cache().get_value(report_key):
        return {"success": True, "data": {"already_reported": True}}

    frappe.cache().set_value(report_key, 1, expires_in_sec=86400)
    frappe.db.set_value("Creator Portfolio", portfolio.name, "report_count", cint(portfolio.report_count) + 1)
    frappe.db.commit()
    return {"success": True, "data": {"reported": True}}
