# Copyright (c) 2022, Bhavesh Maheshwari and contributors
# For license information, please see license.txt

import re

import frappe
import requests
from frappe import _


def _get_wati_settings():
	settings = frappe.get_single("Wati Setting")
	if not settings.url or not settings.token:
		frappe.throw(_("URL and Token are mandatory in Wati Setting"))
	return settings


def _wati_headers(token):
	return {
		"Authorization": f"Bearer {token}",
		"Accept": "application/json",
		"Content-Type": "application/json",
	}


def _normalize_base_url(url):
	return (url or "").rstrip("/")


def _parse_header(header):
	"""Return (header_type, header_document_variable) from WATI header payload."""
	if not header:
		return "None", ""

	header_type = "None"
	header_var = ""

	if isinstance(header, str):
		# Text header or raw string with {{var}}
		vars_found = re.findall(r"\{\{?\s*([^{}]+?)\s*\}?\}", header)
		if vars_found:
			header_var = vars_found[0].strip()
			header_type = "Document"
		elif header.strip():
			header_type = "Text"
		return header_type, header_var

	if isinstance(header, dict):
		raw_type = (
			header.get("type")
			or header.get("headerType")
			or header.get("format")
			or header.get("mediaType")
			or ""
		)
		raw_type = str(raw_type).strip()
		type_map = {
			"0": "None",
			"1": "Text",
			"2": "Image",
			"3": "Video",
			"4": "Document",
			"text": "Text",
			"image": "Image",
			"video": "Video",
			"document": "Document",
			"doc": "Document",
			"none": "None",
		}
		header_type = type_map.get(raw_type.lower(), raw_type.title() if raw_type else "None")

		text = header.get("text") or header.get("link") or header.get("mediaLink") or ""
		vars_found = re.findall(r"\{\{?\s*([^{}]+?)\s*\}?\}", str(text))
		if vars_found:
			header_var = vars_found[0].strip()

		param_map = header.get("headerParamMapping") or header.get("paramMapping") or {}
		if isinstance(param_map, dict) and not header_var:
			for key, val in param_map.items():
				if val:
					header_var = str(val).strip().strip("{}")
					break
				if key:
					header_var = str(key).strip().strip("{}")
					break

		if header_type in ("Document", "Image", "Video") and not header_var:
			# common WATI / Meta style media placeholders
			header_var = "pdflink" if header_type == "Document" else "mediaLink"

		return header_type or "None", header_var

	return "None", ""


def _custom_param_names(custom_params):
	names = []
	if not custom_params:
		return names
	for param in custom_params:
		if isinstance(param, dict):
			name = param.get("name") or param.get("paramName") or param.get("key")
			if name:
				names.append(str(name).strip().strip("{}"))
		elif param:
			names.append(str(param).strip().strip("{}"))
	return names


def _body_variable_names(body, custom_params):
	names = _custom_param_names(custom_params)
	if body:
		found = re.findall(r"\{\{?\s*([^{}]+?)\s*\}?\}", body)
		for name in found:
			name = name.strip()
			if name and name not in names:
				names.append(name)
	return names


def _upsert_message_template(template):
	element_name = template.get("elementName") or template.get("name")
	if not element_name:
		return None

	body = template.get("body") or template.get("bodyOriginal") or ""
	header_type, header_var = _parse_header(template.get("header"))
	custom_params = template.get("customParams") or []

	# Prefer media param from customParams when header is media and var still generic
	if header_type in ("Document", "Image", "Video"):
		for name in _custom_param_names(custom_params):
			lower = name.lower()
			if any(x in lower for x in ("pdf", "link", "url", "media", "document", "header")):
				header_var = name
				break

	variables = _body_variable_names(body, custom_params)
	# Keep header media var out of body variables list if present
	if header_var and header_var in variables:
		variables = [v for v in variables if v != header_var]

	values = {
		"template_message": body,
		"template_variables": ",".join(variables),
		"header_type": header_type if header_type in ("None", "Text", "Image", "Video", "Document") else "None",
		"header_document_variable": header_var if header_type in ("Document", "Image", "Video") else "",
	}

	if frappe.db.exists("Message Template", element_name):
		doc = frappe.get_doc("Message Template", element_name)
		doc.flags.from_wati_sync = True
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Message Template",
				"template_name": element_name,
				**values,
			}
		)
		doc.flags.from_wati_sync = True
		doc.insert(ignore_permissions=True)

	return element_name


@frappe.whitelist()
def sync_message_templates():
	"""Fetch templates from WATI getMessageTemplates and upsert Message Template rows."""
	settings = _get_wati_settings()
	base_url = _normalize_base_url(settings.url)
	headers = _wati_headers(settings.token)

	page_number = 1
	page_size = 100
	synced = []
	errors = []

	while True:
		url = f"{base_url}/api/v2/getMessageTemplates"
		params = {"pageNumber": page_number, "pageSize": page_size}
		response = requests.get(url, headers=headers, params=params, timeout=60)

		if response.status_code != 200:
			frappe.throw(
				_("WATI getMessageTemplates failed ({0}): {1}").format(
					response.status_code, response.text[:500]
				)
			)

		payload = response.json() if response.text else {}
		templates = payload.get("messageTemplates") or payload.get("result") or []
		if isinstance(templates, dict):
			templates = templates.get("messageTemplates") or []

		if not templates:
			break

		for template in templates:
			try:
				name = _upsert_message_template(template)
				if name:
					synced.append(name)
			except Exception:
				frappe.log_error(
					title="WATI Template Sync Error",
					message=frappe.get_traceback(),
				)
				errors.append(template.get("elementName") or template.get("id") or "?")

		link = payload.get("link") or {}
		total = link.get("total") or payload.get("total")
		if total is not None and page_number * page_size >= int(total):
			break
		if len(templates) < page_size:
			break
		if not link.get("nextPage"):
			# stop if API does not advertise another page and we got a short page
			if len(templates) < page_size:
				break
		page_number += 1
		if page_number > 50:
			break

	frappe.db.commit()
	msg = _("Synced {0} template(s) from WATI").format(len(synced))
	if errors:
		msg += ". " + _("Failed: {0}").format(", ".join(errors[:10]))
	return {"synced": synced, "failed": errors, "message": msg}
