"""
Tests for the Markdown -> merge -> wkhtmltopdf pipeline behind
_render_agreement_pdf(). merge_fields() is pure logic (no Frappe needed);
render_markdown_to_pdf() shells out to wkhtmltopdf via frappe.utils.pdf, so
those tests need a real site (run via bench run-tests).
"""

import unittest

from flamezo_backend.flamezo.utils.agreement_pdf import merge_fields, render_markdown_to_pdf


class TestMergeFields(unittest.TestCase):
	def test_all_fields_resolved(self):
		merged, unresolved = merge_fields(
			"Name: {{legal_name}}, GST: {{gst_number}}",
			{"legal_name": "Acme Pvt Ltd", "gst_number": "24ABCDE1234F1Z5"},
		)
		self.assertEqual(merged, "Name: Acme Pvt Ltd, GST: 24ABCDE1234F1Z5")
		self.assertEqual(unresolved, [])

	def test_missing_field_left_blank_and_reported(self):
		merged, unresolved = merge_fields("GST: {{gst_number}}", {})
		self.assertEqual(merged, "GST: ")
		self.assertEqual(unresolved, ["gst_number"])

	def test_none_value_treated_as_unresolved_not_literal_none(self):
		# A field genuinely present in the snapshot dict but with value None
		# (e.g. FSSAI not captured for this outlet) must render as blank,
		# never as the literal string "None".
		merged, unresolved = merge_fields("FSSAI: {{fssai_number}}", {"fssai_number": None})
		self.assertEqual(merged, "FSSAI: ")
		self.assertEqual(unresolved, ["fssai_number"])

	def test_value_is_html_escaped(self):
		# Values flow through Markdown->HTML next — an untrusted merchant
		# name containing HTML-significant characters must not break or
		# inject into the rendered document.
		merged, _ = merge_fields("Name: {{legal_name}}", {"legal_name": "A&B <Foods> Pvt Ltd"})
		self.assertEqual(merged, "Name: A&amp;B &lt;Foods&gt; Pvt Ltd")

	def test_field_appearing_multiple_times_all_replaced(self):
		merged, unresolved = merge_fields(
			"{{legal_name}} agrees. Signed: {{legal_name}}", {"legal_name": "Acme"}
		)
		self.assertEqual(merged, "Acme agrees. Signed: Acme")
		self.assertEqual(unresolved, [])

	def test_no_placeholders_passes_through_unchanged(self):
		merged, unresolved = merge_fields("Plain text, no merge fields here.", {"legal_name": "X"})
		self.assertEqual(merged, "Plain text, no merge fields here.")
		self.assertEqual(unresolved, [])


class TestRenderMarkdownToPdf(unittest.TestCase):
	def test_produces_real_pdf_bytes(self):
		pdf_bytes = render_markdown_to_pdf("# Title\n\n**Bold** text and a table:\n\n"
			"| A | B |\n|---|---|\n| 1 | 2 |\n")
		self.assertTrue(pdf_bytes.startswith(b"%PDF"))
		self.assertGreater(len(pdf_bytes), 500)
