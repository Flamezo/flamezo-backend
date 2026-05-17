"""
UI API Routes

Maps to: flamezo_backend.flamezo.api.ui.*

STRICT RULES:
- Accept EXACT same parameters as ERPNext
- Return EXACT same responses as ERPNext
- NO transformation
- NO business logic
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
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
class GetDoctypeMetaRequest(BaseModel):
	"""Request for get_doctype_meta"""
	doctype: str


class GetUserPermissionsRequest(BaseModel):
	"""Request for get_user_permissions"""
	doctype: str


class GetRestaurantSetupProgressRequest(BaseModel):
	"""Request for get_restaurant_setup_progress"""
	restaurant_id: str


# Route Implementations
# Note: ERPNext uses dot notation in method paths
# FastAPI doesn't match dots well, so we use a catch-all and dispatch by method name
# The router prefix is /api/method, so routes are relative to that

@router.post("/flamezo_backend.flamezo.api.ui.get_doctype_meta", include_in_schema=True)
async def get_doctype_meta(
	request: GetDoctypeMetaRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get DocType metadata
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_doctype_meta
	Type: READ
	Cache: Yes (60s)
	"""
	client = get_erpnext_client()
	
	try:
		# Forward request to ERPNext - unchanged
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_doctype_meta",
			data=request.dict(),
			http_method="POST"
		)
		
		# Return response - unchanged
		return response
		
	except Exception as e:
		logger.error(f"Error in get_doctype_meta: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.ui.get_user_permissions")
async def get_user_permissions(
	request: GetUserPermissionsRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get user permissions for a DocType
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_user_permissions
	Type: READ
	Cache: Yes (30s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_user_permissions",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_user_permissions: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.ui.get_all_doctypes")
async def get_all_doctypes(
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get list of all doctypes
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_all_doctypes
	Type: READ
	Cache: Yes (300s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_all_doctypes",
			data={},  # No parameters
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_all_doctypes: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.ui.get_user_restaurants")
async def get_user_restaurants(
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get restaurants for current user
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_user_restaurants
	Type: READ
	Cache: Yes (60s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_user_restaurants",
			data={},  # No parameters
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_user_restaurants: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.ui.get_restaurant_setup_progress")
async def get_restaurant_setup_progress(
	request: GetRestaurantSetupProgressRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get restaurant setup wizard progress
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_restaurant_setup_progress
	Type: READ
	Cache: No (real-time status)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_restaurant_setup_progress",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_restaurant_setup_progress: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.ui.get_setup_wizard_steps")
async def get_setup_wizard_steps(
	# Temporarily disable auth for testing - TODO: Re-enable after login endpoint is implemented
	# current_user: TokenData = Depends(get_current_user)
):
	"""
	Get setup wizard steps configuration
	
	Mirrors: flamezo_backend.flamezo.api.ui.get_setup_wizard_steps
	Type: READ
	Cache: Yes (300s)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.ui.get_setup_wizard_steps",
			data={},  # No parameters
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_setup_wizard_steps: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)

