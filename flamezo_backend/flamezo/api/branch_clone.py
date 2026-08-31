# Copyright (c) Flamezo. Licensed under MIT.
"""
Admin-only "Copy content to branches".

A platform admin (Flamezo Supervisor / System Manager) fills one branch fully,
then copies its full menu setup into the merchant's OTHER branches in one click.

Design goals
------------
* ADMIN ONLY. Merchants can never call this (role-gated).
* Only shows / targets branches that belong to the SAME owner as the source
  (matched on Restaurant.owner_email) — never unrelated outlets.
* Independent copies: each branch gets its own Menu Category / Menu Product /
  Addon Group records, so editing one branch never affects another.
* Zero image-generation cost: product/category images are reused by URL
  (product_media.media_url / category_image point at the same CDN files) — we
  never re-upload or regenerate an image.
* Non-destructive: existing items in a target branch (matched by name) are
  skipped, never overwritten or deleted. (Replace / Add-only modes are a future
  enhancement — deliberately omitted for now.)

Identity / money / operational data is NEVER copied (address, phone, GST, bank /
Razorpay KYC, tables, staff, orders, ledgers, customers) — that stays unique to
each branch.
"""

import frappe
from frappe import _


ADMIN_ROLES = {"System Manager", "Administrator", "Flamezo Supervisor"}


