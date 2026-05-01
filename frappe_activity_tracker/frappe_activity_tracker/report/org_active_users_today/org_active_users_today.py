"""
Report: Org Active Users Today
Shows all users who have been active today with their total active time,
idle time, productivity score and session count.
Intended for the Activity Tracker Dashboard – Organisation Overview section.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import today


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
            "label": _("Sessions"),
            "fieldname": "sessions",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Active Time (hrs)"),
            "fieldname": "active_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 150,
        },
        {
            "label": _("Idle Time (hrs)"),
            "fieldname": "idle_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 140,
        },
        {
            "label": _("Productivity (%)"),
            "fieldname": "productivity_score",
            "fieldtype": "Float",
            "precision": 2,
            "width": 150,
        },
        {
            "label": _("Pages Visited"),
            "fieldname": "pages_visited",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": _("Doctypes Accessed"),
            "fieldname": "doctypes_accessed",
            "fieldtype": "Int",
            "width": 160,
        },
        {
            "label": _("Button Clicks"),
            "fieldname": "button_clicks",
            "fieldtype": "Int",
            "width": 130,
        },
    ]


def get_data(filters):
    target_date = filters.get("date") or today()

    activity = frappe.db.sql(
        """
        SELECT
            ual.`user`,
            COUNT(*)                                                               AS sessions,
            ROUND(SUM(ual.`active_time`) / 3600, 2)                               AS active_hours,
            ROUND(SUM(ual.`idle_time`) / 3600, 2)                                 AS idle_hours,
            ROUND(
                SUM(ual.`active_time`) /
                NULLIF(SUM(ual.`active_time`) + SUM(ual.`idle_time`), 0) * 100
            , 2)                                                                   AS productivity_score,
            COUNT(DISTINCT ual.`route`)                                            AS pages_visited,
            COUNT(DISTINCT ual.`ref_doctype`)                                      AS doctypes_accessed
        FROM `tabUser Activity Log` ual
        WHERE DATE(ual.`creation`) = %(date)s
        GROUP BY ual.`user`
        ORDER BY active_hours DESC
        """,
        {"date": target_date},
        as_dict=True,
    )

    # Enrich with button click counts
    clicks = frappe.db.sql(
        """
        SELECT `user`, COUNT(*) AS cnt
        FROM `tabButton Click Log`
        WHERE DATE(`creation`) = %(date)s
        GROUP BY `user`
        """,
        {"date": target_date},
        as_dict=True,
    )
    click_map = {r.user: r.cnt for r in clicks}

    for row in activity:
        row["button_clicks"] = click_map.get(row["user"], 0)

    return activity
