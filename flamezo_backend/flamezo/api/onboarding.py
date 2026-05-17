import frappe
import secrets
from frappe import _
from frappe.utils import get_url, now_datetime

@frappe.whitelist()
def generate_onboarding_link(restaurant_name=None, linked_restaurant=None):
    """
    Generate a unique onboarding link for a restaurant.
    Targeted for Flamezo Admin.
    """
    try:
        # Check admin access (Reuse logic from admin.py)
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        if not restaurant_name and not linked_restaurant:
            return {'success': False, 'error': 'Restaurant name or direct link is required'}

        # If linked_restaurant is provided, get the name
        if linked_restaurant:
            res_details = frappe.db.get_value('Restaurant', linked_restaurant, ['restaurant_name', 'owner_email', 'owner_phone'], as_dict=1)
            if res_details:
                restaurant_name = res_details.get('restaurant_name')

        # Generate a secure token
        token = secrets.token_urlsafe(16)
        
        # Create the onboarding record
        doc = frappe.new_doc('Restaurant Onboarding')
        doc.restaurant_name = restaurant_name
        doc.linked_restaurant = linked_restaurant
        
        # Prefill from existing if available
        if linked_restaurant and res_details:
            doc.owner_email = res_details.get('owner_email')
            doc.owner_phone = res_details.get('owner_phone')

        doc.unique_token = token
        doc.status = 'Pending'
        
        # Build the link
        base_url = get_url()
        doc.onboarding_link = f"{base_url}/onboard?token={token}"
        
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            'success': True,
            'data': {
                'name': doc.name,
                'link': doc.onboarding_link,
                'token': token
            }
        }
    except Exception as e:
        frappe.log_error("Onboarding API Error", f"Error generating link: {str(e)}")
        return {'success': False, 'error': str(e)}

@frappe.whitelist(allow_guest=True)
def get_onboarding_details(token):
    """
    Fetch onboarding details for the client using the unique token.
    Public endpoint.
    """
    try:
        if not token:
            return {'success': False, 'error': 'Token is missing'}
            
        doc_name = frappe.db.get_value('Restaurant Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid or expired onboarding link'}
            
        doc = frappe.get_doc('Restaurant Onboarding', doc_name)
        
        # Step 1-6 (Defensive checks for fields that might not have synced to DB yet)
        data_dict = {
            'restaurant_name': doc.restaurant_name,
            'owner_name': getattr(doc, 'owner_name', None),
            'owner_email': getattr(doc, 'owner_email', None),
            'owner_phone': getattr(doc, 'owner_phone', None),
            'whatsapp_number': getattr(doc, 'whatsapp_number', None),
            'fssai_number': getattr(doc, 'fssai_number', None),
            'gst_number': getattr(doc, 'gst_number', None),
            'tax_rate': getattr(doc, 'tax_rate', None),
            'pan_number': getattr(doc, 'pan_number', None),
            'opening_time': str(doc.opening_time) if getattr(doc, 'opening_time', None) else None,
            'closing_time': str(doc.closing_time) if getattr(doc, 'closing_time', None) else None,
            'swiggy_link': getattr(doc, 'swiggy_link', None),
            'zomato_link': getattr(doc, 'zomato_link', None),
            'subtitle': getattr(doc, 'subtitle', None),
            'description': getattr(doc, 'description', None),
            'default_theme': getattr(doc, 'default_theme', None),
            'menu_layout': getattr(doc, 'menu_layout', None),
            'enable_table_booking': getattr(doc, 'enable_table_booking', None),
            'enable_banquet_booking': getattr(doc, 'enable_banquet_booking', None),
            'enable_events': getattr(doc, 'enable_events', None),
            'enable_offers': getattr(doc, 'enable_offers', None),
            'enable_experience_lounge': getattr(doc, 'enable_experience_lounge', None),
            'address': getattr(doc, 'address', None),
            'city': getattr(doc, 'city', None),
            'state': getattr(doc, 'state', None),
            'zip_code': getattr(doc, 'zip_code', None),
            'google_map_url': getattr(doc, 'google_map_url', None),
            'tagline': getattr(doc, 'tagline', None),
            'instagram_link': getattr(doc, 'instagram_link', None),
            'facebook_link': getattr(doc, 'facebook_link', None),
            'website_link': getattr(doc, 'website_link', None),
            'menu_link': getattr(doc, 'menu_link', None),
            'logo': getattr(doc, 'logo', None)
        }
        
        data_dict['menu_photos'] = [p.file for p in doc.menu_photos] if hasattr(doc, 'menu_photos') else []
        
        return {
            'success': True,
            'data': data_dict
        }
    except Exception as e:
        frappe.log_error("Get Onboarding Details Error", str(e))
        return {'success': False, 'error': str(e)}

