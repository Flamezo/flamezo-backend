import base64
import hashlib
import html
import os
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from io import BytesIO

import frappe
from frappe.utils import get_url
from frappe import _
from flamezo_backend.flamezo.utils.common import safe_log_error, resolve_and_fetch_media


def normalize_qr_color(color):
	default_color = "#DB782F"
	if not color:
		return default_color

	try:
		from PIL import ImageColor

		candidate = color.strip()
		if re.fullmatch(r"[0-9a-fA-F]{6}", candidate):
			candidate = f"#{candidate}"
		ImageColor.getrgb(candidate)
		return candidate
	except Exception:
		return default_color


def safe_restaurant_path(value):
	return re.sub(r"[^a-z0-9-]", "", (value or "restaurant").lower()) or "restaurant"


def resolve_qr_branding(restaurant_doc, override_background_url=None):
	from flamezo_backend.flamezo.media.utils import get_media_asset_data

	config_name = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant_doc.name}, "name")
	primary_color = None
	logo_url = ""
	background_image_url = override_background_url or ""

	if config_name:
		# Use a safer fetch for primary_color and logo
		config_values = frappe.db.get_value(
			"Restaurant Config",
			config_name,
			["primary_color", "logo"],
			as_dict=True,
		) or {}
		
		primary_color = config_values.get("primary_color")
		
		# Attempt to get qr_background safely
		try:
			background_image_url = frappe.db.get_value("Restaurant Config", config_name, "qr_background")
		except Exception:
			# Field doesn't exist yet, fallback to override or empty
			pass

		if not background_image_url:
			background_image_url = override_background_url or ""
		
		logo_url = get_media_asset_data(
			"Restaurant Config",
			config_name,
			"restaurant_config_logo",
			config_values.get("logo") or restaurant_doc.logo,
		).get("url", "")

	if not logo_url and restaurant_doc.logo:
		logo_url = get_url(restaurant_doc.logo) if restaurant_doc.logo.startswith("/") else restaurant_doc.logo

	# For SILVER users, ALWAYS use Flamezo logo (override any custom logo)
	if restaurant_doc.plan_type == 'SILVER':
		logo_url = "/files/flamezo_backend-logoddffe5.svg"
		if not frappe.db.exists("File", {"file_url": logo_url}):
			logo_url = "/flamezo_backend/images/flamezo_backend-logo.svg"

	# ─────────────────────────────────────────────────────────────────
	# LEGACY BACKGROUND LOGIC REMOVED
	# We no longer fallback to gallery images or home features.
	# QR background is now explicitly provided or white.
	# ─────────────────────────────────────────────────────────────────

	return {
		"restaurant_name": restaurant_doc.restaurant_name or restaurant_doc.name,
		"primary_color": normalize_qr_color(primary_color),
		"logo_url": logo_url,
		"background_image_url": background_image_url,
	}


def build_table_qr_url(restaurant_doc, table_number):
	from flamezo_backend.flamezo.utils.config_helpers import get_app_base_url
	base_url = get_app_base_url()
	return f"{base_url.rstrip('/')}/{restaurant_doc.restaurant_id}?table_no={table_number}"


def build_table_qr_cache_key(restaurant_doc, table_number, qr_url, branding, force=False):
	import time
	
	payload = "|".join(
		[
			"v8",
			str(restaurant_doc.restaurant_id or ""),
			str(table_number),
			str(qr_url or ""),
			str(branding.get("restaurant_name") or ""),
			str(branding.get("primary_color") or ""),
			str(branding.get("logo_url") or ""),
			str(branding.get("background_image_url") or ""),
		]
	)
	
	# Add timestamp when forcing regeneration to ensure unique cache key
	if force:
		payload += f"|{int(time.time())}"
	
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_table_qr_object_keys(restaurant_doc, table_number, cache_key):
	restaurant_key = safe_restaurant_path(restaurant_doc.restaurant_id or restaurant_doc.name)
	base_path = f"restaurants/{restaurant_key}/restaurant/{restaurant_key}/table_qr/{table_number}/{cache_key}"
	return {
		"svg": f"{base_path}/card.svg",
		"png": f"{base_path}/card.png",
	}


