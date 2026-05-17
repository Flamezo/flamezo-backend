"""
FastAPI Proxy Shield - Main Application Entry Point

This is the main FastAPI application that acts as a transparent proxy between
the frontend and ERPNext backend.

STRICT RULES:
- NO business logic here
- NO data transformation
- NO field renaming
- ONLY routing, authentication, rate limiting, and caching
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import time

# Handle imports - work as both module and script
import sys
import os

# Add current directory to path for absolute imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
	sys.path.insert(0, _current_dir)

# Use absolute imports
from config import settings
from middleware.logging import setup_logging
from middleware.error_handler import error_handler_middleware
from routes import (
	ui_routes,
	order_routes,
	document_routes,
	restaurant_routes,
	frappe_routes,
	resource_routes,
	media_routes,
	ai_routes,
	delivery_routes
)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
	title="Flamezo FastAPI Proxy Shield",
	description="Transparent, protective proxy for ERPNext backend",
	version="1.0.0",
	docs_url="/docs" if settings.fastapi_debug else None,
	redoc_url="/redoc" if settings.fastapi_debug else None
)

# Setup rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_origins_list,
	allow_credentials=settings.cors_allow_credentials,
	allow_methods=settings.cors_allow_methods.split(",") if settings.cors_allow_methods != "*" else ["*"],
	allow_headers=settings.cors_allow_headers.split(",") if settings.cors_allow_headers != "*" else ["*"],
)

# Error handler middleware
app.middleware("http")(error_handler_middleware)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
	"""Log all requests"""
	start_time = time.time()
	
	# Get request info
	method = request.method
	url = str(request.url)
	client = request.client.host if request.client else "unknown"
	
	logger.info(f"Request started: {method} {url} from {client}")
	
	# Process request
	try:
		response = await call_next(request)
		process_time = time.time() - start_time
		
		logger.info(
			f"Request completed: {method} {url} - "
			f"Status: {response.status_code} - "
			f"Time: {process_time:.3f}s"
		)
		
		# Add processing time header
		response.headers["X-Process-Time"] = str(process_time)
		
		return response
	except Exception as e:
		process_time = time.time() - start_time
		logger.error(
			f"Request failed: {method} {url} - "
			f"Error: {str(e)} - "
			f"Time: {process_time:.3f}s"
		)
		raise


# Health check endpoint
@app.get("/health")
async def health_check():
	"""Health check endpoint - no rate limiting"""
	return {
		"status": "healthy",
		"service": "flamezo_backend-fastapi-proxy",
		"version": "1.0.0"
	}


# Include routers
# ERPNext uses dot notation: /api/method/flamezo_backend.flamezo.api.ui.get_setup_wizard_steps
# Routes are defined with full method paths, prefix is just /api/method
app.include_router(ui_routes.router, prefix="/api/method", tags=["UI APIs"])
app.include_router(order_routes.router, prefix="/api/method", tags=["Order Management"])
app.include_router(document_routes.router, prefix="/api/method", tags=["Document Management"])
app.include_router(restaurant_routes.router, prefix="/api/method", tags=["Restaurant"])
app.include_router(frappe_routes.router, prefix="/api/method", tags=["Frappe Client"])
app.include_router(resource_routes.router, prefix="/api/resource", tags=["Resource API"])
app.include_router(media_routes.router, prefix="/api/media", tags=["Media Management"])
app.include_router(ai_routes.router, prefix="/api/ai", tags=["AI Media Management"])
app.include_router(delivery_routes.router, prefix="/api/delivery", tags=["Delivery Management"])


# Debug: Catch-all route to see what paths are being requested
# This must be AFTER all other routes to catch unmatched paths
# Using {path:path} to capture the full method name including dots
@app.api_route("/api/method/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def catch_all_method(path: str, request: Request):
	"""Catch-all for /api/method/* to debug routing - shows what path was received"""
	logger.warning(f"Catch-all route hit: /api/method/{path}")
	return JSONResponse(
		status_code=404,
		content={
			"debug": True,
			"path": path,
			"full_path": f"/api/method/{path}",
			"method": request.method,
			"message": "Route not found - this is a catch-all debug route. Check if route is registered."
		}
	)


# Root endpoint
@app.get("/")
async def root():
	"""Root endpoint"""
	return {
		"service": "Flamezo FastAPI Proxy Shield",
		"version": "1.0.0",
		"status": "running",
		"docs": "/docs" if settings.fastapi_debug else "disabled"
	}


if __name__ == "__main__":
	import uvicorn
	
	logger.info(f"Starting FastAPI Proxy on {settings.fastapi_host}:{settings.fastapi_port}")
	logger.info(f"Environment: {settings.fastapi_env}")
	logger.info(f"Debug: {settings.fastapi_debug}")
	logger.info(f"ERPNext Backend: {settings.erpnext_base_url}")
	
	uvicorn.run(
		app,  # Use app directly instead of string
		host=settings.fastapi_host,
		port=settings.fastapi_port,
		reload=settings.fastapi_debug,
		log_level=settings.log_level.lower()
	)

