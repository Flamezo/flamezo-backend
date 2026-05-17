# Copyright (c) 2025, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils.file_manager import get_file_path
import json
import time
from datetime import datetime
import os
import re
import requests
import hashlib
from flamezo_backend.flamezo.services.ai.menu_extraction import MenuExtractor, extract_and_generate
from flamezo_backend.flamezo.services.ai.recommendations import RecommendationEngine


class MenuImageExtractor(Document):
	def validate(self):
		"""Auto-fill restaurant_name from restaurant field if not provided"""
		if self.restaurant and not self.restaurant_name:
			# Get restaurant name from the selected restaurant
			restaurant_name = frappe.db.get_value("Restaurant", self.restaurant, "restaurant_name")
			if restaurant_name:
				self.restaurant_name = restaurant_name

	def on_trash(self):
		"""Delete all associated Media Assets from R2 when the extraction doc is deleted"""
		if self.menu_images:
			for row in self.menu_images:
				if row.media_asset:
					# Delete the Media Asset document
					# This will trigger the cloud storage cleanup if the Media Asset is configured to do so
					if frappe.db.exists("Media Asset", row.media_asset):
						frappe.delete_doc("Media Asset", row.media_asset)

	def cleanup_source_images(self):
		"""Delete all associated Menu Image source files from storage to save space"""
		if not self.menu_images:
			return
			
		for row in self.menu_images:
			if row.media_asset:
				try:
					if frappe.db.exists("Media Asset", row.media_asset):
						frappe.delete_doc("Media Asset", row.media_asset, ignore_permissions=True)
				except Exception as e:
					frappe.log_error(title="Menu Extraction Cleanup Error", message=f"Failed to cleanup image {row.media_asset}: {str(e)}")
		
		# Optional: Clear the table links too if we want to be thorough, 
		# but keeping the rows (now with empty media_asset) provides a record of what was uploaded.

def generate_product_id_from_name(product_name, restaurant=None):
	"""Generate a slug-like product_id from product_name, unique within restaurant"""
	if not product_name:
		return None
	
	# Convert to lowercase
	product_id = product_name.lower()
	
	# Replace spaces and special characters with hyphens
	product_id = re.sub(r'[^\w\s-]', '', product_id)  # Remove special chars
	product_id = re.sub(r'[-\s]+', '-', product_id)  # Replace spaces and multiple hyphens with single hyphen
	product_id = product_id.strip('-')  # Remove leading/trailing hyphens
	
	# Limit length to 140 characters (Frappe name field limit)
	if len(product_id) > 140:
		product_id = product_id[:140].rstrip('-')
	
	# Ensure uniqueness within the restaurant by checking if it exists
	if restaurant:
		base_id = product_id
		counter = 1
		while frappe.db.get_value("Menu Product", {"product_id": product_id, "restaurant": restaurant}, "name"):
			product_id = f"{base_id}-{counter}"
			counter += 1
			# Prevent infinite loop
			if counter > 1000:
				import time
				product_id = f"{base_id}-{int(time.time())}"
				break
	
	return product_id


def generate_category_id_from_name(category_name, restaurant=None):
	"""Generate a slug-like category_id from category_name, unique within restaurant"""
	if not category_name:
		return None
	
	# Convert to lowercase
	category_id = category_name.lower()
	
	# Replace spaces and special characters with hyphens
	category_id = re.sub(r'[^\w\s-]', '', category_id)  # Remove special chars
	category_id = re.sub(r'[-\s]+', '-', category_id)  # Replace spaces and multiple hyphens with single hyphen
	category_id = category_id.strip('-')  # Remove leading/trailing hyphens
	
	# Limit length to 140 characters (Frappe name field limit)
	if len(category_id) > 140:
		category_id = category_id[:140].rstrip('-')
	
	# Ensure uniqueness within the restaurant by checking if it exists
	if restaurant:
		base_id = category_id
		counter = 1
		while frappe.db.get_value("Menu Category", {"category_id": category_id, "restaurant": restaurant}, "name"):
			category_id = f"{base_id}-{counter}"
			counter += 1
			# Prevent infinite loop
			if counter > 1000:
				import time
				category_id = f"{base_id}-{int(time.time())}"
				break
	
	return category_id


