from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
import logging

from clients.erpnext_client import get_erpnext_client
from utils.auth import get_current_user, TokenData

logger = logging.getLogger(__name__)
router = APIRouter()

class AIRequest(BaseModel):
    restaurant: str
    owner_doctype: str
    owner_name: str
    original_image_url: str

@router.post("/enhance")
async def enqueue_enhancement(
    request: AIRequest,
    current_user: TokenData = Depends(get_current_user)
):
    client = get_erpnext_client()
    try:
        response = await client.call_method(
            "flamezo_backend.flamezo.api.ai_media.enqueue_enhancement",
            data=request.dict()
        )
        return response
    except Exception as e:
        logger.error(f"Error calling enqueue_enhancement: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{generation_id}")
async def get_status(
    generation_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    client = get_erpnext_client()
    try:
        response = await client.call_method(
            "flamezo_backend.flamezo.api.ai_media.get_enhancement_status",
            data={"generation_id": generation_id}
        )
        return response
    except Exception as e:
        logger.error(f"Error calling get_enhancement_status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_to_product(
    generation_id: str = Body(..., embed=True),
    current_user: TokenData = Depends(get_current_user)
):
    client = get_erpnext_client()
    try:
        response = await client.call_method(
            "flamezo_backend.flamezo.api.ai_media.apply_to_product",
            data={"generation_id": generation_id}
        )
        return response
    except Exception as e:
        logger.error(f"Error calling apply_to_product: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
