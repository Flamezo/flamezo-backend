"""
FastAPI Proxy Shield for Flamezo ERPNext Backend

This proxy acts as a transparent, protective layer between the frontend and ERPNext.
It MUST NOT change any business logic, API contracts, or response formats.

Golden Rule: FastAPI must behave exactly like ERPNext, just sitting in between.
"""

__version__ = "1.0.0"

