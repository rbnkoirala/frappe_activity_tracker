"""
Report: Productivity Score Per User
Reads from the pre-aggregated Productivity Summary doctype.
Shows daily productivity scores per user.
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
			"label": _("Active Time (s)"),
			"fieldname": "total_active_time",
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
			"fieldname": "total_idle_time",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": _("Productivity Score (%)"),
			"fieldname": "productivity_score",
			"fieldtype": "Float",
			"precision": 2,
			"width": 180,
		},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			`user`,
			`date`,
			`total_active_time`,
			ROUND(`total_active_time` / 3600, 2) AS active_hours,
			`total_idle_time`,
			`productivity_score`
		FROM `tabProductivity Summary`
		WHERE 1=1
		  {conditions}
		ORDER BY `date` DESC, `productivity_score` DESC
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
