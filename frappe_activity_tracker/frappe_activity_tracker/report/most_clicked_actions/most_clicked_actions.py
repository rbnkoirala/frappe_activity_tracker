"""
Report: Most Clicked Actions
Groups button click events by action_type to show which workflow actions
(save, submit, cancel, delete, …) are performed most often.
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
			"label": _("Action Type"),
			"fieldname": "action_type",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Click Count"),
			"fieldname": "total",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": _("Unique Users"),
			"fieldname": "unique_users",
			"fieldtype": "Int",
			"width": 130,
		},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			COALESCE(`action_type`, 'custom') AS action_type,
			COUNT(*)                           AS total,
			COUNT(DISTINCT `user`)             AS unique_users
		FROM `tabButton Click Log`
		WHERE 1=1
		  {conditions}
		GROUP BY `action_type`
		ORDER BY total DESC
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
