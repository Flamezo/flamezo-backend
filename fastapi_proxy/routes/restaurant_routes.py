"""
Restaurant Routes

Maps to: flamezo_backend.flamezo.doctype.restaurant.restaurant.*

STRICT RULES:
- Accept EXACT same parameters as ERPNext
- Return EXACT same responses as ERPNext
- NO transformation
- NO business logic
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import logging
import sys
import os

# Handle imports - work as both module and script
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
	sys.path.insert(0, _parent_dir)

from clients.erpnext_client import get_erpnext_client
from utils.auth import get_current_user, TokenData
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# Request Models (match ERPNext parameters exactly)
class GenerateQRCodesPdfRequest(BaseModel):
	"""Request for generate_qr_codes_pdf"""
	restaurant: str


class GetQRCodesPdfUrlRequest(BaseModel):
	"""Request for get_qr_codes_pdf_url"""
	restaurant: str


class GetTableQrAssetsRequest(BaseModel):
	"""Request for get_table_qr_assets"""
	restaurant: str
	force: int = 0


# Route Implementations

@router.post("/flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf")
async def generate_qr_codes_pdf(
	request: GenerateQRCodesPdfRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Generate QR codes PDF for restaurant tables
	
	Mirrors: flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in generate_qr_codes_pdf: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.doctype.restaurant.restaurant.get_table_qr_assets")
async def get_table_qr_assets(
	request: GetTableQrAssetsRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get branded SVG and PNG QR assets for restaurant tables
	
	Mirrors: flamezo_backend.flamezo.doctype.restaurant.restaurant.get_table_qr_assets
	Type: READ
	Cache: Yes (60s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.doctype.restaurant.restaurant.get_table_qr_assets",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_table_qr_assets: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url")
async def get_qr_codes_pdf_url(
	request: GetQRCodesPdfUrlRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get QR codes PDF URL for restaurant
	
	Mirrors: flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url
	Type: READ
	Cache: Yes (60s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_qr_codes_pdf_url: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
