import frappe

def run():
    if not frappe.db.has_column('Menu Category', 'is_active'):
        frappe.db.sql('ALTER TABLE `tabMenu Category` ADD COLUMN `is_active` TINYINT(1) DEFAULT 1')
        print("Added is_active to Menu Category")
    else:
        print("is_active already exists in Menu Category")

run()
