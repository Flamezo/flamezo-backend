# Copyright (c) 2026, Flamezo and contributors
"""
Lightweight server-side link-preview fetcher for crowd chat — WhatsApp-style
title/description/image for a URL a customer typed. Server-side (not
client-side) only because a mobile client can't fetch arbitrary third-party
HTML directly (CORS); kept deliberately small — plain regex over the first
few KB of HTML, no HTML-parsing dependency, cached in Redis so the same
link is never re-fetched twice.
"""

import hashlib
import re
from urllib.parse import urlparse

import frappe
import requests

_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
_FETCH_TIMEOUT_SECONDS = 6
# Most sites put og/meta tags in the first few KB of <head>, but some
# (YouTube confirmed by testing) bury them ~700KB deep behind inline
# JSON/script payloads. Sized to reliably catch that real, common case
# while staying a bounded single read — not full-page parsing.
_MAX_BYTES = 900_000

_OG_RE = lambda prop: re.compile(  # noqa: E731
    rf'<meta[^>]+property=["\']og:{prop}["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)


def _cache_key(url):
    return "link_preview:" + hashlib.sha256(url.encode("utf-8")).hexdigest()


def fetch_link_preview(url):
    """Returns {url, title, description, image} (any field may be ""), or
    None if unfetchable/not worth showing. Best-effort — never raises."""
    if not url or len(url) > 2000:
        return None

    cache_key = _cache_key(url)
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return cached or None

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        # Basic guard against pointing this at the server's own loopback/
        # local network — not exhaustive SSRF hardening, just the obvious cases.
        if parsed.hostname in ("localhost", "127.0.0.1") or parsed.hostname.startswith(("10.", "192.168.", "172.")):
            return None

        resp = requests.get(
            url,
            timeout=_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FlamezoLinkPreview/1.0)"},
            stream=True,
        )
        html = resp.raw.read(_MAX_BYTES, decode_content=True).decode("utf-8", errors="ignore")

        def first(rx):
            m = rx.search(html)
            return m.group(1).strip() if m else ""

        title = first(_OG_RE("title")) or first(_TITLE_RE)
        description = first(_OG_RE("description")) or first(_DESC_RE)
        image = first(_OG_RE("image"))

        if not title and not description and not image:
            frappe.cache().set_value(cache_key, {}, expires_in_sec=_CACHE_TTL_SECONDS)
            return None

        preview = {"url": url, "title": title[:200], "description": description[:300], "image": image[:500]}
        frappe.cache().set_value(cache_key, preview, expires_in_sec=_CACHE_TTL_SECONDS)
        return preview

    except Exception:
        frappe.cache().set_value(cache_key, {}, expires_in_sec=3600)
        return None
