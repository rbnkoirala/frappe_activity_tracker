"""
Report: User Interaction Count
Shows the total number of button clicks per user, giving a quick overview
of user engagement and interaction levels within Frappe Desk.
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
			"width": 220,
		},
		{
			"label": _("Total Clicks"),
			"fieldname": "total_clicks",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Unique Actions"),
			"fieldname": "unique_actions",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Unique Buttons"),
			"fieldname": "unique_buttons",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Unique Doctypes"),
			"fieldname": "unique_doctypes",
			"fieldtype": "Int",
			"width": 150,
		},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			`user`,
			COUNT(*)                      AS total_clicks,
			COUNT(DISTINCT `action_type`) AS unique_actions,
			COUNT(DISTINCT `label`)       AS unique_buttons,
			COUNT(DISTINCT `ref_doctype`) AS unique_doctypes
		FROM `tabButton Click Log`
		WHERE 1=1
		  {conditions}
		GROUP BY `user`
		ORDER BY total_clicks DESC
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
