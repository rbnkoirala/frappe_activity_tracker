"""
Report: Time Per Doctype
Shows total active time (seconds and hours) spent per DocType,
optionally filtered by user and date range.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("DocType"),
			"fieldname": "ref_doctype",
			"fieldtype": "Link",
			"options": "DocType",
			"width": 200,
		},
		{
			"label": _("Sessions"),
			"fieldname": "sessions",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Active Time (s)"),
			"fieldname": "active_time",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Active Time (hrs)"),
			"fieldname": "active_hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 150,
		},
		{
			"label": _("Idle Time (s)"),
			"fieldname": "idle_time",
			"fieldtype": "Int",
			"width": 130,
		},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			COALESCE(`ref_doctype`, 'Unknown')   AS ref_doctype,
			COUNT(*)                              AS sessions,
			SUM(`active_time`)                    AS active_time,
			ROUND(SUM(`active_time`) / 3600, 2)  AS active_hours,
			SUM(`idle_time`)                      AS idle_time
		FROM `tabUser Activity Log`
		WHERE `ref_doctype` IS NOT NULL
		  AND `ref_doctype` != ''
		  {conditions}
		GROUP BY `ref_doctype`
		ORDER BY active_time DESC
		""",
		values,
		as_dict=True,
	)


def build_conditions(filters):
	conditions = ""
	values = {}
	if filters.get("user"):
		conditions += " AND `user` = %(user)s"
		values["user"] = filters["user"]
	if filters.get("from_date"):
		conditions += " AND DATE(`creation`) >= %(from_date)s"
		values["from_date"] = getdate(filters["from_date"])
	if filters.get("to_date"):
		conditions += " AND DATE(`creation`) <= %(to_date)s"
		values["to_date"] = getdate(filters["to_date"])
	return conditions, values
