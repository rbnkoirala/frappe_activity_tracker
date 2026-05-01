from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

# Minimum active time (seconds) to be worth recording
MIN_ACTIVE_SECONDS = 10


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
