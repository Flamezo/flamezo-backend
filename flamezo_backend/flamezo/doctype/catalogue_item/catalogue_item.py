import frappe
from frappe.model.document import Document


class CatalogueItem(Document):
	def validate(self):
		# Ensure category belongs to the same restaurant
		if self.category:
			cat_restaurant = frappe.db.get_value("Catalogue Category", self.category, "outlet")
			if cat_restaurant and cat_restaurant != self.outlet:
				frappe.throw("Category does not belong to this outlet.")

		# Ensure only one sub_item row is marked primary in item_media
		primary_count = sum(1 for m in (self.item_media or []) if m.is_primary)
		if primary_count == 0 and self.item_media:
			self.item_media[0].is_primary = 1
		elif primary_count > 1:
			for i, m in enumerate(self.item_media):
				m.is_primary = 1 if i == 0 else 0

	def on_update(self):
		_invalidate_catalogue_cache(self.outlet)

	def on_trash(self):
		_invalidate_catalogue_cache(self.outlet)


def _invalidate_catalogue_cache(restaurant):
	if restaurant:
		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant}")
