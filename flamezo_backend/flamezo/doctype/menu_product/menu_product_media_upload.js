// Media Upload Handler for Menu Product
// Handles direct upload to Cloudflare R2 via new media architecture

frappe.provide('flamezo_backend.media');

flamezo_backend.media.ProductMediaUploader = class {
	constructor(frm) {
		this.frm = frm;
	}

	async upload_file(file, row_idx) {
		const media_type = this.get_media_type(file);
		const media_role = media_type === 'video' ? 'product_video' : 'product_image';
		
		try {
			// Step 1: Request upload session
			const session = await this.request_upload_session(file, media_role);
			
			// Step 2: Upload to R2
			await this.upload_to_r2(file, session);
			
			// Step 3: Confirm upload
			const result = await this.confirm_upload(session, row_idx);
			
			// Step 4: Update the row with Media Asset info
			this.update_product_media_row(row_idx, result, media_type);
			
			return result;
		} catch (error) {
			console.error('Upload failed:', error);
			throw error;
		}
	}

	async request_upload_session(file, media_role) {
		const response = await frappe.call({
			method: 'flamezo_backend.flamezo.media.api.request_upload_session',
			args: {
				owner_doctype: 'Menu Product',
				owner_name: this.frm.doc.name,
				media_role: media_role,
				filename: file.name,
				content_type: file.type,
				size_bytes: file.size
			}
		});

		if (!response.message) {
			throw new Error('Failed to request upload session');
		}

		return response.message;
	}

	async upload_to_r2(file, session) {
		// Backend issues a presigned PUT URL, so we must PUT the raw file bytes.
		const response = await fetch(session.upload_url, {
			method: 'PUT',
			headers: {
				...(session.headers || {}),
			},
			body: file
		});

		if (!response.ok) {
			throw new Error(`R2 upload failed: ${response.status}`);
		}

		return response;
	}

	async confirm_upload(session, row_idx) {
		const row = this.frm.doc.product_media[row_idx];
		
		const response = await frappe.call({
			method: 'flamezo_backend.flamezo.media.api.confirm_upload',
			args: {
				upload_id: session.upload_id,
				owner_doctype: 'Menu Product',
				owner_name: this.frm.doc.name,
				media_role: row.media_type === 'video' ? 'product_video' : 'product_image',
				alt_text: row.alt_text || '',
				caption: row.caption || '',
				display_order: row.display_order || row_idx + 1
			}
		});

		if (!response.message) {
			throw new Error('Failed to confirm upload');
		}

		return response.message;
	}

	update_product_media_row(row_idx, result, media_type) {
		const row = this.frm.doc.product_media[row_idx];
		
		// Update row with Media Asset reference and CDN URL
		frappe.model.set_value(row.doctype, row.name, {
			'media_asset': result.media_id,
			'media_url': result.primary_url || '',
			'media_type': media_type
		});
		
		this.frm.refresh_field('product_media');
	}

	get_media_type(file) {
		const video_extensions = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv'];
		const extension = file.name.split('.').pop().toLowerCase();
		
		if (file.type.startsWith('video/') || video_extensions.includes(extension)) {
			return 'video';
		}
		return 'image';
	}

	validate_can_add_media(media_type) {
		const current_count = this.frm.doc.product_media ? this.frm.doc.product_media.length : 0;
		const video_count = this.frm.doc.product_media ? 
			this.frm.doc.product_media.filter(m => m.media_type === 'video').length : 0;

		if (current_count >= 3) {
			frappe.throw(__('Maximum 3 media items allowed per product'));
			return false;
		}

		if (media_type === 'video' && video_count >= 1) {
			frappe.throw(__('Maximum 1 video allowed per product'));
			return false;
		}

		return true;
	}
};

// Export for use in menu_product.js
window.flamezo_backend = window.flamezo_backend || {};
window.flamezo_backend.media = window.flamezo_backend.media || {};
window.flamezo_backend.media.ProductMediaUploader = flamezo_backend.media.ProductMediaUploader;
