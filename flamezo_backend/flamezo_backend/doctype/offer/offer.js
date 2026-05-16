// Copyright (c) 2025, Hetvi Patel and contributors
// For license information, please see license.txt

frappe.ui.form.on("Offer", {
	refresh(frm) {
		// Add R2 upload button for image_src field
		if (!frm.is_new() && frappe.r2_media) {
			frappe.r2_media.add_upload_button(frm, 'image_src', 'offer_image');
		}
	}
});
