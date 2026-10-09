// Copyright (c) 2022, Bhavesh Maheshwari and contributors
// For license information, please see license.txt

frappe.listview_settings["Message Template"] = {
	onload: function (listview) {
		listview.page.add_inner_button(__("Get Templates"), function () {
			frappe.call({
				method: "wati_integration.api.templates.sync_message_templates",
				freeze: true,
				freeze_message: __("Syncing templates from WATI..."),
				callback: function (r) {
					if (!r.message) {
						return;
					}
					frappe.msgprint({
						title: __("Get Templates"),
						message: r.message.message || __("Sync complete"),
						indicator: r.message.failed && r.message.failed.length ? "orange" : "green",
					});
					listview.refresh();
				},
			});
		});
	},
};
