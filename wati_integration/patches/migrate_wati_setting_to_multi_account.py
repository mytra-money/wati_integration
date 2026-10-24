# Copyright (c) 2026, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

"""Migrate legacy Single Wati Setting to multi-record Wati Setting accounts.

Must run as [post_model_sync] so `tabWati Setting` exists before insert.
"""

from __future__ import annotations

import frappe

DEFAULT_ACCOUNT_NAME = "Default"

LEGACY_FIELDS = (
	"url",
	"whatsapp_number",
	"token",
	"default_proforma_invoice_template",
	"default_payment_link_template",
)


def execute():
	log = frappe.logger("wati_integration.migrate_wati_setting_to_multi_account")

	if frappe.get_meta("Wati Setting").issingle:
		log.warning("Wati Setting is still Single; skipping multi-account migrate")
		return

	if not frappe.db.table_exists("Wati Setting"):
		log.warning("tabWati Setting missing; skipping")
		return

	account_name = _ensure_default_account(log)
	if not account_name:
		account_name = frappe.db.get_value("Wati Setting", {}, "name", order_by="creation asc")
		if not account_name:
			log.info("no Wati Setting account available; nothing to backfill")
			return

	_rename_and_backfill_templates(account_name, log)
	_backfill_link("Wati Message Rule", "wati_setting", account_name)
	_backfill_link("Send Wati Message", "wati_setting", account_name)
	_backfill_link("Wati Message Log", "wati_setting", account_name)
	_update_template_links_on_setting(account_name)
	# Only clean Singles after a successful multi-row account exists
	_cleanup_singles()


def _ensure_default_account(log):
	"""Create Default account from legacy Singles data if needed."""
	if frappe.db.exists("Wati Setting", DEFAULT_ACCOUNT_NAME):
		log.info("Wati Setting %s already exists", DEFAULT_ACCOUNT_NAME)
		return DEFAULT_ACCOUNT_NAME

	existing = frappe.db.get_value("Wati Setting", {}, "name", order_by="creation asc")
	if existing:
		log.info("Wati Setting rows already exist; using %s", existing)
		return existing

	old = _get_old_settings_from_singles()
	if not old:
		log.info("no legacy Wati Setting rows in tabSingles; nothing to migrate")
		return None

	url = (old.get("url") or "").strip()
	token = (old.get("token") or "").strip()
	whatsapp_number = (old.get("whatsapp_number") or "").strip()

	if not url or not token:
		log.info("legacy Singles missing url/token; skipping account create")
		return None

	doc = frappe.get_doc(
		{
			"doctype": "Wati Setting",
			"account_name": DEFAULT_ACCOUNT_NAME,
			"enabled": 1,
			"url": url,
			"whatsapp_number": whatsapp_number or "0000000000",
			"token": token,
			"default_proforma_invoice_template": old.get("default_proforma_invoice_template")
			or "",
			"default_payment_link_template": old.get("default_payment_link_template") or "",
		}
	)
	doc.insert(ignore_permissions=True)
	log.info("created Wati Setting %s from Singles", doc.name)
	return doc.name


def _get_old_settings_from_singles():
	result = frappe.db.sql(
		"""
		SELECT field, value
		FROM `tabSingles`
		WHERE doctype = 'Wati Setting'
		AND field IN %s
		""",
		(LEGACY_FIELDS,),
		as_dict=True,
	)
	if not result:
		return None
	return {row["field"]: row["value"] for row in result}


def _rename_and_backfill_templates(account_name, log):
	"""Stamp wati_setting and rename docs to {account}-{template_name}."""
	if not frappe.db.has_column("Message Template", "wati_setting"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, template_name, wati_setting
		FROM `tabMessage Template`
		""",
		as_dict=True,
	)
	if not rows:
		return

	link_map = {}

	for row in rows:
		wati_setting = (row.wati_setting or "").strip() or account_name
		template_name = (row.template_name or row.name or "").strip()
		if not template_name:
			continue

		new_name = f"{wati_setting}-{template_name}"
		old_name = row.name

		if not (row.wati_setting or "").strip():
			frappe.db.set_value(
				"Message Template",
				old_name,
				"wati_setting",
				wati_setting,
				update_modified=False,
			)

		if old_name == new_name:
			continue

		if frappe.db.exists("Message Template", new_name):
			link_map[old_name] = new_name
			if old_name != new_name:
				frappe.delete_doc(
					"Message Template", old_name, force=True, ignore_permissions=True
				)
			continue

		frappe.rename_doc(
			"Message Template",
			old_name,
			new_name,
			force=True,
			merge=False,
			show_alert=False,
		)
		link_map[old_name] = new_name
		log.info("renamed Message Template %s -> %s", old_name, new_name)

	for old_name, new_name in link_map.items():
		if old_name == new_name:
			continue
		_rewrite_template_link("Wati Message Rule", "message_template", old_name, new_name)
		_rewrite_template_link("Send Wati Message", "message_template", old_name, new_name)
		_rewrite_template_link(
			"Wati Setting", "default_proforma_invoice_template", old_name, new_name
		)
		_rewrite_template_link(
			"Wati Setting", "default_payment_link_template", old_name, new_name
		)


def _rewrite_template_link(doctype, fieldname, old_name, new_name):
	if not frappe.db.table_exists(doctype):
		return
	if not frappe.db.has_column(doctype, fieldname):
		return
	frappe.db.sql(
		f"""
		UPDATE `tab{doctype}`
		SET `{fieldname}` = %s
		WHERE `{fieldname}` = %s
		""",
		(new_name, old_name),
	)


def _backfill_link(doctype, fieldname, account_name):
	if not frappe.db.table_exists(doctype):
		return
	if not frappe.db.has_column(doctype, fieldname):
		return
	frappe.db.sql(
		f"""
		UPDATE `tab{doctype}`
		SET `{fieldname}` = %s
		WHERE `{fieldname}` IS NULL OR `{fieldname}` = ''
		""",
		(account_name,),
	)


def _update_template_links_on_setting(account_name):
	if not frappe.db.exists("Wati Setting", account_name):
		return

	doc = frappe.get_doc("Wati Setting", account_name)
	changed = False
	for field in ("default_proforma_invoice_template", "default_payment_link_template"):
		old = doc.get(field)
		if not old:
			continue
		if frappe.db.exists("Message Template", old):
			continue
		candidate = f"{account_name}-{old}"
		if frappe.db.exists("Message Template", candidate):
			doc.set(field, candidate)
			changed = True
	if changed:
		doc.save(ignore_permissions=True)


def _cleanup_singles():
	if frappe.db.count("Wati Setting") < 1:
		return
	frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'Wati Setting'")
