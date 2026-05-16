# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CustomerSession(Document):
	"""
	Durable session record persisted in MariaDB.
	Complements the Redis-backed session for resilience across deployments/restarts.
	"""
	pass