@frappe.whitelist(allow_guest=True)
def submit_onboarding_data(token, data):
    """
    Saves data submitted by the restaurant owner.
    Public endpoint.
    """
    try:
        if isinstance(data, str):
            import json
            data = json.loads(data)
            
        doc_name = frappe.db.get_value('Restaurant Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid token'}
            
        doc = frappe.get_doc('Restaurant Onboarding', doc_name)
        
        if doc.status == 'Completed':
            return {'success': False, 'error': 'Onboarding is already completed'}

        # Update fields
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'whatsapp_number', 
            'tagline', 'instagram_link', 'facebook_link', 'website_link', 
            'menu_link', 'address', 'city', 'state', 'zip_code', 'google_map_url',
            'logo', 'hero_image', 'fssai_number', 'gst_number', 'tax_rate', 
            'pan_number', 'opening_time', 'closing_time', 
            'swiggy_link', 'zomato_link', 'subtitle', 'description', 
            'default_theme', 'menu_layout', 'enable_table_booking', 
            'enable_banquet_booking', 'enable_events', 'enable_offers', 
            'enable_experience_lounge'
        ]
        
        for field in fields:
            if field in data:
                setattr(doc, field, data[field])
        
        # Handle menu photos (child table)
        if 'menu_photos' in data and isinstance(data['menu_photos'], list):
            doc.set('menu_photos', [])
            for photo in data['menu_photos']:
                doc.append('menu_photos', {
                    'file': photo,
                    'media_type': 'Menu Image'
                })
        
        doc.status = 'Client Submitted'
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Optional: Send notification to Admin here
        
        return {'success': True, 'message': 'Information submitted successfully!'}
    except Exception as e:
        frappe.log_error("Onboarding Submission Error", str(e))
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def get_all_onboarding_requests():
    """
    Returns all non-finalized onboarding requests.
    Admin only.
    """
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        requests = frappe.get_all(
            'Restaurant Onboarding',
            filters={'status': ['!=', 'Completed']},
            fields=['name', 'restaurant_name', 'owner_name', 'owner_email', 'status', 'unique_token', 'onboarding_link', 'creation'],
            order_by='creation desc'
        )

        # Ensure onboarding_link is populated even if it was created before the field was added
        base_url = get_url()
        for r in requests:
            if not r.get('onboarding_link') and r.get('unique_token'):
                r['onboarding_link'] = f"{base_url}/onboard?token={r['unique_token']}"
        
        return {
            'success': True,
            'data': requests
        }
    except Exception as e:
        frappe.log_error("Get Onboarding Requests Error", str(e))
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def delete_onboarding_request(name):
    """
    Deletes an onboarding request.
    Admin only.
    """
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        frappe.delete_doc('Restaurant Onboarding', name, ignore_permissions=True)
        frappe.db.commit()
        
        return {'success': True, 'message': 'Request deleted successfully'}
    except Exception as e:
        frappe.log_error("Delete Onboarding Request Error", str(e))
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def bulk_delete_onboarding_requests(names):
    """
    Deletes multiple onboarding requests.
    Admin only.
    """
    import json
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        if isinstance(names, str):
            names = json.loads(names)

        for name in names:
            frappe.delete_doc('Restaurant Onboarding', name, ignore_permissions=True)
            
        frappe.db.commit()
        
        return {'success': True, 'message': f'Successfully deleted {len(names)} requests'}
    except Exception as e:
        frappe.log_error("Bulk Delete Onboarding Error", str(e))

@frappe.whitelist(allow_guest=True)
def upload_onboarding_media(token):
    """
    Standard upload_file is restricted for guests.
    This custom endpoint allows guests to upload files if they provide a valid onboarding token.
    """
    try:
        if not token:
            return {'success': False, 'error': 'Authentication token required for upload'}

        # Validate token
        doc_name = frappe.db.get_value('Restaurant Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid or expired onboarding session'}

        # Check status
        status = frappe.db.get_value('Restaurant Onboarding', doc_name, 'status')
        if status == 'Completed':
            return {'success': False, 'error': 'This onboarding session has already been finalized'}

        # Get the uploaded file
        if 'file' not in frappe.request.files:
            return {'success': False, 'error': 'No file found in request'}

        file = frappe.request.files['file']
        
        # Safe upload using Frappe's file manager
        from frappe.utils.file_manager import save_file
        
        file_doc = save_file(
            fname=file.filename,
            content=file.read(),
            dt='Restaurant Onboarding',
            dn=doc_name,
            decode=False,
            is_private=0,
            folder='Home/Attachments'
        )

        return {
            'success': True,
            'file_url': file_doc.file_url,
            'name': file_doc.name
        }
    except Exception as e:
        frappe.log_error("Onboarding Upload Error", str(e))
        return {'success': False, 'error': str(e)}
