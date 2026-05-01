"""
Tests for frappe_activity_tracker.install
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, call

# frappe mock seeded by conftest.py
import frappe

from frappe_activity_tracker.install import (
    APP_DOCTYPES,
    APP_ROLES,
    APP_WORKSPACE,
    MODULE,
    _create_roles,
    _create_workspace,
    _delete_data,
    _delete_roles,
    _delete_workspaces,
    after_install,
    before_uninstall,
    cleanup_before_uninstall,
    reset_all,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_db():
    frappe.db.exists.reset_mock()
    frappe.db.exists.side_effect = None
    frappe.db.exists.return_value = False
    frappe.db.count.reset_mock()
    frappe.db.count.side_effect = None
    frappe.db.count.return_value = 0
    frappe.db.delete.reset_mock()
    frappe.db.delete.side_effect = None
    frappe.db.commit.reset_mock()
    frappe.db.commit.side_effect = None
    frappe.db.get_all.reset_mock()
    frappe.db.get_all.side_effect = None
    frappe.db.get_all.return_value = []
    frappe.db.table_exists.reset_mock()
    frappe.db.table_exists.side_effect = None
    frappe.db.table_exists.return_value = False
    frappe.get_doc.reset_mock()
    frappe.get_doc.side_effect = None
    frappe.get_doc.return_value = MagicMock()
    frappe.delete_doc.reset_mock()
    frappe.delete_doc.side_effect = None
    frappe.get_all.reset_mock()
    frappe.get_all.side_effect = None
    frappe.get_all.return_value = []
    frappe.logger.return_value = MagicMock()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants(unittest.TestCase):

    def test_app_doctypes_contains_expected_entries(self):
        expected = {
            "User Activity Log",
            "Button Click Log",
            "Productivity Summary",
            "Timesheet Auto Log",
        }
        self.assertEqual(set(APP_DOCTYPES), expected)

    def test_app_roles_contains_viewer_role(self):
        self.assertIn("Activity Tracker Viewer", APP_ROLES)

    def test_app_workspace_is_string(self):
        self.assertIsInstance(APP_WORKSPACE, str)
        self.assertTrue(len(APP_WORKSPACE) > 0)

    def test_module_is_string(self):
        self.assertIsInstance(MODULE, str)


# ---------------------------------------------------------------------------
# _create_roles
# ---------------------------------------------------------------------------


class TestCreateRoles(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_creates_role_when_not_exists(self):
        frappe.db.exists.return_value = False
        mock_doc = MagicMock()
        frappe.get_doc.return_value = mock_doc

        _create_roles()

        frappe.get_doc.assert_called()
        mock_doc.insert.assert_called()

    def test_skips_role_creation_when_already_exists(self):
        frappe.db.exists.return_value = True  # role already there

        _create_roles()

        frappe.get_doc.assert_not_called()

    def test_handles_insert_exception_gracefully(self):
        frappe.db.exists.return_value = False
        mock_doc = MagicMock()
        mock_doc.insert.side_effect = Exception("DB error")
        frappe.get_doc.return_value = mock_doc

        # Should not raise
        _create_roles()


# ---------------------------------------------------------------------------
# _create_workspace
# ---------------------------------------------------------------------------


class TestCreateWorkspace(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_creates_workspace_when_not_exists(self):
        frappe.db.exists.return_value = False
        mock_doc = MagicMock()
        frappe.get_doc.return_value = mock_doc

        _create_workspace()

        frappe.get_doc.assert_called_once()
        mock_doc.insert.assert_called_once()

    def test_skips_workspace_when_already_exists(self):
        frappe.db.exists.return_value = True

        _create_workspace()

        frappe.get_doc.assert_not_called()

    def test_handles_insert_exception_gracefully(self):
        frappe.db.exists.return_value = False
        mock_doc = MagicMock()
        mock_doc.insert.side_effect = Exception("DB error")
        frappe.get_doc.return_value = mock_doc

        _create_workspace()  # must not raise


# ---------------------------------------------------------------------------
# after_install
# ---------------------------------------------------------------------------


class TestAfterInstall(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_after_install_calls_commit(self):
        frappe.db.exists.return_value = False
        frappe.get_doc.return_value = MagicMock()

        after_install()

        frappe.db.commit.assert_called()


# ---------------------------------------------------------------------------
# _delete_data
# ---------------------------------------------------------------------------


class TestDeleteData(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_deletes_all_app_doctypes(self):
        frappe.db.count.return_value = 10

        _delete_data()

        # delete called once per doctype
        self.assertEqual(frappe.db.delete.call_count, len(APP_DOCTYPES))

    def test_commit_called_for_each_doctype(self):
        frappe.db.count.return_value = 5

        _delete_data()

        self.assertEqual(frappe.db.commit.call_count, len(APP_DOCTYPES))

    def test_handles_delete_exception_gracefully(self):
        frappe.db.delete.side_effect = Exception("error")

        _delete_data()  # must not raise


# ---------------------------------------------------------------------------
# _delete_workspaces
# ---------------------------------------------------------------------------


class TestDeleteWorkspaces(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_deletes_workspaces_returned_by_get_all(self):
        frappe.get_all.return_value = ["Activity Tracker Dashboard"]

        _delete_workspaces()

        frappe.delete_doc.assert_called_once_with(
            "Workspace", "Activity Tracker Dashboard",
            ignore_permissions=True, force=True,
        )

    def test_handles_empty_workspace_list(self):
        frappe.get_all.return_value = []
        _delete_workspaces()  # must not raise and not call delete_doc
        frappe.delete_doc.assert_not_called()

    def test_handles_delete_exception_gracefully(self):
        frappe.get_all.return_value = ["SomeWorkspace"]
        frappe.delete_doc.side_effect = Exception("error")
        _delete_workspaces()  # must not raise


# ---------------------------------------------------------------------------
# _delete_roles
# ---------------------------------------------------------------------------


class TestDeleteRoles(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_skips_nonexistent_role(self):
        frappe.db.exists.return_value = False

        _delete_roles()

        frappe.delete_doc.assert_not_called()

    def test_deletes_existing_role_and_permissions(self):
        frappe.db.exists.return_value = True

        _delete_roles()

        frappe.delete_doc.assert_called()

    def test_removes_docperm_for_each_app_doctype(self):
        frappe.db.exists.return_value = True

        _delete_roles()

        # frappe.db.delete should be called for each doctype (to remove DocPerms)
        delete_calls = [c for c in frappe.db.delete.call_args_list if c[0][0] == "DocPerm"]
        self.assertEqual(len(delete_calls), len(APP_DOCTYPES))


# ---------------------------------------------------------------------------
# cleanup_before_uninstall / before_uninstall
# ---------------------------------------------------------------------------


class TestCleanupBeforeUninstall(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_before_uninstall_delegates_to_cleanup(self):
        """before_uninstall must call cleanup_before_uninstall."""
        frappe.db.exists.return_value = False
        frappe.get_all.return_value = []

        before_uninstall()

        # Cleanup should call commit at end
        frappe.db.commit.assert_called()

    def test_cleanup_calls_commit(self):
        frappe.db.exists.return_value = False
        frappe.get_all.return_value = []

        cleanup_before_uninstall()

        frappe.db.commit.assert_called()


# ---------------------------------------------------------------------------
# reset_all
# ---------------------------------------------------------------------------


class TestResetAll(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_reset_all_deletes_data_and_commits(self):
        frappe.db.count.return_value = 3

        reset_all()

        self.assertEqual(frappe.db.delete.call_count, len(APP_DOCTYPES))
        frappe.db.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
