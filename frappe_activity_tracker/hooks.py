from __future__ import unicode_literals

app_name = "frappe_activity_tracker"
app_title = "Frappe Activity Tracker"
app_publisher = "rbnkoirala"
app_description = "Tracks user activity inside Frappe Desk and provides productivity analytics"
app_email = ""
app_license = "MIT"
app_version = "0.0.1"

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------
app_include_js = ["frappe_activity_tracker/js/tracker.js"]

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler_events = {
"daily": [
"frappe_activity_tracker.tasks.compute_productivity_summary",
"frappe_activity_tracker.tasks.generate_timesheet_logs",
]
}

# ---------------------------------------------------------------------------
# Fixtures – ship Role definition with the app
# ---------------------------------------------------------------------------
fixtures = [
{
"doctype": "Role",
"filters": [["role_name", "=", "Activity Tracker Viewer"]],
}
]

# ---------------------------------------------------------------------------
# Permissions – backend-enforced access control
# ---------------------------------------------------------------------------
has_permission = {
"User Activity Log": "frappe_activity_tracker.permissions.has_permission",
"Button Click Log": "frappe_activity_tracker.permissions.has_permission",
"Productivity Summary": "frappe_activity_tracker.permissions.has_permission",
"Timesheet Auto Log": "frappe_activity_tracker.permissions.has_permission",
}