@frappe.whitelist()
def extract_menu_data(docname):
	"""
	Extract menu data from uploaded images using the external API
	This function immediately enqueues batch processing jobs - no timeouts, no waiting
	Returns instantly after queuing all batches
	"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)
		
		# Hardening: Prevent duplicate extractions if already processing
		if doc.extraction_status == "Processing":
			return {
				'success': True,
				'message': _("Extraction is already in progress for this session."),
				'status': 'processing'
			}

		# Validation: Check image list
		if not doc.menu_images:
			frappe.throw(_("Please upload at least one menu image"))
		
		if len(doc.menu_images) > 20:
			frappe.throw(_("Maximum 20 images allowed. Currently {0} images uploaded.").format(len(doc.menu_images)))
		
		# Prepare batch info
		batch_size = 5
		image_batches = []
		for i in range(0, len(doc.menu_images), batch_size):
			batch = doc.menu_images[i:i + batch_size]
			image_batches.append([img.menu_image for img in batch])

		# Reset extraction metrics and set processing state
		doc.extracted_dishes = []
		doc.extraction_log = _("Extraction started. Processing images in batches...")
		doc.categories_created = 0
		doc.items_created = 0
		doc.items_updated = 0
		doc.items_skipped = 0
		doc.extraction_date = None
		doc.processing_time = None
		doc.approval_status = 'Pending'
		doc.extraction_status = 'Processing'
		doc.total_batches = len(image_batches)
		doc.completed_batches = 0
		
		# Save and commit before enqueuing to ensure frontend sees the state
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		
		# Enqueue each batch as a separate job - no timeout, process in parallel
		for batch_idx, image_batch in enumerate(image_batches):
			frappe.enqueue(
				"flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor._extract_batch_internal",
				docname=docname,
				batch_images=image_batch,
				batch_number=batch_idx + 1,
				total_batches=len(image_batches),
				queue="short",
				timeout=7200,  # 2 hours per batch (very generous)
				job_id=f"menu_extraction_{docname}_batch_{batch_idx + 1}",
				is_async=True,
				now=False  # Don't wait - queue immediately
			)
		
		# Return immediately - all batches are queued
		return {
			'success': True,
			'message': _("Extraction started in the background. Processing {0} images in {1} batch(es). Please wait for it to complete.").format(
				len(doc.menu_images), len(image_batches)
			),
			'status': 'queued',
			'total_images': len(doc.menu_images),
			'total_batches': len(image_batches)
		}
		
	except frappe.exceptions.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(title="Menu Extraction - Enqueue Error", message=frappe.get_traceback())
		frappe.throw(_("Error starting extraction: {0}").format(str(e)))


def scrub_price(price_val):
	"""Sanitize price value to float by removing currency symbols and whitespace"""
	if not price_val:
		return 0.0
	if isinstance(price_val, (int, float)):
		return float(price_val)
	try:
		# Remove everything except digits and decimal point
		cleaned = re.sub(r'[^\d.]', '', str(price_val))
		return float(cleaned) if cleaned else 0.0
	except:
		return 0.0


@frappe.whitelist()
def get_extraction_status(docname):
	"""
	Dedicated status polling API - reads DIRECTLY from DB, bypasses all SDK caching.
	Returns current state of extraction: status, batch progress, and metadata.
	Mirrors the pattern used by AI Enhancement's get_enhancement_status.
	"""
	# Read directly from DB - no doc cache
	result = frappe.db.get_value(
		"Menu Image Extractor",
		docname,
		[
			"extraction_status",
			"total_batches",
			"completed_batches",
			"extraction_log",
			"items_created",
			"categories_created",
		],
		as_dict=True
	)
	if not result:
		frappe.throw("Extraction document not found: {}".format(docname))

	return {
		"status": result.extraction_status,
		"total_batches": result.total_batches or 0,
		"completed_batches": result.completed_batches or 0,
		"extraction_log": result.extraction_log,
		"items_created": result.items_created or 0,
		"categories_created": result.categories_created or 0,
	}



def _extract_batch_internal(docname, batch_images, batch_number, total_batches):
	"""
	Process a single batch of images
	This runs as a background job - no timeouts, processes in parallel with other batches
	"""
	try:
		# Log that batch processing started
		frappe.log_error(
			title="Menu Extraction - Batch Start",
			message=(
				f"Batch {batch_number}/{total_batches} started processing\n"
				f"Document: {docname}\n"
				f"Images in batch: {len(batch_images)}"
			)
		)
		
		doc = frappe.get_doc("Menu Image Extractor", docname)
		
		# Check if document still exists and is in Processing status
		if doc.extraction_status != "Processing":
			frappe.log_error(
				title="Menu Extraction - Batch Skip",
				message=f"Batch {batch_number} skipped: Document status is {doc.extraction_status}, not Processing"
			)
			return
		
		start_time = time.time()
		
		# Internal extraction logic
		image_paths = []
		temp_files = []  # Track files to delete later

		for image_url in batch_images:
			try:
				local_path, is_temp = _get_local_image_path(image_url)
				if local_path and os.path.exists(local_path):
					image_paths.append(local_path)
					if is_temp:
						temp_files.append(local_path)
				else:
					frappe.log_error(title="Menu Extraction - Path Error", message=f"Batch {batch_number}: Could not resolve image path for {image_url}")
			except Exception as e:
				frappe.log_error(title="Menu Extraction - Resolution Error", message=f"Batch {batch_number}: Error resolving image {image_url}\n{str(e)}")

		if not image_paths:
			frappe.log_error(title="Menu Extraction - Batch Empty", message=f"Batch {batch_number}: No valid image files found")
			_update_batch_completion(docname, batch_number, total_batches, None, None)
			return

		# Call local AI service
		restaurant_name_for_api = doc.restaurant_name
		if not restaurant_name_for_api and doc.restaurant:
			restaurant_name_for_api = frappe.db.get_value("Restaurant", doc.restaurant, "restaurant_name")

		result = extract_and_generate(
			image_paths=image_paths,
			restaurant_name=restaurant_name_for_api,
			generate_descriptions=bool(doc.generate_descriptions)
		)
		
		# Log successful result
		frappe.log_error(
			title="Menu Extraction - Internal Success",
			message=(
				f"Batch {batch_number}: Extraction Success\n"
				f"Success: {result.get('success')}\n"
				f"Categories: {len(result.get('data', {}).get('categories', []))}\n"
				f"Dishes: {len(result.get('data', {}).get('dishes', []))}"
			)
		)
		
		processing_time = time.time() - start_time
		
		# Process batch result
		if result.get('success'):
			data = result.get('data', {})
			# Store batch results temporarily
			_store_batch_results(docname, batch_number, data, processing_time)
		else:
			frappe.log_error(
				title="Menu Extraction - Batch Service Error",
				message=f"Batch {batch_number} extraction returned success=False: {result.get('error', 'Unknown error')}"
			)
			_update_batch_completion(docname, batch_number, total_batches, None, None)
	
	except Exception as e:
		frappe.log_error(title="Menu Extraction - Batch Error", message=f"Batch {batch_number} failed: {str(e)}\n{frappe.get_traceback()}")
		_update_batch_completion(docname, batch_number, total_batches, None, None)
	
	finally:
		# CLEANUP: Delete temporary downloaded files
		if 'temp_files' in locals() and temp_files:
			for temp_file in temp_files:
				try:
					if os.path.exists(temp_file):
						os.remove(temp_file)
				except Exception as cleanup_err:
					frappe.log_error(title="Menu Extraction - Cleanup Error", message=f"Failed to cleanup temp file {temp_file}: {str(cleanup_err)}")


def _get_local_image_path(image_url):
	"""
	Resolve a URL/path to a local file path.
	If it's an external URL, download it to a temporary location.
	Returns (file_path, is_temporary)
	"""
	if not image_url:
		return None, False

	# CASE 1: External URL (matches http:// or https://)
	if image_url.startswith(('http://', 'https://')):
		try:
			# Check if it corresponds to the local cdn (just in case)
			cdn_prefix = frappe.conf.get("cdn_url") or "cdn.flamezo_backend.com"
			if cdn_prefix in image_url:
				# It is highly likely to be on R2
				pass
			
			# Download to tmp
			tmp_dir = frappe.get_site_path('tmp', 'mie_extractions')
			if not os.path.exists(tmp_dir):
				os.makedirs(tmp_dir, exist_ok=True)
			
			# Generate a unique filename to avoid collisions
			url_hash = hashlib.md5(image_url.encode()).hexdigest()
			ext = os.path.splitext(image_url.split('?')[0])[1] or '.png'
			temp_path = os.path.join(tmp_dir, f"mie_{url_hash}{ext}")
			
			# Skip download if it already exists (unlikely in same job but good practice)
			if os.path.exists(temp_path):
				return temp_path, True
				
			response = requests.get(image_url, timeout=30)
			response.raise_for_status()
			
			with open(temp_path, 'wb') as f:
				f.write(response.content)
			
			return temp_path, True
			
		except Exception as e:
			frappe.log_error(title="Menu Extraction - Download Error", message=f"Failed to download external image {image_url}: {str(e)}")
			return None, False

	# CASE 2: Local Frappe URL or Path
	try:
		file_path = get_file_path(image_url)
		if file_path and os.path.exists(file_path):
			return file_path, False
			
		# Fallback manual path resolving if get_file_path fails
		clean_path = image_url if not image_url.startswith('/') else image_url[1:]
		
		# Try public files
		full_path = frappe.get_site_path('public', clean_path)
		if os.path.exists(full_path): return full_path, False
		
		# Try private files
		full_path = frappe.get_site_path('private', clean_path)
		if os.path.exists(full_path): return full_path, False
		
		# Try public files directory specifically
		full_path = frappe.get_site_path('public', 'files', clean_path)
		if os.path.exists(full_path): return full_path, False
		
	except Exception:
		pass
		
	return None, False


def _store_batch_results(docname, batch_number, data, processing_time):
	"""Store results from a single batch and check if all batches are complete"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)
		
		# Get existing batch results or initialize
		batch_results = json.loads(doc.get('batch_results') or '{}')
		batch_results[str(batch_number)] = {
			'data': data,
			'processing_time': processing_time,
			'completed_at': datetime.now().isoformat()
		}
		
		# Store batch results
		doc.db_set('batch_results', json.dumps(batch_results), update_modified=False)
		
		# Update completed batches count
		completed = (doc.get('completed_batches') or 0) + 1
		doc.db_set('completed_batches', completed, update_modified=False)
		
		total_batches = doc.get('total_batches') or 1
		
		# Update progress log
		extraction_log = _("Processing batches... {0}/{1} completed").format(completed, total_batches)
		doc.db_set('extraction_log', extraction_log, update_modified=False)

		# Check if all batches are complete
		if completed >= total_batches:
			# All batches complete - aggregate and process
			_aggregate_and_process_batches(docname)
		
		frappe.db.commit()
	
	except Exception as e:
		frappe.log_error(
			title="Menu Extraction - Store Batch Error",
			message=f"Error storing batch {batch_number} results: {str(e)}\n{frappe.get_traceback()}"
		)


