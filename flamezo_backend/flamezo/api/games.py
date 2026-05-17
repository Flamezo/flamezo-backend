# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Games/Experience Lounge
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
from frappe.utils import get_url
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api


@frappe.whitelist(allow_guest=True)
def get_games(restaurant_id, featured=None, category=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.games.get_games
	Get all games available in the experience lounge
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Build filters
		filters = {"restaurant": restaurant, "is_active": 1}
		
		if featured is not None:
			filters["featured"] = 1 if featured else 0
		
		if category:
			filters["category"] = category
		
		# Get games
		games = frappe.get_all(
			"Game",
			fields=[
				"name as id",
				"title",
				"image_src",
				"image_alt",
				"description",
				"category",
				"featured",
				"is_available",
				"is_active"
			],
			filters=filters,
			order_by="display_order asc, title asc"
		)
		
		# Format games
		formatted_games = []
		for game in games:
			game_data = {
				"id": str(game["id"]),
				"title": game["title"],
				"description": game.get("description", ""),
				"category": game.get("category", ""),
				"featured": bool(game.get("featured", False)),
				"isAvailable": bool(game.get("is_available", False))
			}
			
			if game.get("image_src"):
				image_src = game["image_src"]
				if image_src.startswith("/files/"):
					image_src = get_url(image_src)
				game_data["imageSrc"] = image_src
			
			if game.get("image_alt"):
				game_data["imageAlt"] = game["image_alt"]
			
			formatted_games.append(game_data)
		
		return {
			"success": True,
			"data": {
				"games": formatted_games
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_games: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "GAME_FETCH_ERROR",
				"message": str(e)
			}
		}


