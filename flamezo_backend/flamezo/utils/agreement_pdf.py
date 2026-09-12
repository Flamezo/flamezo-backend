"""
Renders an Agreement Template's Markdown source (with {{merge_field}}
placeholders in Schedule A/B) into a per-party PDF.

Pipeline: Markdown -> styled HTML -> wkhtmltopdf (via frappe.utils.pdf,
already a core Frappe dependency on every bench, no extra install needed
in production). This mirrors the same CSS used to hand-build
FlameZO_Merchant_Agreement_v2.2.pdf for the Leegality Workflow upload, so
what gets sent for signing looks identical to what was reviewed/approved.
"""

import base64
import html
import os
import re

import markdown as markdown_lib

_MERGE_FIELD_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "agreement_stamps")

# Confirmed live: the CSS previously named "Georgia"/"Times New Roman" as the
# font, which wkhtmltopdf silently substitutes with whatever serif font
# happens to be installed on the machine actually running the render — a Mac
# has Georgia, a bare Linux server typically doesn't, and got DejaVu Serif
# instead. Different fonts have different character widths, which reflows
# the whole document to a DIFFERENT PAGE COUNT — and since Leegality's
# Aadhaar-signature field position is calibrated in absolute (page, x, y)
# coordinates against one specific rendered PDF, a repaginated document sent
# via a later API call puts the signer's field on the wrong page entirely,
# silently failing to render the visible signature mark even though the
# Aadhaar OTP itself completes successfully. Embedding the font file via
# @font-face was tried and rejected — wkhtmltopdf's WebKit engine parses it
# without error but then renders every glyph blank. The fix instead: name
# "DejaVu Serif" explicitly (see _CSS below) and make sure it's actually
# installed identically everywhere this pipeline runs (`brew install --cask
# font-dejavu` on macOS dev machines; already present by default on the
# Linux bench servers — confirmed via fc-list).

# Onomatrix Labs' own side of the SIGNATURES block never changes per party —
# it's baked into every document as real images, not a Leegality
# organisational-countersign step (that's a separate paid "Doc Signer"
# feature requiring Leegality-side setup; this is simpler, free, and
# equivalent to a company pre-stamping a paper contract before sending it
# out for the other party's counter-signature).
_STATIC_STAMPS = {
	"onomatrix_director_signature": "onomatrix_director_signature.png",
	"onomatrix_company_seal": "onomatrix_company_seal.png",
}


def _stamp_data_uri(filename: str) -> str:
	path = os.path.join(_ASSETS_DIR, filename)
	with open(path, "rb") as f:
		encoded = base64.b64encode(f.read()).decode("ascii")
	return f"data:image/png;base64,{encoded}"


def embed_static_stamps(markdown_text: str) -> str:
	"""Replaces {{onomatrix_director_signature}} / {{onomatrix_company_seal}}
	with real Markdown image syntax pointing at embedded base64 data —
	fully self-contained, no filesystem-path dependency at render time. Must
	run BEFORE merge_fields(), since those treats any unknown {{token}} as
	an unresolved per-party field and blanks it."""
	# Cropped-content heights differ (signature is a wide short strip,
	# seal is roughly square) — sized independently so both read clearly
	# at real-document scale rather than one arbitrary height for both.
	heights = {"onomatrix_director_signature": "50px", "onomatrix_company_seal": "85px"}
	for token, filename in _STATIC_STAMPS.items():
		placeholder = "{{" + token + "}}"
		if placeholder in markdown_text:
			uri = _stamp_data_uri(filename)
			markdown_text = markdown_text.replace(
				placeholder,
				f'<img src="{uri}" style="height:{heights[token]}; vertical-align:middle;">',
			)
	return markdown_text

# Embedding the font via @font-face (base64 data: URI) was tried first and
# rejected: wkhtmltopdf's WebKit engine loads it without a parse error once
# the format() hint is dropped, but then silently renders every glyph blank
# (confirmed directly — headings/rules show, all text is invisible). Naming
# a real, identically-installed system font is the reliable path instead —
# "DejaVu Serif" is installed via `brew install --cask font-dejavu` on this
# Mac and already present by default on the Linux bench servers (confirmed
# via fc-list on dev.flamezo.in). Both environments now resolve the same
# font file family, so pagination is consistent without relying on a
# fragile embedding path.
_CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: "DejaVu Serif", serif;
  font-size: 10.5pt;
  line-height: 1.5;
  color: #1a1a1a;
  max-width: 100%;
}
h1 {
  font-size: 20pt;
  text-align: center;
  letter-spacing: 2px;
  margin: 0 0 2pt 0;
  font-weight: 700;
}
h2 {
  font-size: 13pt;
  font-weight: 700;
  margin: 22pt 0 8pt 0;
  padding-bottom: 3pt;
  border-bottom: 1.5px solid #1a1a1a;
  page-break-after: avoid;
}
h1 + h2 {
  text-align: center;
  border-bottom: none;
  font-size: 14pt;
  margin-top: 4pt;
  letter-spacing: 1px;
}
h3 {
  font-size: 11pt;
  font-weight: 700;
  margin: 14pt 0 6pt 0;
  page-break-after: avoid;
}
p { margin: 0 0 9pt 0; text-align: justify; orphans: 3; widows: 3; }
strong { font-weight: 700; }
hr { border: none; border-top: 1px solid #999; margin: 16pt 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 10pt 0 14pt 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #888;
  padding: 5pt 7pt;
  text-align: left;
  vertical-align: top;
}
th { background: #eeeeee; font-weight: 700; }
ul, ol { margin: 0 0 9pt 22pt; padding: 0; }
li { margin-bottom: 4pt; }
"""


def merge_fields(markdown_text: str, values: dict) -> tuple[str, list[str]]:
	"""Replaces every {{field}} placeholder with values[field], HTML-escaped
	since the result still goes through Markdown->HTML. Returns
	(merged_text, unresolved_field_names) — unresolved fields are left as
	literal blanks rather than raising, since a party missing e.g. GST
	number (unregistered dealer) is a real, valid case, not a bug — but the
	caller should log/flag unresolved fields so gaps are visible."""
	unresolved = []

	def _sub(m: re.Match) -> str:
		field = m.group(1)
		if field not in values or values[field] in (None, ""):
			unresolved.append(field)
			return ""
		return html.escape(str(values[field]))

	merged = _MERGE_FIELD_RE.sub(_sub, markdown_text)
	return merged, unresolved


def render_markdown_to_pdf(markdown_text: str) -> bytes:
	from frappe.utils.pdf import get_pdf

	body_html = markdown_lib.markdown(markdown_text, extensions=["extra", "sane_lists"])
	full_html = f"<html><head><style>{_CSS}</style></head><body>{body_html}</body></html>"
	return get_pdf(full_html)
