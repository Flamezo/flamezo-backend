import frappe
import secrets
from frappe import _
from frappe.utils import get_url, now_datetime

@frappe.whitelist()
def generate_onboarding_link(outlet_name=None, linked_restaurant=None):
    """
    Generate a unique onboarding link for an outlet.
    Targeted for Flamezo Admin.
    """
    try:
        # Check admin access (Reuse logic from admin.py)
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        if not outlet_name and not linked_restaurant:
            return {'success': False, 'error': 'Outlet name or direct link is required'}

        # If linked_restaurant is provided, get the name
        if linked_restaurant:
            res_details = frappe.db.get_value('Outlet', linked_restaurant, ['restaurant_name', 'owner_email', 'owner_phone'], as_dict=1)
            if res_details:
                outlet_name = res_details.get('restaurant_name')

        # Generate a secure token
        token = secrets.token_urlsafe(16)
        
        # Create the onboarding record
        doc = frappe.new_doc('Outlet Onboarding')
        doc.restaurant_name = outlet_name
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
            
        doc_name = frappe.db.get_value('Outlet Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid or expired onboarding link'}
            
        doc = frappe.get_doc('Outlet Onboarding', doc_name)
        
        # Step 1-6 (Defensive checks for fields that might not have synced to DB yet)
        data_dict = {
            'outlet_name': doc.restaurant_name,
            'owner_name': getattr(doc, 'owner_name', None),
            'owner_email': getattr(doc, 'owner_email', None),
            'owner_phone': getattr(doc, 'owner_phone', None),
            'whatsapp_number': getattr(doc, 'whatsapp_number', None),
            'fssai_number': getattr(doc, 'fssai_number', None),
            'gst_number': getattr(doc, 'gst_number', None),
            'tax_rate': getattr(doc, 'tax_rate', None),
            'pan_number': getattr(doc, 'pan_number', None),
            'owner_pan': getattr(doc, 'owner_pan', None),
            'legal_name': getattr(doc, 'legal_name', None),
            'business_type': getattr(doc, 'business_type', None),
            'bank_account_number': getattr(doc, 'bank_account_number', None),
            'bank_ifsc': getattr(doc, 'bank_ifsc', None),
            'bank_holder_name': getattr(doc, 'bank_holder_name', None),
            'cancelled_cheque': getattr(doc, 'cancelled_cheque', None),
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
            'tables': getattr(doc, 'tables', None),
            'enable_events': getattr(doc, 'enable_events', None),
            'enable_offers': getattr(doc, 'enable_offers', None),
            
            'address': getattr(doc, 'address', None),
            'city': getattr(doc, 'city', None),
            'state': getattr(doc, 'state', None),
            'zip_code': getattr(doc, 'zip_code', None),
            'google_map_url': getattr(doc, 'google_map_url', None),
            'tagline': getattr(doc, 'tagline', None),
            'instagram_link': getattr(doc, 'instagram_link', None),
            'facebook_link': getattr(doc, 'facebook_link', None),
            'website_link': getattr(doc, 'website_link', None),
            'google_review_link': getattr(doc, 'google_review_link', None),
            'menu_link': getattr(doc, 'menu_link', None),
            'logo': getattr(doc, 'logo', None)
        }
        
        data_dict['menu_photos'] = [p.file for p in doc.menu_photos] if hasattr(doc, 'menu_photos') else []
        data_dict['google_maps_api_key'] = (
            frappe.conf.get('google_maps_api_key') or
            frappe.db.get_single_value('Flamezo Settings', 'google_maps_api_key') or ''
        )

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
    Saves data submitted by the outlet owner.
    Public endpoint.
    """
    try:
        if isinstance(data, str):
            import json
            data = json.loads(data)
            
        doc_name = frappe.db.get_value('Outlet Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid token'}
            
        doc = frappe.get_doc('Outlet Onboarding', doc_name)
        
        if doc.status == 'Completed':
            return {'success': False, 'error': 'Onboarding is already completed'}

        # Update fields
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'whatsapp_number', 
            'tagline', 'instagram_link', 'facebook_link', 'website_link', 
            'google_review_link', 'menu_link', 'address', 'city', 'state', 'zip_code', 'google_map_url',
            'logo', 'hero_image', 'fssai_number', 'gst_number', 'tax_rate', 
            'pan_number', 'owner_pan', 'legal_name', 'business_type', 'bank_account_number', 'bank_ifsc', 'bank_holder_name', 'cancelled_cheque', 'opening_time', 'closing_time',
            'swiggy_link', 'zomato_link', 'subtitle', 'description', 
            'default_theme', 'menu_layout', 'enable_table_booking', 
            'enable_banquet_booking', 'tables', 'enable_events', 'enable_offers', 
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
    Returns all onboarding requests (including Completed).
    Frontend filters by status. Admin only.
    """
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        requests = frappe.get_all(
            'Outlet Onboarding',
            fields=['name', 'restaurant_name', 'owner_name', 'owner_email', 'status', 'unique_token', 'onboarding_link', 'creation', 'linked_restaurant'],
            order_by='creation desc',
            limit=0,
        )

        # Ensure onboarding_link is populated even if it was created before the field was added
        base_url = get_url()
        for r in requests:
            if not r.get('onboarding_link') and r.get('unique_token'):
                r['onboarding_link'] = f"{base_url}/onboard?token={r['unique_token']}"
            r['outlet_name'] = r.pop('restaurant_name', None)

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

        frappe.delete_doc('Outlet Onboarding', name, ignore_permissions=True)
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
            frappe.delete_doc('Outlet Onboarding', name, ignore_permissions=True)
            
        frappe.db.commit()
        
        return {'success': True, 'message': f'Successfully deleted {len(names)} requests'}
    except Exception as e:
        frappe.log_error("Bulk Delete Onboarding Error", str(e))

