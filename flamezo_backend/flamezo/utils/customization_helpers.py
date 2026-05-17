import frappe
import json
from frappe import _
from frappe.utils import flt, cint
from collections import defaultdict

def load_product_customizations(product_doc):
	"""
	Load customization questions and options for a product.
	Optimized to load all options in a single query (1+1 pattern).
	"""
	if not product_doc.get("customization_questions"):
		return
	
	# Load all options for all questions in one query
	question_names = [q.name for q in product_doc.customization_questions]
	
	options_list = frappe.get_all(
		"Customization Option",
		filters={
			"parent": ["in", question_names],
			"parenttype": "Customization Question",
			"parentfield": "options"
		},
		fields=["parent", "option_id", "label", "price", "is_vegetarian", "is_default", "display_order"],
		order_by="display_order asc"
	)
	
	# Map options to their parent question
	options_by_question = defaultdict(list)
	for opt in options_list:
		options_by_question[opt["parent"]].append(frappe._dict(opt))
	
	# Attach options to questions
	for question in product_doc.customization_questions:
		question.options = options_by_question.get(question.name, [])


def validate_customizations(product, selections):
	"""
	Validate that all required customization questions have been answered 
	and that the selected options are valid.
	"""
	if not product.get("customization_questions"):
		if selections:
			frappe.throw(_("This product does not support customizations"), frappe.ValidationError)
		return

	# Ensure options are loaded for validation
	if any(not hasattr(q, "options") for q in product.customization_questions):
		load_product_customizations(product)

	for question in product.customization_questions:
		question_id = question.question_id
		selected_options = selections.get(question_id, [])
		
		# Handle string vs list in selections
		if isinstance(selected_options, (str, int)):
			selected_options = [selected_options] if selected_options else []
		
		# Check required
		if question.is_required and not selected_options:
			frappe.throw(
				_("Customization '{0}' is required").format(question.title),
				frappe.ValidationError
			)
		
		# Check single choice
		if question.question_type == "single" and len(selected_options) > 1:
			frappe.throw(
				_("Only one option can be selected for '{0}'").format(question.title),
				frappe.ValidationError
			)
		
		# Check options validity
		valid_option_ids = {str(opt.option_id) for opt in question.options}
		for opt_id in selected_options:
			if str(opt_id) not in valid_option_ids:
				frappe.throw(
					_("Invalid option '{0}' for question '{1}'").format(opt_id, question.title),
					frappe.ValidationError
				)

def get_customization_options_map(question_names):
	"""
	Bulk load options for a list of question names.
	Used for listing APIs to avoid N+1 queries.
	"""
	if not question_names:
		return {}
		
	options_list = frappe.get_all(
		"Customization Option",
		filters={
			"parent": ["in", question_names],
			"parenttype": "Customization Question"
		},
		fields=["parent", "option_id", "label", "price", "is_vegetarian", "is_default", "display_order"],
		order_by="display_order asc"
	)
	
	options_by_question = defaultdict(list)
	for opt in options_list:
		options_by_question[opt["parent"]].append(opt)
		
	return options_by_question