def _update_batch_completion(docname, batch_number, total_batches, data, processing_time):
	"""Update batch completion status"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)
		completed = doc.get('completed_batches') or 0
		doc.db_set('completed_batches', completed + 1, update_modified=False)
		
		if completed + 1 >= total_batches:
			# All batches complete (even if some failed)
			_aggregate_and_process_batches(docname)
		else:
			doc.db_set('extraction_log',
				_("Processing batches... {0}/{1} completed").format(completed + 1, total_batches),
				update_modified=False)
		
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(title="Menu Extraction - Batch Update Error", message=f"Error updating batch completion: {str(e)}")


def _aggregate_and_process_batches(docname):
	"""Aggregate results from all batches and process them"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)
		
		# Get all batch results
		batch_results = json.loads(doc.get('batch_results') or '{}')
		
		# Aggregate categories and dishes from all batches
		all_categories = {}
		all_dishes = []
		
		for batch_num, batch_data in batch_results.items():
			data = batch_data.get('data', {})
			categories = data.get('categories', [])
			dishes = data.get('dishes', [])
			
			# Handle categories - can be list or dict
			if isinstance(categories, dict):
				categories = list(categories.values())
			elif not isinstance(categories, list):
				categories = []
			
			# Aggregate categories (deduplicate by id)
			for cat in categories:
				if isinstance(cat, dict) and cat.get('id'):
					all_categories[cat['id']] = cat
			
			# Handle dishes - can be list or dict
			if isinstance(dishes, dict):
				dishes = list(dishes.values())
			elif not isinstance(dishes, list):
				dishes = []
			
			# Aggregate dishes
			all_dishes.extend(dishes)
		
		# Create aggregated data structure
		aggregated_data = {
			'categories': list(all_categories.values()),
			'dishes': all_dishes,
			'restaurantBrand': {}  # Can be merged if needed
		}
		
		# Store aggregated data
		store_extracted_data(aggregated_data, doc)
		
		# Update metrics for display (frontend counts)
		doc.categories_created = len(all_categories)
		doc.items_created = len(all_dishes)
		
		# Update status
		doc.extraction_status = "Pending Approval"
		doc.approval_status = "Pending"
		doc.extraction_log = f"Extraction completed successfully!\n\n" + \
			f"Categories extracted: {len(all_categories)}\n" + \
			f"Dishes extracted: {len(all_dishes)}\n\n" + \
			"Please review the extracted data below and click 'Approve and Create Menu Items' to add them to the database."
		doc.extraction_date = datetime.now()
		
		# Calculate total processing time
		total_time = sum(b.get('processing_time', 0) for b in batch_results.values())
		doc.processing_time = f"{total_time:.2f} seconds"
		
		# Store raw response
		doc.raw_response = json.dumps({'data': aggregated_data}, indent=2)
		
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			title="Menu Extraction - Aggregate Error",
			message=f"Error aggregating batches: {str(e)}\n{frappe.get_traceback()}"
		)
		# Fallback to reload and set failed
		try:
			doc = frappe.get_doc("Menu Image Extractor", docname)
			doc.db_set('extraction_status', 'Failed', update_modified=False)
			doc.db_set('extraction_log', f"Error aggregating batch results: {str(e)}", update_modified=False)
			frappe.db.commit()
		except:
			pass


def store_extracted_data(data, extractor_doc):
	"""
	Store extracted data in both HTML report format and editable child tables
	"""
	# Extract data sections
	categories_data = data.get('categories', [])
	dishes_data = data.get('dishes', [])
	
	# Ensure categories_data and dishes_data are lists
	if not isinstance(categories_data, list):
		if isinstance(categories_data, dict):
			categories_data = list(categories_data.values())
		else:
			categories_data = []
	
	if not isinstance(dishes_data, list):
		if isinstance(dishes_data, dict):
			dishes_data = list(dishes_data.values())
		else:
			dishes_data = []
	
	# Clear existing child table data
	extractor_doc.extracted_dishes = []
	
	# Populate editable child tables for dishes
	for dish_data in dishes_data:
		if not isinstance(dish_data, dict):
			continue
		
		dish_name = dish_data.get('name')
		
		if not dish_name:
			continue
		
		# Generate dish_id from dish_name
		dish_id = generate_product_id_from_name(dish_name)
		
		# Store media and customizations as JSON strings
		media_json = json.dumps(dish_data.get('media', [])) if dish_data.get('media') else None
		customizations_json = json.dumps(dish_data.get('customizationQuestions', [])) if dish_data.get('customizationQuestions') else None
		
		extractor_doc.append('extracted_dishes', {
			'dish_id': dish_id,
			'dish_name': dish_name,
			'price': dish_data.get('price', 0),
			'original_price': dish_data.get('originalPrice'),
			'category': dish_data.get('category', ''),
			'description': dish_data.get('description', ''),
			'calories': dish_data.get('calories'),
			'is_vegetarian': 1 if dish_data.get('isVegetarian') else 0,
			'estimated_time': dish_data.get('estimatedTime'),
			'serving_size': dish_data.get('servingSize'),
			'has_no_media': 1 if dish_data.get('hasNoMedia') else 0,
			'main_category': dish_data.get('mainCategory', ''),
			'media_json': media_json,
			'customizations_json': customizations_json
		})
	
	# Also store raw data in raw_response for backup
	if not extractor_doc.raw_response:
		extractor_doc.raw_response = json.dumps({'data': data}, indent=2)


