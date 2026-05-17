#!/usr/bin/env python3
"""
Generate a test JWT token for FastAPI Proxy

Usage:
    python3 generate_test_token.py [email] [user_id]

Example:
    python3 generate_test_token.py admin@example.com admin
"""

import sys
import os

# Add current directory to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from utils.auth import create_access_token

def main():
    # Get email and user_id from command line or use defaults
    email = sys.argv[1] if len(sys.argv) > 1 else "test@example.com"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "test_user"
    
    # Create token
    token_data = {
        "user_id": user_id,
        "email": email,
        "restaurant_access": []  # Add restaurant IDs if needed
    }
    
    token = create_access_token(token_data)
    
    print("=" * 60)
    print("JWT Token Generated Successfully")
    print("=" * 60)
    print(f"\nEmail: {email}")
    print(f"User ID: {user_id}")
    print(f"\nToken (copy this):")
    print(token)
    print("\n" + "=" * 60)
    print("\nUsage example:")
    print(f'curl -X POST http://127.0.0.1:9005/api/method/flamezo_backend.flamezo.api.ui.get_doctype_meta \\')
    print(f'  -H "Authorization: Bearer {token}" \\')
    print(f'  -H "Content-Type: application/json" \\')
    print(f'  -d \'{{"doctype": "Restaurant"}}\'')
    print("=" * 60)

if __name__ == "__main__":
    main()