def read_logo_bytes(logo_url):
	if not logo_url:
		return None

	try:
		from PIL import Image
		
		# Handle local file paths
		if logo_url.startswith("/"):
			if os.path.exists(logo_url):
				if logo_url.endswith('.svg'):
					return convert_svg_to_png(logo_url)
				else:
					with Image.open(logo_url) as img:
						img = img.convert("RGBA")
						img.thumbnail((320, 320), Image.Resampling.LANCZOS)
						buffer = BytesIO()
						img.save(buffer, format="PNG")
						return buffer.getvalue()
			else:
				logo_url = get_url(logo_url)

		# Use unified media fetcher (handles CDN/R2 and HTTP with User-Agent)
		content = resolve_and_fetch_media(logo_url)
		
		if logo_url.endswith('.svg') or b'<svg' in content[:100]:
			with tempfile.NamedTemporaryFile(delete=False, suffix='.svg') as temp_file:
				temp_file.write(content)
				temp_path = temp_file.name
			try:
				return convert_svg_to_png(temp_path)
			finally:
				if os.path.exists(temp_path):
					os.remove(temp_path)
		else:
			with Image.open(BytesIO(content)) as img:
				img = img.convert("RGBA")
				img.thumbnail((320, 320), Image.Resampling.LANCZOS)
				buffer = BytesIO()
				img.save(buffer, format="PNG")
				return buffer.getvalue()
	except Exception as e:
		safe_log_error("QR Logo Error", f"Error reading logo {logo_url}: {e}")
		return None


def convert_svg_to_png(svg_path):
	"""Convert SVG to PNG using cairosvg or fallback method"""
	try:
		import cairosvg
		png_bytes = cairosvg.svg2png(url=svg_path, output_width=320, output_height=320)
		return png_bytes
	except ImportError:
		# cairosvg not installed — warn admin and create placeholder
		frappe.log_error(
			"cairosvg is not installed. SVG logos cannot be converted. Run: pip install cairosvg",
			"QR SVG Conversion Missing Dependency"
		)
		from PIL import Image, ImageDraw, ImageFont
		img = Image.new('RGBA', (320, 320), (255, 87, 34, 255))
		draw = ImageDraw.Draw(img)
		try:
			font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
		except Exception:
			font = ImageFont.load_default()
		draw.text((80, 100), "D", fill=(255, 255, 255, 255), font=font)
		buffer = BytesIO()
		img.save(buffer, format="PNG")
		return buffer.getvalue()
	except Exception as e:
		frappe.log_error(f"Error converting SVG to PNG: {e}", "QR SVG Conversion Error")
		from PIL import Image, ImageDraw
		img = Image.new('RGBA', (320, 320), (255, 87, 34, 255))
		buffer = BytesIO()
		img.save(buffer, format="PNG")
		return buffer.getvalue()


def read_background_image_bytes(image_url, size=(940, 980)):
	if not image_url:
		return None

	try:
		from PIL import Image, ImageEnhance, ImageOps
		
		# Handle local file paths first
		if image_url.startswith("/"):
			if os.path.exists(image_url):
				with Image.open(image_url) as img:
					img = ImageOps.exif_transpose(img)
					img = img.convert("RGB")
					img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
					img = ImageEnhance.Brightness(img).enhance(0.75)
					buffer = BytesIO()
					img.save(buffer, format="JPEG", quality=75, optimize=True)
					return buffer.getvalue()
			else:
				image_url = get_url(image_url)

		# Use unified media fetcher
		content = resolve_and_fetch_media(image_url)
		with Image.open(BytesIO(content)) as img:
			img = ImageOps.exif_transpose(img)
			img = img.convert("RGB")
			img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
			img = ImageEnhance.Brightness(img).enhance(0.75)
			buffer = BytesIO()
			img.save(buffer, format="JPEG", quality=75, optimize=True)
			return buffer.getvalue()
	except Exception as e:
		safe_log_error("QR Background Error", f"Error reading background image {image_url}: {e}")
		return None


def extract_svg_payload(svg_markup):
	root = ET.fromstring(svg_markup)
	view_box = root.attrib.get("viewBox")
	if not view_box:
		width = root.attrib.get("width", "100")
		height = root.attrib.get("height", "100")
		width_num = re.sub(r"[^0-9.]", "", str(width)) or "100"
		height_num = re.sub(r"[^0-9.]", "", str(height)) or "100"
		view_box = f"0 0 {width_num} {height_num}"
	inner_markup = "".join(ET.tostring(child, encoding="unicode") for child in list(root))
	return view_box, inner_markup


def load_font(size, bold=False):
	from PIL import ImageFont

	font_candidates = [
		"/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
		"/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
		"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
		"/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
	]
	for font_path in font_candidates:
		if os.path.exists(font_path):
			return ImageFont.truetype(font_path, size)
	return ImageFont.load_default()


def measure_text(draw, text, font):
	bbox = draw.textbbox((0, 0), text, font=font)
	return bbox[2] - bbox[0], bbox[3] - bbox[1]