def generate_extraction_report_html(categories_data, dishes_data):
	"""
	Generate an Excel-like HTML report of extracted data
	"""
	html = """
	<style>
		.extraction-report {
			font-family: 'Segoe UI', Arial, sans-serif;
			width: 100%;
			margin: 20px 0;
			background-color: #ffffff;
		}
		.report-section {
			margin-bottom: 40px;
		}
		.report-title {
			font-size: 16px;
			font-weight: bold;
			margin-bottom: 15px;
			color: #1a1a1a;
			padding: 12px 15px;
			background: linear-gradient(to right, #4472C4, #5B9BD5);
			color: white;
			border-radius: 4px 4px 0 0;
		}
		.data-table {
			width: 100%;
			border-collapse: collapse;
			margin-top: 0;
			background-color: white;
			border: 2px solid #4472C4;
			font-size: 13px;
		}
		.data-table th {
			background: linear-gradient(to bottom, #4472C4, #5B9BD5);
			color: white;
			padding: 12px 10px;
			text-align: left;
			font-weight: bold;
			border: 1px solid #2E5C8A;
			white-space: nowrap;
			position: sticky;
			top: 0;
			z-index: 10;
		}
		.data-table td {
			padding: 10px;
			border: 1px solid #D0D0D0;
			background-color: white;
			vertical-align: top;
		}
		.data-table tr:nth-child(even) td {
			background-color: #F2F2F2;
		}
		.data-table tr:nth-child(odd) td {
			background-color: #FFFFFF;
		}
		.data-table tr:hover td {
			background-color: #D9E1F2;
		}
		.data-table tbody tr {
			border-bottom: 1px solid #D0D0D0;
		}
		.text-center {
			text-align: center;
		}
		.text-right {
			text-align: right;
		}
		.badge {
			display: inline-block;
			padding: 4px 10px;
			border-radius: 3px;
			font-size: 11px;
			font-weight: bold;
			text-transform: uppercase;
		}
		.badge-yes {
			background-color: #70AD47;
			color: white;
		}
		.badge-no {
			background-color: #C00000;
			color: white;
		}
		.summary-box {
			background: linear-gradient(to right, #E7F3FF, #D0E8FF);
			padding: 18px 20px;
			border-radius: 6px;
			margin-bottom: 25px;
			border: 2px solid #4472C4;
			box-shadow: 0 2px 4px rgba(0,0,0,0.1);
		}
		.summary-box strong {
			color: #1a1a1a;
			font-size: 14px;
		}
		.summary-box br {
			line-height: 1.8;
		}
		.table-container {
			overflow-x: auto;
			border: 2px solid #4472C4;
			border-radius: 0 0 4px 4px;
		}
	</style>
	<div class="extraction-report">
	"""
	
	# Summary section
	html += f"""
		<div class="summary-box">
			<strong>Extraction Summary:</strong><br>
			• Categories Found: <strong>{len(categories_data)}</strong><br>
			• Dishes Found: <strong>{len(dishes_data)}</strong>
		</div>
	"""
	
	# Categories table
	if categories_data:
		html += """
		<div class="report-section">
			<div class="report-title">📁 Extracted Categories</div>
			<div class="table-container">
			<table class="data-table">
				<thead>
					<tr>
						<th style="width: 50px;">#</th>
						<th style="min-width: 120px;">Category ID</th>
						<th style="min-width: 150px;">Category Name</th>
						<th style="min-width: 150px;">Display Name</th>
						<th style="min-width: 200px;">Description</th>
						<th style="width: 100px;" class="text-center">Is Special</th>
						<th style="min-width: 150px;">Image</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for idx, cat_data in enumerate(categories_data, 1):
			if not isinstance(cat_data, dict):
				continue
			
			category_id = cat_data.get('id', '')
			category_name = cat_data.get('name', '')
			display_name = cat_data.get('displayName', category_name)
			cat_description = cat_data.get('description') or ''
			description = cat_description[:100] + ('...' if len(cat_description) > 100 else '')
			is_special = 'Yes' if cat_data.get('isSpecial') else 'No'
			image = cat_data.get('image', '')
			
			html += f"""
					<tr>
						<td class="text-center">{idx}</td>
						<td>{category_id}</td>
						<td><strong>{category_name}</strong></td>
						<td>{display_name}</td>
						<td>{description}</td>
						<td class="text-center"><span class="badge {'badge-yes' if cat_data.get('isSpecial') else 'badge-no'}">{is_special}</span></td>
						<td>{image[:50] + ('...' if len(image) > 50 else '') if image else '-'}</td>
					</tr>
			"""
		
		html += """
				</tbody>
			</table>
			</div>
		</div>
		"""
	
	# Dishes table
	if dishes_data:
		html += """
		<div class="report-section">
			<div class="report-title">🍽️ Extracted Dishes</div>
			<div class="table-container">
			<table class="data-table">
				<thead>
					<tr>
						<th style="width: 50px;">#</th>
						<th style="min-width: 180px;">Dish Name</th>
						<th style="min-width: 120px;">Category</th>
						<th style="width: 80px;" class="text-right">Price</th>
						<th style="width: 100px;" class="text-right">Original Price</th>
						<th style="width: 80px;" class="text-center">Calories</th>
						<th style="width: 90px;" class="text-center">Vegetarian</th>
						<th style="width: 100px;" class="text-center">Est. Time</th>
						<th style="width: 100px;" class="text-center">Serving Size</th>
						<th style="min-width: 200px;">Description</th>
						<th style="width: 90px;" class="text-center">Media</th>
						<th style="width: 110px;" class="text-center">Customizations</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for idx, dish_data in enumerate(dishes_data, 1):
			if not isinstance(dish_data, dict):
				continue
			
			dish_name = dish_data.get('name', '')
			category = dish_data.get('category', '')
			price = dish_data.get('price', 0)
			original_price = dish_data.get('originalPrice', '')
			calories = dish_data.get('calories', '')
			is_vegetarian = 'Yes' if dish_data.get('isVegetarian') else 'No'
			estimated_time = dish_data.get('estimatedTime', '')
			serving_size = dish_data.get('servingSize', '')
			dish_description = dish_data.get('description') or ''
			description = dish_description[:80] + ('...' if len(dish_description) > 80 else '')
			
			# Safely get media and customizations, handling None values
			media = dish_data.get('media')
			media_count = len(media) if media is not None else 0
			
			customizations = dish_data.get('customizationQuestions')
			customizations_count = len(customizations) if customizations is not None else 0
			
			html += f"""
					<tr>
						<td class="text-center">{idx}</td>
						<td><strong>{dish_name}</strong></td>
						<td>{category}</td>
						<td class="text-right">{price if price else '-'}</td>
						<td class="text-right">{original_price if original_price else '-'}</td>
						<td class="text-center">{calories if calories else '-'}</td>
						<td class="text-center"><span class="badge {'badge-yes' if dish_data.get('isVegetarian') else 'badge-no'}">{is_vegetarian}</span></td>
						<td class="text-center">{estimated_time if estimated_time else '-'}</td>
						<td class="text-center">{serving_size if serving_size else '-'}</td>
						<td>{description}</td>
						<td class="text-center">{media_count}</td>
						<td class="text-center">{customizations_count}</td>
					</tr>
			"""
		
		html += """
				</tbody>
			</table>
			</div>
		</div>
		"""
	
	html += """
	</div>
	"""
	
	return html


