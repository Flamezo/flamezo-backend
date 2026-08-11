"""
Authentication utilities

This module handles JWT-based authentication for the FastAPI proxy.

STRICT RULES:
- Frontend users authenticate with FastAPI (NOT ERPNext directly)
- FastAPI issues JWT tokens
- All ERPNext calls use system user credentials
- User context is passed via API parameters (NOT via authentication)
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import sys
import os

# Handle imports - work as both module and script
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
	sys.path.insert(0, _parent_dir)

from config import settings

# Security scheme
security = HTTPBearer()


class TokenData(BaseModel):
	"""JWT token payload data"""
	user_id: str
	email: str
	outlet_access: list = []
	exp: datetime


def create_access_token(data: Dict[str, Any]) -> str:
	"""
	Create JWT access token
	
	Args:
		data: Token payload data (user_id, email, outlet_access)
	
	Returns:
		Encoded JWT token
	"""
	to_encode = data.copy()
	expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
	to_encode.update({"exp": expire})
	
	encoded_jwt = jwt.encode(
		to_encode,
		settings.jwt_secret_key,
		algorithm=settings.jwt_algorithm
	)
	
	return encoded_jwt


def verify_token(token: str) -> TokenData:
	"""
	Verify and decode JWT token
	
	Args:
		token: JWT token string
	
	Returns:
		Decoded token data
	
	Raises:
		HTTPException: If token is invalid or expired
	"""
	try:
		payload = jwt.decode(
			token,
			settings.jwt_secret_key,
			algorithms=[settings.jwt_algorithm]
		)
		
		return TokenData(**payload)
		
	except jwt.ExpiredSignatureError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Token has expired",
			headers={"WWW-Authenticate": "Bearer"},
		)
	except jwt.InvalidTokenError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid token",
			headers={"WWW-Authenticate": "Bearer"},
		)


async def get_current_user(
	credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
	"""
	FastAPI dependency to get current authenticated user from JWT
	
	Args:
		credentials: HTTP Bearer token from request header
	
	Returns:
		Decoded token data with user information
	"""
	token = credentials.credentials
	return verify_token(token)


# Optional authentication dependency (for public endpoints)
async def get_current_user_optional(
	credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[TokenData]:
	"""
	Optional authentication - returns None if no token provided
	"""
	if credentials is None:
		return None
	
	token = credentials.credentials
	return verify_token(token)