def _assert_admin():
	"""Only platform admins may copy content across branches."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & ADMIN_ROLES):
		frappe.throw(_("Only Flamezo admins can copy content across branches."), frappe.PermissionError)


def _parse_ids(target_outlet_ids):
	"""Accept a JSON string, comma list, or python list of outlet ids."""
	if isinstance(target_outlet_ids, (list, tuple)):
		return [str(x).strip() for x in target_outlet_ids if str(x).strip()]
	if not target_outlet_ids:
		return []
	import json
	try:
		parsed = json.loads(target_outlet_ids)
		if isinstance(parsed, (list, tuple)):
			return [str(x).strip() for x in parsed if str(x).strip()]
	except Exception:
		pass
	return [b.strip() for b in str(target_outlet_ids).split(",") if b.strip()]


@frappe.whitelist()
def search_branches(query=None, limit=20):
	"""Type-ahead search over outlets (name / id / city) — used when picking
	branches for a group. Admin-only."""
	_assert_admin()
	q = (query or "").strip()
	or_filters = None
	if q:
		like = f"%{q}%"
		or_filters = [
			["outlet_name", "like", like],
			["name", "like", like],
			["city", "like", like],
		]
	rows = frappe.get_all(
		"Outlet",
		or_filters=or_filters,
		fields=["name as id", "outlet_name", "city", "outlet_type", "branch_group"],
		order_by="outlet_name asc",
		limit=int(limit or 20),
	)
	return {"success": True, "branches": rows}


@frappe.whitelist()
def list_groups():
	"""All Merchant Groups with their branch counts — for group dropdowns/filters."""
	_assert_admin()
	groups = frappe.get_all("Merchant Group", fields=["name as id", "group_name"], order_by="group_name asc")
	for g in groups:
		g["branch_count"] = frappe.db.count("Outlet", {"branch_group": g["id"]})
	return {"success": True, "groups": groups}


@frappe.whitelist()
def list_group_branches(group_id):
	"""Branches that belong to a Merchant Group."""
	_assert_admin()
	rows = frappe.get_all(
		"Outlet",
		filters={"branch_group": group_id},
		fields=["name as id", "outlet_name", "city", "outlet_type"],
		order_by="outlet_name asc",
	)
	return {"success": True, "branches": rows}


@frappe.whitelist()
def create_group(group_name, outlet_ids=None):
	"""Create a named Merchant Group and (optionally) assign branches to it."""
	_assert_admin()
	name = (group_name or "").strip()
	if not name:
		return {"success": False, "error": "Group name is required"}
	if frappe.db.exists("Merchant Group", {"group_name": name}):
		return {"success": False, "error": f"A group named '{name}' already exists"}

	group = frappe.get_doc({"doctype": "Merchant Group", "group_name": name})
	group.insert(ignore_permissions=True)

	ids = [r for r in _parse_ids(outlet_ids) if frappe.db.exists("Outlet", r)]
	for r in ids:
		frappe.db.set_value("Outlet", r, "branch_group", group.name)
	return {"success": True, "group": group.name, "group_name": name, "assigned": len(ids)}


@frappe.whitelist()
def add_to_group(group_id, outlet_ids):
	"""Add one or more branches to an existing Merchant Group."""
	_assert_admin()
	if not frappe.db.exists("Merchant Group", group_id):
		return {"success": False, "error": "Group not found"}
	ids = [r for r in _parse_ids(outlet_ids) if frappe.db.exists("Outlet", r)]
	for r in ids:
		frappe.db.set_value("Outlet", r, "branch_group", group_id)
	return {"success": True, "group": group_id, "assigned": len(ids)}


@frappe.whitelist()
def remove_from_group(outlet_id):
	"""Detach a branch from its group (make it standalone)."""
	_assert_admin()
	if not frappe.db.exists("Outlet", outlet_id):
		return {"success": False, "error": "Outlet not found"}
	frappe.db.set_value("Outlet", outlet_id, "branch_group", None)
	return {"success": True}


@frappe.whitelist()
def rename_group(group_id, group_name):
	"""Rename an existing Merchant Group."""
	_assert_admin()
	if not frappe.db.exists("Merchant Group", group_id):
		return {"success": False, "error": "Group not found"}
	name = (group_name or "").strip()
	if not name:
		return {"success": False, "error": "Group name is required"}
	# Block a name collision with a DIFFERENT group.
	clash = frappe.db.get_value("Merchant Group", {"group_name": name}, "name")
	if clash and clash != group_id:
		return {"success": False, "error": f"A group named '{name}' already exists"}
	frappe.db.set_value("Merchant Group", group_id, "group_name", name)
	return {"success": True, "group": group_id, "group_name": name}


@frappe.whitelist()
def delete_group(group_id):
	"""Delete a Merchant Group. Any branches in it are detached (made standalone),
	never deleted — only the grouping is removed."""
	_assert_admin()
	if not frappe.db.exists("Merchant Group", group_id):
		return {"success": False, "error": "Group not found"}
	detached = 0
	for r in frappe.get_all("Outlet", filters={"branch_group": group_id}, pluck="name"):
		frappe.db.set_value("Outlet", r, "branch_group", None)
		detached += 1
	frappe.delete_doc("Merchant Group", group_id, ignore_permissions=True, force=True)
	return {"success": True, "detached": detached}


@frappe.whitelist()
def assign_outlet_group(outlet_id, group_id=None, group_name=None):
	"""Assign ONE outlet to a group — the "add merchant to a group" action used by
	the add-merchant popup and the group manager. If group_id is given, use it; else
	if group_name is given, reuse an existing group of that name or CREATE a new one.
	Pass neither to detach the outlet (make it standalone)."""
	_assert_admin()
	if not frappe.db.exists("Outlet", outlet_id):
		return {"success": False, "error": "Outlet not found"}

	target = None
	if group_id:
		if not frappe.db.exists("Merchant Group", group_id):
			return {"success": False, "error": "Group not found"}
		target = group_id
	elif group_name and group_name.strip():
		name = group_name.strip()
		existing = frappe.db.get_value("Merchant Group", {"group_name": name}, "name")
		if existing:
			target = existing
		else:
			target = frappe.get_doc({"doctype": "Merchant Group", "group_name": name}).insert(ignore_permissions=True).name

	frappe.db.set_value("Outlet", outlet_id, "branch_group", target)  # None = detach
	return {"success": True, "outlet": outlet_id, "group": target,
	        "group_name": frappe.db.get_value("Merchant Group", target, "group_name") if target else None}


# ──────────────────────────────────────────────────────────────────────────────
# Cloning helpers — each returns a mapping of source docname -> target docname so
# foreign keys (category, parent_category, addon_group) can be re-pointed.
# ──────────────────────────────────────────────────────────────────────────────

def _clone_addon_groups(source, target):
	mapping = {}
	for g in frappe.get_all("Addon Group", filters={"outlet": source}, fields=["name", "group_name"]):
		existing = frappe.db.get_value("Addon Group", {"outlet": target, "group_name": g.group_name}, "name")
		if existing:
			mapping[g.name] = existing
			continue
		src = frappe.get_doc("Addon Group", g.name)
		new = frappe.copy_doc(src)
		new.outlet = target
		new.group_id = None  # regenerated in before_insert
		new.insert(ignore_permissions=True)
		mapping[g.name] = new.name
	return mapping


def _clone_categories(source, target):
	mapping = {}
	cats = frappe.get_all(
		"Menu Category",
		filters={"outlet": source},
		fields=["name", "category_name", "parent_category"],
	)
	# Parents (no parent_category) first so child->parent remap resolves.
	cats.sort(key=lambda c: 0 if not c.parent_category else 1)

	for c in cats:
		existing = frappe.db.get_value("Menu Category", {"outlet": target, "category_name": c.category_name}, "name")
		if existing:
			mapping[c.name] = existing
			continue
		src = frappe.get_doc("Menu Category", c.name)
		new = frappe.copy_doc(src)
		new.outlet = target
		new.category_id = None  # regenerated in validate
		# Re-point parent link to the target's copy (None = becomes top-level).
		new.parent_category = mapping.get(src.parent_category) if src.parent_category else None
		new.insert(ignore_permissions=True)
		mapping[c.name] = new.name
	return mapping


def _clone_products(source, target, cat_map, group_map):
	copied = 0
	skipped = 0
	for p in frappe.get_all("Menu Product", filters={"outlet": source}, fields=["name", "product_name"]):
		if frappe.db.exists("Menu Product", {"outlet": target, "product_name": p.product_name}):
			skipped += 1
			continue
		src = frappe.get_doc("Menu Product", p.name)
		new = frappe.copy_doc(src)
		new.outlet = target
		new.product_id = None  # regenerated in validate
		new.seo_slug = None    # regenerated in validate
		# Re-point category link to the target's copied category.
		if new.category:
			new.category = cat_map.get(src.category)
		# Re-point add-on group links.
		for row in (new.addon_groups or []):
			if row.addon_group:
				row.addon_group = group_map.get(row.addon_group, row.addon_group)
		# Images: keep the CDN url (zero cost, reused file); drop the cross-tenant
		# Media Asset link so deleting the source's asset can't cascade here.
		for m in (new.product_media or []):
			m.media_asset = None
		new.insert(ignore_permissions=True)
		copied += 1
	return copied, skipped


def _clone_offers(source, target):
	"""Copy display Offers. Additive: skip an offer whose title already exists."""
	copied = skipped = 0
	for o in frappe.get_all("Offer", filters={"outlet": source}, fields=["name", "title"]):
		if o.title and frappe.db.exists("Offer", {"outlet": target, "title": o.title}):
			skipped += 1
			continue
		src = frappe.get_doc("Offer", o.name)
		new = frappe.copy_doc(src)          # image_src (URL) reused — no cost
		new.outlet = target
		new.insert(ignore_permissions=True)
		copied += 1
	return copied, skipped


def _clone_coupons(source, target):
	"""Copy merchant coupons. Additive: skip a coupon whose code already exists.
	System-managed coupons (UGC shadow coupons) are never copied — the target
	branch manages its own."""
	copied = skipped = 0
	for c in frappe.get_all("Coupon", filters={"outlet": source}, fields=["name", "code", "category"]):
		if (c.category or "") == "ugc_exclusive":
			continue  # auto-synced from the target's own UGC config
		if c.code and frappe.db.exists("Coupon", {"outlet": target, "code": c.code}):
			skipped += 1
			continue
		src = frappe.get_doc("Coupon", c.name)
		new = frappe.copy_doc(src)
		new.outlet = target             # autoname becomes {target}-{code}
		new.insert(ignore_permissions=True)
		copied += 1
	return copied, skipped


def _clone_gallery(source, target):
	"""Copy gallery items. Additive: skip an item whose url already exists.
	Media urls are reused — no re-upload.

	Google Places photos (source="Google Places") are NOT copied — every branch
	pulls its own Google photos from its own Google Business listing, so leaking
	the source branch's Google images into a sibling's showcase would be wrong.
	Only the merchant's own uploaded gallery is shared across the group."""
	copied = skipped = 0
	for g in frappe.get_all("Outlet Gallery Item", filters={"outlet": source}, fields=["name", "url", "source"]):
		if (g.source or "") == "Google Places":
			skipped += 1
			continue
		if g.url and frappe.db.exists("Outlet Gallery Item", {"outlet": target, "url": g.url}):
			skipped += 1
			continue
		src = frappe.get_doc("Outlet Gallery Item", g.name)
		new = frappe.copy_doc(src)
		new.outlet = target
		new.insert(ignore_permissions=True)
		copied += 1
	return copied, skipped


