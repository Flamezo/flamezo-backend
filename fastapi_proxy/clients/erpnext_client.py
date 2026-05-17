"""
ERPNext HTTP Client

CRITICAL: This module handles ALL communication with ERPNext backend.

STRICT RULES:
- NO response transformation
- NO field renaming
- NO business logic
- ONLY HTTP communication
- Pass errors through unchanged
- Return responses as-is
"""

import httpx
import logging
from typing import Dict, Any, Optional
import json
import sys
import os

# Handle imports - work as both module and script
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
	sys.path.insert(0, _parent_dir)

from config import settings

logger = logging.getLogger(__name__)


class ERPNextClient:
	"""
	HTTP client for ERPNext API communication
	
	Uses system user credentials (API key + secret) for all requests.
	Frontend user context is NOT used here - ERPNext sees only system user.
	"""
	
	def __init__(self):
		self.base_url = settings.erpnext_base_url.rstrip("/")
		self.api_key = settings.erpnext_api_key
		self.api_secret = settings.erpnext_api_secret
		self.timeout = 30.0  # 30 seconds timeout
		
		# Validate configuration
		if not all([self.base_url, self.api_key, self.api_secret]):
			raise ValueError("ERPNext client configuration is incomplete")
		
		# Create httpx client
		self.client = httpx.AsyncClient(
			base_url=self.base_url,
			timeout=self.timeout,
			headers={
				"Authorization": f"token {self.api_key}:{self.api_secret}",
				"Content-Type": "application/json",
				"Accept": "application/json"
			}
		)
	
	async def call_method(
		self,
		method_path: str,
		params: Optional[Dict[str, Any]] = None,
		data: Optional[Dict[str, Any]] = None,
		http_method: str = "POST"
	) -> Dict[str, Any]:
		"""
		Call an ERPNext whitelisted method
		
		Args:
			method_path: Method path (e.g., "flamezo_backend.flamezo.api.ui.get_doctype_meta")
			params: Query parameters (for GET requests)
			data: Request body data (for POST requests)
			http_method: HTTP method (GET, POST, PUT, DELETE)
		
		Returns:
			Response from ERPNext AS-IS (no transformation)
		
		Raises:
			httpx.HTTPStatusError: If response status is error
		"""
		url = f"/api/method/{method_path}"
		
		logger.debug(f"ERPNext API call: {http_method} {url}")
		logger.debug(f"Params: {params}")
		logger.debug(f"Data: {data}")
		
		try:
			# Make request
			if http_method.upper() == "GET":
				response = await self.client.get(url, params=params)
			elif http_method.upper() == "POST":
				response = await self.client.post(url, json=data, params=params)
			elif http_method.upper() == "PUT":
				response = await self.client.put(url, json=data, params=params)
			elif http_method.upper() == "DELETE":
				response = await self.client.delete(url, params=params)
			else:
				raise ValueError(f"Unsupported HTTP method: {http_method}")
			
			# Log response
			logger.debug(f"ERPNext response status: {response.status_code}")
			
			# Raise for error status codes
			response.raise_for_status()
			
			# Return response as-is (parsed JSON)
			return response.json()
			
		except httpx.HTTPStatusError as e:
			logger.error(f"ERPNext API error: {e.response.status_code} - {e.response.text}")
			# Return error response as-is
			try:
				return e.response.json()
			except:
				return {
					"exc_type": "HTTPError",
					"exception": str(e),
					"_server_messages": str(e.response.text)
				}
		
		except Exception as e:
			logger.error(f"ERPNext client error: {str(e)}")
			raise
	
	async def get_resource(
		self,
		doctype: str,
		name: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
		fields: Optional[list] = None,
		limit_page_length: int = 20,
		order_by: Optional[str] = None
	) -> Dict[str, Any]:
		"""
		Call ERPNext Resource API (GET)
		Maps to wrapper methods in ERPNext
		
		Args:
			doctype: DocType name
			name: Document name (for single document)
			filters: Filters for list query
			fields: Fields to fetch
			limit_page_length: Limit results
			order_by: Sort order
		
		Returns:
			Response from ERPNext AS-IS
		"""
		# Map to wrapper method
		if name:
			# Get single document
			return await self.call_method(
				"flamezo_backend.flamezo.api.documents.get_doc",
				data={"doctype": doctype, "name": name},
				http_method="POST"
			)
		else:
			# Get list of documents
			return await self.call_method(
				"flamezo_backend.flamezo.api.documents.get_doc_list",
				data={
					"doctype": doctype,
					"filters": json.dumps(filters) if filters else None,
					"fields": json.dumps(fields) if fields else None,
					"limit_page_length": limit_page_length,
					"order_by": order_by
				},
				http_method="POST"
			)
	
	async def create_resource(
		self,
		doctype: str,
		doc_data: Dict[str, Any]
	) -> Dict[str, Any]:
		"""
		Create a document via Resource API
		Maps to wrapper method in ERPNext
		"""
		doc_data["doctype"] = doctype
		return await self.call_method(
			"flamezo_backend.flamezo.api.documents.insert_doc",
			data={"doc": json.dumps(doc_data)},
			http_method="POST"
		)
	
	async def update_resource(
		self,
		doctype: str,
		name: str,
		doc_data: Dict[str, Any]
	) -> Dict[str, Any]:
		"""
		Update a document via Resource API
		Maps to wrapper method in ERPNext
		"""
		return await self.call_method(
			"flamezo_backend.flamezo.api.documents.update_document",
			data={
				"doctype": doctype,
				"name": name,
				"doc_data": json.dumps(doc_data)
			},
			http_method="POST"
		)
	
	async def delete_resource(
		self,
		doctype: str,
		name: str
	) -> Dict[str, Any]:
		"""
		Delete a document via Resource API
		Maps to wrapper method in ERPNext
		"""
		return await self.call_method(
			"flamezo_backend.flamezo.api.documents.delete_doc",
			data={"doctype": doctype, "name": name},
			http_method="POST"
		)
	
	async def close(self):
		"""Close the HTTP client"""
		await self.client.aclose()


# Global client instance
_client: Optional[ERPNextClient] = None


def get_erpnext_client() -> ERPNextClient:
	"""Get or create ERPNext client instance"""
	global _client
	if _client is None:
		_client = ERPNextClient()
	return _client


async def close_erpnext_client():
	"""Close ERPNext client"""
	global _client
	if _client is not None:
		await _client.close()
		_client = None