@frappe.whitelist()
def get_onboarding_by_name(name):
    """
    Fetch full onboarding doc details for admin review panel.
    Admin only.
    """
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        doc = frappe.get_doc('Outlet Onboarding', name)

        data = {
            'name': doc.name,
            'outlet_name': doc.restaurant_name,
            'linked_restaurant': getattr(doc, 'linked_restaurant', None),
            'status': doc.status,
            'owner_name': getattr(doc, 'owner_name', None),
            'owner_email': getattr(doc, 'owner_email', None),
            'owner_phone': getattr(doc, 'owner_phone', None),
            'whatsapp_number': getattr(doc, 'whatsapp_number', None),
            'fssai_number': getattr(doc, 'fssai_number', None),
            'gst_number': getattr(doc, 'gst_number', None),
            'tax_rate': getattr(doc, 'tax_rate', None),
            'pan_number': getattr(doc, 'pan_number', None),
            'owner_pan': getattr(doc, 'owner_pan', None),
            'legal_name': getattr(doc, 'legal_name', None),
            'business_type': getattr(doc, 'business_type', None),
            'bank_account_number': getattr(doc, 'bank_account_number', None),
            'bank_ifsc': getattr(doc, 'bank_ifsc', None),
            'bank_holder_name': getattr(doc, 'bank_holder_name', None),
            'cancelled_cheque': getattr(doc, 'cancelled_cheque', None),
            'opening_time': str(doc.opening_time) if getattr(doc, 'opening_time', None) else None,
            'closing_time': str(doc.closing_time) if getattr(doc, 'closing_time', None) else None,
            'subtitle': getattr(doc, 'subtitle', None),
            'description': getattr(doc, 'description', None),
            'default_theme': getattr(doc, 'default_theme', None),
            'menu_layout': getattr(doc, 'menu_layout', None),
            'enable_table_booking': getattr(doc, 'enable_table_booking', None),
            'enable_banquet_booking': getattr(doc, 'enable_banquet_booking', None),
            'tables': getattr(doc, 'tables', None),
            'address': getattr(doc, 'address', None),
            'city': getattr(doc, 'city', None),
            'state': getattr(doc, 'state', None),
            'zip_code': getattr(doc, 'zip_code', None),
            'google_map_url': getattr(doc, 'google_map_url', None),
            'tagline': getattr(doc, 'tagline', None),
            'instagram_link': getattr(doc, 'instagram_link', None),
            'facebook_link': getattr(doc, 'facebook_link', None),
            'website_link': getattr(doc, 'website_link', None),
            'google_review_link': getattr(doc, 'google_review_link', None),
            'menu_link': getattr(doc, 'menu_link', None),
            'logo': getattr(doc, 'logo', None),
            'hero_image': getattr(doc, 'hero_image', None),
            'menu_photos': [p.file for p in doc.menu_photos] if hasattr(doc, 'menu_photos') else [],
        }

        return {'success': True, 'data': data}
    except Exception as e:
        frappe.log_error('Get Onboarding By Name Error', str(e))
        return {'success': False, 'error': str(e)}


