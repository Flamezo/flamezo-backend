import frappe


def execute():
	"""Ensure Restaurant Config.primary_color is populated based on color palette.

	For existing Restaurant Config records where primary_color is empty, pick the first
	non-empty value from the configured color palette fields. If no palette colors are
	set, fall back to the Flamezo default #DB782F.

	This keeps the stored primary_color in sync with how the API derives it, so other
	consumers (e.g. Desk UI, reports, or external integrations) can rely on a single
	source of truth.
	"""

	color_fields = [
		"color_palette_violet",
		"color_palette_indigo",
		"color_palette_blue",
		"color_palette_green",
		"color_palette_yellow",
		"color_palette_orange",
		"color_palette_red",
	]

	configs = frappe.get_all(
		"Restaurant Config",
		fields=["name", "primary_color"] + color_fields,
	)

	for cfg in configs:
		# Skip configs that already have a primary color
		if cfg.get("primary_color"):
			continue

		primary = None
		for field in color_fields:
			val = cfg.get(field)
			if val:
				primary = val
				break

		# Fallback to default brand color if nothing set
		if not primary:
			primary = "#DB782F"

		frappe.db.set_value("Restaurant Config", cfg["name"], "primary_color", primary, update_modified=False)

