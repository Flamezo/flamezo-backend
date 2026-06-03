from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import httpx
import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from utils.auth import get_current_user, TokenData
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── ERPNext REST helpers ──────────────────────────────────────────────────────

ERPNEXT_BASE = settings.erpnext_base_url.rstrip("/")
ERPNEXT_HEADERS = {
    "Authorization": f"token {settings.erpnext_api_key}:{settings.erpnext_api_secret}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


async def _erpnext_get(doctype: str, name: str) -> Dict[str, Any]:
    """GET /api/resource/{doctype}/{name}"""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{ERPNEXT_BASE}/api/resource/{doctype}/{name}", headers=ERPNEXT_HEADERS)
        r.raise_for_status()
        return r.json().get("data", {})


async def _erpnext_patch(doctype: str, name: str, fields: Dict[str, Any]) -> None:
    """PATCH /api/resource/{doctype}/{name}  – updates only supplied fields"""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.patch(
            f"{ERPNEXT_BASE}/api/resource/{doctype}/{name}",
            headers=ERPNEXT_HEADERS,
            json=fields,
        )
        r.raise_for_status()


# ── Request models ─────────────────────────────────────────────────────────────

class AssignDeliveryRequest(BaseModel):
    order_id: str
    delivery_mode: str          # 'auto' or 'manual'
    partner_name: Optional[str] = None
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    eta: Optional[str] = None


class CancelDeliveryRequest(BaseModel):
    order_id: str
    delivery_id: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/assign")
async def assign_delivery(
    request: AssignDeliveryRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Assign delivery – Manual rider only"""
    try:
        await _erpnext_patch("Order", request.order_id, {
            "delivery_partner": "manual",
            "delivery_status": "assigned",
            "delivery_rider_name": request.rider_name,
            "delivery_rider_phone": request.rider_phone,
            "delivery_eta": request.eta,
        })
        return {"success": True, "message": "Manual delivery assigned"}

    except Exception as e:
        logger.error(f"assign_delivery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel")
async def cancel_delivery(
    request: CancelDeliveryRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Cancel an active delivery assignment"""
    try:
        await _erpnext_patch("Order", request.order_id, {
            "delivery_id":          None,
            "delivery_status":      "cancelled",
            "delivery_rider_name":  None,
            "delivery_rider_phone": None,
            "delivery_tracking_url": None,
        })
        return {"success": True}

    except Exception as e:
        logger.error(f"cancel_delivery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
