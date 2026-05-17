"""
Resource API Routes

Maps to: /api/resource/*
These routes map to wrapper methods in flamezo_backend.flamezo.api.documents

STRICT RULES:
- Accept EXACT same parameters as ERPNext
- Return EXACT same responses as ERPNext
- NO transformation
- NO business logic
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
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


# Route Implementations
# Resource API uses path parameters and query strings

@router.get("/{doctype}")
async def resource_get_list(
	doctype: str,
	filters: Optional[str] = Query(None),
	fields: Optional[str] = Query(None),
	limit_page_length: Optional[int] = Query(20),
	order_by: Optional[str] = Query(None),
	current_user: TokenData = Depends(get_current_user)
):
	"""
	GET /api/resource/{doctype} - Get list of documents
	Maps to: flamezo_backend.flamezo.api.documents.get_doc_list
	
	Type: READ
	Cache: Yes (depends on doctype - see caching rules)
	"""
	client = get_erpnext_client()
	
	try:
		# Parse filters and fields from query strings (JSON strings)
		import json
		filters_dict = None
		fields_list = None
		
		if filters:
			try:
				filters_dict = json.loads(filters)
			except:
				pass
		
		if fields:
			try:
				fields_list = json.loads(fields) if isinstance(json.loads(fields), list) else [json.loads(fields)]
			except:
				pass
		
		data = {
			"doctype": doctype,
			"limit_page_length": limit_page_length
		}
		
		if filters_dict:
			data["filters"] = filters_dict
		if fields_list:
			data["fields"] = fields_list
		if order_by:
			data["order_by"] = order_by
		
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc_list",
			data=data,
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in GET /api/resource/{doctype}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.get("/{doctype}/{name}")
async def resource_get_doc(
	doctype: str,
	name: str,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	GET /api/resource/{doctype}/{name} - Get a single document
	Maps to: flamezo_backend.flamezo.api.documents.get_doc
	
	Type: READ
	Cache: No (user-specific, real-time data)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc",
			data={
				"doctype": doctype,
				"name": name
			},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in GET /api/resource/{doctype}/{name}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.put("/{doctype}/{name}")
async def resource_update_doc(
	doctype: str,
	name: str,
	doc_data: Dict[str, Any],
	current_user: TokenData = Depends(get_current_user)
):
	"""
	PUT /api/resource/{doctype}/{name} - Update a document
	Maps to: flamezo_backend.flamezo.api.documents.update_document
	
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.update_document",
			data={
				"doctype": doctype,
				"name": name,
				"doc_data": doc_data
			},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in PUT /api/resource/{doctype}/{name}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.delete("/{doctype}/{name}")
async def resource_delete_doc(
	doctype: str,
	name: str,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	DELETE /api/resource/{doctype}/{name} - Delete a document
	Maps to: flamezo_backend.flamezo.api.documents.delete_doc
	
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.delete_doc",
			data={
				"doctype": doctype,
				"name": name
			},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in DELETE /api/resource/{doctype}/{name}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
