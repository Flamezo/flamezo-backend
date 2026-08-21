"""
AI Event Creation — Gemini 2.5 Flash
====================================

Two merchant-facing modes (mirrors the coupon generator):

  • "Describe Event" — the merchant types the event in plain words and the AI
    turns it into structured Event fields.
  • "Upload Poster"  — the merchant attaches the event poster (up to 3 images);
    Gemini vision reads it and extracts the event exactly as printed.

Both return Event-doctype-shaped dicts ready to pre-fill the merchant's Event
dialog (the merchant always reviews before saving). Quota/billing is shared with
the AI coupon generator so a restaurant has one monthly AI allowance.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe.utils import now_datetime, getdate, today

from flamezo_backend.flamezo.services.ai.base import get_gemini_client, handle_ai_error
from flamezo_backend.flamezo.services.ai.coupon_generator import (
    _extract_json_array,
    _check_and_increment_quota,
    FREE_MONTHLY_QUOTA,
)

logger = frappe.logger("flamezo.event_generator")

VALID_REPEATS = ("Daily", "Weekly", "Monthly", "Yearly")
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

EVENT_SCHEMA = """
Return a JSON array of event objects (usually ONE). Each object MUST have these fields:

{
  "title": "<short, punchy event name the customer sees>",
  "description": "<2-3 sentences: what happens, who it's for, why come>",
  "category": "<short free-text category in Title Case, using the merchant's own wording — e.g. Live Music, Brunch, DJ Night, Comedy Night, Kids Special, Festival>",
  "date": "<YYYY-MM-DD, or null if it is a purely recurring event>",
  "time": "<HH:MM:SS start time, 24h>",
  "end_time": "<HH:MM:SS end time, 24h, or null>",
  "location": "<venue / area text, or the restaurant name if not stated>",
  "registration_link": "<url or null>",
  "featured": <true only if it is a flagship/marquee event>,
  "repeat_this_event": <true if it repeats weekly/daily etc>,
  "repeat_on": "<null, or Daily|Weekly|Monthly|Yearly>",
  "repeat_till": "<YYYY-MM-DD or null — only when repeat_this_event is true>",
  "days": <[] or ["friday","saturday"] — weekdays it runs, only for recurring events>
}

HARD RULES:
0. LANGUAGE: the merchant may write in Hinglish, Hindi, Gujarati or any mix/script
   (e.g. "is saturday ko rooftop pe live music night rakhni hai, 7 baje se"), and a
   poster may also be in a regional language. UNDERSTAND any of it, but ALWAYS write
   EVERY output field in clean, natural ENGLISH — title, description, category and
   location must never be in Hinglish/Hindi. Keep proper nouns (venue, artist, dish
   names) as-is.
1. `date` must be TODAY or in the FUTURE — never a past date.
2. Resolve relative dates ("this Saturday", "next Friday", "tonight") against TODAY given below.
3. Times must be 24-hour "HH:MM:SS" (e.g. 8pm -> "20:00:00").
4. If the event repeats, set repeat_this_event=true, a sensible repeat_on, and list `days`.
5. Never invent a registration_link — use null unless one is explicitly given.
6. Keep `title` under 60 characters.
"""


def _outlet_context(outlet_id: str) -> dict[str, Any]:
    """Light context for the prompt. Defensive: a site missing any of these
    columns must never break event generation."""
    try:
        return frappe.db.get_value(
            "Outlet",
            outlet_id,
            ["outlet_name", "city", "state", "address"],
            as_dict=True,
        ) or {}
    except Exception:
        return {"outlet_name": frappe.db.get_value("Outlet", outlet_id, "outlet_name") or ""}


def _build_prompt(ctx: dict, user_prompt: str | None, from_poster: bool) -> str:
    now = now_datetime()
    today_str = now.strftime("%Y-%m-%d")
    weekday = now.strftime("%A")

    if from_poster:
        source_block = """
## SOURCE: EVENT POSTER IMAGE(S) — highest priority
One to three images are attached. They are DIFFERENT shots of the SAME event
(e.g. the poster plus its details/terms). Read them TOGETHER as one event.

STRICT RULES:
- Produce EXACTLY ONE event object matching what the poster shows. Return an array with ONE object.
- Use the EXACT title, date, time, venue, price and wording printed on the poster.
- Do NOT invent extra events or details that are not on the poster.
- If a field isn't shown, fill it in sensibly for this restaurant (or null).
- If the image has no readable event, return an empty array [].
"""
    else:
        source_block = f"""
## MERCHANT'S REQUEST — highest priority
The restaurant owner described the event in their own words:
"{(user_prompt or '').strip()}"

STRICT RULES:
- Build EXACTLY the event they described. Return an array with ONE object
  (only more if they clearly describe several distinct events).
- Use the exact day/time/price/details they mention. Don't invent extras.
- If something isn't specified, choose a sensible default for this restaurant.
"""

    return f"""You are an experienced restaurant events manager in India.
Turn the source below into a structured event for THIS restaurant.
{source_block}
## Restaurant
- Name: {ctx.get("outlet_name") or "this restaurant"}
- City: {ctx.get("city") or "India"}{", " + ctx["state"] if ctx.get("state") else ""}
- Address (use as default location): {ctx.get("address") or ctx.get("city") or ""}

## Today
- TODAY is {today_str} ({weekday}). Resolve every relative date against this.

