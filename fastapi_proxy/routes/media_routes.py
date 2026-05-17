"""
Media API Routes

Maps to: /api/media/*
These routes handle media upload sessions and management

STRICT RULES:
- Accept EXACT same parameters as Frappe media APIs
- Return EXACT same responses as Frappe media APIs
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

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models

class UploadSessionRequest(BaseModel):
	"""Request model for upload session"""
	owner_doctype: str
	owner_name: str
	media_role: str
	filename: str
	content_type: str
	size_bytes: int


class ConfirmUploadRequest(BaseModel):
	"""Request model for confirm upload"""
	upload_id: str
	owner_doctype: str
	owner_name: str
	media_role: str
	alt_text: Optional[str] = None
	caption: Optional[str] = None
	display_order: Optional[int] = 0


class DeleteMediaRequest(BaseModel):
	"""Request model for delete media"""
	media_id: str


# Route Implementations

@router.post("/upload-session")
async def request_upload_session(
	request: UploadSessionRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	POST /api/media/upload-session
	Request upload session for direct R2 upload
	
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.media.api.request_upload_session",
			data={
				"owner_doctype": request.owner_doctype,
				"owner_name": request.owner_name,
				"media_role": request.media_role,
				"filename": request.filename,
				"content_type": request.content_type,
				"size_bytes": request.size_bytes
			},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in upload-session: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.post("/confirm-upload")
async def confirm_upload(
	request: ConfirmUploadRequest,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	POST /api/media/confirm-upload
	Confirm upload and create Media Asset
	
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.media.api.confirm_upload",
			data={
				"upload_id": request.upload_id,
				"owner_doctype": request.owner_doctype,
				"owner_name": request.owner_name,
				"media_role": request.media_role,
				"alt_text": request.alt_text,
				"caption": request.caption,
				"display_order": request.display_order
			},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in confirm-upload: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.get("/{media_id}")
async def get_media_asset(
	media_id: str,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	GET /api/media/{media_id}
	Get media asset details
	
	Type: READ
	Cache: No (real-time status needed)
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.media.api.get_media_asset",
			data={"media_id": media_id},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in get_media_asset: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)


@router.delete("/{media_id}")
async def delete_media_asset(
	media_id: str,
	current_user: TokenData = Depends(get_current_user)
):
	"""
	DELETE /api/media/{media_id}
	Soft delete media asset
	
	Type: WRITE
	Cache: No
	"""
	client = get_erpnext_client()
	
	try:
		response = await client.call_method(
			"flamezo_backend.flamezo.media.api.delete_media_asset",
			data={"media_id": media_id},
			http_method="POST"
		)
		return response
		
	except Exception as e:
		logger.error(f"Error in delete_media_asset: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=str(e)
		)
