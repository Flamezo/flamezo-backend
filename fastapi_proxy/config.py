"""
Configuration management for FastAPI Proxy

STRICT RULES:
- All configuration from environment variables
- No hardcoded secrets
- Fail fast if required config missing
"""

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
	"""Application settings from environment variables"""
	
	# ERPNext Backend
	erpnext_base_url: str
	erpnext_api_key: str
	erpnext_api_secret: str
	
	# FastAPI Server
	fastapi_host: str = "0.0.0.0"
	fastapi_port: int = 8001
	fastapi_env: str = "development"
	fastapi_debug: bool = False
	
	# Security
	jwt_secret_key: str
	jwt_algorithm: str = "HS256"
	jwt_expiration_minutes: int = 60
	
	# Rate Limiting
	rate_limit_enabled: bool = True
	rate_limit_read_per_minute: int = 100
	rate_limit_write_per_minute: int = 20
	rate_limit_global_per_minute: int = 1000
	rate_limit_burst_per_second: int = 50
	
	# Caching
	cache_enabled: bool = True
	cache_redis_url: str = "redis://localhost:6379/0"
	cache_default_ttl: int = 60
	cache_doctype_meta_ttl: int = 60
	cache_permissions_ttl: int = 30
	cache_doctypes_list_ttl: int = 300
	cache_restaurants_ttl: int = 60
	cache_wizard_steps_ttl: int = 300
	cache_qr_url_ttl: int = 60
	cache_categories_ttl: int = 600
	cache_products_ttl: int = 300
	
	# CORS
	cors_origins: str = "http://localhost:3000,http://localhost:5173"
	cors_allow_credentials: bool = True
	cors_allow_methods: str = "*"
	cors_allow_headers: str = "*"
	
	# Logging
	log_level: str = "INFO"
	log_format: str = "json"
	
	class Config:
		env_file = ".env"
		case_sensitive = False
	
	@property
	def cors_origins_list(self) -> List[str]:
		"""Parse CORS origins string into list"""
		return [origin.strip() for origin in self.cors_origins.split(",")]
	
	def validate_required_settings(self):
		"""Validate that all required settings are present"""
		required = [
			("erpnext_base_url", self.erpnext_base_url),
			("erpnext_api_key", self.erpnext_api_key),
			("erpnext_api_secret", self.erpnext_api_secret),
			("jwt_secret_key", self.jwt_secret_key),
		]
		
		missing = [name for name, value in required if not value]
		if missing:
			raise ValueError(f"Missing required configuration: {', '.join(missing)}")
		
		# Validate JWT secret length
		if len(self.jwt_secret_key) < 32:
			raise ValueError("JWT secret key must be at least 32 characters long")


# Global settings instance
settings = Settings()

# Validate on import
settings.validate_required_settings()

