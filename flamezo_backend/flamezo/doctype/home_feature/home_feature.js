frappe.ui.form.on('Home Feature', {
    refresh: function(frm) {
        // Add custom handler for image uploads
        if (frm.doc.image_src) {
            // Show current image
            frm.set_df_property('image_src', 'options', frm.doc.image_src);
        }
    },
    
    before_save: function(frm) {
        // Before saving, ensure we have the latest image reference
        if (frm.doc.image_src) {
            // Log the image being saved
            console.log('Saving Home Feature with image:', frm.doc.image_src);
        }
    },
    
    after_save: function(frm) {
        // After saving, force update Media Assets
        if (frm.doc.image_src && frm.doc.name) {
            frappe.call({
                method: 'flamezo_backend.flamezo.doctype.home_feature.home_feature.update_media_assets_from_ui',
                args: {
                    home_feature_name: frm.doc.name,
                    image_src: frm.doc.image_src
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Background image updated successfully'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    }
});