@frappe.whitelist()
def sync_onboarding_to_outlet(name):
    """
    Syncs onboarding submission data to the linked Restaurant doc and its Restaurant Config.
    Marks the onboarding as Completed and records who finalized it.
    Admin only.
    """
    try:
        from flamezo_backend.flamezo.api.admin import check_admin_access
        access_check = check_admin_access()
        if not access_check.get('success') or not access_check.get('data', {}).get('allowed'):
            return {'success': False, 'error': 'Admin access required'}

        doc = frappe.get_doc('Outlet Onboarding', name)

        if not doc.linked_restaurant:
            return {
                'success': False,
                'error': 'No linked outlet found. This onboarding must be linked to an existing outlet before syncing.'
            }

        restaurant = doc.linked_restaurant

        # ── Sync to Restaurant ──────────────────────────────────────────────
        res_doc = frappe.get_doc('Outlet', restaurant)

        outlet_field_map = {
            'owner_name': 'owner_name',
            'owner_email': 'owner_email',
            'owner_phone': 'owner_phone',
            'address': 'address',
            'city': 'city',
            'state': 'state',
            'zip_code': 'zip_code',
            'google_map_url': 'google_map_url',
            'legal_name': 'legal_name',
            'business_type': 'business_type',
            'gst_number': 'gst_number',
            'pan_number': 'pan_number',
            'owner_pan': 'owner_pan',
            'bank_account_number': 'bank_account_number',
            'bank_ifsc': 'bank_ifsc',
            'bank_holder_name': 'bank_holder_name',
            'tax_rate': 'tax_rate',
            'tables': 'tables',
            'logo': 'logo',
            'description': 'description',
        }

        for onboard_field, res_field in outlet_field_map.items():
            value = getattr(doc, onboard_field, None)
            if value is not None and value != '':
                setattr(res_doc, res_field, value)

        res_doc.save(ignore_permissions=True)

        # ── Sync to Restaurant Config ───────────────────────────────────────
        config_name = frappe.db.get_value('Outlet Config', {'restaurant': restaurant}, 'name')
        if config_name:
            config_doc = frappe.get_doc('Outlet Config', config_name)

            config_field_map = {
                'tagline': 'tagline',
                'subtitle': 'subtitle',
                'description': 'description',
                'default_theme': 'default_theme',
                'menu_layout': 'menu_layout',
                'enable_table_booking': 'enable_table_booking',
                'enable_banquet_booking': 'enable_banquet_booking',
                'google_review_link': 'google_review_link',
            }
            # Fields with different names between onboarding and config
            config_field_remap = {
                'instagram_link': 'instagram_profile_link',
                'facebook_link': 'facebook_profile_link',
                'whatsapp_number': 'whatsapp_phone_number',
            }

            for onboard_field, config_field in config_field_map.items():
                value = getattr(doc, onboard_field, None)
                if value is not None and value != '':
                    setattr(config_doc, config_field, value)

            for onboard_field, config_field in config_field_remap.items():
                value = getattr(doc, onboard_field, None)
                if value is not None and value != '':
                    setattr(config_doc, config_field, value)

            config_doc.save(ignore_permissions=True)

        # ── Mark onboarding complete ────────────────────────────────────────
        doc.status = 'Completed'
        doc.created_restaurant = restaurant
        doc.finalized_by = frappe.session.user
        doc.finalized_on = now_datetime()
        doc.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            'success': True,
            'message': f'Synced to {res_doc.restaurant_name} successfully',
            'data': {'outlet_id': restaurant}
        }
    except Exception as e:
        frappe.log_error('Sync Onboarding Error', str(e))
        return {'success': False, 'error': str(e)}


# ── Auto-sync onboarding display/branding fields → live Restaurant ────────────
# The Setup Wizard writes logo/tagline/etc. to the Restaurant Onboarding record,
# but the Branding pool, discovery feed, detail page and the app all read the
# LIVE Restaurant (+ its Restaurant Config). Previously these only synced when an
# admin ran sync_onboarding_to_restaurant() manually, so an uploaded logo often
# never reached the app (Branding = 0 assets, inconsistent across outlets). This
# on_update hook copies the *display* fields straight through on every save, so
# branding behaves like gallery/menu media (which already write to live,
# restaurant-keyed tables). Owner/bank/legal fields intentionally stay on the
# manual admin sync.
_ONBOARD_RESTAURANT_DISPLAY = {'logo': 'logo', 'description': 'description'}
_ONBOARD_CONFIG_DISPLAY = {
    'tagline': 'tagline',
    'subtitle': 'subtitle',
    'description': 'description',
}


