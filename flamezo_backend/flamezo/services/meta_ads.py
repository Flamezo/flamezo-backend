"""
Meta Marketing API v25.0 — Campaign lifecycle management for Flamezo Boost.

All restaurant ads run from Flamezo's own Ad Account. Restaurants do not need
a Meta account. The System User Token authenticates all API calls.

Ref: https://developers.facebook.com/docs/marketing-api/reference/
"""
import json
import requests
import frappe
from frappe.utils import flt  # noqa: F401


def _conf(key):
	"""Read a meta_* key from site_config.json."""
	return frappe.conf.get(key) or ""


def _base():
	return f"https://graph.facebook.com/{_conf('meta_graph_api_version')}"


def _token():
	return _conf("meta_system_user_token")


def _ad_account():
	return _conf("meta_ad_account_id")


def _page_id():
	return _conf("meta_page_id")


def _headers():
	return {"Content-Type": "application/json"}


def _post(endpoint, data, retries=3):
	"""POST to Meta Graph API with retry. Raises on final failure."""
	import time
	data["access_token"] = _token()
	url = f"{_base()}/{endpoint}"
	last_error = None
	for attempt in range(retries):
		try:
			resp = requests.post(url, json=data, timeout=45)
			body = resp.json()
			if "error" in body:
				error_msg = body["error"].get("message", "Unknown Meta API error")
				error_code = body["error"].get("code", "")
				# Transient errors (rate limit, server error) — retry
				if error_code in (1, 2, 4, 17, 32, 190) and attempt < retries - 1:
					time.sleep(2 ** attempt)
					continue
				frappe.log_error(
					message=f"Meta API Error: {error_code} — {error_msg}\nEndpoint: {endpoint}\nPayload: {json.dumps(data, default=str)[:2000]}",
					title="Meta Ads API Error"
				)
				frappe.throw(f"Meta Ads API error: {error_msg}")
			return body
		except requests.exceptions.Timeout:
			last_error = "Meta API timeout"
			if attempt < retries - 1:
				time.sleep(2 ** attempt)
				continue
		except requests.exceptions.ConnectionError:
			last_error = "Meta API connection error"
			if attempt < retries - 1:
				time.sleep(2 ** attempt)
				continue
	frappe.throw(f"Meta API failed after {retries} attempts: {last_error}")
	return {}  # unreachable — frappe.throw always raises


def _get(endpoint, params=None):
	"""GET from Meta Graph API."""
	params = params or {}
	params["access_token"] = _token()
	url = f"{_base()}/{endpoint}"
	resp = requests.get(url, params=params, timeout=30)
	body = resp.json()
	if "error" in body:
		error_msg = body["error"].get("message", "Unknown Meta API error")
		frappe.log_error(
			message=f"Meta API GET Error: {error_msg}\nEndpoint: {endpoint}",
			title="Meta Ads API Error"
		)
		frappe.throw(f"Meta Ads API error: {error_msg}")
	return body


# ─── Campaign Creation ─────────────────────────────────────────────

def create_campaign(boost_campaign):
	"""Create a Meta ad campaign (PAUSED) for a Boost Campaign doc."""
	data = {
		"name": f"BOOST | {boost_campaign.restaurant} | {boost_campaign.name}",
		"objective": "OUTCOME_TRAFFIC",
		"status": "PAUSED",
		"special_ad_categories": "[]",
		"is_adset_budget_sharing_enabled": False,
	}
	result = _post(f"{_ad_account()}/campaigns", data)
	return result["id"]


def create_ad_set(boost_campaign, meta_campaign_id):
	"""Create a geo-targeted ad set with daily budget."""
	radius_km = int(boost_campaign.geo_radius_km or 5)
	daily_budget_paisa = boost_campaign.get_daily_budget_paisa()

	targeting = {
		"geo_locations": {
			"custom_locations": [{
				"latitude": float(boost_campaign.restaurant_lat),
				"longitude": float(boost_campaign.restaurant_lng),
				"radius": radius_km,
				"distance_unit": "kilometer"
			}]
		},
		"age_min": int(boost_campaign.target_age_min or 18),
		"age_max": int(boost_campaign.target_age_max or 55),
		"targeting_automation": {"advantage_audience": 0},
	}

	data = {
		"name": f"AdSet | {boost_campaign.restaurant} | {boost_campaign.name}",
		"campaign_id": meta_campaign_id,
		"billing_event": "IMPRESSIONS",
		"optimization_goal": "LINK_CLICKS",
		"daily_budget": str(daily_budget_paisa),
		"bid_amount": "500",
		"targeting": json.dumps(targeting),
		"status": "ACTIVE",
	}
	result = _post(f"{_ad_account()}/adsets", data)
	return result["id"]


def upload_ad_image(image_url):
	"""Upload an image to the ad account. Downloads first, then uploads as multipart file."""
	# Download the image
	img_resp = requests.get(image_url, timeout=30)
	if img_resp.status_code != 200:
		frappe.throw(f"Failed to download image from {image_url}: HTTP {img_resp.status_code}")

	filename = image_url.split('/')[-1].split('?')[0] or 'boost_ad.jpg'
	content_type = img_resp.headers.get('content-type', 'image/jpeg')

	url = f"{_base()}/{_ad_account()}/adimages"
	files = {"filename": (filename, img_resp.content, content_type)}
	data = {"access_token": _token()}
	resp = requests.post(url, data=data, files=files, timeout=60)
	body = resp.json()
	if "error" in body:
		frappe.throw(f"Meta image upload error: {body['error'].get('message', 'Unknown')}")
	images = body.get("images", {})
	for key, val in images.items():
		return val.get("hash", "")
	frappe.throw("Meta image upload returned no hash")


