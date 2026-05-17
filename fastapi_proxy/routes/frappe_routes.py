"""
Frappe Client Routes

Maps to: frappe.client.*
These routes map to wrapper methods in flamezo_backend.flamezo.api.documents

STRICT RULES:
- Accept EXACT same parameters as ERPNext
- Return EXACT same responses as ERPNext
- NO transformation
- NO business logic
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
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


# Request Models (match frappe.client parameters exactly)
class FrappeClientGetListRequest(BaseModel):
	"""Request for frappe.client.get_list"""
	doctype: str
	filters: Optional[Dict[str, Any]] = None
	fields: Optional[List[str]] = None
	limit_start: Optional[int] = 0
	limit_page_length: Optional[int] = 20
	order_by: Optional[str] = None


class FrappeClientGetRequest(BaseModel):
	"""Request for frappe.client.get"""
	doctype: str
	name: str
	fields: Optional[List[str]] = None


class FrappeClientInsertRequest(BaseModel):
	"""Request for frappe.client.insert"""
	doc: Dict[str, Any]


class FrappeClientDeleteRequest(BaseModel):
	"""Request for frappe.client.delete"""
	doctype: str
	name: str


# Route Implementations
# These map to wrapper methods in flamezo_backend.flamezo.api.documents

@router.post("/frappe.client.get_list")
async def frappe_client_get_list(
	request: FrappeClientGetListRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get list of documents (maps to flamezo_backend.flamezo.api.documents.get_doc_list)
	
	Mirrors: frappe.client.get_list → flamezo_backend.flamezo.api.documents.get_doc_list
	Type: READ
	Cache: Yes (depends on doctype - see caching rules)
	"""
	client = get_erpnext_client()
	
	try:
		# Map to wrapper method
		# Convert limit_start + limit_page_length to just limit_page_length
		data = request.dict(exclude_none=True)
		if 'limit_start' in data:
			# Wrapper uses limit_page_length only
			del data['limit_start']
		
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc_list",
			data=data,
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in frappe.client.get_list: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/frappe.client.get")
async def frappe_client_get(
	request: FrappeClientGetRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get a single document (maps to flamezo_backend.flamezo.api.documents.get_doc)
	
	Mirrors: frappe.client.get → flamezo_backend.flamezo.api.documents.get_doc
	Type: READ
	Cache: No (user-specific, real-time data)
	"""
	client = get_erpnext_client()
	
	try:
		# Map to wrapper method - fields parameter is ignored in wrapper
		data = {
			"doctype": request.doctype,
			"name": request.name
		}
		
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc",
			data=data,
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in frappe.client.get: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/frappe.client.insert")
async def frappe_client_insert(
	request: FrappeClientInsertRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Insert a document (maps to flamezo_backend.flamezo.api.documents.insert_doc)
	
	Mirrors: frappe.client.insert → flamezo_backend.flamezo.api.documents.insert_doc
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.insert_doc",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in frappe.client.insert: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/frappe.client.delete")
async def frappe_client_delete(
	request: FrappeClientDeleteRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Delete a document (maps to flamezo_backend.flamezo.api.documents.delete_doc)
	
	Mirrors: frappe.client.delete → flamezo_backend.flamezo.api.documents.delete_doc
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.delete_doc",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in frappe.client.delete: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
