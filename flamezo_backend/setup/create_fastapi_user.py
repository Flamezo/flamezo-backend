#!/usr/bin/env python3
"""
Create FastAPI System User for ERPNext Backend Access

This script creates a dedicated system user that FastAPI will use to communicate with ERPNext.
All frontend requests will be proxied through FastAPI → ERPNext using this user.

STRICT RULES:
- This user MUST have API access
- This user MUST have System Manager role (full access)
- This user MUST NOT be used for frontend authentication
- API keys are generated once and stored securely in FastAPI

Usage:
    bench --site [site-name] execute flamezo_backend.setup.create_fastapi_user.create_fastapi_system_user
"""

import frappe
from frappe import _
import secrets
import string


def generate_api_credentials():
	"""Generate secure API key and secret"""
	# API Key: 32 characters alphanumeric
	api_key = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
	
	# API Secret: 64 characters alphanumeric + special chars for extra security
	api_secret = secrets.token_urlsafe(48)  # ~64 characters base64
	
	return api_key, api_secret


def create_fastapi_system_user():
	"""
	Create the FastAPI system user with API access
	
	Returns:
		dict: Contains api_key and api_secret - MUST BE SAVED SECURELY
	"""
	try:
		username = "fastapi_system_user"
		email = "fastapi@flamezo_backend.local"
		
		# Check if user already exists
		if frappe.db.exists("User", email):
			print(f"⚠️  User {email} already exists!")
			
			# Ask if we should regenerate API keys
			user_doc = frappe.get_doc("User", email)
			print(f"   Current User: {user_doc.name}")
			print(f"   Roles: {', '.join([r.role for r in user_doc.roles])}")
			
			# Check for existing API keys
			existing_keys = frappe.get_all(
				"User API Key",
				filters={"user": email},
				fields=["name", "api_key", "creation"]
			)
			
			if existing_keys:
				print(f"\n   Existing API Keys ({len(existing_keys)}):")
				for key in existing_keys:
					print(f"   - Key: {key.api_key[:10]}... (created: {key.creation})")
				
				print("\n❌ User and API keys already exist. Skipping creation.")
				print("   If you need new keys, manually delete the user first:")
				print(f"   bench --site [site] execute frappe.delete_doc --args \"['User', '{email}', true]\"")
				return {
					"success": False,
					"message": "User already exists. Delete manually to regenerate."
				}
			else:
				# User exists but no API keys - generate new ones
				print("\n   No API keys found. Generating new keys...")
				api_key, api_secret = generate_api_credentials()
				
				# Create API key document
				api_key_doc = frappe.get_doc({
					"doctype": "User API Key",
					"user": email,
					"api_key": api_key,
					"api_secret": api_secret
				})
				api_key_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				
				print(f"\n✅ API Keys generated for existing user!")
				print(f"\n{'=' * 80}")
				print(f"SAVE THESE CREDENTIALS SECURELY - THEY WILL NOT BE SHOWN AGAIN")
				print(f"{'=' * 80}")
				print(f"Email: {email}")
				print(f"API Key: {api_key}")
				print(f"API Secret: {api_secret}")
				print(f"{'=' * 80}\n")
				
				return {
					"success": True,
					"email": email,
					"api_key": api_key,
					"api_secret": api_secret,
					"message": "API keys generated for existing user"
				}
		
		# Create new user
		print(f"\n📝 Creating FastAPI system user: {email}")
		
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "FastAPI",
			"last_name": "System User",
			"username": username,
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			# Roles
			"roles": [
				{"role": "System Manager"}  # Full access to all ERPNext APIs
			]
		})
		
		user.insert(ignore_permissions=True)
		print(f"✅ User created successfully")
		
		# Generate API credentials
		print(f"🔑 Generating API credentials...")
		api_key, api_secret = generate_api_credentials()
		
		# Create API key document
		api_key_doc = frappe.get_doc({
			"doctype": "User API Key",
			"user": email,
			"api_key": api_key,
			"api_secret": api_secret
		})
		api_key_doc.insert(ignore_permissions=True)
		
		frappe.db.commit()
		print(f"✅ API credentials generated")
		
		# Display credentials (IMPORTANT - these won't be shown again)
		print(f"\n{'=' * 80}")
		print(f"SAVE THESE CREDENTIALS SECURELY - THEY WILL NOT BE SHOWN AGAIN")
		print(f"{'=' * 80}")
		print(f"Email: {email}")
		print(f"API Key: {api_key}")
		print(f"API Secret: {api_secret}")
		print(f"{'=' * 80}\n")
		
		print(f"📝 Next Steps:")
		print(f"   1. Copy the API Key and API Secret")
		print(f"   2. Store them in FastAPI environment variables:")
		print(f"      ERPNEXT_API_KEY={api_key}")
		print(f"      ERPNEXT_API_SECRET={api_secret}")
		print(f"   3. Never commit these credentials to version control")
		print(f"   4. Use a secrets manager in production\n")
		
		return {
			"success": True,
			"email": email,
			"api_key": api_key,
			"api_secret": api_secret,
			"message": "User and API keys created successfully"
		}
		
	except Exception as e:
		import traceback
		frappe.log_error(f"Error creating FastAPI system user: {str(e)}\n{traceback.format_exc()}")
		print(f"❌ Error: {str(e)}")
		print(traceback.format_exc())
		return {
			"success": False,
			"message": str(e)
		}


if __name__ == "__main__":
	# This allows the script to be run directly via bench execute
	result = create_fastapi_system_user()
	print("\n" + ("=" * 80))
	if result["success"]:
		print("✅ SUCCESS: FastAPI system user created")
	else:
		print(f"❌ FAILED: {result['message']}")
	print("=" * 80)