def generate_svg_card(qr_data, restaurant_name, brand_color, table_number, logo_bytes, background_image_bytes):
	import qrcode
	from qrcode.image.svg import SvgPathImage

	qr = qrcode.QRCode(
		version=None,
		error_correction=qrcode.constants.ERROR_CORRECT_H,
		box_size=16,
		border=4,
		image_factory=SvgPathImage,
	)
	qr.add_data(qr_data)
	qr.make(fit=True)
	buffer = BytesIO()
	qr.make_image(fill_color=brand_color, back_color="white").save(buffer)
	qr_markup = buffer.getvalue().decode("utf-8")
	view_box, inner_markup = extract_svg_payload(qr_markup)

	logo_overlay_markup = ""
	background_markup = ""
	if background_image_bytes:
		background_b64 = base64.b64encode(background_image_bytes).decode("ascii")
		background_markup = (
			'<defs><clipPath id="scanner-panel-clip"><rect x="130" y="360" width="940" height="980" rx="48" ry="48"/></clipPath></defs>'
			f'<image x="130" y="360" width="940" height="980" href="data:image/png;base64,{background_b64}" preserveAspectRatio="xMidYMid slice" clip-path="url(#scanner-panel-clip)"/>'
			'<rect x="130" y="360" width="940" height="980" rx="48" fill="#000000" opacity="0.08"/>'
		)
	if logo_bytes and not background_image_bytes:
		logo_b64 = base64.b64encode(logo_bytes).decode("ascii")
		logo_overlay_markup = (
			'<rect x="510" y="750" width="180" height="180" rx="42" fill="white" stroke="#E7E7E7" stroke-width="8"/>'
			f'<image x="535" y="775" width="130" height="130" href="data:image/png;base64,{logo_b64}" preserveAspectRatio="xMidYMid meet"/>'
		)
	cutout_markup = '<rect x="300" y="530" width="600" height="600" rx="46" fill="white" fill-opacity="0.96" stroke="#F0E8F3" stroke-width="4"/>'
	qr_group = (
		f'<svg x="340" y="570" width="520" height="520" viewBox="{html.escape(view_box)}">'
		f"{inner_markup}</svg>"
	)
	footer = "Powered by Flamezo"
	cutout_markup = '<rect x="300" y="530" width="600" height="600" rx="46" fill="white" fill-opacity="0.98" stroke="#F0E8F3" stroke-width="4"/>'
	
	banner_markup = ""
	if background_image_bytes:
		# Lighter overlay for better readability over images
		banner_markup = '<rect x="52" y="1320" width="1096" height="228" rx="0" fill="white" fill-opacity="0.85"/>'

	return (
		'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">'
		'<rect width="1200" height="1600" rx="72" fill="#FFFFFF"/>'
		f'<rect x="52" y="52" width="1096" height="1496" rx="56" fill="#FFFFFF" stroke="{brand_color}" stroke-width="18"/>'
		f'{background_markup}'
		f'<text x="600" y="210" text-anchor="middle" font-family="Baskerville, Georgia, Times New Roman, serif" font-size="52" font-weight="700" fill="{brand_color}">Table {table_number}</text>'
		f'<rect x="130" y="360" width="940" height="980" rx="48" fill="none" stroke="{brand_color}" stroke-opacity="0.28" stroke-width="3"/>'
		f'{banner_markup}{cutout_markup}{qr_group}{logo_overlay_markup}'
		f'<text x="600" y="1385" text-anchor="middle" font-family="Baskerville, Georgia, Times New Roman, serif" font-size="48" font-weight="700" fill="#222222">Scan to order</text>'
		f'<text x="600" y="1465" text-anchor="middle" font-family="Baskerville, Georgia, Times New Roman, serif" font-size="34" font-weight="500" fill="#666666">{html.escape(footer)}</text>'
		'</svg>'
	).encode("utf-8")


def build_artistic_qr_image(qr_data, logo_bytes, background_image_bytes):
	import segno
	from PIL import Image

	if not logo_bytes:
		return None
		
	logo_stream = BytesIO(logo_bytes)
	target_stream = BytesIO()
	qr = segno.make(qr_data, error="h")
	
	qr.to_artistic(background=logo_stream, target=target_stream, scale=8, kind="png", border=0)
	
	target_stream.seek(0)
	qr_img = Image.open(target_stream).convert("RGB")
	
	final_img = Image.new("RGBA", qr_img.size, "white")
	final_img.paste(qr_img, (0, 0))

	return final_img


