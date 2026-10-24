# Copyright (c) 2022, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_default_wati_setting_name():
	"""Return name of the Wati Setting with Default Wati Account checked, or None."""
	return frappe.db.get_value(
		"Wati Setting",
		{"default_wati_account": 1, "enabled": 1},
		"name",
	)


def get_wati_setting(name=None):
	"""Return a Wati Setting document by name, or the default account if name is empty."""
	name = (name or "").strip() or get_default_wati_setting_name()
	if not name:
		frappe.throw(
			_(
				"Wati Setting is required. Pass an account or mark one Wati Setting "
				"as Default Wati Account."
			)
		)
	return frappe.get_doc("Wati Setting", name)


def validate_wati_setting_credentials(settings):
	"""Throw if URL, WhatsApp number, or token is missing."""
	if not settings.url or not settings.get("whatsapp_number") or not settings.get("token"):
		frappe.throw(
			_("URL, Whatsapp Number and Token are mandatory in Wati Setting {0}").format(
				frappe.bold(settings.name)
			)
		)
	if settings.get("enabled") is not None and not settings.enabled:
		frappe.throw(_("Wati Setting {0} is disabled").format(frappe.bold(settings.name)))