def auto_sync_onboarding_display(doc, method=None):
    """doc_events on_update hook for `Restaurant Onboarding` — pushes display
    fields (logo/tagline/subtitle/description) to the linked Restaurant + its
    Restaurant Config so a Setup Wizard upload shows up immediately in the
    Branding pool / feed / app. Only copies non-empty values; never clears.
    `logo` is Restaurant-only — Restaurant.logo is the single source of truth
    (Restaurant Config.logo was removed, see the consolidate_logo_to_restaurant patch)."""
    try:
        restaurant = getattr(doc, 'linked_restaurant', None)
        if not restaurant or not frappe.db.exists('Outlet', restaurant):
            return

        r_updates = {}
        for src, dest in _ONBOARD_RESTAURANT_DISPLAY.items():
            value = getattr(doc, src, None)
            if value not in (None, ''):
                r_updates[dest] = value
        if r_updates:
            frappe.db.set_value('Outlet', restaurant, r_updates)

        config = frappe.db.get_value('Outlet Config', {'restaurant': restaurant}, 'name')
        if config:
            c_updates = {}
            for src, dest in _ONBOARD_CONFIG_DISPLAY.items():
                value = getattr(doc, src, None)
                if value not in (None, ''):
                    c_updates[dest] = value
            if c_updates:
                frappe.db.set_value('Outlet Config', config, c_updates)
    except Exception:
        frappe.log_error(frappe.get_traceback(), 'onboarding.auto_sync_onboarding_display')


def backfill_onboarding_display():
    """One-off backfill for outlets whose logo/display fields never synced
    (Branding = 0 assets). Run once after deploy:

        bench --site backend.flamezo.in execute \\
          flamezo_backend.flamezo.api.onboarding.backfill_onboarding_display

    Not whitelisted — bench-only (privileged), so no web exposure."""
    rows = frappe.get_all(
        'Outlet Onboarding',
        filters={'linked_restaurant': ['is', 'set']},
        fields=['name'],
    )
    synced = 0
    for r in rows:
        try:
            auto_sync_onboarding_display(frappe.get_doc('Outlet Onboarding', r['name']))
            synced += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), 'onboarding.backfill_onboarding_display')
    frappe.db.commit()
    print(f'backfill_onboarding_display: synced {synced} onboarding record(s)')
    return synced


# backfill_restaurant_logo_from_config() was removed — `Restaurant Config.logo`
# no longer exists (dropped by the consolidate_logo_to_restaurant patch, which
# ran this exact backfill as part of the migration). Re-adding a function that
# queries `c.logo` here would just crash on the missing column.


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
        doc_name = frappe.db.get_value('Outlet Onboarding', {'unique_token': token}, 'name')
        if not doc_name:
            return {'success': False, 'error': 'Invalid or expired onboarding session'}

        # Check status
        status = frappe.db.get_value('Outlet Onboarding', doc_name, 'status')
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
            dt='Outlet Onboarding',
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


@frappe.whitelist(allow_guest=True)
def extract_cheque_details(token, base64_image=None):
	"""Onboarding cheque OCR — token-scoped so the guest onboarding form can use
	the same cancelled-cheque extraction as the merchant Direct Bank Payouts page,
	without exposing the AI endpoint to anonymous callers.

	Validates the onboarding token, then runs the existing bank-details OCR and
	returns {success, data:{account_number, ifsc_code, legal_business_name}}.
	"""
	try:
		if not token:
			return {'success': False, 'error': 'Missing onboarding token'}
		if not frappe.db.exists('Outlet Onboarding', {'unique_token': token}):
			return {'success': False, 'error': 'Invalid or expired onboarding link'}
		if not base64_image:
			return {'success': False, 'error': 'No image provided'}

		from flamezo_backend.flamezo.api.kyc_ai import extract_bank_details
		return extract_bank_details(base64_image=base64_image)
	except Exception as e:
		frappe.log_error(f"extract_cheque_details failed: {e}", "onboarding.cheque_ocr")
		return {'success': False, 'error': 'Could not read the cheque. Please enter details manually.'}
