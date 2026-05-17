# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import unittest
import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant, cleanup_restaurant

class TestEvent(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.restaurant = make_restaurant("TEST-EVENT-RES").name

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Event", {"restaurant": cls.restaurant})
		cleanup_restaurant(cls.restaurant)

	def test_create_event(self):
		doc = frappe.get_doc({
			"doctype": "Event",
			"restaurant": self.restaurant,
			"title": "Test Event",
			"date": "2026-05-01",
			"time": "19:00:00",
			"image_src": "http://example.com/image.jpg",
			"is_active": 1,
			"category": "Party"
		})
		doc.insert()
		self.assertTrue(frappe.db.exists("Event", doc.name))

	def test_get_list_with_filters(self):
		# This will test the reportview.py logic
		from frappe.desk.reportview import execute
		
		# Insert a test event
		doc = frappe.get_doc({
			"doctype": "Event",
			"restaurant": self.restaurant,
			"title": "Filter Test Event",
			"date": "2026-05-01",
			"time": "19:00:00",
			"image_src": "http://example.com/image.jpg",
			"is_active": 1
		}).insert()

		# Test with proper filters (as expected by execute)
		filters = [["Event", "restaurant", "=", self.restaurant]]
		results = execute("Event", filters=filters, fields=["name", "title"])
		self.assertTrue(len(results) >= 1)
		
		# Test with the format that was failing in reportview.py if fieldname is None
		# Although execute expects fieldname, we want to ensure no crash if something weird happens
		# But primarily we are testing that it works now.
		
	def test_reportview_safeguard(self):
		# Directly test the safeguard in is_standard
		from frappe.desk.reportview import is_standard
		
		# Should not crash and return False
		self.assertFalse(is_standard(None))
		self.assertFalse(is_standard(""))

	def test_upload_session_as_restaurant(self):
		# This tests the fix for "event_image role not allowed for Restaurant"
		from flamezo_backend.flamezo.media.api import request_upload_session
		
		# Set session user to Administrator to bypass access checks easily
		old_user = frappe.session.user
		frappe.set_user("Administrator")
		
		try:
			# This should NOT throw ValidationError anymore
			result = request_upload_session(
				owner_doctype="Restaurant",
				owner_name=self.restaurant,
				media_role="event_image",
				filename="test.jpg",
				content_type="image/jpeg",
				size_bytes=1024
			)
			self.assertIn("upload_id", result)
		finally:
			frappe.set_user(old_user)

	def test_custom_category(self):
		# This tests the fix for custom category validation
		event = frappe.get_doc({
			"doctype": "Event",
			"restaurant": self.restaurant,
			"title": "Custom Category Event",
			"image_src": "https://example.com/test.jpg",
			"date": "2026-05-10",
			"time": "18:00:00",
			"category": "Suscipit cupiditate" # This should now be allowed
		})
		event.insert()
		self.assertEqual(event.category, "Suscipit cupiditate")

if __name__ == "__main__":
	unittest.main()