def process_extracted_data(data, extractor_doc):
	"""
	Process extracted data and create Menu Categories and Menu Products
	This is called after approval
	"""
	stats = {
		'categories_created': 0,
		'items_created': 0,
		'items_updated': 0,
		'items_skipped': 0
	}
	
	# Get restaurant from extractor document
	restaurant = None
	
	# First, try to use the restaurant Link field (preferred)
	if extractor_doc.restaurant:
		restaurant = extractor_doc.restaurant
		# Validate restaurant exists
		if not frappe.db.exists("Restaurant", restaurant):
			frappe.throw(
				_("Selected restaurant '{0}' does not exist. Please select a valid restaurant.").format(restaurant),
				title=_("Invalid Restaurant")
			)
	
	# Fallback: Try to find restaurant by restaurant_name (for backward compatibility)
	if not restaurant and extractor_doc.restaurant_name:
		# Try to find restaurant by restaurant_name or restaurant_id
		restaurant = frappe.db.get_value("Restaurant", {"restaurant_name": extractor_doc.restaurant_name}, "name")
		if not restaurant:
			# Try by restaurant_id (slug format)
			restaurant_id = extractor_doc.restaurant_name.lower().strip().replace(" ", "-")
			restaurant = frappe.db.get_value("Restaurant", {"restaurant_id": restaurant_id}, "name")
	
	if not restaurant:
		frappe.throw(
			_("Restaurant is required. Please select a restaurant from the Restaurant field."),
			title=_("Restaurant Required")
		)
	
	# Extract data sections
	categories_data = data.get('categories', [])
	dishes_data = data.get('dishes', [])
	restaurant_brand = data.get('restaurantBrand', {})
	
	# Ensure categories_data and dishes_data are lists
	if not isinstance(categories_data, list):
		if isinstance(categories_data, dict):
			categories_data = list(categories_data.values())
		else:
			categories_data = []
	
	if not isinstance(dishes_data, list):
		if isinstance(dishes_data, dict):
			dishes_data = list(dishes_data.values())
		else:
			dishes_data = []
	
	# If no categories in API response, extract unique categories from dishes
	if not categories_data and dishes_data:
		unique_categories = {}
		for dish in dishes_data:
			if isinstance(dish, dict):
				category_name = dish.get('category') or dish.get('mainCategory')
				if category_name and category_name not in unique_categories:
					# Create a category entry from dish data
					category_id = generate_category_id_from_name(category_name)
					unique_categories[category_name] = {
						'id': category_id,
						'name': category_name,
						'displayName': category_name,
						'description': '',
						'isSpecial': False
					}
		
		if unique_categories:
			categories_data = list(unique_categories.values())
			frappe.log_error(
				f"Categories extracted from dishes: {len(categories_data)} categories found",
				"Menu Category Auto-Extraction"
			)
	
	# Ensure categories_data is always a list (safety check)
	if not isinstance(categories_data, list):
		categories_data = []
	
	# Create or update categories
	category_map = {}  # Map category names to category IDs
	
	for cat_data in categories_data:
		try:
			# Ensure cat_data is a dict
			if not isinstance(cat_data, dict):
				continue
			category_id = cat_data.get('id')
			category_name = cat_data.get('name') or cat_data.get('displayName') or category_id
			
			if not category_id or not category_name:
				frappe.log_error(
					title="Menu Category Creation Skip",
					message=f"Skipping category: still missing critical identity after fallback. id={category_id}, name={category_name}"
				)
				continue
			
			# Normalize name for mapping
			norm_cat_name = str(category_name).strip().lower()
			
			# Check if category already exists for THIS restaurant (by category_id AND restaurant)
			existing_category_name = frappe.db.get_value(
				"Menu Category", 
				{"category_id": category_id, "restaurant": restaurant}, 
				"name"
			)
			
			if not existing_category_name:
				# Also check by category_name AND restaurant in case category_id changed
				existing_category_name = frappe.db.get_value(
					"Menu Category", 
					{"category_name": category_name, "restaurant": restaurant}, 
					"name"
				)
			
			if existing_category_name:
				# Update existing category
				cat_doc = frappe.get_doc("Menu Category", existing_category_name)
				cat_doc.display_name = cat_data.get('displayName', category_name)
				cat_doc.description = cat_data.get('description', '')
				cat_doc.is_special = 1 if cat_data.get('isSpecial') else 0
				
				cat_doc.save(ignore_permissions=True)
				stats['categories_created'] += 1
				category_map[category_name] = cat_doc.category_id
			else:
				# Create new category
				# IMPORTANT: Since category_id is no longer globally unique, 
				# we just use the one provided (which generate_category_id_from_name ensures is unique for us)
				# But if the API provided a conflicting one, let's double check
				if frappe.db.get_value("Menu Category", {"category_id": category_id, "restaurant": restaurant}, "name"):
					# This should be handled by the update logic above, but safety first
					category_id = generate_category_id_from_name(category_name, restaurant=restaurant)

				cat_doc = frappe.new_doc("Menu Category")
				cat_doc.category_id = category_id
				cat_doc.restaurant = restaurant
				cat_doc.category_name = category_name
				cat_doc.display_name = cat_data.get('displayName', category_name)
				cat_doc.description = cat_data.get('description', '')
				cat_doc.is_special = 1 if cat_data.get('isSpecial') else 0
				
				cat_doc.save(ignore_permissions=True)
				stats['categories_created'] += 1
				category_map[category_name] = category_id
			
			# Populate map with both original and normalized name for maximum fallback compatibility
			category_map[category_name] = category_id
			category_map[norm_cat_name] = category_id
			
		except Exception as e:
			raw_err = str(e)
			error_msg = f"Error creating category {category_id or 'unknown'}: {raw_err[:100]}"
			frappe.log_error(title="Menu Category Creation Error", message=f"{error_msg}\n\n{frappe.get_traceback()}")
			continue
	
	# Create or update dishes/products
	for dish_data in dishes_data:
		# Ensure dish_data is a dict
		if not isinstance(dish_data, dict):
			stats['items_skipped'] += 1
			continue
		
		product_name = dish_data.get('name')
		if not product_name:
			stats['items_skipped'] += 1
			continue
		
		product_id = dish_data.get('id') or generate_product_id_from_name(product_name, restaurant=restaurant)
		
		# Check if product exists for THIS restaurant
		existing_product_name = frappe.db.get_value(
			"Menu Product", 
			{"product_id": product_id, "restaurant": restaurant}, 
			"name"
		)
		
		if not existing_product_name:
			existing_product_name = frappe.db.get_value(
				"Menu Product", 
				{"product_name": product_name, "restaurant": restaurant}, 
				"name"
			)
		
		if existing_product_name:
			# Update existing product
			product_doc = frappe.get_doc("Menu Product", existing_product_name)
			stats['items_updated'] += 1
		else:
			# Create new product
			# Re-generate product_id ensures it's unique within the restaurant
			product_id = generate_product_id_from_name(product_name, restaurant=restaurant)
			product_doc = frappe.new_doc("Menu Product")
			product_doc.product_id = product_id
			stats['items_created'] += 1
		
		# Set restaurant (mandatory field)
		product_doc.restaurant = restaurant
		
		# Set basic fields
		product_doc.product_name = product_name
		product_doc.price = scrub_price(dish_data.get('price', 0))
		product_doc.original_price = scrub_price(dish_data.get('originalPrice', 0))
		
		# Handle description
		api_description = dish_data.get('description', '').strip()
		if not product_doc.description or not product_doc.description.strip():
			product_doc.description = api_description
		
		product_doc.is_vegetarian = 1 if dish_data.get('isVegetarian') else 0
		product_doc.has_no_media = 1 if dish_data.get('hasNoMedia') else 0
		
		# Set category with robust matching
		category_name = dish_data.get('category')
		cat_to_link = None
		
		if category_name:
			norm_dish_cat = str(category_name).strip().lower()
			cat_to_link = category_map.get(category_name) or category_map.get(norm_dish_cat)
			
			if not cat_to_link:
				# Deep lookup in DB for this restaurant if not in current map
				cat_to_link = frappe.db.get_value("Menu Category", {"category_id": category_name, "restaurant": restaurant}, "category_id")
				if not cat_to_link:
					cat_to_link = frappe.db.get_value("Menu Category", {"category_name": category_name, "restaurant": restaurant}, "category_id")
		
		if cat_to_link:
			product_doc.category = frappe.db.get_value("Menu Category", {"category_id": cat_to_link, "restaurant": restaurant}, "name")
			product_doc.category_name = category_name or frappe.db.get_value("Menu Category", product_doc.category, "category_name")
		elif category_name:
			product_doc.category_name = category_name
			frappe.log_error(title="Menu Extraction - Link Warning", message=f"Dish '{product_name}' refers to unknown category '{category_name}'. Link failed.")
		
		# Set main category
		main_category = dish_data.get('mainCategory')
		if main_category:
			product_doc.main_category = main_category
		
		# Set calories if present
		if dish_data.get('calories'):
			product_doc.calories = dish_data.get('calories')
		
		# Set estimated time and serving size
		if dish_data.get('estimatedTime'):
			product_doc.estimated_time = dish_data.get('estimatedTime')
		if dish_data.get('servingSize'):
			product_doc.serving_size = dish_data.get('servingSize')
		
		# Handle media if present
		media_list = dish_data.get('media', [])
		if media_list and isinstance(media_list, list) and len(media_list) > 0:
			product_doc.product_media = []
			media_added = 0
			for idx, media_item in enumerate(media_list):
				media_url = None
				if isinstance(media_item, str):
					media_url = media_item
				elif isinstance(media_item, dict):
					media_url = media_item.get('url') or media_item.get('media_url') or media_item.get('src')
				
				if not media_url: continue
				
				media_type = 'video' if any(ext in media_url.lower() for ext in ['.mp4', '.mov', '.avi', '.webm']) else 'image'
				media_row = product_doc.append('product_media', {})
				media_row.media_url = media_url
				media_row.media_type = media_type
				media_row.display_order = idx + 1
				media_added += 1
		
		try:
			# Clear customizations from the object before saving to avoid validation errors
			# (We will handle them manually after the product is saved)
			product_doc.set('customization_questions', [])
			product_doc.save(ignore_permissions=True)
			
			# Explicitly handle nested customizations (Questions -> Options)
			# Standard product_doc.save() often fails to recurse into nested child tables
			if dish_data.get('customizationQuestions'):
				# Clear existing customizations for this product to prevent duplicates
				existing_questions = frappe.get_all("Customization Question", filters={"parent": product_doc.name}, fields=["name"])
				for eq in existing_questions:
					frappe.db.delete("Customization Option", {"parent": eq.name, "parenttype": "Customization Question"})
					frappe.db.delete("Customization Question", {"name": eq.name})
				
				# Re-insert questions and options manually
				for q_idx, custom_data in enumerate(dish_data.get('customizationQuestions', [])):
					if not isinstance(custom_data, dict): continue
					options_list = custom_data.get('options')
					if not isinstance(options_list, list) or len(options_list) == 0: continue
					valid_options = [opt for opt in options_list if isinstance(opt, dict) and opt.get('label')]
					if not valid_options: continue
					
					cq = frappe.new_doc("Customization Question")
					cq.parent = product_doc.name
					cq.parenttype = "Menu Product"
					cq.parentfield = "customization_questions"
					cq.question_id = custom_data.get('id', '')
					cq.title = custom_data.get('title', '')
					cq.subtitle = custom_data.get('subtitle', '')
					cq.question_type = custom_data.get('type', 'single')
					cq.is_required = 1 if custom_data.get('required') else 0
					cq.display_order = custom_data.get('displayOrder', q_idx)
					
					for opt_idx, option_data in enumerate(valid_options):
						raw_opt_price = option_data.get('price', 0)
						if isinstance(raw_opt_price, str):
							raw_opt_price = re.sub(r'[^\d.]', '', raw_opt_price)
							price = float(raw_opt_price) if raw_opt_price else 0
						else:
							price = raw_opt_price
							
						cq.append('options', {
							'option_id': option_data.get('id') or f"opt_{opt_idx}_{int(time.time())}",
							'label': option_data.get('label'),
							'price': price,
							'is_default': 1 if option_data.get('isDefault') else 0,
							'is_vegetarian': 1 if option_data.get('isVegetarian') else 0,
							'display_order': option_data.get('displayOrder', opt_idx)
						})
					
					cq.insert(ignore_permissions=True)

		except Exception as e:
			raw_err = str(e)
			display_name = product_name[:30] + "..." if len(product_name) > 30 else product_name
			error_msg = f"Error saving {display_name}: {raw_err[:100]}"
			frappe.log_error(title="Menu Product Save Error", message=f"{error_msg}\n\n{frappe.get_traceback()}")
			stats['items_skipped'] += 1
			if not existing_product_name:
				stats['items_created'] -= 1
			else:
				stats['items_updated'] -= 1
	
	frappe.db.commit()
	
	return stats


