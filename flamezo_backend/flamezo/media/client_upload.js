/**
 * Centralized R2 Media Upload System for Frappe Client
 * 
 * This provides a unified interface for uploading media to R2 from any DocType form.
 * Usage:
 *   frappe.r2_media.upload_file(file, doctype, docname, media_role, options)
 */

frappe.provide('frappe.r2_media');

frappe.r2_media = {
	/**
	 * Upload a file to R2 and create Media Asset
	 * @param {File} file - The file to upload
	 * @param {string} owner_doctype - Owner DocType (e.g., "Event", "Offer")
	 * @param {string} owner_name - Owner document name
	 * @param {string} media_role - Media role (e.g., "event_image", "offer_image")
	 * @param {Object} options - Additional options
	 * @param {string} options.alt_text - Alt text for images
	 * @param {string} options.caption - Caption
	 * @param {number} options.display_order - Display order
	 * @param {Function} options.on_progress - Progress callback (percent)
	 * @param {Function} options.on_success - Success callback (media_asset_data)
	 * @param {Function} options.on_error - Error callback (error)
	 * @returns {Promise} - Resolves with media asset data
	 */
	upload_file: async function(file, owner_doctype, owner_name, media_role, options = {}) {
		try {
			// Step 1: Request upload session
			const session_response = await frappe.call({
				method: 'flamezo_backend.flamezo.media.api.request_upload_session',
				args: {
					owner_doctype: owner_doctype,
					owner_name: owner_name,
					media_role: media_role,
					filename: file.name,
					content_type: file.type,
					size_bytes: file.size
				}
			});

			if (!session_response.message || !session_response.message.upload_url) {
				throw new Error('Invalid upload session response');
			}

			const session = session_response.message;

			// Step 2: Upload directly to R2 using presigned PUT URL
			const xhr = new XMLHttpRequest();
			
			// Track upload progress
			if (options.on_progress) {
				xhr.upload.addEventListener('progress', (e) => {
					if (e.lengthComputable) {
						const percent = Math.round((e.loaded / e.total) * 100);
						options.on_progress(percent);
					}
				});
			}

			// Perform the upload
			await new Promise((resolve, reject) => {
				xhr.open('PUT', session.upload_url, true);
				
				// Set headers from session
				if (session.headers) {
					Object.keys(session.headers).forEach(key => {
						xhr.setRequestHeader(key, session.headers[key]);
					});
				}

				xhr.onload = function() {
					if (xhr.status >= 200 && xhr.status < 300) {
						resolve();
					} else {
						reject(new Error(`R2 upload failed: ${xhr.status}`));
					}
				};

				xhr.onerror = function() {
					reject(new Error('R2 upload network error'));
				};

				xhr.send(file);
			});

			// Step 3: Confirm upload and create Media Asset
			const confirm_response = await frappe.call({
				method: 'flamezo_backend.flamezo.media.api.confirm_upload',
				args: {
					upload_id: session.upload_id,
					owner_doctype: owner_doctype,
					owner_name: owner_name,
					media_role: media_role,
					alt_text: options.alt_text || '',
					caption: options.caption || '',
					display_order: options.display_order || 0
				}
			});

			const result = confirm_response.message;

			if (options.on_success) {
				options.on_success(result);
			}

			return result;

		} catch (error) {
			if (options.on_error) {
				options.on_error(error);
			}
			throw error;
		}
	},

	/**
	 * Add R2 upload button to a form field
	 * @param {Object} frm - Frappe form object
	 * @param {string} fieldname - Field name (Attach or Attach Image)
	 * @param {string} media_role - Media role for this field
	 * @param {Object} options - Additional options
	 */
	add_upload_button: function(frm, fieldname, media_role, options = {}) {
		const field = frm.fields_dict[fieldname];
		if (!field) return;

		// Create file input
		const input = document.createElement('input');
		input.type = 'file';
		input.style.display = 'none';
		
		// Set accept attribute based on field type
		const field_df = frm.get_field(fieldname).df;
		if (field_df.fieldtype === 'Attach Image') {
			input.accept = 'image/*';
		} else if (options.accept) {
			input.accept = options.accept;
		}

		input.addEventListener('change', async (e) => {
			const file = e.target.files[0];
			if (!file) return;

			if (!frm.doc.name || frm.doc.__islocal) {
				frappe.msgprint(__('Please save the document before uploading files'));
				return;
			}

			// Show progress
			frappe.show_progress(__('Uploading to R2...'), 0, 100, __('Starting upload...'));

			try {
				const result = await frappe.r2_media.upload_file(
					file,
					frm.doctype,
					frm.doc.name,
					media_role,
					{
						on_progress: (percent) => {
							frappe.show_progress(__('Uploading to R2...'), percent, 100, __(`${percent}% uploaded`));
						}
					}
				);

				// Update field with CDN URL
				frm.set_value(fieldname, result.primary_url);
				frappe.hide_progress();
				frappe.show_alert({
					message: __('File uploaded successfully'),
					indicator: 'green'
				});

				// Refresh field
				frm.refresh_field(fieldname);

			} catch (error) {
				frappe.hide_progress();
				frappe.msgprint({
					title: __('Upload Failed'),
					message: error.message || __('Failed to upload file'),
					indicator: 'red'
				});
			}

			// Reset input
			input.value = '';
		});

		// Add button to field
		field.$wrapper.find('.attached-file-link, .control-value').after(
			$(`<button class="btn btn-xs btn-default" style="margin-left: 8px;">
				<i class="fa fa-cloud-upload"></i> Upload to R2
			</button>`).on('click', () => input.click())
		);

		// Append input to wrapper
		field.$wrapper.append(input);
	},

	/**
	 * Get media role from field name (smart defaults)
	 * @param {string} doctype - DocType name
	 * @param {string} fieldname - Field name
	 * @returns {string} - Media role
	 */
	get_media_role: function(doctype, fieldname) {
		const role_map = {
			'Event': { 'image_src': 'event_image' },
			'Offer': { 'image_src': 'offer_image' },
			'Legacy Content': {
				'hero_media_src': 'legacy_hero_media',
				'hero_fallback_image': 'legacy_hero_fallback',
				'footer_media_src': 'legacy_footer_media'
			},
			'Legacy Member': { 'image': 'legacy_member_image' },
			'Legacy Testimonial': { 'avatar': 'legacy_testimonial_avatar' }
		};

		if (role_map[doctype] && role_map[doctype][fieldname]) {
			return role_map[doctype][fieldname];
		}

		// Default: doctype_fieldname
		return `${doctype.toLowerCase().replace(/ /g, '_')}_${fieldname}`;
	}
};
