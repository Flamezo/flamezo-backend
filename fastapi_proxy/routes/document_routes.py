"""
Document Management Routes

Maps to: flamezo_backend.flamezo.api.documents.*

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


# Request Models (match ERPNext parameters exactly)
class CreateDocumentRequest(BaseModel):
	"""Request for create_document"""
	doctype: str
	doc_data: Dict[str, Any]


class UpdateDocumentRequest(BaseModel):
	"""Request for update_document"""
	doctype: str
	name: str
	doc_data: Dict[str, Any]


class GetDocListRequest(BaseModel):
	"""Request for get_doc_list"""
	doctype: str
	filters: Optional[Dict[str, Any]] = None
	fields: Optional[List[str]] = None
	limit_page_length: Optional[int] = 20
	order_by: Optional[str] = None


class GetDocRequest(BaseModel):
	"""Request for get_doc"""
	doctype: str
	name: str


class InsertDocRequest(BaseModel):
	"""Request for insert_doc - doc is a dict with doctype and fields"""
	doc: Dict[str, Any]


class DeleteDocRequest(BaseModel):
	"""Request for delete_doc"""
	doctype: str
	name: str


# Route Implementations

@router.post("/flamezo_backend.flamezo.api.documents.create_document")
async def create_document(
	request: CreateDocumentRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Create a document
	
	Mirrors: flamezo_backend.flamezo.api.documents.create_document
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.create_document",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in create_document: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.documents.update_document")
async def update_document(
	request: UpdateDocumentRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Update a document
	
	Mirrors: flamezo_backend.flamezo.api.documents.update_document
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.update_document",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in update_document: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.documents.get_doc_list")
async def get_doc_list(
	request: GetDocListRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get list of documents
	
	Mirrors: flamezo_backend.flamezo.api.documents.get_doc_list
	Type: READ
	Cache: Yes (depends on doctype - see caching rules)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc_list",
			data=request.dict(exclude_none=True),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_doc_list: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.documents.get_doc")
async def get_doc(
	request: GetDocRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Get a single document
	
	Mirrors: flamezo_backend.flamezo.api.documents.get_doc
	Type: READ
	Cache: No (user-specific, real-time data)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.api.documents.get_doc",
			data=request.dict(),
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_doc: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.documents.insert_doc")
async def insert_doc(
	request: InsertDocRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Insert a document (wrapper for frappe.client.insert)
	
	Mirrors: flamezo_backend.flamezo.api.documents.insert_doc
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
		logger.error(f"Error in insert_doc: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/flamezo_backend.flamezo.api.documents.delete_doc")
async def delete_doc(
	request: DeleteDocRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	Delete a document (wrapper for frappe.client.delete)
	
	Mirrors: flamezo_backend.flamezo.api.documents.delete_doc
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
		logger.error(f"Error in delete_doc: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