## Output Format
{EVENT_SCHEMA}

CRITICAL OUTPUT INSTRUCTIONS:
- Return ONLY a raw JSON array. No markdown, no code fences, no commentary.
- Your response MUST start with [ and end with ].
"""


def _clean_time(t: Any) -> str | None:
    if not t:
        return None
    s = str(t).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
    if not m:
        return None
    h, mi, sec = int(m.group(1)), m.group(2), m.group(3) or "00"
    if h > 23:
        return None
    return f"{h:02d}:{mi}:{sec}"


def _clean_date(d: Any) -> str | None:
    if not d:
        return None
    s = str(d).strip()[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def _validate_and_clean_event(e: dict) -> dict | None:
    """Validate one AI event dict into Event-doctype shape. None if unusable."""
    try:
        title = str(e.get("title") or "").strip()[:140]
        if not title:
            return None

        date = _clean_date(e.get("date"))
        # Never create an event in the past.
        if date and getdate(date) < getdate(today()):
            date = None

        repeat = bool(e.get("repeat_this_event"))
        repeat_on = e.get("repeat_on") if e.get("repeat_on") in VALID_REPEATS else None
        if repeat and not repeat_on:
            repeat_on = "Weekly"

        raw_days = e.get("days") or []
        days = {d.lower() for d in raw_days if isinstance(d, str)} & set(DAY_NAMES)

        cleaned = {
            "title": title,
            "description": str(e.get("description") or "").strip()[:1000],
            "category": str(e.get("category") or "other").strip()[:50],
            "date": date,
            "time": _clean_time(e.get("time")) or "19:00:00",
            "end_time": _clean_time(e.get("end_time")),
            "location": str(e.get("location") or "").strip()[:200],
            "registration_link": str(e.get("registration_link") or "").strip()[:500] or None,
            "featured": bool(e.get("featured")),
            "repeat_this_event": repeat,
            "repeat_on": repeat_on,
            "repeat_till": _clean_date(e.get("repeat_till")) if repeat else None,
            "status": "recurring" if repeat else "upcoming",
            "is_active": 1,
        }
        # Individual weekday flags, as the Event doctype stores them.
        for d in DAY_NAMES:
            cleaned[d] = 1 if d in days else 0
        return cleaned
    except Exception as ex:
        logger.warning(f"[event_generator] Skipping invalid event: {ex} — raw: {e}")
        return None


def generate_events(
    outlet_id: str,
    user_prompt: str | None = None,
    poster_base64: str | list | None = None,
) -> dict[str, Any]:
    """Main entry. Returns {success, events[], quota} or {success: False, ...}."""
    if not user_prompt and not poster_base64:
        return {"success": False, "error_code": "NO_INPUT",
                "message": "Describe the event or attach a poster first."}

    # Normalize poster input → list of up to 3 base64 images.
    posters: list[str] = []
    if poster_base64:
        if isinstance(poster_base64, (list, tuple)):
            posters = list(poster_base64)
        else:
            s = str(poster_base64).strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    posters = parsed if isinstance(parsed, list) else [s]
                except Exception:
                    posters = [s]
            else:
                posters = [s]
        posters = [p for p in posters if p][:3]

    quota = _check_and_increment_quota(outlet_id)
    if not quota["allowed"]:
        return {
            "success": False,
            "error_code": "QUOTA_EXCEEDED",
            "message": (
                f"You've used all {FREE_MONTHLY_QUOTA} free AI generations this month. "
                f"Quota resets on {quota['resets_on']}."
            ),
            "quota": quota,
        }

    ctx = _outlet_context(outlet_id)
    prompt = _build_prompt(ctx, user_prompt, from_poster=bool(posters))

    try:
        model = get_gemini_client()
        generation_config = {
            "temperature": 0.6,
            "top_p": 0.95,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        if posters:
            parts: list = [prompt]
            for img in posters:
                b64 = img.split("base64,")[1] if "base64," in img else img
                parts.append({"mime_type": "image/jpeg", "data": b64})
            content = parts
        else:
            content = prompt
        response = model.generate_content(content, generation_config=generation_config)
        raw_text = response.text.strip()
    except Exception as ex:
        # Roll back the quota increment since generation failed.
        used = int(frappe.db.get_value("Outlet", outlet_id, "ai_coupon_generations_this_month") or 1)
        frappe.db.set_value("Outlet", outlet_id,
            {"ai_coupon_generations_this_month": max(used - 1, 0)}, update_modified=False)
        frappe.db.commit()
        return handle_ai_error(ex)

    raw_events = _extract_json_array(raw_text)
    if raw_events is None:
        logger.error(f"[event_generator] JSON parse failed for {outlet_id}: {raw_text[:300]}")
        return {"success": False, "error_code": "PARSE_ERROR",
                "message": "AI returned an unexpected format. Please try again.",
                "quota": {k: v for k, v in quota.items() if k != "allowed"}}

    events = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        cleaned = _validate_and_clean_event(raw)
        if cleaned:
            events.append(cleaned)

    if not events:
        return {"success": False, "error_code": "NO_VALID_EVENTS",
                "message": ("Couldn't read an event from that. Try adding more detail, "
                            "or a clearer poster."),
                "quota": {k: v for k, v in quota.items() if k != "allowed"}}

    return {
        "success": True,
        "events": events,
        "quota": {k: v for k, v in quota.items() if k != "allowed"},
    }