# Presentation-only fields. Identity / social / security / per-branch state are
# deliberately excluded (restaurant_name, *_link, whatsapp, pins, tokens, paid/status/history).
# The AI menu-theme background / wallpapers ("Vibes for you") are ALSO excluded on
# purpose — each branch keeps its own AI menu background, never the source's.
_BRANDING_FIELDS = [
	"tagline", "subtitle", "description", "default_theme", "logo_size",
	"hero_video", "apple_touch_icon", "menu_layout", "qr_background",
]


def _clone_branding(source, target):
	"""Copy the brand look (logo, theme, colours, layout) so all branches of a
	brand match. Unlike menu/offers, branding is OVERWRITTEN — a brand's branches
	are meant to look identical. The AI menu-theme background / wallpapers
	("Vibes for you") are NOT copied — each branch keeps its own. Returns True if
	anything changed."""
	changed = False

	# Logo lives on Restaurant (single source of truth), cloned separately.
	src_logo = frappe.db.get_value("Outlet", source, "logo")
	if src_logo and frappe.db.get_value("Outlet", target, "logo") != src_logo:
		frappe.db.set_value("Outlet", target, "logo", src_logo)
		changed = True

	src_cfg = frappe.db.get_value("Outlet Config", {"outlet": source}, "name")
	tgt_cfg = frappe.db.get_value("Outlet Config", {"outlet": target}, "name")
	if not src_cfg or not tgt_cfg:
		return changed
	src_doc = frappe.get_doc("Outlet Config", src_cfg)
	tgt_doc = frappe.get_doc("Outlet Config", tgt_cfg)
	for f in _BRANDING_FIELDS:
		val = src_doc.get(f)
		if val not in (None, "") and tgt_doc.get(f) != val:
			tgt_doc.set(f, val)
			changed = True
	if changed:
		tgt_doc.save(ignore_permissions=True)
	return changed


