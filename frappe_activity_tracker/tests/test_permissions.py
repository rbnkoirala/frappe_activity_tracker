"""
Tests for frappe_activity_tracker.permissions
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

# conftest.py must already have seeded sys.modules with the frappe mock.
import frappe

from frappe_activity_tracker.permissions import has_permission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc(owner=None):
    """Return a minimal document-like object."""
    if owner is not None:
        return type("Doc", (), {"owner": owner})()
    # No `owner` attribute at all
    return type("Doc", (), {})()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHasPermission(unittest.TestCase):

    def setUp(self):
        frappe.get_roles.reset_mock()
        frappe.get_roles.return_value = []

    # -- Guest ----------------------------------------------------------------

    def test_guest_user_is_always_denied(self):
        doc = _doc(owner="alice@example.com")
        self.assertFalse(has_permission(doc, ptype="read", user="Guest"))

    def test_guest_user_denied_even_when_owner(self):
        """Guest cannot access even if listed as doc owner."""
        doc = _doc(owner="Guest")
        self.assertFalse(has_permission(doc, ptype="read", user="Guest"))

    # -- Owner read access ----------------------------------------------------

    def test_owner_can_read_own_document(self):
        doc = _doc(owner="alice@example.com")
        self.assertTrue(has_permission(doc, ptype="read", user="alice@example.com"))

    def test_owner_read_does_not_need_viewer_role(self):
        """Owner read access is granted without any role."""
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = []
        self.assertTrue(has_permission(doc, ptype="read", user="alice@example.com"))

    def test_non_owner_cannot_read_via_owner_shortcut(self):
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = []
        self.assertFalse(has_permission(doc, ptype="read", user="bob@example.com"))

    # -- Owner write access requires role -------------------------------------

    def test_owner_write_not_special_cased_without_role(self):
        """ptype='write' skips the owner shortcut; role is required."""
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = []
        self.assertFalse(has_permission(doc, ptype="write", user="alice@example.com"))

    def test_owner_write_granted_when_has_viewer_role(self):
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        self.assertTrue(has_permission(doc, ptype="write", user="alice@example.com"))

    # -- Role-based access ----------------------------------------------------

    def test_activity_tracker_viewer_role_grants_access(self):
        doc = _doc()
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        self.assertTrue(has_permission(doc, ptype="read", user="bob@example.com"))

    def test_system_manager_role_grants_access(self):
        doc = _doc()
        frappe.get_roles.return_value = ["System Manager"]
        self.assertTrue(has_permission(doc, ptype="read", user="admin@example.com"))

    def test_both_allowed_roles_grants_access(self):
        doc = _doc()
        frappe.get_roles.return_value = ["Activity Tracker Viewer", "System Manager"]
        self.assertTrue(has_permission(doc, ptype="read", user="super@example.com"))

    def test_unrelated_role_is_denied(self):
        doc = _doc()
        frappe.get_roles.return_value = ["Sales User", "Purchase User"]
        self.assertFalse(has_permission(doc, ptype="read", user="sales@example.com"))

    def test_empty_roles_list_denied(self):
        doc = _doc()
        frappe.get_roles.return_value = []
        self.assertFalse(has_permission(doc, ptype="read", user="nobody@example.com"))

    # -- Default user ---------------------------------------------------------

    def test_default_user_comes_from_frappe_session(self):
        frappe.session.user = "session@example.com"
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        doc = _doc()
        # No `user` argument – should fall back to frappe.session.user
        self.assertTrue(has_permission(doc))

    def test_session_guest_is_denied_by_default(self):
        frappe.session.user = "Guest"
        doc = _doc()
        self.assertFalse(has_permission(doc))

    # -- Doc without owner attribute ------------------------------------------

    def test_doc_without_owner_attribute_uses_role(self):
        """If doc has no .owner, the owner shortcut is skipped entirely."""
        doc = type("Doc", (), {})()  # no owner attr
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        self.assertTrue(has_permission(doc, ptype="read", user="alice@example.com"))

    def test_doc_without_owner_denied_without_role(self):
        doc = type("Doc", (), {})()
        frappe.get_roles.return_value = []
        self.assertFalse(has_permission(doc, ptype="read", user="alice@example.com"))

    # -- ptype variations -----------------------------------------------------

    def test_delete_ptype_uses_role_check(self):
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        self.assertTrue(has_permission(doc, ptype="delete", user="alice@example.com"))

    def test_create_ptype_without_role_denied(self):
        doc = _doc(owner="alice@example.com")
        frappe.get_roles.return_value = []
        self.assertFalse(has_permission(doc, ptype="create", user="alice@example.com"))


if __name__ == "__main__":
    unittest.main()
