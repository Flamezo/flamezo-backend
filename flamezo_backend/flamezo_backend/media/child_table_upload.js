/**
 * Child Table Grid R2 Upload Integration
 * 
 * Adds R2 upload capability to child table grids for Attach/Attach Image fields
 */

frappe.provide('frappe.r2_media.grid');

frappe.r2_media.grid = {
	/**
	 * Add R2 upload to child table grid
	 * @param {Object} frm - Parent form object
	 * @param {string} fieldname - Child table fieldname
	 * @param {string} image_field - Image field in child table
	 * @param {Function} get_media_role - Function to get media role for row
	 */
	setup_grid_upload: function(frm, fieldname, image_field, get_media_role) {
		const grid = frm.fields_dict[fieldname].grid;
		
		// Override grid row refresh to add upload buttons
		grid.grid_rows.forEach(row => {
			this.add_upload_button_to_row(frm, row, image_field, get_media_role);
		});
		
		// Add upload button when new rows are added
		grid.on_grid_row_render = (grid_row) => {
			this.add_upload_button_to_row(frm, grid_row, image_field, get_media_role);
		};
	},
	
	/**
	 * Add upload button to a specific grid row
	 */
	add_upload_button_to_row: function(frm, grid_row, image_field, get_media_role) {
		if (!grid_row.doc || !grid_row.doc.name) return;
		
		const field_wrapper = grid_row.grid_form.fields_dict[image_field].$wrapper;
		if (!field_wrapper) return;
		
		// Check if button already exists
		if (field_wrapper.find('.r2-upload-btn').length > 0) return;
		
		// Create file input
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = 'image/*';
		input.style.display = 'none';
		
		input.addEventListener('change', async (e) => {
			const file = e.target.files[0];
			if (!file) return;
			
			const row_name = grid_row.doc.name;
			const parent_doctype = frm.doctype;
			const parent_name = frm.doc.name;
			
			if (!parent_name || frm.doc.__islocal) {
				frappe.msgprint(__('Please save the parent document before uploading files'));
				return;
			}
			
			// Get media role for this row
			const media_role = get_media_role(grid_row.doc);
			const owner_doctype = grid_row.doctype;
			
			// Show progress
			frappe.show_progress(__('Uploading to R2...'), 0, 100, __('Starting upload...'));
			
			try {
				const result = await frappe.r2_media.upload_file(
					file,
					owner_doctype,
					row_name,
					media_role,
					{
						on_progress: (percent) => {
							frappe.show_progress(__('Uploading to R2...'), percent, 100, __(`${percent}% uploaded`));
						}
					}
				);
				
				// Update the row with CDN URL
				frappe.model.set_value(owner_doctype, row_name, image_field, result.primary_url);
				frappe.model.set_value(owner_doctype, row_name, 'media_asset', result.media_asset_id);
				
				frappe.hide_progress();
				frappe.show_alert({
					message: __('File uploaded successfully'),
					indicator: 'green'
				});
				
				// Refresh the grid row
				grid_row.refresh();
				
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
		
		// Add button
		field_wrapper.find('.attached-file-link, .control-value').after(
			$(`<button class="btn btn-xs btn-default r2-upload-btn" style="margin-left: 8px;">
				<i class="fa fa-cloud-upload"></i> R2 Upload
			</button>`).on('click', (e) => {
				e.preventDefault();
				input.click();
			})
		);
		
		// Append input
		field_wrapper.append(input);
	}
};

// Auto-setup for Legacy Content child tables
frappe.ui.form.on("Legacy Content", {
	refresh(frm) {
		if (frm.is_new()) return;
		
		// Setup gallery images upload
		if (frm.fields_dict.gallery_featured_images) {
			frappe.r2_media.grid.setup_grid_upload(
				frm,
				'gallery_featured_images',
				'image',
				() => 'legacy_gallery_image'
			);
		}
		
		// Setup member images upload
		if (frm.fields_dict.members) {
			frappe.r2_media.grid.setup_grid_upload(
				frm,
				'members',
				'image',
				() => 'legacy_member_image'
			);
		}
	}
});

// Auto-setup for Legacy Testimonial child table
frappe.ui.form.on("Legacy Testimonial", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.name) return;
		
		// This will be called when the child table form is rendered
		setTimeout(() => {
			const grid_row = frm.fields_dict.testimonials.grid.grid_rows_by_docname[cdn];
			if (grid_row && grid_row.grid_form) {
				frappe.r2_media.grid.add_upload_button_to_row(
					frm,
					grid_row,
					'avatar',
					() => 'legacy_testimonial_avatar'
				);
			}
		}, 100);
	}
});
