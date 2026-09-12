"""
IFSC -> bank name/branch lookup via Razorpay's free public IFSC API
(https://ifsc.razorpay.com/{code}) — no auth, no rate-limit key needed,
confirmed against their own real response shape. Used so Schedule A's
"Bank Name & Branch" row can auto-fill from the IFSC code the merchant
already provides during Route KYC, without asking for a second input.
"""

import requests

_TIMEOUT_SECONDS = 5


def lookup_ifsc(ifsc_code: str) -> dict | None:
	"""Returns {"bank": ..., "branch": ..., "city": ...} or None if the
	code is invalid/unrecognized or the lookup fails for any reason —
	callers must treat None as "leave the field blank", never raise."""
	if not ifsc_code or len(ifsc_code.strip()) != 11:
		return None
	code = ifsc_code.strip().upper()
	try:
		resp = requests.get(f"https://ifsc.razorpay.com/{code}", timeout=_TIMEOUT_SECONDS)
	except requests.RequestException:
		return None
	if resp.status_code != 200:
		return None
	try:
		data = resp.json()
	except ValueError:
		return None
	bank = data.get("BANK")
	branch = data.get("BRANCH")
	if not bank:
		return None
	return {"bank": bank, "branch": branch, "city": data.get("CITY")}


def format_bank_name_branch(ifsc_code: str) -> str | None:
	"""Convenience wrapper returning a single display string, e.g.
	"Axis Bank - Adajan, Surat", or None if lookup didn't resolve."""
	result = lookup_ifsc(ifsc_code)
	if not result:
		return None
	parts = [result["bank"]]
	if result.get("branch"):
		parts.append(result["branch"].title())
	label = " - ".join(parts)
	if result.get("city"):
		label += f", {result['city'].title()}"
	return label
