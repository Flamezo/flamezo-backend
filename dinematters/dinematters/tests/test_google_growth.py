import frappe
import unittest
import json
from dinematters.dinematters.api.google_business import generate_seo_slug, get_google_auth_url

class TestGoogleGrowth(unittest.TestCase):
    def setUp(self):
        self.restaurant = frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_name": "Test Google Restaurant",
            "owner_email": "test@google.com",
            "is_active": 1
        }).insert()
        frappe.db.commit()

    def tearDown(self):
        try:
            # Delete linked products first if they exist
            products = frappe.get_all("Menu Product", filters={"restaurant": self.restaurant.name})
            for p in products:
                frappe.delete_doc("Menu Product", p.name, force=True)
            
            frappe.delete_doc("Restaurant", self.restaurant.name, force=True)
            frappe.db.commit()
        except:
            frappe.db.rollback()

    def test_slug_generation(self):
        self.assertEqual(generate_seo_slug("Hello World!"), "hello-world")
        self.assertEqual(generate_seo_slug("Pizza & Pasta"), "pizza-pasta")
        self.assertEqual(generate_seo_slug("   Spaces   "), "spaces")

    def test_auth_url_generation(self):
        # Mock site config
        frappe.conf.google_client_id = "test_client_id"
        frappe.conf.google_redirect_uri = "https://test.com/callback"
        
        res = get_google_auth_url(self.restaurant.name)
        self.assertIn("client_id=test_client_id", res["auth_url"])
        self.assertIn(f"state={self.restaurant.name}", res["auth_url"])

    def test_menu_sync_payload(self):
        # Create a product
        product = frappe.get_doc({
            "doctype": "Menu Product",
            "product_name": "Test Pizza",
            "restaurant": self.restaurant.name,
            "price": 500,
            "category_name": "Pizzas",
            "is_active": 1
        }).insert()
        
        # Test the sync logic (mocked)
        from dinematters.dinematters.api.google_business import sync_menu_to_google
        
        # Should fail because enable_google_sync is 0
        res = sync_menu_to_google(self.restaurant.name)
        self.assertFalse(res["success"])
        
        # Enable sync
        frappe.db.set_value("Restaurant", self.restaurant.name, "enable_google_sync", 1)
        frappe.db.set_value("Restaurant", self.restaurant.name, "google_business_location_id", "test_loc")
        
        # Should still fail because no refresh token
        res = sync_menu_to_google(self.restaurant.name)
        self.assertFalse(res["success"])
        self.assertIn("Account not authorized", res["message"])