def generate_png_card(qr_data, restaurant_name, brand_color, table_number, logo_bytes, background_image_bytes):
	import qrcode
	from PIL import Image, ImageDraw, ImageOps

	def draw_text_with_shadow(draw_obj, position, text, font, fill, shadow_fill=(0, 0, 0, 170), shadow_offset=(3, 4)):
		x, y = position
		draw_obj.text((x + shadow_offset[0], y + shadow_offset[1]), text, fill=shadow_fill, font=font)
		draw_obj.text((x, y), text, fill=fill, font=font)

	canvas = Image.new("RGBA", (1200, 1600), "white")
	draw = ImageDraw.Draw(canvas)
	if background_image_bytes:
		with Image.open(BytesIO(background_image_bytes)) as bg_img:
			bg_img = ImageOps.exif_transpose(bg_img)
			bg_img = bg_img.convert("RGBA")
			bg_img = ImageOps.fit(bg_img, (1096, 1496), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
			canvas.paste(bg_img, (52, 52), bg_img)
	else:
		draw.rounded_rectangle((52, 52, 1148, 1548), radius=56, fill="white")

	title_font = load_font(64, bold=True)
	footer_font = load_font(60, bold=True)
	brand_font = load_font(44, bold=False)

	if background_image_bytes:
		# Subtle white overlay for text readability over images
		overlay = Image.new("RGBA", (1096, 250), (255, 255, 255, 210))
		canvas.paste(overlay, (52, 1298), overlay)
	
	# Draw table title
	title_text = f"Table {table_number}"
	title_w, _ = measure_text(draw, title_text, title_font)
	draw.text(((1200 - title_w) / 2, 110), title_text, fill=brand_color, font=title_font)

	# Generate QR code (always use the clean qrcode approach for consistent quality)
	qr = qrcode.QRCode(
		version=None,
		error_correction=qrcode.constants.ERROR_CORRECT_H,
		box_size=20,
		border=4,
	)
	qr.add_data(qr_data)
	qr.make(fit=True)
	qr_img = qr.make_image(fill_color=brand_color, back_color="white").convert("RGBA")
	qr_img = qr_img.resize((520, 520), Image.Resampling.NEAREST)

	# Paste QR on canvas
	canvas.paste(qr_img, (340, 570), qr_img if qr_img.mode == 'RGBA' else None)

	if logo_bytes:
		with Image.open(BytesIO(logo_bytes)) as logo_img:
			logo_img = logo_img.convert("RGBA")
			logo_img.thumbnail((130, 130), Image.Resampling.LANCZOS)
			logo_card = Image.new("RGBA", (180, 180), (255, 255, 255, 0))
			logo_draw = ImageDraw.Draw(logo_card)
			logo_draw.rounded_rectangle((4, 4, 176, 176), radius=42, fill="white", outline="#E7E7E7", width=8)
			logo_x = (180 - logo_img.width) // 2
			logo_y = (180 - logo_img.height) // 2
			logo_card.paste(logo_img, (logo_x, logo_y), logo_img)
			canvas.paste(logo_card, (510, 750), logo_card)

	scan_text = "Scan to order"
	scan_width, _ = measure_text(draw, scan_text, footer_font)
	draw.text(((1200 - scan_width) / 2, 1340), scan_text, fill="#222222", font=footer_font)

	brand_text = "Powered by Flamezo"
	brand_width, _ = measure_text(draw, brand_text, brand_font)
	draw.text(((1200 - brand_width) / 2, 1435), brand_text, fill="#666666", font=brand_font)

	buffer = BytesIO()
	canvas.save(buffer, format="PNG", optimize=True)
	return buffer.getvalue()


def upload_content_bytes(content, suffix, object_key, content_type):
	from flamezo_backend.flamezo.media.storage import upload_object

	with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
		temp_file.write(content)
		temp_path = temp_file.name
	try:
		return upload_object(temp_path, object_key, content_type=content_type)
	finally:
		if os.path.exists(temp_path):
			os.remove(temp_path)


def ensure_table_qr_assets(restaurant_doc, table_number, force=False, branding=None, logo_bytes=None, background_image_bytes=None, override_background_url=None):
	from flamezo_backend.flamezo.media.storage import get_cdn_url, verify_object_exists

	# Use provided branding or fetch it (for backward compatibility)
	if branding is None:
		branding = resolve_qr_branding(restaurant_doc, override_background_url=override_background_url)
	
	background_image_url = branding.get("background_image_url") or override_background_url

	qr_url = build_table_qr_url(restaurant_doc, table_number)
	cache_key = build_table_qr_cache_key(restaurant_doc, table_number, qr_url, branding, force=force)
	object_keys = build_table_qr_object_keys(restaurant_doc, table_number, cache_key)

	# Always regenerate when force=True, regardless of whether files exist
	if not force:
		svg_exists = verify_object_exists(object_keys["svg"]).get("exists")
		png_exists = verify_object_exists(object_keys["png"]).get("exists")

		if svg_exists and png_exists:
			return {
				"table_number": table_number,
				"qr_data": qr_url,
				"cache_key": cache_key,
				"svg_url": get_cdn_url(object_keys["svg"]),
				"png_url": get_cdn_url(object_keys["png"]),
				"svg_object_key": object_keys["svg"],
				"png_object_key": object_keys["png"],
			}

	# Use provided images or download them (for backward compatibility)
	if logo_bytes is None:
		logo_bytes = read_logo_bytes(branding.get("logo_url"))
	if background_image_bytes is None:
		background_image_bytes = read_background_image_bytes(branding.get("background_image_url"))
	
	svg_bytes = generate_svg_card(
		qr_url,
		branding["restaurant_name"],
		branding["primary_color"],
		table_number,
		logo_bytes,
		background_image_bytes,
	)
	png_bytes = generate_png_card(
		qr_url,
		branding["restaurant_name"],
		branding["primary_color"],
		table_number,
		logo_bytes,
		background_image_bytes,
	)

	svg_url = upload_content_bytes(svg_bytes, ".svg", object_keys["svg"], "image/svg+xml")
	png_url = upload_content_bytes(png_bytes, ".png", object_keys["png"], "image/png")

	return {
		"table_number": table_number,
		"qr_data": qr_url,
		"cache_key": cache_key,
		"svg_url": svg_url,
		"png_url": png_url,
		"svg_object_key": object_keys["svg"],
		"png_object_key": object_keys["png"],
	}


def build_table_qr_assets(restaurant_doc, force=False, override_background_url=None):
	if not restaurant_doc.restaurant_id:
		frappe.throw("Restaurant ID is required to generate QR codes")
	if not restaurant_doc.tables or restaurant_doc.tables <= 0:
		frappe.throw("Number of tables must be greater than 0")

	# Download branding images once and reuse for all tables
	branding = resolve_qr_branding(restaurant_doc, override_background_url=override_background_url)
	logo_bytes = read_logo_bytes(branding.get("logo_url"))
	background_image_bytes = read_background_image_bytes(branding.get("background_image_url"))
	
	assets = []
	for i in range(1, restaurant_doc.tables + 1):
		asset = ensure_table_qr_assets(
			restaurant_doc, 
			i, 
			force=force, 
			branding=branding, 
			logo_bytes=logo_bytes, 
			background_image_bytes=background_image_bytes,
			override_background_url=override_background_url
		)
		assets.append(asset)
	return assets


# ─────────────────────────────────────────────────────────────────
# PDF Generation — Multi-layout support  (1-per-page or 2×2 grid)
# ─────────────────────────────────────────────────────────────────

def generate_pdf_from_assets(assets, layout="2x2"):
	"""
	Generate a PDF from QR assets.
	layout: '1x1' (one card per A4 page) or '2x2' (four cards per A4 page — industry standard)
	Returns: bytes of the PDF
	"""
	import os
	import tempfile
	from io import BytesIO
	from flamezo_backend.flamezo.media.storage import download_object
	from reportlab.lib.pagesizes import A4, landscape
	from reportlab.lib.units import inch
	from reportlab.pdfgen import canvas as rl_canvas
	from reportlab.lib.utils import ImageReader
	from PIL import Image

	pdf_buffer = BytesIO()

	if layout == "2x2":
		# Landscape A4 for 2×2 grid — 4 QR cards per page
		page_width, page_height = landscape(A4)
		
		# GEOMETRY FIX: Landscape A4 is 8.27 inches high. 
		# Two cards at 3.8" + margins will fit perfectly.
		card_width = 3.3 * inch
		card_height = 3.7 * inch
		
		pdf_canvas_obj = rl_canvas.Canvas(pdf_buffer, pagesize=landscape(A4))
		
		# Margins for perfect centering
		total_w = 2 * card_width
		total_h = 2 * card_height
		margin_x = (page_width - total_w) / 3
		margin_y = (page_height - total_h) / 3

		positions_per_page = [
			(margin_x, page_height - margin_y - card_height),
			(margin_x * 2 + card_width, page_height - margin_y - card_height),
			(margin_x, margin_y),
			(margin_x * 2 + card_width, margin_y),
		]

		for page_start in range(0, len(assets), 4):
			page_assets = assets[page_start:page_start + 4]

			for slot_idx, asset in enumerate(page_assets):
				x_pos, y_pos = positions_per_page[slot_idx]
				card_buffer = _download_asset_as_jpeg(asset, download_object, Image)
				if card_buffer:
					# Subtle light grey boundary cut-line for merchant convenience
					pdf_canvas_obj.setStrokeColorRGB(0.9, 0.9, 0.9)
					pdf_canvas_obj.setLineWidth(0.5)
					pdf_canvas_obj.rect(x_pos - 1, y_pos - 1, card_width + 2, card_height + 2, fill=0, stroke=1)
					
					pdf_canvas_obj.drawImage(ImageReader(card_buffer), x_pos, y_pos, width=card_width, height=card_height)

			# Footer positioned at very bottom
			pdf_canvas_obj.setFont("Helvetica", 7)
			pdf_canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
			pdf_canvas_obj.drawCentredString(page_width / 2, 0.2 * inch, "Generated by Flamezo • Print and trim along light lines")
			pdf_canvas_obj.showPage()

	else:
		# 1×1: One card centred per A4 page
		page_width, page_height = A4
		card_width = 4.4 * inch
		card_height = 5.85 * inch

		pdf_canvas_obj = rl_canvas.Canvas(pdf_buffer, pagesize=A4)

		for index, asset in enumerate(assets, start=1):
			card_buffer = _download_asset_as_jpeg(asset, download_object, Image)
			x = (page_width - card_width) / 2
			y = (page_height - card_height) / 2 + 0.1 * inch

			if card_buffer:
				pdf_canvas_obj.drawImage(ImageReader(card_buffer), x, y, width=card_width, height=card_height)

			pdf_canvas_obj.setFont("Helvetica", 9)
			pdf_canvas_obj.setFillColorRGB(0.4, 0.4, 0.4)
			pdf_canvas_obj.drawCentredString(page_width / 2, y - 0.18 * inch, asset["qr_data"])

			if index < len(assets):
				pdf_canvas_obj.showPage()

	pdf_canvas_obj.save()
	pdf_buffer.seek(0)
	return pdf_buffer.getvalue()


def _download_asset_as_jpeg(asset, download_object_fn, Image):
	"""Download a PNG asset from R2 and return as JPEG BytesIO. Returns None on failure (safe for multi-card pages)."""
	import tempfile
	temp_path = None
	try:
		with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
			temp_path = temp_file.name
		download_object_fn(asset["png_object_key"], temp_path)

		card_buffer = BytesIO()
		with Image.open(temp_path) as img:
			if img.mode in ('RGBA', 'LA', 'P'):
				rgb_img = Image.new('RGB', img.size, (255, 255, 255))
				if img.mode == 'P':
					img = img.convert('RGBA')
				rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
				img = rgb_img
			else:
				img = img.convert('RGB')

			img.save(card_buffer, format='JPEG', quality=88, optimize=True)
			card_buffer.seek(0)
		return card_buffer
	except Exception as e:
		frappe.log_error(
			f"Failed to render QR card for table {asset.get('table_number', '?')}: {e}",
			"QR PDF Card Render Error"
		)
		return None
	finally:
		if temp_path and os.path.exists(temp_path):
			os.remove(temp_path)


# ─────────────────────────────────────────────────────────────────
# Special QR Codes — Takeaway & Delivery
# Each encodes: {base_url}/{restaurant_id}?order_type=takeaway|delivery
# Branding, caching, and storage are identical to table QR cards.
# ─────────────────────────────────────────────────────────────────

SPECIAL_QR_CONFIGS = {
	"takeaway": {
		"label": "Takeaway",
		"subtitle": "Scan to place a takeaway order",
		"footer": "Order Takeaway • Powered by Flamezo",
	},
	"delivery": {
		"label": "Delivery",
		"subtitle": "Scan to order doorstep delivery",
		"footer": "Order Delivery • Powered by Flamezo",
	},
}


def build_special_qr_url(restaurant_doc, order_type):
	from flamezo_backend.flamezo.utils.config_helpers import get_app_base_url
	base_url = get_app_base_url()
	return f"{base_url.rstrip('/')}/{restaurant_doc.restaurant_id}?order_type={order_type}"


def build_special_qr_object_keys(restaurant_doc, order_type, cache_key):
	restaurant_key = safe_restaurant_path(restaurant_doc.restaurant_id or restaurant_doc.name)
	base_path = f"restaurants/{restaurant_key}/restaurant/{restaurant_key}/special_qr/{order_type}/{cache_key}"
	return {
		"svg": f"{base_path}/card.svg",
		"png": f"{base_path}/card.png",
	}


def generate_special_svg_card(qr_data, restaurant_name, brand_color, order_type, logo_bytes, background_image_bytes):
	import qrcode
	from qrcode.image.svg import SvgPathImage

	cfg = SPECIAL_QR_CONFIGS.get(order_type, SPECIAL_QR_CONFIGS["takeaway"])

	qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=16, border=4, image_factory=SvgPathImage)
	qr.add_data(qr_data)
	qr.make(fit=True)
	buf = BytesIO()
	qr.make_image(fill_color=brand_color, back_color="white").save(buf)
	view_box, inner_markup = extract_svg_payload(buf.getvalue().decode("utf-8"))

	bg_markup = ""
	logo_markup = ""
	if background_image_bytes:
		b64 = base64.b64encode(background_image_bytes).decode("ascii")
		bg_markup = (
			'<defs><clipPath id="sp-clip"><rect x="130" y="360" width="940" height="980" rx="48" ry="48"/></clipPath></defs>'
			f'<image x="130" y="360" width="940" height="980" href="data:image/png;base64,{b64}" preserveAspectRatio="xMidYMid slice" clip-path="url(#sp-clip)"/>'
			'<rect x="130" y="360" width="940" height="980" rx="48" fill="#000000" opacity="0.08"/>'
		)
	if logo_bytes and not background_image_bytes:
		lb64 = base64.b64encode(logo_bytes).decode("ascii")
		logo_markup = (
			'<rect x="510" y="750" width="180" height="180" rx="42" fill="white" stroke="#E7E7E7" stroke-width="8"/>'
			f'<image x="535" y="775" width="130" height="130" href="data:image/png;base64,{lb64}" preserveAspectRatio="xMidYMid meet"/>'
		)
	cutout = '<rect x="300" y="530" width="600" height="600" rx="46" fill="white" fill-opacity="0.96" stroke="#F0E8F3" stroke-width="4"/>'
	qr_svg = f'<svg x="340" y="570" width="520" height="520" viewBox="{html.escape(view_box)}">{inner_markup}</svg>'
	return (
		'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">'
		'<rect width="1200" height="1600" rx="72" fill="#FFFFFF"/>'
		f'<rect x="52" y="52" width="1096" height="1496" rx="56" fill="#FFFFFF" stroke="{brand_color}" stroke-width="18"/>'
		f'<text x="600" y="175" text-anchor="middle" font-family="Baskerville,Georgia,serif" font-size="50" font-weight="700" fill="{brand_color}">{html.escape(restaurant_name)}</text>'
		f'<text x="600" y="255" text-anchor="middle" font-family="Baskerville,Georgia,serif" font-size="58" font-weight="700" fill="#222222">{cfg["label"]} QR</text>'
		f'{bg_markup}'
		f'<rect x="130" y="360" width="940" height="980" rx="48" fill="none" stroke="{brand_color}" stroke-opacity="0.28" stroke-width="3"/>'
		f'{cutout}{qr_svg}{logo_markup}'
		f'<text x="600" y="1365" text-anchor="middle" font-family="Baskerville,Georgia,serif" font-size="42" font-weight="600" fill="#555555">{cfg["subtitle"]}</text>'
		f'<text x="600" y="1450" text-anchor="middle" font-family="Baskerville,Georgia,serif" font-size="36" fill="#666666">{html.escape(cfg["footer"])}</text>'
		'</svg>'
	).encode("utf-8")


