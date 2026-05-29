import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class AddonGroup(Document):
    def before_insert(self):
        if not self.group_id:
            self.group_id = self._generate_group_id()

    def validate(self):
        self._validate_selections()
        self._validate_items()
        self._assign_item_ids()

    def _generate_group_id(self):
        """Auto-generate a slug-based group_id from group_name."""
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', self.group_name.lower()).strip('-')
        # Ensure uniqueness within restaurant
        existing = frappe.db.count("Addon Group", {
            "restaurant": self.restaurant,
            "group_id": ["like", f"{slug}%"]
        })
        if existing:
            slug = f"{slug}-{existing + 1}"
        return slug

    def _validate_selections(self):
        """Validate min/max selection constraints are logical."""
        min_sel = cint(self.min_selections)
        max_sel = cint(self.max_selections)

        if min_sel < 0:
            frappe.throw(_("Minimum selections cannot be negative"))
        if max_sel < 0:
            frappe.throw(_("Maximum selections cannot be negative"))
        if max_sel > 0 and min_sel > max_sel:
            frappe.throw(_("Minimum selections cannot exceed maximum selections"))

        # For variations, enforce single select
        if self.group_type == "variation":
            if max_sel != 1:
                self.max_selections = 1
            if min_sel > 1:
                self.min_selections = 1

    def _validate_items(self):
        """Ensure at least one item exists and display orders are set."""
        if not self.items:
            frappe.throw(_("Addon Group must have at least one item"))

        for idx, item in enumerate(self.items):
            if not item.display_order:
                item.display_order = idx

    def _assign_item_ids(self):
        """Auto-generate item_id for items that don't have one."""
        import re
        for item in self.items:
            if not item.item_id:
                slug = re.sub(r'[^a-z0-9]+', '-', item.item_name.lower()).strip('-')
                item.item_id = f"{self.group_id}--{slug}"
