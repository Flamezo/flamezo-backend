import frappe
from frappe.model.document import Document


class CatalogueCategory(Document):
	def on_update(self):
		_invalidate_catalogue_cache(self.restaurant)

	def on_trash(self):
		_invalidate_catalogue_cache(self.restaurant)


def _invalidate_catalogue_cache(restaurant):
	if restaurant:
		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant}")
