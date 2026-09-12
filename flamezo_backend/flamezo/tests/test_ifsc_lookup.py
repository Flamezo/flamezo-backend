"""
Tests for the IFSC -> bank/branch lookup used to auto-fill Schedule A's
"Bank Name & Branch" row. Fixture shape is Razorpay's own real response
(https://ifsc.razorpay.com/UTIB0000566), fetched and verified live before
writing this test, not guessed.
"""

import unittest
from unittest.mock import MagicMock, patch

from flamezo_backend.flamezo.utils.ifsc_lookup import format_bank_name_branch, lookup_ifsc

_REAL_RESPONSE_SHAPE = {
	"BRANCH": "ADAJAN",
	"SWIFT": None,
	"ISO3166": "IN-GJ",
	"CONTACT": "",
	"NEFT": True,
	"DISTRICT": "SURAT",
	"RTGS": True,
	"UPI": True,
	"ADDRESS": "18,19,20, SHRIDHAR COMPLEX, ANAND MAHAL ROAD, ADAJAN, SURAT 395009",
	"MICR": "395211004",
	"STATE": "GUJARAT",
	"IMPS": True,
	"CITY": "SURAT",
	"CENTRE": "SURAT",
	"BANK": "Axis Bank",
	"BANKCODE": "UTIB",
	"IFSC": "UTIB0000566",
}


class TestLookupIfsc(unittest.TestCase):
	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_valid_ifsc_real_response_shape(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = _REAL_RESPONSE_SHAPE
		mock_get.return_value = mock_response

		result = lookup_ifsc("UTIB0000566")

		self.assertEqual(result, {"bank": "Axis Bank", "branch": "ADAJAN", "city": "SURAT"})
		mock_get.assert_called_once_with("https://ifsc.razorpay.com/UTIB0000566", timeout=5)

	def test_wrong_length_rejected_without_network_call(self):
		self.assertIsNone(lookup_ifsc("TOO_SHORT"))
		self.assertIsNone(lookup_ifsc(""))
		self.assertIsNone(lookup_ifsc(None))

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_lowercase_input_normalized_to_uppercase_url(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = _REAL_RESPONSE_SHAPE
		mock_get.return_value = mock_response

		lookup_ifsc("utib0000566")

		mock_get.assert_called_once_with("https://ifsc.razorpay.com/UTIB0000566", timeout=5)

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_404_returns_none_not_raise(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 404
		mock_get.return_value = mock_response

		self.assertIsNone(lookup_ifsc("XXXX0000000"))

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_network_error_returns_none_not_raise(self, mock_get):
		import requests

		mock_get.side_effect = requests.exceptions.Timeout("simulated timeout")

		self.assertIsNone(lookup_ifsc("UTIB0000566"))

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_malformed_json_returns_none_not_raise(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.side_effect = ValueError("not json")
		mock_get.return_value = mock_response

		self.assertIsNone(lookup_ifsc("UTIB0000566"))

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_response_missing_bank_field_returns_none(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"BRANCH": "SOMEWHERE"}
		mock_get.return_value = mock_response

		self.assertIsNone(lookup_ifsc("UTIB0000566"))


class TestFormatBankNameBranch(unittest.TestCase):
	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_formats_bank_branch_city(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = _REAL_RESPONSE_SHAPE
		mock_get.return_value = mock_response

		self.assertEqual(format_bank_name_branch("UTIB0000566"), "Axis Bank - Adajan, Surat")

	@patch("flamezo_backend.flamezo.utils.ifsc_lookup.requests.get")
	def test_lookup_failure_returns_none_not_partial_string(self, mock_get):
		mock_response = MagicMock()
		mock_response.status_code = 404
		mock_get.return_value = mock_response

		self.assertIsNone(format_bank_name_branch("INVALID0000"))

	def test_none_ifsc_returns_none(self):
		self.assertIsNone(format_bank_name_branch(None))
