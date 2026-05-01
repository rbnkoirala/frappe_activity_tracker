"""
Scheduled background tasks for frappe_activity_tracker.

Both functions are triggered once per day via hooks.py → scheduler_events.
"""
from __future__ import unicode_literals

import json
from datetime import date, timedelta

import frappe
from frappe.utils import today


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yesterday() -> str:
	"""Return yesterday's date string (YYYY-MM-DD)."""
	return str(date.today() - timedelta(days=1))


# ---------------------------------------------------------------------------
# Task 1 – Productivity Summary
# ---------------------------------------------------------------------------

def compute_productivity_summary() -> None:
	"""
	Aggregate User Activity Log for the previous day and upsert a
	Productivity Summary record per user.
	"""
	target_date = _yesterday()

	rows = frappe.db.sql(
		"""
		SELECT
			`user`,
			SUM(`active_time`)  AS total_active_time,
			SUM(`idle_time`)    AS total_idle_time
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(date)s
		GROUP BY `user`
		""",
		{"date": target_date},
		as_dict=True,
	)

	for row in rows:
		active = row.total_active_time or 0
		idle = row.total_idle_time or 0
		total = active + idle
		score = round((active / total) * 100, 2) if total else 0.0

		existing = frappe.db.get_value(
			"Productivity Summary",
			{"user": row.user, "date": target_date},
			"name",
		)
		if existing:
			frappe.db.set_value(
				"Productivity Summary",
				existing,
				{
					"total_active_time": active,
					"total_idle_time": idle,
					"productivity_score": score,
				},
			)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Productivity Summary",
					"user": row.user,
					"date": target_date,
					"total_active_time": active,
					"total_idle_time": idle,
					"productivity_score": score,
				}
			)
			doc.insert(ignore_permissions=True)

	frappe.db.commit()


# ---------------------------------------------------------------------------
# Task 2 – Timesheet Auto Log
# ---------------------------------------------------------------------------

def generate_timesheet_logs() -> None:
	"""
	Group User Activity Log for the previous day by (user, ref_doctype) and
	create/update a Timesheet Auto Log record per user per day.
	"""
	target_date = _yesterday()

	rows = frappe.db.sql(
		"""
		SELECT
			`user`,
			COALESCE(`ref_doctype`, 'Unknown') AS ref_doctype,
			SUM(`active_time`) AS total_seconds
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(date)s
		GROUP BY `user`, `ref_doctype`
		""",
		{"date": target_date},
		as_dict=True,
	)

	# Group by user → {ref_doctype: hours}
	user_map: dict[str, dict] = {}
	for row in rows:
		entry = user_map.setdefault(row.user, {})
		entry[row.ref_doctype] = round((row.total_seconds or 0) / 3600, 4)

	for user, breakdown in user_map.items():
		total_hours = round(sum(breakdown.values()), 4)
		breakdown_json = json.dumps(breakdown)

		existing = frappe.db.get_value(
			"Timesheet Auto Log",
			{"user": user, "date": target_date},
			"name",
		)
		if existing:
			frappe.db.set_value(
				"Timesheet Auto Log",
				existing,
				{
					"total_hours": total_hours,
					"doctype_breakdown": breakdown_json,
				},
			)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Timesheet Auto Log",
					"user": user,
					"date": target_date,
					"total_hours": total_hours,
					"doctype_breakdown": breakdown_json,
					"report_breakdown": "{}",
				}
			)
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
