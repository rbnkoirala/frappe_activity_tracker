"""
Report: User Idle Active Breakdown
Shows daily active vs idle time and productivity score per user.
Covers a configurable date range for trend analysis.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import getdate, today
import datetime


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
            "label": _("Date"),
            "fieldname": "date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Active Time (hrs)"),
            "fieldname": "active_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 155,
        },
        {
            "label": _("Idle Time (hrs)"),
            "fieldname": "idle_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 145,
        },
        {
            "label": _("Total Time (hrs)"),
            "fieldname": "total_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 145,
        },
        {
            "label": _("Active %"),
            "fieldname": "active_pct",
            "fieldtype": "Float",
            "precision": 2,
            "width": 100,
        },
        {
            "label": _("Idle %"),
            "fieldname": "idle_pct",
            "fieldtype": "Float",
            "precision": 2,
            "width": 90,
        },
        {
            "label": _("Productivity Score (%)"),
            "fieldname": "productivity_score",
            "fieldtype": "Float",
            "precision": 2,
            "width": 185,
        },
    ]


def get_data(filters):
    conditions, values = build_conditions(filters)

    return frappe.db.sql(
        f"""
        SELECT
            `user`,
            DATE(`creation`)                                                             AS date,
            ROUND(SUM(`active_time`) / 3600, 2)                                         AS active_hours,
            ROUND(SUM(`idle_time`) / 3600, 2)                                            AS idle_hours,
            ROUND((SUM(`active_time`) + SUM(`idle_time`)) / 3600, 2)                    AS total_hours,
            ROUND(
                SUM(`active_time`) /
                NULLIF(SUM(`active_time`) + SUM(`idle_time`), 0) * 100
            , 2)                                                                         AS active_pct,
            ROUND(
                SUM(`idle_time`) /
                NULLIF(SUM(`active_time`) + SUM(`idle_time`), 0) * 100
            , 2)                                                                         AS idle_pct,
            ROUND(
                SUM(`active_time`) /
                NULLIF(SUM(`active_time`) + SUM(`idle_time`), 0) * 100
            , 2)                                                                         AS productivity_score
        FROM `tabUser Activity Log`
        WHERE 1=1
          {conditions}
        GROUP BY `user`, DATE(`creation`)
        ORDER BY date DESC, active_hours DESC
        """,
        values,
        as_dict=True,
    )


def build_conditions(filters):
    today_str = today()
    conditions = ""
    values = {}
    if filters.get("user"):
        conditions += " AND `user` = %(user)s"
        values["user"] = filters["user"]
    if filters.get("from_date"):
        conditions += " AND DATE(`creation`) >= %(from_date)s"
        values["from_date"] = getdate(filters["from_date"])
    else:
        default_from = str(getdate(today_str) - datetime.timedelta(days=30))
        conditions += " AND DATE(`creation`) >= %(from_date)s"
        values["from_date"] = default_from
    if filters.get("to_date"):
        conditions += " AND DATE(`creation`) <= %(to_date)s"
        values["to_date"] = getdate(filters["to_date"])
    return conditions, values
