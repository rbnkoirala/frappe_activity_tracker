from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from frappe_activity_tracker.install import APP_DOCTYPES

# Minimum active time (seconds) to be worth recording
MIN_ACTIVE_SECONDS = 10

# Maximum number of entries accepted in a single batch call
MAX_BATCH_ENTRIES = 200


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