def create_ad_creative(boost_campaign, image_hash):
	"""Create an ad creative with image, text, CTA, and link."""
	page_id = _page_id()
	# Landing page: public coupon claim page
	restaurant_id = boost_campaign.restaurant
	coupon_code = boost_campaign.coupon_code
	link_url = f"https://flamezo.in/{restaurant_id}/boost-offer?code={coupon_code}"

	cta_map = {
		"GET_OFFER": "GET_OFFER",
		"LEARN_MORE": "LEARN_MORE",
		"ORDER_NOW": "ORDER_NOW",
		"BOOK_NOW": "BOOK_NOW",
	}
	template = None
	if boost_campaign.template_id:
		template = frappe.db.get_value("Boost Template", boost_campaign.template_id, "cta_type")
	cta_type = cta_map.get(template or "GET_OFFER", "GET_OFFER")

	data = {
		"name": f"Creative | {boost_campaign.name}",
		"object_story_spec": json.dumps({
			"page_id": page_id,
			"link_data": {
				"image_hash": image_hash,
				"link": link_url,
				"message": boost_campaign.ad_primary_text or "",
				"name": boost_campaign.ad_headline or "",
				"call_to_action": {
					"type": cta_type,
					"value": {"link": link_url}
				}
			}
		}),
	}
	result = _post(f"{_ad_account()}/adcreatives", data)
	return result["id"]


def create_ad(boost_campaign, meta_creative_id, meta_adset_id):
	"""Create the actual ad linking creative to ad set."""
	data = {
		"name": f"Ad | {boost_campaign.name}",
		"adset_id": meta_adset_id,
		"creative": json.dumps({"creative_id": meta_creative_id}),
		"status": "ACTIVE",
	}
	result = _post(f"{_ad_account()}/ads", data)
	return result["id"]


# ─── Campaign Management ───────────────────────────────────────────

def activate_campaign(meta_campaign_id):
	"""Set campaign status to ACTIVE."""
	_post(meta_campaign_id, {"status": "ACTIVE"})


def pause_campaign(meta_campaign_id):
	"""Set campaign status to PAUSED."""
	_post(meta_campaign_id, {"status": "PAUSED"})


def delete_campaign(meta_campaign_id):
	"""Delete a campaign (only for Draft/Failed that never went live)."""
	url = f"{_base()}/{meta_campaign_id}"
	params = {"access_token": _token()}
	requests.delete(url, params=params, timeout=30)


# ─── Insights ──────────────────────────────────────────────────────

def get_campaign_insights(meta_campaign_id):
	"""Pull performance metrics for a campaign."""
	params = {
		"fields": "impressions,reach,clicks,spend,cpm,ctr,actions",
		"date_preset": "lifetime",
	}
	result = _get(f"{meta_campaign_id}/insights", params)
	data_list = result.get("data", [])
	if not data_list:
		return {
			"impressions": 0, "reach": 0, "clicks": 0,
			"spend": "0", "cpm": "0", "ctr": "0"
		}
	return data_list[0]


# ─── Full Launch Sequence ──────────────────────────────────────────

def launch_boost_campaign(campaign_name):
	"""
	Full Meta campaign launch sequence for a Boost Campaign.
	Called as a background job after payment verification.

	1. Upload image → get hash
	2. Create campaign (PAUSED)
	3. Create ad set (geo + budget)
	4. Create creative (image + text + CTA)
	5. Create ad (link creative to adset)
	6. Activate campaign
	7. Update Boost Campaign doc → Live
	"""
	campaign = frappe.get_doc("Boost Campaign", campaign_name)

	try:
		# Step 1: Upload image
		image_url = campaign.ad_image_with_overlay or campaign.ad_image_url
		if not image_url:
			frappe.throw("No ad image URL set on campaign")
		image_hash = upload_ad_image(image_url)

		# Step 2: Create campaign
		meta_campaign_id = create_campaign(campaign)
		campaign.meta_campaign_id = meta_campaign_id

		# Step 3: Create ad set
		meta_adset_id = create_ad_set(campaign, meta_campaign_id)
		campaign.meta_adset_id = meta_adset_id

		# Step 4: Create creative
		meta_creative_id = create_ad_creative(campaign, image_hash)
		campaign.meta_creative_id = meta_creative_id

		# Step 5: Create ad
		meta_ad_id = create_ad(campaign, meta_creative_id, meta_adset_id)
		campaign.meta_ad_id = meta_ad_id

		# Step 6: Activate
		activate_campaign(meta_campaign_id)

		# Step 7: Mark live
		campaign.mark_live()

		frappe.logger().info(f"Boost campaign {campaign_name} launched on Meta: {meta_campaign_id}")

	except Exception as e:
		campaign.status = "Failed"
		campaign.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.log_error(
			message=f"Campaign: {campaign_name}\nError: {str(e)}",
			title="Boost Campaign Launch Failed"
		)
		raise
