"""
Report: Daily Work Hours
Reads from the Timesheet Auto Log doctype.
Shows total hours worked per user per day.
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
			"label": _("User"),
			"fieldname": "user",
			"fieldtype": "Link",
			"options": "User",
			"width": 200,
		},
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Total Hours"),
			"fieldname": "total_hours",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("DocType Breakdown"),
			"fieldname": "doctype_breakdown",
			"fieldtype": "Data",
			"width": 400,
		},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			`user`,
			`date`,
			`total_hours`,
			`doctype_breakdown`
		FROM `tabTimesheet Auto Log`
		WHERE 1=1
		  {conditions}
		ORDER BY `date` DESC, `total_hours` DESC
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
		conditions += " AND `date` >= %(from_date)s"
		values["from_date"] = getdate(filters["from_date"])
	if filters.get("to_date"):
		conditions += " AND `date` <= %(to_date)s"
		values["to_date"] = getdate(filters["to_date"])
	return conditions, values
