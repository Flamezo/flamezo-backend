# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for document creation/update with better error handling
"""

import frappe
from frappe import _
import json


@frappe.whitelist()
def create_document(doctype, doc_data):
	"""
	Create a document with proper error handling
	"""
	try:
		# Parse doc_data if it's a string
		if isinstance(doc_data, str):
			doc_data = json.loads(doc_data)
		
		# Ensure doctype is set
		doc_data['doctype'] = doctype
		
		# Create document
		doc = frappe.get_doc(doc_data)
		doc.insert()
		
		# Return the created document
		return {
			'success': True,
			'message': doc.as_dict(),
			'name': doc.name
		}
	except frappe.ValidationError as e:
		frappe.log_error(f"Create Validation: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'ValidationError',
				'message': str(e)
			}
		}
	except frappe.PermissionError as e:
		frappe.log_error(f"Create Permission: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'PermissionError',
				'message': 'You do not have permission to create this document'
			}
		}
	except Exception as e:
		frappe.log_error(f"Create Error: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'Error',
				'message': str(e)
			}
		}


@frappe.whitelist()
def update_document(doctype, name, doc_data):
	"""
	Update a document with proper error handling
	"""
	try:
		# Parse doc_data if it's a string
		if isinstance(doc_data, str):
			doc_data = json.loads(doc_data)
		
		# Get existing document
		doc = frappe.get_doc(doctype, name)
		
		def prepare_dict_recursive(dt, data_item, parent_field=None, parent_type=None):
			if isinstance(data_item, list):
				return [prepare_dict_recursive(dt, item, parent_field, parent_type) for item in data_item]
			if isinstance(data_item, dict):
				data_item['doctype'] = dt
				# Remove name to treat as new row for recreation
				data_item.pop('name', None)
				
				# Explicitly set parent fields for nested child table rows
				if parent_field:
					data_item['parentfield'] = parent_field
				if parent_type:
					data_item['parenttype'] = parent_type
				
				# Recurse into table fields
				meta = frappe.get_meta(dt)
				for field in meta.get_table_fields():
					if field.fieldname in data_item and isinstance(data_item[field.fieldname], list):
						data_item[field.fieldname] = prepare_dict_recursive(field.options, data_item[field.fieldname], field.fieldname, dt)
				return data_item
			return data_item

		def load_deep_children(parent_doc):
			"""Recursively load child table rows for children of children."""
			meta = parent_doc.meta
			for field in meta.get_table_fields():
				children = parent_doc.get(field.fieldname)
				if not children:
					continue
				for child in children:
					if not hasattr(child, "doctype"): continue
					child_meta = frappe.get_meta(child.doctype)
					for subfield in child_meta.get_table_fields():
						if not child.get(subfield.fieldname):
							sub_children = frappe.get_all(
								subfield.options,
								filters={"parent": child.name, "parentfield": subfield.fieldname},
								fields=["*"]
							)
							child.set(subfield.fieldname, sub_children)
					load_deep_children(child)

		# Ensure the full hierarchy is loaded into memory
		load_deep_children(doc)

		def save_deep_children(parent_doc):
			meta = parent_doc.meta
			for field in meta.get_table_fields():
				children = parent_doc.get(field.fieldname)
				if not children:
					continue
					
				for child in children:
					# Check if this child has its own table fields
					child_meta = frappe.get_meta(child.doctype)
					for subfield in child_meta.get_table_fields():
						sub_children = child.get(subfield.fieldname)
						if sub_children:
							# Clear existing sub-children in DB for this child to avoid duplicates on update
							frappe.db.delete(subfield.options, {"parent": child.name, "parentfield": subfield.fieldname})
							
							for sub_child in sub_children:
								sub_child.parent = child.name
								sub_child.parenttype = child.doctype
								sub_child.parentfield = subfield.fieldname
								# Use db_insert to bypass validation since we already validated the parent
								sub_child.db_insert()
							
							# Recurse further if needed
							save_deep_children(child)

		# Update fields
		table_fields = [f.fieldname for f in doc.meta.get_table_fields()]
		for key, value in doc_data.items():
			if key in ['doctype', 'name']:
				continue
				
			if key in table_fields:
				if isinstance(value, list):
					child_dt = doc.meta.get_field(key).options
					# Set the table field with nested dicts. doc.set is recursive.
					doc.set(key, prepare_dict_recursive(child_dt, value, key, doctype))
			else:
				doc.set(key, value)
		
		# Only perform deep save if we actually updated table fields in this request
		updated_tables = any(key in table_fields for key in doc_data.keys())
		
		doc.save()
		
		if updated_tables and doctype == "Menu Product":
			save_deep_children(doc)
		
		return {
			'success': True,
			'message': doc.as_dict(),
			'name': doc.name
		}
	except frappe.ValidationError as e:
		frappe.log_error(f"Update Validation: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'ValidationError',
				'message': str(e)
			}
		}
	except frappe.PermissionError as e:
		frappe.log_error(f"Update Permission: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'PermissionError',
				'message': 'You do not have permission to update this document'
			}
		}
	except Exception as e:
		frappe.log_error(f"Update Error: {doctype}", str(e))
		return {
			'success': False,
			'error': {
				'type': 'Error',
				'message': str(e)
			}
		}


@frappe.whitelist()
def get_doc_list(doctype, filters=None, fields=None, limit_page_length=20, order_by=None):
	"""
	Wrapper for frappe.client.get_list
	Maintains EXACT same API contract as frappe.client.get_list
	"""
	try:
		# Parse filters and fields if they're JSON strings
		if isinstance(filters, str):
			try:
				filters = json.loads(filters)
			except:
				pass
		
		if isinstance(fields, str):
			try:
				fields = json.loads(fields)
			except:
				pass
		
		# Convert limit_page_length to int if needed
		if limit_page_length:
			try:
				limit_page_length = int(limit_page_length)
			except:
				limit_page_length = 20
		
		# Build kwargs for get_list
		kwargs = {
			'doctype': doctype
		}
		
		if filters:
			kwargs['filters'] = filters
		
		if fields:
			kwargs['fields'] = fields
		else:
			kwargs['fields'] = ['name']
		
		if limit_page_length:
			kwargs['limit_page_length'] = limit_page_length
		
		if order_by:
			kwargs['order_by'] = order_by
		
		# Call frappe.get_list (same as frappe.client.get_list internally uses)
		result = frappe.get_list(**kwargs)
		
		# Return in exact same format as frappe.client.get_list
		return result
		
	except frappe.PermissionError as e:
		frappe.log_error("get_doc_list Permission Error", str(e))
		frappe.throw(_("You do not have permission to access this document type"))
	except Exception as e:
		frappe.log_error("get_doc_list Error", str(e))
		frappe.throw(_("Failed to fetch documents: {0}").format(str(e)))


@frappe.whitelist()
def get_doc(doctype, name):
	"""
	Wrapper for frappe.client.get
	Maintains EXACT same API contract as frappe.client.get
	"""
	try:
		# Check if document exists
		if not frappe.db.exists(doctype, name):
			frappe.throw(_("{0} {1} not found").format(doctype, name))
		
		# Get document (with permission checks)
		doc = frappe.get_doc(doctype, name)
		
		# Return as dict (exact same format as frappe.client.get)
		return doc.as_dict()
		
	except frappe.PermissionError as e:
		frappe.log_error("get_doc Permission Error", str(e))
		frappe.throw(_("You do not have permission to access this document"))
	except Exception as e:
		frappe.log_error("get_doc Error", str(e))
		frappe.throw(_("Failed to fetch document: {0}").format(str(e)))


@frappe.whitelist()
def insert_doc(doc):
	"""
	Wrapper for frappe.client.insert
	Maintains EXACT same API contract as frappe.client.insert
	"""
	try:
		# Parse doc if it's a string
		if isinstance(doc, str):
			doc = json.loads(doc)
		
		# Ensure doctype is present
		if 'doctype' not in doc:
			frappe.throw(_("doctype is required"))
		
		# Create document
		new_doc = frappe.get_doc(doc)
		new_doc.insert()
		
		# Return as dict (exact same format as frappe.client.insert)
		return new_doc.as_dict()
		
	except frappe.ValidationError as e:
		frappe.log_error("insert_doc Validation Error", str(e))
		frappe.throw(str(e))
	except frappe.PermissionError as e:
		frappe.log_error("insert_doc Permission Error", str(e))
		frappe.throw(_("You do not have permission to create this document"))
	except Exception as e:
		frappe.log_error("insert_doc Error", str(e))
		frappe.throw(_("Failed to create document: {0}").format(str(e)))


@frappe.whitelist()
def delete_doc(doctype, name):
	"""
	Wrapper for frappe.client.delete
	Maintains EXACT same API contract as frappe.client.delete
	"""
	try:
		# Check if document exists
		if not frappe.db.exists(doctype, name):
			frappe.throw(_("{0} {1} not found").format(doctype, name))
		
		# Delete document (with permission checks)
		frappe.delete_doc(doctype, name)
		
		# Return success message (exact same format as frappe.client.delete)
		return {
			'message': _('Deleted')
		}
		
	except frappe.PermissionError as e:
		frappe.log_error("delete_doc Permission Error", str(e))
		frappe.throw(_("You do not have permission to delete this document"))
	except frappe.LinkExistsError as e:
		frappe.log_error("delete_doc Link Exists Error", str(e))
		frappe.throw(_("Cannot delete {0} {1} because it is linked with other documents").format(doctype, name))
	except Exception as e:
		frappe.log_error("delete_doc Error", str(e))
		frappe.throw(_("Failed to delete document: {0}").format(str(e)))


@frappe.whitelist()
def delete_multiple_docs(doctype, names, force=False):
	"""
	Delete multiple documents with proper error handling
	"""
	try:
		# Parse names if it's a string
		if isinstance(names, str):
			names = json.loads(names)
		
		# Ensure force is a boolean
		force = frappe.parse_json(force)
		
		deleted_count = 0
		errors = []
		
		# For bulk delete, we can optimize by checking existence once or just attempting
		for name in names:
			try:
				# Using frappe.delete_doc with force=force
				# If force=True, it skips link validation which is much faster
				frappe.delete_doc(doctype, name, force=force, ignore_permissions=False, ignore_missing=True)
				deleted_count += 1
			except Exception as e:
				error_msg = str(e)
				frappe.log_error(f"Bulk Delete Item Error: {doctype} {name}", error_msg)
				errors.append(f"Failed to delete {name}: {error_msg}")
		
		# Commit after all deletions are done
		frappe.db.commit()
		
		return {
			'success': len(errors) == 0,
			'deleted_count': deleted_count,
			'errors': errors
		}
	except Exception as e:
		frappe.log_error(f"Bulk Delete Error: {doctype}", str(e))
		return {
			'success': False,
			'error': str(e)
		}


