import frappe
from flamezo_backend.flamezo.utils.roles import DESK_RESTRICTED_ROLES, is_global_admin


def restrict_merchant_desk_access():
    """
    Prevent Restaurant Admin and Restaurant Staff roles from accessing the Frappe Desk (/app).
    They should only use the custom React dashboard at /flamezo_backend.
    """
    if not frappe.request:
        return
    
    path = frappe.request.path
    
    # Only intercept if they are trying to access the Desk (/app)
    # We allow /flamezo_backend, /api, and standard login paths
    if not path.startswith("/app"):
        return
    
    # Get current user roles
    user_roles = frappe.get_roles()
    
    # Define roles that are BANNED from the Desk
    merchant_roles = DESK_RESTRICTED_ROLES
    
    # System Managers and Administrators should ALWAYS have access for support
    if is_global_admin():
        return
    
    # Check if user has any merchant roles
    is_merchant = any(role in DESK_RESTRICTED_ROLES for role in user_roles)
    
    if is_merchant:
        # User is a merchant trying to enter the Desk. 
        # Redirect them to the custom dashboard.
        frappe.local.flags.redirect_location = "/flamezo_backend"
        raise frappe.Redirect