def generate_special_png_card(qr_data, restaurant_name, brand_color, order_type, logo_bytes, background_image_bytes):
	import qrcode
	from PIL import Image, ImageDraw, ImageOps

	cfg = SPECIAL_QR_CONFIGS.get(order_type, SPECIAL_QR_CONFIGS["takeaway"])

	def draw_shadow(draw_obj, pos, text, font, fill, shadow=(0, 0, 0, 170), offset=(3, 4)):
		x, y = pos
		draw_obj.text((x + offset[0], y + offset[1]), text, fill=shadow, font=font)
		draw_obj.text((x, y), text, fill=fill, font=font)

	canvas = Image.new("RGBA", (1200, 1600), "white")
	draw = ImageDraw.Draw(canvas)

	if background_image_bytes:
		with Image.open(BytesIO(background_image_bytes)) as bg:
			bg = bg.convert("RGBA")
			bg = ImageOps.fit(bg, (1096, 1496), method=Image.Resampling.LANCZOS, centering=(0.5, 0.78))
			canvas.paste(bg, (52, 52), bg)
	else:
		draw.rounded_rectangle((52, 52, 1148, 1548), radius=56, fill="white")

	title_font = load_font(48, bold=True)
	label_font = load_font(64, bold=True)
	sub_font = load_font(40, bold=True)
	footer_font = load_font(38, bold=False)

	if background_image_bytes:
		# Light overlay for readability
		overlay = Image.new("RGBA", (1096, 280), (255, 255, 255, 210))
		canvas.paste(overlay, (52, 1278), overlay)

	name_w, _ = measure_text(draw, restaurant_name, title_font)
	draw.text(((1200 - name_w) / 2, 105), restaurant_name, fill=brand_color, font=title_font)

	label_text = f"{cfg['label']} QR"
	label_w, _ = measure_text(draw, label_text, label_font)
	draw.text(((1200 - label_w) / 2, 185), label_text, fill="#222222", font=label_font)

	# QR code
	qr_img = None
	if logo_bytes and background_image_bytes:
		try:
			qr_img = build_artistic_qr_image(qr_data, logo_bytes, background_image_bytes)
			qr_img = qr_img.resize((520, 520), Image.Resampling.LANCZOS)
		except Exception:
			qr_img = None

	if qr_img is None:
		qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=4)
		qr.add_data(qr_data)
		qr.make(fit=True)
		qr_img = qr.make_image(fill_color=brand_color, back_color="white").convert("RGBA")
		qr_img = qr_img.resize((520, 520), Image.Resampling.NEAREST)

	canvas.paste(qr_img, (340, 540), qr_img if qr_img.mode == 'RGBA' else None)

	if logo_bytes and not background_image_bytes:
		with Image.open(BytesIO(logo_bytes)) as logo_img:
			logo_img = logo_img.convert("RGBA")
			logo_img.thumbnail((130, 130), Image.Resampling.LANCZOS)
			logo_card = Image.new("RGBA", (180, 180), (255, 255, 255, 0))
			logo_draw = ImageDraw.Draw(logo_card)
			logo_draw.rounded_rectangle((4, 4, 176, 176), radius=42, fill="white", outline="#E7E7E7", width=8)
			lx, ly = (180 - logo_img.width) // 2, (180 - logo_img.height) // 2
			logo_card.paste(logo_img, (lx, ly), logo_img)
			canvas.paste(logo_card, (510, 710), logo_card)

	sub_w, _ = measure_text(draw, cfg["subtitle"], sub_font)
	draw.text(((1200 - sub_w) / 2, 1315), cfg["subtitle"], fill="#222222", font=sub_font)

	footer_w, _ = measure_text(draw, cfg["footer"], footer_font)
	draw.text(((1200 - footer_w) / 2, 1405), cfg["footer"], fill="#666666", font=footer_font)

	buf = BytesIO()
	canvas.save(buf, format="PNG", optimize=True)
	return buf.getvalue()


