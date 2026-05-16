// Copyright (c) 2025, Hetvi Patel and contributors
// For license information, please see license.txt

frappe.ui.form.on("Legacy Content", {
	refresh(frm) {
		// Add R2 upload buttons for media fields
		if (!frm.is_new() && frappe.r2_media) {
			frappe.r2_media.add_upload_button(frm, 'hero_media_src', 'legacy_hero_media', {
				accept: 'image/*,video/*'
			});
			frappe.r2_media.add_upload_button(frm, 'hero_fallback_image', 'legacy_hero_fallback');
			frappe.r2_media.add_upload_button(frm, 'footer_media_src', 'legacy_footer_media', {
				accept: 'image/*,video/*'
			});
		}
	}
});
