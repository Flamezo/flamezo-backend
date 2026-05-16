import frappe
import json

def run_test():
    """
    Test the frappe.core.doctype.user.user.reset_password whitelisted method.
    """
    test_user = "contact@flamezo_backend.com"
    invalid_user = "nonexistent@flamezo_backend.com"

    print(f"--- Testing Forgot Password API ---")

    # Test 1: Valid User
    print(f"Test 1: Valid user ({test_user})")
    try:
        # Note: reset_password in Frappe is whitelisted and can be called via frappe.call
        # Here we call it directly as if it was a web request
        from frappe.core.doctype.user.user import reset_password
        reset_password(test_user)
        print("SUCCESS: reset_password called without error for valid user.")
    except Exception as e:
        print(f"FAILURE: reset_password failed for valid user: {str(e)}")

    # Test 2: Invalid User
    print(f"\nTest 2: Invalid user ({invalid_user})")
    try:
        reset_password(invalid_user)
        # Frappe usually throws a ValidationError or similar if user not found
        print("WARNING: reset_password did not throw error for invalid user (Frappe might handle this silently to prevent user enumeration)")
    except frappe.ValidationError:
        print("SUCCESS: reset_password threw ValidationError for invalid user.")
    except Exception as e:
        print(f"INFO: reset_password threw {type(e).__name__}: {str(e)}")

    print(f"\n--- End of Test ---")

if __name__ == "__main__":
    run_test()
