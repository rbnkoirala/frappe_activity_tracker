"""
Report: User Button Click Frequency
Shows how many button clicks each user has performed, broken down by
button label and action type, for a configurable date range.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import getdate, today


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
            "label": _("Button Label"),
            "fieldname": "label",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Action Type"),
            "fieldname": "action_type",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("DocType"),
            "fieldname": "ref_doctype",
            "fieldtype": "Link",
            "options": "DocType",
            "width": 180,
        },
        {
            "label": _("View Type"),
            "fieldname": "view_type",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Click Count"),
            "fieldname": "total_clicks",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Days Active"),
            "fieldname": "days_active",
            "fieldtype": "Int",
            "width": 110,
        },
    ]


def get_data(filters):
    conditions, values = build_conditions(filters)

    return frappe.db.sql(
        f"""
        SELECT
            `user`,
            `label`,
            COALESCE(`action_type`, 'custom')  AS action_type,
            COALESCE(`ref_doctype`, '')         AS ref_doctype,
            COALESCE(`view_type`, '')           AS view_type,
            COUNT(*)                            AS total_clicks,
            COUNT(DISTINCT DATE(`creation`))    AS days_active
        FROM `tabButton Click Log`
        WHERE 1=1
          {conditions}
        GROUP BY `user`, `label`, `action_type`, `ref_doctype`, `view_type`
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
