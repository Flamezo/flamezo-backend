"""Canonical list of dish attributes (dietary / highlight badges).

Single source of truth shared by the merchant dashboard (to render the
selectable pills on the Edit Item page) and the consumer app (to render the
badges on the dish card / detail page). Selected attribute *keys* are stored on
`Menu Product.dietary_attributes` as a JSON array of strings, e.g.
["veg", "spicy", "new"]. Never store labels/icons on the product — resolve them
from here at read time so they can never drift.

Icons are named after **Lucide** icon components (lucide-react), rendered by the
frontend. No emoji — Lucide renders identically on every device and can be
tinted per attribute.

Curated for the Indian market (no beef/pork/kosher/shellfish).
"""

import frappe
import json

# Maximum attributes a merchant can assign to a single dish. Shared by the
# doctype controller (enforcement) and the merchant UI (via get_dish_attributes).
MAX_DISH_ATTRIBUTES = 10

# group -> ordered list of attributes.
#   key      : stable id stored on the product (never change once shipped)
#   label    : display text
#   icon     : Lucide icon component name (see frontend ICON_MAP)
#   primary  : eligible to lead the compact dish CARD when there are many tags
ATTRIBUTE_GROUPS = [
	{
		"group": "highlight",
		"group_label": "Highlight",
		"attributes": [
			{"key": "new", "label": "New", "icon": "Sparkles", "primary": True},
			{"key": "bestseller", "label": "Bestseller", "icon": "Flame", "primary": True},
			{"key": "must-try", "label": "Must Try", "icon": "Star", "primary": False},
			{"key": "recommended", "label": "Recommended", "icon": "ThumbsUp", "primary": False},
			{"key": "seasonal", "label": "Seasonal", "icon": "Sun", "primary": False},
		],
	},
	{
		"group": "diet",
		"group_label": "Diet",
		"attributes": [
			{"key": "veg", "label": "Veg", "icon": "Leaf", "primary": True},
			{"key": "non-veg", "label": "Non-Veg", "icon": "Drumstick", "primary": True},
			{"key": "egg", "label": "Egg", "icon": "Egg", "primary": False},
			{"key": "vegan", "label": "Vegan", "icon": "Sprout", "primary": False},
			{"key": "jain", "label": "Jain", "icon": "Flower2", "primary": True},
			{"key": "no-onion-garlic", "label": "No Onion-Garlic", "icon": "Ban", "primary": False},
			{"key": "sattvic", "label": "Sattvic", "icon": "Gem", "primary": False},
		],
	},
	{
		"group": "spice",
		"group_label": "Spice Level",
		"attributes": [
			{"key": "mild", "label": "Mild", "icon": "Flame", "primary": False},
			{"key": "spicy", "label": "Spicy", "icon": "Flame", "primary": True},
			{"key": "extra-spicy", "label": "Extra Spicy", "icon": "Flame", "primary": False},
		],
	},
	{
		"group": "health",
		"group_label": "Health",
		"attributes": [
			{"key": "gluten-free", "label": "Gluten-Free", "icon": "WheatOff", "primary": False},
			{"key": "sugar-free", "label": "Sugar-Free", "icon": "Ban", "primary": False},
			{"key": "keto", "label": "Keto", "icon": "Beef", "primary": False},
			{"key": "high-protein", "label": "High-Protein", "icon": "Dumbbell", "primary": False},
			{"key": "low-calorie", "label": "Low-Calorie", "icon": "Feather", "primary": False},
			{"key": "organic", "label": "Organic", "icon": "Leaf", "primary": False},
		],
	},
	{
		"group": "allergen",
		"group_label": "Allergen",
		"attributes": [
			{"key": "contains-nuts", "label": "Contains Nuts", "icon": "TriangleAlert", "primary": False},
			{"key": "contains-dairy", "label": "Contains Dairy", "icon": "Milk", "primary": False},
		],
	},
]

# When a compact card must trim to a few badges, prefer these groups in order.
_CARD_GROUP_ORDER = ["highlight", "diet", "spice"]

# Show every selected attribute on the card up to this count; beyond it, trim to
# the best few.
_CARD_SHOW_ALL_UPTO = 3

# Flat lookup: key -> {..attr.., "group": group} — built once at import.
_ATTR_BY_KEY = {}
for _g in ATTRIBUTE_GROUPS:
	for _a in _g["attributes"]:
		_ATTR_BY_KEY[_a["key"]] = {**_a, "group": _g["group"]}


def parse_keys(raw):
	"""Normalise a stored `dietary_attributes` value into a clean list of keys.

	Accepts a JSON array string, a comma-separated string, or a list. Silently
	drops anything that isn't a known attribute key so bad data never reaches
	the UI.
	"""
	if not raw:
		return []
	keys = raw
	if isinstance(raw, str):
		raw = raw.strip()
		try:
			keys = json.loads(raw) if raw.startswith("[") else [k.strip() for k in raw.split(",")]
		except (ValueError, TypeError):
			keys = [k.strip() for k in raw.split(",")]
	if not isinstance(keys, (list, tuple)):
		return []
	# de-dupe while preserving order, keep only known keys
	seen, out = set(), []
	for k in keys:
		if k in _ATTR_BY_KEY and k not in seen:
			seen.add(k)
			out.append(k)
	return out


def resolve(raw):
	"""Turn a stored value into the full badge objects the UI renders.

	Returns a list of {key, label, icon, group, primary} in the order the
	merchant selected them.
	"""
	return [
		{
			"key": k,
			"label": _ATTR_BY_KEY[k]["label"],
			"icon": _ATTR_BY_KEY[k]["icon"],
			"group": _ATTR_BY_KEY[k]["group"],
			"primary": _ATTR_BY_KEY[k]["primary"],
		}
		for k in parse_keys(raw)
	]


def card_badges(raw):
	"""Badges to show on a compact dish card.

	Up to 3 selected -> show them all (order preserved). More than 3 -> trim to
	the 3 best (primary first, then Highlight/Diet/Spice order).
	"""
	resolved = resolve(raw)
	if len(resolved) <= _CARD_SHOW_ALL_UPTO:
		return resolved
	rank = {g: i for i, g in enumerate(_CARD_GROUP_ORDER)}
	ranked = sorted(
		resolved,
		key=lambda a: (not a["primary"], rank.get(a["group"], len(_CARD_GROUP_ORDER))),
	)
	return ranked[:_CARD_SHOW_ALL_UPTO]


@frappe.whitelist(allow_guest=True)
def get_dish_attributes():
	"""Return the full grouped attribute catalogue for the merchant Edit Item UI."""
	return {"groups": ATTRIBUTE_GROUPS}
