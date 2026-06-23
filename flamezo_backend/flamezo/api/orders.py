import frappe
import random
import string


def generate_order_number() -> str:
	"""Generate a short human-readable order number, e.g. FZ-A3X9."""
	chars = string.ascii_uppercase + string.digits
	suffix = "".join(random.choices(chars, k=4))
	return f"FZ-{suffix}"
