# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Currency helper utilities for API responses
"""

import frappe


def get_currency_symbol(currency_code):
	"""
	Get currency symbol from Currency doctype
	
	Args:
		currency_code (str): Currency code (e.g., 'USD', 'INR')
	
	Returns:
		dict: Dictionary with currency symbol and symbol_on_right flag
	"""
	if not currency_code:
		currency_code = "INR"
	
	try:
		res = frappe.db.get_value("Currency", currency_code, ["symbol", "symbol_on_right"], as_dict=True)
		if res:
			symbol = res.get("symbol") or currency_code
			symbol_on_right = bool(res.get("symbol_on_right", False))
		else:
			raise frappe.DoesNotExistError
	except (frappe.DoesNotExistError, Exception):
		# Fallback to common currency symbols
		fallback_symbols = {
			'USD': '$',
			'INR': '₹',
			'EUR': '€',
			'GBP': '£',
			'JPY': '¥',
			'AUD': 'A$',
			'CAD': 'C$',
			'CHF': 'CHF',
			'CNY': '¥',
			'SGD': 'S$',
		}
		symbol = fallback_symbols.get(currency_code, currency_code)
		symbol_on_right = False
	
	return {
		"symbol": symbol,
		"symbolOnRight": symbol_on_right
	}


def get_restaurant_currency_info(restaurant_id):
	"""
	Get currency code and symbol for a restaurant
	
	Args:
		restaurant_id (str): Restaurant ID
	
	Returns:
		dict: Dictionary with currency code and symbol info
	"""
	currency_code = "INR"  # Default
	
	try:
		# Try to get from Restaurant Config first
		config_currency = frappe.db.get_value(
			"Restaurant Config",
			{"restaurant": restaurant_id},
			"currency"
		)
		
		if config_currency:
			currency_code = config_currency
		else:
			# Fallback to Restaurant doctype
			restaurant_currency = frappe.db.get_value(
				"Restaurant",
				restaurant_id,
				"currency"
			)
			if restaurant_currency:
				currency_code = restaurant_currency
	except:
		pass
	
	currency_info = get_currency_symbol(currency_code)
	currency_info["currency"] = currency_code
	
	return currency_info

