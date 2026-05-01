"""
Installation, uninstallation, and reset helpers for frappe_activity_tracker.

Hooks wired in hooks.py:
    after_install    -> frappe_activity_tracker.install.after_install
    before_uninstall -> frappe_activity_tracker.install.before_uninstall
"""
from __future__ import unicode_literals

import frappe
from frappe import _

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE = "Frappe Activity Tracker"

APP_DOCTYPES = [
    "User Activity Log",
    "Button Click Log",
    "Productivity Summary",
    "Timesheet Auto Log",
]

APP_ROLES = [
    "Activity Tracker Viewer",
]

APP_WORKSPACE = "Activity Tracker Dashboard"


# ---------------------------------------------------------------------------
# after_install
# ---------------------------------------------------------------------------

def after_install() -> None:
    """
    Run once after `bench install-app frappe_activity_tracker`.

    Creates:
    * Required custom roles
    * Activity Tracker Dashboard workspace
    """
    _create_roles()
    _create_workspace()
    frappe.db.commit()
    frappe.logger().info("[frappe_activity_tracker] after_install complete")


def _create_roles() -> None:
    for role_name in APP_ROLES:
        if frappe.db.exists("Role", role_name):
            frappe.logger().info(f"[frappe_activity_tracker] Role '{role_name}' already exists – skipping")
            continue
        try:
            role = frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            })
            role.insert(ignore_permissions=True)
            frappe.logger().info(f"[frappe_activity_tracker] Created role: {role_name}")
        except Exception:
            frappe.logger().warning(
                f"[frappe_activity_tracker] Could not create role '{role_name}'",
                exc_info=True,
            )


