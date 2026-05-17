"""
Order Management Routes

Maps to: flamezo_backend.flamezo.api.order_status.*

STRICT RULES:
- Accept EXACT same parameters as ERPNext
- Return EXACT same responses as ERPNext
- NO transformation
- NO business logic
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
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
class UpdateStatusRequest(BaseModel):
	"""Request for update_status"""
	order_id: str
	status: str


class UpdateTableNumberRequest(BaseModel):
	"""Request for update_table_number"""
	order_id: str
	table_number: Optional[int] = None


# Route Implementations

@router.post("/flamezo_backend.flamezo.api.order_status.update_status")
async def update_status(
	request: UpdateStatusRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Update order status
	
	Mirrors: flamezo_backend.flamezo.api.order_status.update_status
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.order_status.update_status",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in update_status: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.order_status.update_table_number")
async def update_table_number(
	request: UpdateTableNumberRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Update order table number
	
	Mirrors: flamezo_backend.flamezo.api.order_status.update_table_number
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.order_status.update_table_number",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in update_table_number: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