@frappe.whitelist()
def approve_extracted_data(docname):
	"""
	Approve extracted data and create Menu Categories and Menu Products
	"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)

		# Hardening: Prevent double-approval
		if doc.approval_status == "Approved" or doc.extraction_status == "Completed":
			return {
				'success': True,
				'message': _("This extraction has already been approved and items have been created."),
				'stats': {
					'items_created': doc.items_created,
					'categories_created': doc.categories_created
				}
			}

		frappe.log_error(title="Menu Approval - Start", message=f"Approving extracted data for {docname}")
		if doc.extraction_status != "Pending Approval":
			frappe.throw(_("Only documents with 'Pending Approval' status can be approved."))
		
		# Get data from editable child tables (user may have edited the data)
		# Convert child table data back to the format expected by process_extracted_data
		data = {
			'categories': [],
			'dishes': []
		}
		
		# Check if child tables have data
		if not doc.extracted_dishes:
			# Fallback to raw_response if child tables are empty
			if not doc.raw_response:
				frappe.throw(_("No extracted data found. Please extract menu data first."))
			
			try:
				raw_data = json.loads(doc.raw_response)
				if isinstance(raw_data, dict):
					if 'data' in raw_data:
						data = raw_data['data']
					elif 'success' in raw_data and isinstance(raw_data.get('data'), dict):
						data = raw_data['data']
					else:
						data = raw_data.get('data', raw_data)
					
					# Ensure media is included in dishes from raw_response
					if data.get('dishes'):
						dishes_list = data['dishes']
						if not isinstance(dishes_list, list):
							dishes_list = list(dishes_list.values()) if isinstance(dishes_list, dict) else []
						
						for dish in dishes_list:
							if isinstance(dish, dict) and not dish.get('media'):
								# Try to ensure media array exists (even if empty)
								dish['media'] = dish.get('media', [])
				else:
					frappe.throw(_("Invalid data format. Please re-extract the menu data."))
			except json.JSONDecodeError:
				frappe.throw(_("Invalid data format. Please re-extract the menu data."))
		else:
			# Get categories from raw_response (categories come from API response)
			if doc.raw_response:
				try:
					raw_data = json.loads(doc.raw_response)
					if isinstance(raw_data, dict):
						if 'data' in raw_data:
							raw_data_obj = raw_data['data']
						elif 'success' in raw_data and isinstance(raw_data.get('data'), dict):
							raw_data_obj = raw_data['data']
						else:
							raw_data_obj = raw_data.get('data', raw_data)
						
						# Get categories from raw data
						categories_data = raw_data_obj.get('categories', [])
						if not isinstance(categories_data, list):
							if isinstance(categories_data, dict):
								categories_data = list(categories_data.values())
							else:
								categories_data = []
						
						for cat_data in categories_data:
							if isinstance(cat_data, dict):
								data['categories'].append(cat_data)
					
					# Log if no categories found
					if not data.get('categories'):
						frappe.log_error(
							title="Menu Category Extraction Warning",
							message=f"No categories found in raw_response for {docname}. Raw data keys: {list(raw_data_obj.keys()) if isinstance(raw_data_obj, dict) else 'N/A'}"
						)
				except Exception as e:
					error_msg = f"Error parsing categories from raw_response for {docname}: {str(e)[:140]}"
					frappe.log_error(title="Menu Category Parsing Error", message=error_msg)
					# Don't silently fail - log the error so we can debug
			
			# Get raw dishes data for media fallback
			raw_dishes_map = {}
			if doc.raw_response:
				try:
					raw_data = json.loads(doc.raw_response)
					if isinstance(raw_data, dict):
						raw_data_obj = raw_data.get('data', raw_data)
						if isinstance(raw_data_obj, dict) and 'dishes' in raw_data_obj:
							raw_dishes = raw_data_obj['dishes']
							if isinstance(raw_dishes, list):
								for raw_dish in raw_dishes:
									if isinstance(raw_dish, dict) and raw_dish.get('id'):
										raw_dishes_map[raw_dish['id']] = raw_dish
							elif isinstance(raw_dishes, dict):
								raw_dishes_map = raw_dishes
				except Exception as e:
					frappe.log_error(title="Menu Approval - Media Fallback Error", message=f"Error parsing raw_response for media fallback: {str(e)}")
			
			# Convert extracted dishes from child table
			for dish_row in doc.extracted_dishes:
				dish_data = {
					'id': dish_row.dish_id,
					'name': dish_row.dish_name,
					'price': dish_row.price or 0,
					'originalPrice': dish_row.original_price,
					'category': dish_row.category or '',
					'description': dish_row.description or '',
					'calories': dish_row.calories,
					'isVegetarian': bool(dish_row.is_vegetarian),
					'estimatedTime': dish_row.estimated_time,
					'servingSize': dish_row.serving_size,
					'hasNoMedia': bool(dish_row.has_no_media),
					'mainCategory': dish_row.main_category or ''
				}
				
				# Parse media JSON if exists
				if dish_row.media_json:
					try:
						dish_data['media'] = json.loads(dish_row.media_json)
					except:
						dish_data['media'] = []
				else:
					# Fallback: Try to get media from raw_response
					raw_dish = raw_dishes_map.get(dish_row.dish_id) or raw_dishes_map.get(dish_row.dish_name)
					if raw_dish and isinstance(raw_dish, dict):
						dish_data['media'] = raw_dish.get('media', [])
				
				# Parse customizations JSON if exists
				if dish_row.customizations_json:
					try:
						dish_data['customizationQuestions'] = json.loads(dish_row.customizations_json)
					except:
						dish_data['customizationQuestions'] = []
				else:
					# Fallback: Try to get customizations from raw_response
					raw_dish = raw_dishes_map.get(dish_row.dish_id) or raw_dishes_map.get(dish_row.dish_name)
					if raw_dish and isinstance(raw_dish, dict):
						dish_data['customizationQuestions'] = raw_dish.get('customizationQuestions', [])
				
				data['dishes'].append(dish_data)
		
		# If no categories found in raw_response, extract from dishes
		if not data.get('categories') and data.get('dishes'):
			unique_categories = {}
			for dish in data['dishes']:
				if isinstance(dish, dict):
					category_name = dish.get('category') or dish.get('mainCategory')
					if category_name and category_name not in unique_categories:
						# Create a category entry from dish data
						category_id = generate_category_id_from_name(category_name)
						unique_categories[category_name] = {
							'id': category_id,
							'name': category_name,
							'displayName': category_name,
							'description': '',
							'isSpecial': False
						}
			
			if unique_categories:
				data['categories'] = list(unique_categories.values())
				frappe.log_error(
					title="Menu Category Auto-Extraction from Dishes",
					message=f"Categories auto-extracted from dishes for {docname}: {len(data['categories'])} categories found"
				)
		
		if not data or (not data.get('categories') and not data.get('dishes')):
			frappe.throw(_("No data found to approve. Please extract menu data first."))
		
		# Process the data and create categories/products
		stats = process_extracted_data(data, doc)
		
		# Update document status
		doc.extraction_status = "Completed"
		doc.approval_status = "Approved"
		doc.extraction_log = f"Data approved and created successfully!\n\n" + \
			f"Categories created: {stats['categories_created']}\n" + \
			f"Items created: {stats['items_created']}\n" + \
			f"Items updated: {stats['items_updated']}\n" + \
			f"Items skipped: {stats['items_skipped']}"
		doc.items_created = stats['items_created']
		doc.categories_created = stats['categories_created']
		doc.save(ignore_permissions=True)
		
		# AUTOMATIC CLEANUP: Delete source menu images now that data is successfully approved
		# This saves significant storage space for the merchant
		try:
			doc.cleanup_source_images()
			doc.extraction_log += "\n\nStorage optimized: Source images cleaned up successfully."
			doc.save(ignore_permissions=True)
		except:
			pass # Don't fail the whole approval if cleanup fails
			
		frappe.db.commit()
		
		return {
			'success': True,
			'message': f"Successfully approved and created {stats['items_created']} items and {stats['categories_created']} categories",
			'stats': stats
		}
		
	except Exception as e:
		frappe.log_error(title="Menu Approval Error", message=frappe.get_traceback())
		frappe.throw(_("Approval failed: {0}").format(str(e)))


@frappe.whitelist()
def generate_recommendations(docname):
	"""
	Generate recommendations for all products of the restaurant from this extraction
	"""
	try:
		doc = frappe.get_doc("Menu Image Extractor", docname)
		
		# Check if extraction is completed
		if doc.extraction_status != "Completed":
			frappe.throw(_("Recommendations can only be generated after extraction is completed."))
		
		# Get restaurant
		if not doc.restaurant:
			frappe.throw(_("Restaurant is required to generate recommendations."))
		
		restaurant = doc.restaurant
		
		# Get restaurant name for API
		restaurant_name = doc.restaurant_name
		if not restaurant_name:
			restaurant_name = frappe.db.get_value("Restaurant", restaurant, "restaurant_name")
		
		# Get all active products for this restaurant
		products = frappe.get_all(
			"Menu Product",
			fields=["product_id", "product_name", "category_name", "main_category", "price", 
			        "description", "is_vegetarian", "name"],
			filters={"restaurant": restaurant, "is_active": 1}
		)
		
		if not products:
			frappe.throw(_("No active products found for this restaurant. Please create products first."))
		
		# Get categories
		categories = frappe.get_all(
			"Menu Category",
			fields=["category_id", "category_name"],
			filters={"restaurant": restaurant}
		)
		
		# Prepare dishes data for API
		dishes = []
		for product in products:
			dishes.append({
				"id": product.product_id,
				"name": product.product_name,
				"category": product.category_name or "",
				"mainCategory": product.main_category or "food",
				"price": float(product.price or 0),
				"description": product.description or "",
				"isVegetarian": bool(product.is_vegetarian)
			})
		
		# Prepare categories data for API
		categories_data = []
		for cat in categories:
			categories_data.append({
				"id": cat.category_id or cat.category_name.lower().replace(" ", "-"),
				"name": cat.category_name
			})
		
		# Call local recommendations engine
		try:
			engine = RecommendationEngine()
			recs_list, insufficient = engine.generate_recommendations(dishes)
			
			# Wrap in 'success' and 'data' for parity with legacy API expectations
			result = {
				'success': True,
				'data': {
					'recommendations': recs_list
				}
			}
		except Exception as e:
			frappe.log_error(title="Recommendations Engine Error", message=frappe.get_traceback())
			frappe.throw(_("Recommendations Engine Failed: {0}").format(str(e)))
		
		if not result.get('success'):
			frappe.throw(_("Recommendations Engine failed: {0}").format(result.get('message', 'Unknown error')))
		
		# Store recommendations in products
		recommendations_data = result.get('data', {}).get('recommendations', [])
		
		# Create a map of product_id to product name for lookup
		product_id_to_name = {p.product_id: p.name for p in products}
		
		updated_count = 0
		for rec_item in recommendations_data:
			product_id = rec_item.get('id')
			if not product_id or product_id not in product_id_to_name:
				continue
			
			product_name = product_id_to_name[product_id]
			recommendations = rec_item.get('recommendations', [])
			
			# Format recommendations for storage
			formatted_recommendations = []
			for rec in recommendations:
				formatted_recommendations.append({
					"id": rec.get('id'),
					"name": rec.get('name'),
					"category": rec.get('category', ''),
					"mainCategory": rec.get('mainCategory', ''),
					"isVegetarian": rec.get('isVegetarian', False),
					"price": rec.get('price', 0),
					"reason": rec.get('reason', ''),
					"score": rec.get('score', 0)
				})
			
			# Update product with recommendations
			try:
				product_doc = frappe.get_doc("Menu Product", product_name)
				product_doc.recommendations = json.dumps(formatted_recommendations)
				product_doc.save(ignore_permissions=True)
				updated_count += 1
			except Exception as e:
				frappe.log_error(
					title="Menu Recommendations - Update Error",
					message=f"Error updating recommendations for product {product_id}: {str(e)}"
				)
				continue
		
		frappe.db.commit()
		
		# Update extraction log
		doc.db_set('extraction_log', 
			f"Recommendations generated successfully!\n\n"
			f"Products updated: {updated_count}\n"
			f"Total recommendations generated: {len(recommendations_data)}",
			update_modified=False)
		frappe.db.commit()
		
		return {
			'success': True,
			'message': _("Successfully generated recommendations for {0} products.").format(updated_count),
			'updated_count': updated_count,
			'total_products': len(products)
		}
		
	except frappe.exceptions.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(title="Menu Recommendations Generation Error", message=frappe.get_traceback())
		frappe.throw(_("Recommendations generation failed: {0}").format(str(e)))

