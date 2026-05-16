// Client script for Menu Product DocType
// Validates Product Media:
// - Maximum 3 media items per product
// - Maximum 1 video per product
// - File type must match media_type (image files for image, video files for video)
// - Integrates with Cloudflare R2 media architecture

frappe.ui.form.on('Menu Product', {
	product_name: function(frm) {
		// Auto-generate product_id from product_name when product_name changes
		if (frm.doc.product_name && !frm.doc.__islocal) {
			// Only update if document is saved (not new)
			// The server-side before_save will handle the update
		}
	},
	
	product_media_add: function(frm) {
		validate_product_media(frm);
	},
	
	'product_media': {
		media_type: function(frm, cdt, cdn) {
			// Validate when media type changes
			validate_media_file_type(frm, cdt, cdn);
			validate_product_media(frm);
		},
		media_url: function(frm, cdt, cdn) {
			// Validate when file is uploaded
			validate_media_file_type(frm, cdt, cdn);
		}
	},
	
	refresh: function(frm) {
		// Hide product_id field for new documents
		if (frm.is_new()) {
			frm.set_df_property('product_id', 'hidden', 1);
		} else {
			// Show product_id field for saved documents
			frm.set_df_property('product_id', 'hidden', 0);
		}
		
		// Initialize media uploader
		if (!frm.is_new() && window.flamezo_backend && window.flamezo_backend.media) {
			frm.media_uploader = new window.flamezo_backend.media.ProductMediaUploader(frm);
		}
		
		// Add custom upload button
		if (!frm.is_new()) {
			setup_media_upload_button(frm);
		}
		
		// Validate media on refresh
		validate_product_media(frm);
	},
	
	validate: function(frm) {
		// Final validation before save
		validate_product_media(frm);
	}
});

function validate_product_media(frm) {
	if (!frm.doc.product_media) return;
	
	let media_count = frm.doc.product_media.length;
	let video_count = 0;
	
	// Count videos
	frm.doc.product_media.forEach(function(row) {
		if (row.media_type === 'video') {
			video_count++;
		}
	});
	
	// Check maximum 3 media items
	if (media_count > 3) {
		frappe.msgprint({
			title: __('Maximum Media Items Exceeded'),
			message: __('Maximum 3 media items allowed per product. Please remove excess items.'),
			indicator: 'red'
		});
		frappe.validated = false;
		return false;
	}
	
	// Check maximum 1 video
	if (video_count > 1) {
		frappe.msgprint({
			title: __('Maximum Videos Exceeded'),
			message: __('Maximum 1 video allowed per product. Please remove excess videos.'),
			indicator: 'red'
		});
		frappe.validated = false;
		return false;
	}
	
	return true;
}

function validate_media_file_type(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.media_url || !row.media_type) return;
	
	// Get file extension
	let file_url = row.media_url;
	let file_extension = '';
	
	if (file_url) {
		// Extract extension from file path
		let parts = file_url.split('.');
		if (parts.length > 1) {
			file_extension = parts[parts.length - 1].toLowerCase();
		}
	}
	
	// Define valid extensions
	let image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'];
	let video_extensions = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv'];
	
	// Validate file type matches media_type
	if (row.media_type === 'image') {
		if (file_extension && !image_extensions.includes(file_extension)) {
			frappe.msgprint({
				title: __('Invalid File Type'),
				message: __('Image media type requires an image file (jpg, png, gif, etc.). Please upload an image file or change media type to video.'),
				indicator: 'red'
			});
			// Clear the file if type doesn't match
			row.media_url = '';
			frm.refresh_field('product_media');
			frappe.validated = false;
			return false;
		}
	} else if (row.media_type === 'video') {
		if (file_extension && !video_extensions.includes(file_extension)) {
			frappe.msgprint({
				title: __('Invalid File Type'),
				message: __('Video media type requires a video file (mp4, webm, mov, etc.). Please upload a video file or change media type to image.'),
				indicator: 'red'
			});
			// Clear the file if type doesn't match
			row.media_url = '';
			frm.refresh_field('product_media');
			frappe.validated = false;
			return false;
		}
	}
	
	return true;
}

function setup_media_upload_button(frm) {
	// Add custom upload button for R2 direct upload
	if (!frm.fields_dict.product_media) return;
	
	const grid = frm.fields_dict.product_media.grid;
	
	// Add custom button to grid
	if (!grid.custom_buttons_added) {
		grid.add_custom_button(__('Upload to R2'), function() {
			upload_media_to_r2(frm);
		});
		grid.custom_buttons_added = true;
	}
}

function upload_media_to_r2(frm) {
	if (!frm.media_uploader) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}
	
	// Create file input
	const input = document.createElement('input');
	input.type = 'file';
	input.accept = 'image/*,video/*';
	input.multiple = false;
	
	input.onchange = async (e) => {
		const file = e.target.files[0];
		if (!file) return;
		
		const media_type = frm.media_uploader.get_media_type(file);
		
		// Validate before upload
		if (!frm.media_uploader.validate_can_add_media(media_type)) {
			return;
		}
		
		// Add new row
		const row = frappe.model.add_child(frm.doc, 'Product Media', 'product_media');
		row.media_type = media_type;
		row.display_order = frm.doc.product_media.length;
		frm.refresh_field('product_media');
		
		const row_idx = frm.doc.product_media.length - 1;
		
		// Show progress
		frappe.show_progress(__('Uploading to R2'), 30, 100, __('Uploading file...'));
		
		try {
			// Upload to R2
			const result = await frm.media_uploader.upload_file(file, row_idx);
			
			frappe.show_progress(__('Uploading to R2'), 70, 100, __('Processing media...'));
			
			// Wait a bit for processing to start
			await new Promise(resolve => setTimeout(resolve, 2000));
			
			frappe.hide_progress();
			
			frappe.show_alert({
				message: __('Media uploaded successfully! Processing in background...'),
				indicator: 'green'
			}, 5);
			
			// Save the form
			frm.save();
			
		} catch (error) {
			frappe.hide_progress();
			frappe.msgprint({
				title: __('Upload Failed'),
				message: error.message || __('Failed to upload media'),
				indicator: 'red'
			});
			
			// Remove the failed row
			frm.doc.product_media.splice(row_idx, 1);
			frm.refresh_field('product_media');
		}
	};
	
	input.click();
}