def _create_workspace() -> None:
    if frappe.db.exists("Workspace", APP_WORKSPACE):
        frappe.logger().info(f"[frappe_activity_tracker] Workspace '{APP_WORKSPACE}' already exists – skipping")
        return
    try:
        ws = frappe.get_doc({
            "doctype": "Workspace",
            "name": APP_WORKSPACE,
            "label": APP_WORKSPACE,
            "module": MODULE,
            "is_standard": 0,
            "public": 1,
            "content": "[]",
        })
        ws.insert(ignore_permissions=True)
        frappe.logger().info(f"[frappe_activity_tracker] Created workspace: {APP_WORKSPACE}")
    except Exception:
        frappe.logger().warning(
            f"[frappe_activity_tracker] Could not create workspace '{APP_WORKSPACE}'",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# before_uninstall
# ---------------------------------------------------------------------------

def before_uninstall() -> None:
    """
    Run just before `bench uninstall-app frappe_activity_tracker`.

    Delegates to cleanup_before_uninstall so the same function can also be
    invoked directly.
    """
    cleanup_before_uninstall()


def cleanup_before_uninstall() -> None:
    """
    Full teardown for frappe_activity_tracker.

    Removes (in order):
    1. All log / summary data rows
    2. Workspaces created by this app
    3. Reports created by this app
    4. Custom Scripts created by this app
    5. Scheduled job types registered by this app
    6. Roles created by this app (and their DocType permissions)
    """
    frappe.logger().info("[frappe_activity_tracker] cleanup_before_uninstall – start")

    _delete_data()
    _delete_workspaces()
    _delete_reports()
    _delete_custom_scripts()
    _delete_scheduled_jobs()
    _delete_roles()

    frappe.db.commit()
    frappe.logger().info("[frappe_activity_tracker] cleanup_before_uninstall – done")


# ---------------------  data -------------------------------------------------

def _delete_data() -> None:
    for doctype in APP_DOCTYPES:
        try:
            count = frappe.db.count(doctype)
            frappe.db.delete(doctype)
            frappe.db.commit()
            frappe.logger().info(
                f"[frappe_activity_tracker] Deleted {count} row(s) from '{doctype}'"
            )
        except Exception:
            frappe.logger().warning(
                f"[frappe_activity_tracker] Could not delete data from '{doctype}'",
                exc_info=True,
            )


# --------------------  workspaces -------------------------------------------

def _delete_workspaces() -> None:
    try:
        workspaces = frappe.get_all(
            "Workspace",
            filters={"module": MODULE},
            pluck="name",
        )
        for ws_name in workspaces:
            try:
                frappe.delete_doc("Workspace", ws_name, ignore_permissions=True, force=True)
                frappe.logger().info(f"[frappe_activity_tracker] Deleted workspace: {ws_name}")
            except Exception:
                frappe.logger().warning(
                    f"[frappe_activity_tracker] Could not delete workspace '{ws_name}'",
                    exc_info=True,
                )
        frappe.db.commit()
    except Exception:
        frappe.logger().warning(
            "[frappe_activity_tracker] Error listing workspaces",
            exc_info=True,
        )


# --------------------  reports ----------------------------------------------

def _delete_reports() -> None:
    try:
        reports = frappe.get_all(
            "Report",
            filters={"module": MODULE, "is_standard": "Yes"},
            pluck="name",
        )
        for report_name in reports:
            try:
                frappe.delete_doc("Report", report_name, ignore_permissions=True, force=True)
                frappe.logger().info(f"[frappe_activity_tracker] Deleted report: {report_name}")
            except Exception:
                frappe.logger().warning(
                    f"[frappe_activity_tracker] Could not delete report '{report_name}'",
                    exc_info=True,
                )
        frappe.db.commit()
    except Exception:
        frappe.logger().warning(
            "[frappe_activity_tracker] Error listing reports",
            exc_info=True,
        )


# --------------------  custom scripts ---------------------------------------

def _delete_custom_scripts() -> None:
    try:
        if not frappe.db.table_exists("Custom Script"):
            return
        scripts = frappe.get_all(
            "Custom Script",
            filters={"dt": ["in", APP_DOCTYPES]},
            pluck="name",
        )
        for script_name in scripts:
            try:
                frappe.delete_doc("Custom Script", script_name, ignore_permissions=True, force=True)
                frappe.logger().info(f"[frappe_activity_tracker] Deleted custom script: {script_name}")
            except Exception:
                frappe.logger().warning(
                    f"[frappe_activity_tracker] Could not delete custom script '{script_name}'",
                    exc_info=True,
                )
        frappe.db.commit()
    except Exception:
        frappe.logger().warning(
            "[frappe_activity_tracker] Error cleaning custom scripts",
            exc_info=True,
        )


# --------------------  scheduled jobs ---------------------------------------

_APP_SCHEDULED_METHODS = {
    "frappe_activity_tracker.tasks.compute_productivity_summary",
    "frappe_activity_tracker.tasks.generate_timesheet_logs",
}


def _delete_scheduled_jobs() -> None:
    """Remove Scheduled Job Type records registered by this app."""
    try:
        if not frappe.db.table_exists("Scheduled Job Type"):
            return
        jobs = frappe.get_all(
            "Scheduled Job Type",
            filters={"method": ["in", list(_APP_SCHEDULED_METHODS)]},
            pluck="name",
        )
        for job_name in jobs:
            try:
                frappe.delete_doc("Scheduled Job Type", job_name, ignore_permissions=True, force=True)
                frappe.logger().info(f"[frappe_activity_tracker] Deleted scheduled job: {job_name}")
            except Exception:
                frappe.logger().warning(
                    f"[frappe_activity_tracker] Could not delete scheduled job '{job_name}'",
                    exc_info=True,
                )
        frappe.db.commit()
    except Exception:
        frappe.logger().warning(
            "[frappe_activity_tracker] Error cleaning scheduled jobs",
            exc_info=True,
        )


# --------------------  roles & permissions ----------------------------------

def _delete_roles() -> None:
    for role_name in APP_ROLES:
        if not frappe.db.exists("Role", role_name):
            continue
        try:
            # Remove DocType-level permissions granted to this role
            for doctype in APP_DOCTYPES:
                try:
                    frappe.db.delete(
                        "DocPerm",
                        {"parent": doctype, "role": role_name},
                    )
                except Exception:
                    frappe.logger().warning(
                        f"[frappe_activity_tracker] Could not remove permissions for role "
                        f"'{role_name}' on '{doctype}'",
                        exc_info=True,
                    )
            frappe.delete_doc("Role", role_name, ignore_permissions=True, force=True)
            frappe.db.commit()
            frappe.logger().info(f"[frappe_activity_tracker] Deleted role: {role_name}")
        except Exception:
            frappe.logger().warning(
                f"[frappe_activity_tracker] Could not delete role '{role_name}'",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# reset_all  (CLI entry-point)
# ---------------------------------------------------------------------------

def reset_all() -> None:
    """
    Delete all log / summary data without uninstalling the app.

    Usage::

        bench --site [site] execute frappe_activity_tracker.install.reset_all
    """
    frappe.logger().info("[frappe_activity_tracker] reset_all – start")
    _delete_data()
    frappe.db.commit()
    frappe.logger().info("[frappe_activity_tracker] reset_all – done")
    print("[frappe_activity_tracker] All activity data has been reset.")
