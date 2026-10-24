# Copyright (c) 2022, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class WatiSetting(Document):
	def validate(self):
		self._validate_single_default_account()

	def _validate_single_default_account(self):
		"""At most one Wati Setting may be marked as Default Wati Account."""
		if not cint(self.default_wati_account):
			return

		other = frappe.db.get_value(
			"Wati Setting",
			{
				"default_wati_account": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if other:
			frappe.throw(
				_(
					"Wati Setting {0} is already marked as Default Wati Account. "
					"Uncheck it before setting another default."
				).format(frappe.bold(other))
			)
