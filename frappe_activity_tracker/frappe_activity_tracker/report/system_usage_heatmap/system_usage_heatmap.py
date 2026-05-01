"""
Report: System Usage Heatmap
Aggregates activity by day-of-week and hour-of-day to reveal peak usage
patterns across the organisation.  Useful for scheduling maintenance windows
and understanding productivity rhythms.
"""
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import getdate, today
import datetime


# Day-of-week labels (MySQL DAYOFWEEK: 1=Sunday … 7=Saturday)
_DOW_LABELS = {
    1: "Sunday",
    2: "Monday",
    3: "Tuesday",
    4: "Wednesday",
    5: "Thursday",
    6: "Friday",
    7: "Saturday",
}


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Day of Week"),
            "fieldname": "day_of_week",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Hour (0-23)"),
            "fieldname": "hour_of_day",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": _("Active Sessions"),
            "fieldname": "sessions",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": _("Unique Users"),
            "fieldname": "unique_users",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": _("Total Active Time (hrs)"),
            "fieldname": "active_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width": 190,
        },
    ]


def get_data(filters):
    conditions, values = build_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            DAYOFWEEK(`creation`)                  AS dow_num,
            HOUR(`creation`)                       AS hour_of_day,
            COUNT(*)                               AS sessions,
            COUNT(DISTINCT `user`)                 AS unique_users,
            ROUND(SUM(`active_time`) / 3600, 2)   AS active_hours
        FROM `tabUser Activity Log`
        WHERE 1=1
          {conditions}
        GROUP BY DAYOFWEEK(`creation`), HOUR(`creation`)
        ORDER BY dow_num, hour_of_day
        """,
        values,
        as_dict=True,
    )

    for row in rows:
        row["day_of_week"] = _DOW_LABELS.get(row.get("dow_num"), str(row.get("dow_num")))

    return rows


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
        default_from = str(getdate(today_str) - datetime.timedelta(days=90))
        conditions += " AND DATE(`creation`) >= %(from_date)s"
        values["from_date"] = default_from
    if filters.get("to_date"):
        conditions += " AND DATE(`creation`) <= %(to_date)s"
        values["to_date"] = getdate(filters["to_date"])
    return conditions, values
