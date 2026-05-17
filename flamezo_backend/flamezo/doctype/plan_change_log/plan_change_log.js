// Copyright (c) 2026, Flamezo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Plan Change Log', {
	refresh: function(frm) {
		// Set form as read-only after creation
		if (!frm.is_new()) {
			frm.set_df_property('restaurant', 'read_only', 1);
			frm.set_df_property('previous_plan', 'read_only', 1);
			frm.set_df_property('new_plan', 'read_only', 1);
			frm.set_df_property('changed_by', 'read_only', 1);
		}
	}
});
