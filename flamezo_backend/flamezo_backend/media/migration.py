# Migration utilities for transitioning to R2 media architecture
# This helps migrate existing Frappe file attachments to Media Assets

import frappe
from frappe import _
import os


def migrate_product_media_to_r2(product_name, dry_run=True):
	"""
	Migrate a product's media from Frappe files to R2 Media Assets
	
	Args:
		product_name: Name of the Menu Product
		dry_run: If True, only show what would be migrated
	
	Returns:
		dict with migration results
	"""
	product = frappe.get_doc("Menu Product", product_name)
	
	if not product.product_media:
		return {"status": "no_media", "message": "No media to migrate"}
	
	results = []
	
	for idx, media_item in enumerate(product.product_media):
		# Skip if already has Media Asset
		if media_item.media_asset:
			results.append({
				"row": idx + 1,
				"status": "skipped",
				"message": "Already has Media Asset"
			})
			continue
		
		# Skip if no media_url
		if not media_item.media_url:
			results.append({
				"row": idx + 1,
				"status": "skipped",
				"message": "No media URL"
			})
			continue
		
		# Check if it's a Frappe file
		if not media_item.media_url.startswith("/files/"):
			results.append({
				"row": idx + 1,
				"status": "skipped",
				"message": "Not a Frappe file (external URL)"
			})
			continue
		
		if dry_run:
			results.append({
				"row": idx + 1,
				"status": "would_migrate",
				"media_url": media_item.media_url,
				"media_type": media_item.media_type
			})
		else:
			# TODO: Implement actual migration
			# This would involve:
			# 1. Get file from Frappe file system
			# 2. Upload to R2 using media API
			# 3. Create Media Asset
			# 4. Link to Product Media
			results.append({
				"row": idx + 1,
				"status": "migration_not_implemented",
				"message": "Migration logic not yet implemented"
			})
	
	return {
		"product": product_name,
		"total_media": len(product.product_media),
		"results": results
	}


@frappe.whitelist()
def get_media_migration_status():
	"""
	Get overview of media migration status across all products
	
	Returns:
		dict with migration statistics
	"""
	products = frappe.get_all("Menu Product", fields=["name", "product_name"])
	
	stats = {
		"total_products": len(products),
		"products_with_media": 0,
		"products_with_r2_media": 0,
		"products_with_legacy_media": 0,
		"products_with_mixed_media": 0,
		"total_media_items": 0,
		"r2_media_items": 0,
		"legacy_media_items": 0
	}
	
	for product in products:
		product_doc = frappe.get_doc("Menu Product", product.name)
		
		if not product_doc.product_media:
			continue
		
		stats["products_with_media"] += 1
		stats["total_media_items"] += len(product_doc.product_media)
		
		r2_count = 0
		legacy_count = 0
		
		for media_item in product_doc.product_media:
			if media_item.media_asset:
				r2_count += 1
				stats["r2_media_items"] += 1
			else:
				legacy_count += 1
				stats["legacy_media_items"] += 1
		
		if r2_count > 0 and legacy_count == 0:
			stats["products_with_r2_media"] += 1
		elif legacy_count > 0 and r2_count == 0:
			stats["products_with_legacy_media"] += 1
		elif r2_count > 0 and legacy_count > 0:
			stats["products_with_mixed_media"] += 1
	
	return stats
