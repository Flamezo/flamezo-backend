// Copyright (c) 2025, Flamezo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Restaurant', {
	refresh: function(frm) {
		// Add button to view/download QR codes PDF
		if (frm.doc.tables && frm.doc.tables > 0) {
			// Check if QR codes PDF exists
			frappe.call({
				method: 'flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url',
				args: {
					restaurant: frm.doc.name
				},
				callback: function(r) {
					// Handle both old format (direct URL) and new format (JSON object)
					let pdf_url = null;
					if (r.message) {
						if (typeof r.message === 'string') {
							// Old format - direct URL
							pdf_url = r.message;
						} else if (r.message.pdf_url) {
							// New format - JSON object with pdf_url
							pdf_url = r.message.pdf_url;
						}
					}
					
					// Only show buttons if pdf_url exists and is not null/empty
					if (pdf_url && pdf_url !== null && pdf_url !== '') {
						// Show button to view/download QR codes
						frm.add_custom_button(__('View QR Codes'), function() {
							window.open(pdf_url, '_blank');
						}, __('Actions'));
						
						// Also add a download button
						frm.add_custom_button(__('Download QR Codes PDF'), function() {
							const link = document.createElement('a');
							link.href = pdf_url;
							link.download = `${frm.doc.restaurant_id}_table_qr_codes.pdf`;
							document.body.appendChild(link);
							link.click();
							document.body.removeChild(link);
						}, __('Actions'));
						
						// Add delete PDF button
						frm.add_custom_button(__('Delete QR Codes PDF'), function() {
							frappe.confirm(
								__('Are you sure you want to delete the QR codes PDF? This action cannot be undone.'),
								function() {
									// Yes - delete the PDF
									frappe.call({
										method: 'flamezo_backend.flamezo.doctype.restaurant.restaurant.delete_qr_codes_pdf',
										args: {
											restaurant: frm.doc.name
										},
										freeze: true,
										freeze_message: __('Deleting QR codes PDF...'),
										callback: function(r) {
											// Check if deletion was successful
											let deleted = false;
											if (r.message) {
												if (typeof r.message === 'boolean') {
													deleted = r.message;
												} else if (r.message.status === 'success') {
													deleted = true;
												}
											}
											
											if (deleted) {
												frm.reload_doc();
											}
										}
									});
								},
								function() {
									// No
								}
							);
						}, __('Actions'));
					} else {
						// Show button to generate QR codes
						frm.add_custom_button(__('Generate QR Codes'), function() {
							frappe.confirm(
								__('Generate QR codes PDF for {0} tables?', [frm.doc.tables]),
								function() {
									// Yes
									frappe.call({
										method: 'flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf',
										args: {
											restaurant: frm.doc.name
										},
										freeze: true,
										freeze_message: __('Generating QR codes PDF...'),
										callback: function(r) {
											// Check if generation was successful
											let generated = false;
											if (r.message) {
												if (typeof r.message === 'string') {
													// Old format - direct URL
													generated = true;
												} else if (r.message.status === 'success') {
													// New format - JSON object
													generated = true;
												}
											}
											
											if (generated) {
												frappe.show_alert({
													message: __('QR codes PDF generated successfully'),
													indicator: 'green'
												}, 5);
												frm.reload_doc();
											}
										}
									});
								},
								function() {
									// No
								}
							);
						}, __('Actions'));
					}
				}
			});
		}
	}
});

