"""
Backend-enforced permission controller for frappe_activity_tracker.

Every doctype listed in hooks.py → has_permission routes through this module.
A user may read tracker data if they:
  • own the record (they created it – write-own pattern for log doctypes), OR
  • hold the "Activity Tracker Viewer" role, OR
  • hold the "System Manager" role.

This is checked at the backend level so the restriction cannot be bypassed
via the REST API, background jobs or console calls.
"""
from __future__ import unicode_literals

import frappe

_ALLOWED_ROLES = frozenset(["Activity Tracker Viewer", "System Manager"])


def has_permission(doc, ptype="read", user=None):
    """
    Return True when the requesting user is allowed to access *doc*.

    Parameters
    ----------
    doc   : Document or str – the document being accessed
    ptype : str             – permission type ("read", "write", …)
    user  : str | None      – requesting user; defaults to frappe.session.user
    """
    user = user or frappe.session.user

    # Guest never gets access
    if user == "Guest":
        return False

    # Owner can always read their own log entry (write-own pattern)
    owner = doc.owner if hasattr(doc, "owner") else None
    if ptype == "read" and owner and owner == user:
        return True

    # Role-based gate
    user_roles = frappe.get_roles(user)
    return bool(_ALLOWED_ROLES & set(user_roles))