def ensure_special_qr_asset(restaurant_doc, order_type, force=False):
	"""
	Generate and cache a PNG + SVG QR card for a special order type (takeaway / delivery).
	Returns asset dict with png_url, svg_url, qr_data, object keys.
	"""
	from flamezo_backend.flamezo.media.storage import get_cdn_url, verify_object_exists

	if order_type not in SPECIAL_QR_CONFIGS:
		frappe.throw(f"Invalid order_type '{order_type}'. Allowed: {list(SPECIAL_QR_CONFIGS.keys())}")

	branding = resolve_qr_branding(restaurant_doc)
	qr_url = build_special_qr_url(restaurant_doc, order_type)

	payload = "|".join([
		"special-v1",
		str(restaurant_doc.restaurant_id or ""),
		order_type,
		qr_url,
		str(branding.get("restaurant_name") or ""),
		str(branding.get("primary_color") or ""),
		str(branding.get("logo_url") or ""),
		str(branding.get("background_image_url") or ""),
	])
	cache_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
	object_keys = build_special_qr_object_keys(restaurant_doc, order_type, cache_key)

	if not force:
		if (verify_object_exists(object_keys["svg"]).get("exists") and
				verify_object_exists(object_keys["png"]).get("exists")):
			return {
				"order_type": order_type,
				"label": SPECIAL_QR_CONFIGS[order_type]["label"],
				"qr_data": qr_url,
				"cache_key": cache_key,
				"svg_url": get_cdn_url(object_keys["svg"]),
				"png_url": get_cdn_url(object_keys["png"]),
				"svg_object_key": object_keys["svg"],
				"png_object_key": object_keys["png"],
			}

	logo_bytes = read_logo_bytes(branding.get("logo_url"))
	bg_bytes = read_background_image_bytes(branding.get("background_image_url"))

	svg_bytes = generate_special_svg_card(qr_url, branding["restaurant_name"], branding["primary_color"], order_type, logo_bytes, bg_bytes)
	png_bytes = generate_special_png_card(qr_url, branding["restaurant_name"], branding["primary_color"], order_type, logo_bytes, bg_bytes)

	svg_url = upload_content_bytes(svg_bytes, ".svg", object_keys["svg"], "image/svg+xml")
	png_url = upload_content_bytes(png_bytes, ".png", object_keys["png"], "image/png")

	return {
		"order_type": order_type,
		"label": SPECIAL_QR_CONFIGS[order_type]["label"],
		"qr_data": qr_url,
		"cache_key": cache_key,
		"svg_url": svg_url,
		"png_url": png_url,
		"svg_object_key": object_keys["svg"],
		"png_object_key": object_keys["png"],
	}

def build_special_qr_assets(restaurant_doc, force=False):
	"""
	Aggregation helper to build all special QRs (takeaway, delivery) for a restaurant.
	"""
	if not restaurant_doc.restaurant_id:
		frappe.throw("Restaurant ID is required to generate QR codes")
	
	assets = []
	for st in ["takeaway", "delivery"]:
		asset = ensure_special_qr_asset(restaurant_doc, st, force=force)
		assets.append(asset)
	return assets
