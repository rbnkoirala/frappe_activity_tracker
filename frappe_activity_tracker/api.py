from __future__ import unicode_literals

import datetime
import json

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from frappe_activity_tracker.install import APP_DOCTYPES

# Minimum active time (seconds) to be worth recording
MIN_ACTIVE_SECONDS = 10

# Maximum number of entries accepted in a single batch call
MAX_BATCH_ENTRIES = 200

_VIEWER_ROLES = frozenset(["Activity Tracker Viewer", "System Manager"])


def _require_viewer_role():
	"""Raise PermissionError if the current user lacks the dashboard viewer role."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	user_roles = set(frappe.get_roles(user))
	if not (_VIEWER_ROLES & user_roles):
		frappe.throw(
			_(
				"You do not have permission to access Activity Tracker dashboards. "
				"Please contact your administrator to be assigned the "
				"'Activity Tracker Viewer' role."
			),
			frappe.PermissionError,
		)


@frappe.whitelist()
def track_time(logs: str | list) -> dict:
	"""
	Accept a JSON-serialised array of activity log entries and bulk-insert
	them into *User Activity Log*.

	Each entry must contain::

		{
		    "route":       "/app/doctype/...",
		    "view_type":   "Form | List | Report | Workspace | Page",
		    "ref_doctype": "Sales Invoice",   # optional
		    "docname":     "SI-0001",          # optional
		    "active_time": 45,                 # seconds
		    "idle_time":   15                  # seconds
		}

	The server-side ``session_id`` and ``user`` are injected automatically so
	the client cannot spoof them.
	"""
	if isinstance(logs, str):
		try:
			logs = json.loads(logs)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid JSON payload"), frappe.ValidationError)

	if not isinstance(logs, list):
		frappe.throw(_("Payload must be a JSON array"), frappe.ValidationError)

	if len(logs) > MAX_BATCH_ENTRIES:
		frappe.throw(
			_("Batch too large: maximum {0} entries per call").format(MAX_BATCH_ENTRIES),
			frappe.ValidationError,
		)

	user = frappe.session.user
	session_id = frappe.session.sid
	now = now_datetime()

	rows = []
	for entry in logs:
		active_time = int(entry.get("active_time") or 0)
		if active_time < MIN_ACTIVE_SECONDS:
			continue  # discard trivially short sessions

		rows.append(
			{
				"name": frappe.generate_hash(length=10),
				"user": user,
				"session_id": session_id,
				"route": (entry.get("route") or "")[:140],
				"view_type": (entry.get("view_type") or "")[:50],
				"ref_doctype": entry.get("ref_doctype") or None,
				"docname": (entry.get("docname") or "")[:140],
				"active_time": active_time,
				"idle_time": int(entry.get("idle_time") or 0),
				"creation": now,
				"modified": now,
				"modified_by": user,
				"owner": user,
				"docstatus": 0,
			}
		)

	if rows:
		frappe.db.bulk_insert(
			"User Activity Log",
			fields=list(rows[0].keys()),
			values=[list(r.values()) for r in rows],
			ignore_duplicates=True,
		)
		frappe.db.commit()

	return {"inserted": len(rows), "skipped": len(logs) - len(rows)}


@frappe.whitelist()
def track_button_click(logs: str | list) -> dict:
	"""
	Accept a JSON-serialised array of button click entries and bulk-insert
	them into *Button Click Log*.

	Each entry must contain::

		{
		    "label":       "Save",
		    "button_type": "primary",
		    "action_type": "save",
		    "view_type":   "Form",
		    "ref_doctype": "Sales Invoice",  # optional
		    "docname":     "SI-0001",         # optional
		    "route":       "/Form/Sales Invoice/SI-0001"
		}

	The server-side ``session_id`` and ``user`` are injected automatically so
	the client cannot spoof them.
	"""
	if isinstance(logs, str):
		try:
			logs = json.loads(logs)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid JSON payload"), frappe.ValidationError)

	if not isinstance(logs, list):
		frappe.throw(_("Payload must be a JSON array"), frappe.ValidationError)

	if len(logs) > MAX_BATCH_ENTRIES:
		frappe.throw(
			_("Batch too large: maximum {0} entries per call").format(MAX_BATCH_ENTRIES),
			frappe.ValidationError,
		)

	user = frappe.session.user
	session_id = frappe.session.sid
	now = now_datetime()

	rows = []
	for entry in logs:
		label = (entry.get("label") or "").strip()
		if not label:
			continue  # skip entries with no label

		rows.append(
			{
				"name": frappe.generate_hash(length=10),
				"user": user,
				"session_id": session_id,
				"label": label[:140],
				"button_type": (entry.get("button_type") or "")[:50],
				"action_type": (entry.get("action_type") or "")[:50],
				"view_type": (entry.get("view_type") or "")[:50],
				"ref_doctype": entry.get("ref_doctype") or None,
				"docname": (entry.get("docname") or "")[:140],
				"route": (entry.get("route") or "")[:140],
				"creation": now,
				"modified": now,
				"modified_by": user,
				"owner": user,
				"docstatus": 0,
			}
		)

	if rows:
		frappe.db.bulk_insert(
			"Button Click Log",
			fields=list(rows[0].keys()),
			values=[list(r.values()) for r in rows],
			ignore_duplicates=True,
		)
		frappe.db.commit()

	return {"inserted": len(rows), "skipped": len(logs) - len(rows)}


# ---------------------------------------------------------------------------
# Dashboard API – require Activity Tracker Viewer role
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_org_overview() -> dict:
	"""
	Return organisation-level KPI summary for the Activity Tracker Dashboard.

	Requires: Activity Tracker Viewer role.
	"""
	_require_viewer_role()

	today_str = today()

	active_users_today = frappe.db.sql(
		"""
		SELECT COUNT(DISTINCT `user`) AS cnt
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(today)s
		""",
		{"today": today_str},
		as_dict=True,
	)

	productivity_avg = frappe.db.sql(
		"""
		SELECT ROUND(AVG(`productivity_score`), 2) AS avg_score
		FROM `tabProductivity Summary`
		WHERE `date` = %(today)s
		""",
		{"today": today_str},
		as_dict=True,
	)

	total_active_seconds = frappe.db.sql(
		"""
		SELECT SUM(`active_time`) AS total
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(today)s
		""",
		{"today": today_str},
		as_dict=True,
	)

	top_users = frappe.db.sql(
		"""
		SELECT `user`, SUM(`active_time`) AS active_time,
		       ROUND(SUM(`active_time`) / 3600, 2) AS active_hours
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(today)s
		GROUP BY `user`
		ORDER BY active_time DESC
		LIMIT 5
		""",
		{"today": today_str},
		as_dict=True,
	)

	least_active = frappe.db.sql(
		"""
		SELECT `user`, SUM(`active_time`) AS active_time,
		       ROUND(SUM(`active_time`) / 3600, 2) AS active_hours
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(today)s
		GROUP BY `user`
		ORDER BY active_time ASC
		LIMIT 5
		""",
		{"today": today_str},
		as_dict=True,
	)

	doctype_distribution = frappe.db.sql(
		"""
		SELECT COALESCE(`ref_doctype`, 'Unknown') AS ref_doctype,
		       SUM(`active_time`) AS active_time,
		       ROUND(SUM(`active_time`) / 3600, 2) AS active_hours
		FROM `tabUser Activity Log`
		WHERE DATE(`creation`) = %(today)s
		  AND `ref_doctype` IS NOT NULL AND `ref_doctype` != ''
		GROUP BY `ref_doctype`
		ORDER BY active_time DESC
		LIMIT 10
		""",
		{"today": today_str},
		as_dict=True,
	)

	return {
		"active_users_today": (active_users_today[0].cnt or 0) if active_users_today else 0,
		"avg_productivity_score": (productivity_avg[0].avg_score or 0.0) if productivity_avg else 0.0,
		"total_active_seconds": (total_active_seconds[0].total or 0) if total_active_seconds else 0,
		"total_active_hours": round(
			((total_active_seconds[0].total or 0) if total_active_seconds else 0) / 3600, 2
		),
		"top_active_users": top_users,
		"least_active_users": least_active,
		"doctype_distribution": doctype_distribution,
	}


@frappe.whitelist()
def get_user_dashboard(user: str = None, period: str = "today") -> dict:
	"""
	Return per-user productivity dashboard data.

	Parameters
	----------
	user   : target user email; defaults to frappe.session.user
	period : "today" | "week" | "month"

	Requires: Activity Tracker Viewer role (or the user viewing their own data).
	"""
	current_user = frappe.session.user
	target_user = user or current_user

	# Users can see their own data; Activity Tracker Viewer can see all
	if target_user != current_user:
		_require_viewer_role()
	elif current_user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	today_str = today()
	if period == "week":
		from_date = str(getdate(today_str) - datetime.timedelta(days=7))
	elif period == "month":
		from_date = str(getdate(today_str) - datetime.timedelta(days=30))
	else:
		from_date = today_str

	activity_summary = frappe.db.sql(
		"""
		SELECT
			SUM(`active_time`)  AS total_active_time,
			SUM(`idle_time`)    AS total_idle_time,
			COUNT(*)            AS sessions,
			ROUND(SUM(`active_time`) / 3600, 2) AS active_hours,
			ROUND(
				SUM(`active_time`) /
				NULLIF(SUM(`active_time`) + SUM(`idle_time`), 0) * 100
			, 2) AS productivity_score
		FROM `tabUser Activity Log`
		WHERE `user` = %(user)s
		  AND DATE(`creation`) BETWEEN %(from_date)s AND %(today)s
		""",
		{"user": target_user, "from_date": from_date, "today": today_str},
		as_dict=True,
	)

	pages_visited = frappe.db.sql(
		"""
		SELECT `route`, `view_type`, SUM(`active_time`) AS active_time,
		       COUNT(*) AS visits
		FROM `tabUser Activity Log`
		WHERE `user` = %(user)s
		  AND DATE(`creation`) BETWEEN %(from_date)s AND %(today)s
		GROUP BY `route`, `view_type`
		ORDER BY active_time DESC
		LIMIT 20
		""",
		{"user": target_user, "from_date": from_date, "today": today_str},
		as_dict=True,
	)

	doctypes_accessed = frappe.db.sql(
		"""
		SELECT COALESCE(`ref_doctype`, 'Unknown') AS ref_doctype,
		       SUM(`active_time`) AS active_time,
		       COUNT(*) AS sessions
		FROM `tabUser Activity Log`
		WHERE `user` = %(user)s
		  AND DATE(`creation`) BETWEEN %(from_date)s AND %(today)s
		  AND `ref_doctype` IS NOT NULL AND `ref_doctype` != ''
		GROUP BY `ref_doctype`
		ORDER BY active_time DESC
		LIMIT 10
		""",
		{"user": target_user, "from_date": from_date, "today": today_str},
		as_dict=True,
	)

	button_interactions = frappe.db.sql(
		"""
		SELECT COUNT(*) AS total_clicks,
		       COUNT(DISTINCT `label`) AS unique_buttons
		FROM `tabButton Click Log`
		WHERE `user` = %(user)s
		  AND DATE(`creation`) BETWEEN %(from_date)s AND %(today)s
		""",
		{"user": target_user, "from_date": from_date, "today": today_str},
		as_dict=True,
	)

	session_history = frappe.db.sql(
		"""
		SELECT DATE(`creation`) AS date,
		       SUM(`active_time`) AS active_time,
		       SUM(`idle_time`) AS idle_time,
		       COUNT(*) AS sessions,
		       ROUND(
		           SUM(`active_time`) /
		           NULLIF(SUM(`active_time`) + SUM(`idle_time`), 0) * 100
		       , 2) AS productivity_score
		FROM `tabUser Activity Log`
		WHERE `user` = %(user)s
		  AND DATE(`creation`) BETWEEN %(from_date)s AND %(today)s
		GROUP BY DATE(`creation`)
		ORDER BY date DESC
		""",
		{"user": target_user, "from_date": from_date, "today": today_str},
		as_dict=True,
	)

	summary = activity_summary[0] if activity_summary else {}
	clicks = button_interactions[0] if button_interactions else {}

	return {
		"user": target_user,
		"period": period,
		"total_active_time": summary.get("total_active_time") or 0,
		"total_idle_time": summary.get("total_idle_time") or 0,
		"active_hours": summary.get("active_hours") or 0.0,
		"sessions": summary.get("sessions") or 0,
		"productivity_score": summary.get("productivity_score") or 0.0,
		"total_button_clicks": clicks.get("total_clicks") or 0,
		"unique_buttons_used": clicks.get("unique_buttons") or 0,
		"pages_visited": pages_visited,
		"doctypes_accessed": doctypes_accessed,
		"session_history": session_history,
	}


# ---------------------------------------------------------------------------
# App reset
# ---------------------------------------------------------------------------

@frappe.whitelist()
def reset_app() -> dict:
	"""
	Delete all activity logs, button click logs, productivity summaries, and
	timesheet auto logs without uninstalling the app.

	Only System Managers may call this endpoint.

	Usage::

	    frappe.call("frappe_activity_tracker.api.reset_app")

	Equivalent CLI::

	    bench --site [site] execute frappe_activity_tracker.install.reset_all
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.has_role("System Manager"):
		frappe.throw(_("Only System Managers can reset the Activity Tracker"), frappe.PermissionError)

	deleted: dict[str, int] = {}
	for doctype in APP_DOCTYPES:
		try:
			count = frappe.db.count(doctype)
			frappe.db.delete(doctype)
			frappe.db.commit()
			deleted[doctype] = count
			frappe.logger().info(
				f"[frappe_activity_tracker] reset_app: deleted {count} row(s) from '{doctype}'"
			)
		except Exception:
			frappe.logger().warning(
				f"[frappe_activity_tracker] reset_app: could not delete data from '{doctype}'",
				exc_info=True,
			)
			deleted[doctype] = -1

	return {"status": "ok", "deleted": deleted}
