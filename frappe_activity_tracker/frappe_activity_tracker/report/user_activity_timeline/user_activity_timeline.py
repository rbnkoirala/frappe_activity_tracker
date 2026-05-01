"""
Report: User Activity Timeline
Shows hour-by-hour activity for a specific user on a given date.
Use as a drill-down view from the User Performance section.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import today, getdate


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
            "width": 110,
        },
        {
            "label": _("Hour"),
            "fieldname": "hour_of_day",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "label": _("Route / Page"),
            "fieldname": "route",
            "fieldtype": "Data",
            "width": 260,
        },
        {
            "label": _("View Type"),
            "fieldname": "view_type",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("DocType"),
            "fieldname": "ref_doctype",
            "fieldtype": "Link",
            "options": "DocType",
            "width": 180,
        },
        {
            "label": _("Active Time (s)"),
            "fieldname": "active_time",
            "fieldtype": "Int",
            "width": 140,
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
            `user`,
            DATE(`creation`)         AS date,
            HOUR(`creation`)         AS hour_of_day,
            `route`,
            `view_type`,
            `ref_doctype`,
            `active_time`,
            `idle_time`
        FROM `tabUser Activity Log`
        WHERE 1=1
          {conditions}
        ORDER BY `creation` ASC
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
    if filters.get("date"):
        conditions += " AND DATE(`creation`) = %(date)s"
        values["date"] = getdate(filters["date"])
    else:
        conditions += " AND DATE(`creation`) = %(date)s"
        values["date"] = today()
    if filters.get("view_type"):
        conditions += " AND `view_type` = %(view_type)s"
        values["view_type"] = filters["view_type"]
    return conditions, values
