# Copyright (c) 2022, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import re

import frappe
from frappe import _
from frappe.model.document import Document


class MessageTemplate(Document):
	def validate(self):
		if self.flags.from_wati_sync:
			return

		if not self.template_message:
			return

		# Derive comma-separated variable names from {var} / {{var}} placeholders
		res = re.findall(r"\{\{?\s*([^{}]+?)\s*\}?\}", self.template_message)
		self.template_variables = ",".join(dict.fromkeys(res)) if res else ""