@frappe.whitelist()
def clone_content_to_branches(source_outlet_id, target_outlet_ids):
	"""Copy the source branch's full menu setup into the given target branches.

	Returns a per-branch summary. Non-destructive: existing items are skipped.
	"""
	_assert_admin()

	if not frappe.db.exists("Outlet", source_outlet_id):
		return {"success": False, "error": "Source branch not found"}

	targets = _parse_ids(target_outlet_ids)
	if not targets:
		return {"success": False, "error": "Select at least one target branch"}

	# Copy only within the source's Merchant Group — never leak a menu across merchants.
	src_group = frappe.db.get_value("Outlet", source_outlet_id, "branch_group")
	results = []

	for t in targets:
		if t == source_outlet_id:
			continue
		if not frappe.db.exists("Outlet", t):
			results.append({"branch": t, "status": "not_found"})
			continue
		t_group = frappe.db.get_value("Outlet", t, "branch_group")
		if not src_group or t_group != src_group:
			results.append({"branch": t, "status": "skipped_different_group"})
			continue

		try:
			group_map = _clone_addon_groups(source_outlet_id, t)
			cat_map = _clone_categories(source_outlet_id, t)
			copied, skipped = _clone_products(source_outlet_id, t, cat_map, group_map)
			offers_copied, offers_skipped = _clone_offers(source_outlet_id, t)
			coupons_copied, coupons_skipped = _clone_coupons(source_outlet_id, t)
			gallery_copied, gallery_skipped = _clone_gallery(source_outlet_id, t)
			branding_copied = _clone_branding(source_outlet_id, t)
			results.append({
				"branch": t,
				"status": "ok",
				"categories": len(cat_map),
				"addon_groups": len(group_map),
				"products_copied": copied,
				"products_skipped": skipped,
				"offers_copied": offers_copied,
				"offers_skipped": offers_skipped,
				"coupons_copied": coupons_copied,
				"coupons_skipped": coupons_skipped,
				"gallery_copied": gallery_copied,
				"gallery_skipped": gallery_skipped,
				"branding_copied": branding_copied,
			})
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(f"clone_content_to_branches {source_outlet_id}->{t}: {e}", "Branch Clone Error")
			results.append({"branch": t, "status": "error", "message": str(e)})

	return {"success": True, "source": source_outlet_id, "results": results}
