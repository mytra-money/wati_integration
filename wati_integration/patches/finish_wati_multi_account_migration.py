# Copyright (c) 2026, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

"""Finish multi-account migration when the first patch ran before schema sync.

Creates a Default Wati Setting if missing (credentials must be re-entered),
then renames/backfills Message Templates and related Links.
"""

from __future__ import annotations

import frappe

from wati_integration.patches.migrate_wati_setting_to_multi_account import (
	DEFAULT_ACCOUNT_NAME,
	_backfill_link,
	_rename_and_backfill_templates,
	_update_template_links_on_setting,
)


def execute():
	log = frappe.logger("wati_integration.finish_wati_multi_account_migration")

	if frappe.get_meta("Wati Setting").issingle:
		return
	if not frappe.db.table_exists("Wati Setting"):
		return

	account_name = frappe.db.get_value("Wati Setting", {}, "name", order_by="creation asc")

	if not account_name:
		# Singles may already have been cleared by an early patch run.
		# Create a disabled placeholder so template backfill can proceed.
		doc = frappe.get_doc(
			{
				"doctype": "Wati Setting",
				"account_name": DEFAULT_ACCOUNT_NAME,
				"enabled": 0,
				"url": "https://live-mt-server.wati.io",
				"whatsapp_number": "0000000000",
				"token": "REPLACE_ME",
			}
		)
		doc.insert(ignore_permissions=True)
		account_name = doc.name
		log.warning(
			"Created disabled Wati Setting %s with placeholder credentials. "
			"Update URL / Whatsapp Number / Token before sending.",
			account_name,
		)
		print(
			f"WARNING: Created Wati Setting '{account_name}' with placeholder credentials. "
			"Update URL, Whatsapp Number, and Token before use."
		)

	_rename_and_backfill_templates(account_name, log)
	_backfill_link("Wati Message Rule", "wati_setting", account_name)
	_backfill_link("Send Wati Message", "wati_setting", account_name)
	_backfill_link("Wati Message Log", "wati_setting", account_name)
	_update_template_links_on_setting(account_name)
