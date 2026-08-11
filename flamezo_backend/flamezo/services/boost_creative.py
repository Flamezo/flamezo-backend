"""
AI-powered ad copy generation for Flamezo Boost campaigns.

Uses Gemini 2.5 Flash (already configured in site_config) to fill
template placeholders with outlet-specific content. The template
structure is fixed (proven hooks) — AI only personalises the fill.
"""
import frappe
import json
import google.generativeai as genai


def _get_gemini_model():
	api_key = frappe.conf.get("gemini_api_key")
	if not api_key:
		frappe.throw("Gemini API key not configured in site_config.json")
	genai.configure(api_key=api_key)
	return genai.GenerativeModel("gemini-2.0-flash")


def generate_ad_copy(outlet_id, template_id, hero_dish_name=None, offer_amount=0):
	"""
	Generate ad copy (primary_text + headline) using template + AI.

	Returns:
		dict: {
			"primary_text": str (max 150 chars),
			"headline": str (max 27 chars),
			"offer_description": str
		}
	"""
	# Fetch outlet data
	restaurant = frappe.get_doc("Restaurant", outlet_id)
	outlet_name = restaurant.restaurant_name or outlet_id
	area = restaurant.city or "your area"
	cuisine = _get_cuisine(outlet_id)

	# Fetch template
	template = frappe.get_doc("Boost Template", template_id)

	# Simple placeholder fill first
	placeholders = {
		"restaurant": outlet_name,
		"dish": hero_dish_name or "our special",
		"area": area,
		"offer": str(int(offer_amount)),
		"cuisine": cuisine,
	}

	primary_text = template.primary_text_template or ""
	headline = template.headline_template or ""
	for key, val in placeholders.items():
		primary_text = primary_text.replace(f"{{{key}}}", val)
		headline = headline.replace(f"{{{key}}}", val)

	# Truncate to Meta limits
	primary_text = primary_text[:150]
	headline = headline[:27]

	offer_description = f"Flat ₹{int(offer_amount)} off (min order ₹{int(offer_amount * 2)})"

	# If template fill is good enough, skip AI
	if len(primary_text) > 30 and len(headline) > 5:
		return {
			"primary_text": primary_text,
			"headline": headline,
			"offer_description": offer_description,
		}

	# Fallback: use AI to generate from scratch
	return _ai_generate(outlet_name, area, cuisine, hero_dish_name,
						offer_amount, template, offer_description)


def _ai_generate(outlet_name, area, cuisine, hero_dish, offer_amount, template, offer_desc):
	"""Use Gemini to generate ad copy when template fill isn't sufficient."""
	model = _get_gemini_model()

	prompt = f"""Generate a Meta (Instagram/Facebook) ad copy for a restaurant.

Restaurant: {outlet_name}
Location: {area}
Cuisine: {cuisine}
{"Hero Dish: " + hero_dish if hero_dish else ""}
Offer: Flat ₹{int(offer_amount)} off
Template style: {template.template_name} — "{template.hook_formula}"

Rules:
1. Primary text: max 150 characters, warm/inviting, mention restaurant name + area + offer
2. Headline: max 27 characters, punchy, include the offer amount
3. No hashtags, no emojis overload (max 1 emoji), no ALL CAPS
4. Tone: casual, local, like a friend recommending a place
5. Must feel authentic to Indian food culture

Return ONLY valid JSON:
{{"primary_text": "...", "headline": "..."}}"""

	try:
		response = model.generate_content(prompt)
		text = response.text.strip()
		# Strip markdown code fence if present
		if text.startswith("```"):
			text = text.split("```")[1]
			if text.startswith("json"):
				text = text[4:]
			text = text.strip()
		result = json.loads(text)
		return {
			"primary_text": result.get("primary_text", "")[:150],
			"headline": result.get("headline", "")[:27],
			"offer_description": offer_desc,
		}
	except Exception as e:
		frappe.log_error(f"Gemini ad copy generation failed: {str(e)}", "Boost Creative AI Error")
		# Return template-filled version as fallback
		return {
			"primary_text": f"Get ₹{int(offer_amount)} off at {outlet_name}. Visit us in {area}!",
			"headline": f"₹{int(offer_amount)} off now",
			"offer_description": offer_desc,
		}


def _get_cuisine(outlet_id):
	"""Get cuisine type from outlet's menu categories."""
	categories = frappe.db.get_all(
		"Menu Category",
		filters={"restaurant": outlet_id},
		fields=["category_name"],
		limit=3,
	)
	if categories:
		return ", ".join([c.category_name for c in categories])
	return "Multi-cuisine"
