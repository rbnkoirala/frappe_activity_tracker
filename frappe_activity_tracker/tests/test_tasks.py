"""
Tests for frappe_activity_tracker.tasks
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

# frappe mock seeded by conftest.py
import frappe

from frappe_activity_tracker.tasks import (
    _yesterday,
    compute_productivity_summary,
    generate_timesheet_logs,
)
from frappe_activity_tracker.tests.conftest import FrappeDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_db():
    frappe.db.sql.reset_mock()
    frappe.db.sql.side_effect = None
    frappe.db.sql.return_value = []
    frappe.db.get_value.reset_mock()
    frappe.db.get_value.side_effect = None
    frappe.db.get_value.return_value = None
    frappe.db.set_value.reset_mock()
    frappe.db.set_value.side_effect = None
    frappe.db.commit.reset_mock()
    frappe.db.commit.side_effect = None
    frappe.get_doc.reset_mock()
    frappe.get_doc.side_effect = None
    frappe.get_doc.return_value = MagicMock()


# ---------------------------------------------------------------------------
# _yesterday
# ---------------------------------------------------------------------------


class TestYesterday(unittest.TestCase):

    def test_returns_string(self):
        result = _yesterday()
        self.assertIsInstance(result, str)

    def test_format_is_iso(self):
        result = _yesterday()
        # Should be parseable as ISO date YYYY-MM-DD
        parsed = date.fromisoformat(result)
        self.assertIsInstance(parsed, date)

    def test_is_actually_yesterday(self):
        result = _yesterday()
        expected = str(date.today() - timedelta(days=1))
        self.assertEqual(result, expected)

    def test_not_today(self):
        result = _yesterday()
        self.assertNotEqual(result, str(date.today()))


# ---------------------------------------------------------------------------
# compute_productivity_summary
# ---------------------------------------------------------------------------


class TestComputeProductivitySummary(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_no_rows_no_insert_or_update(self):
        frappe.db.sql.return_value = []
        compute_productivity_summary()
        frappe.db.get_value.assert_not_called()
        frappe.db.set_value.assert_not_called()
        frappe.get_doc.assert_not_called()
        frappe.db.commit.assert_called_once()

    def test_creates_new_record_when_none_exists(self):
        target_user = "alice@example.com"
        frappe.db.sql.return_value = [
            FrappeDict(user=target_user, total_active_time=3600, total_idle_time=1800)
        ]
        frappe.db.get_value.return_value = None  # no existing record

        compute_productivity_summary()

        frappe.get_doc.assert_called_once()
        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertEqual(call_kwargs["doctype"], "Productivity Summary")
        self.assertEqual(call_kwargs["user"], target_user)

    def test_updates_existing_record_when_found(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="bob@example.com", total_active_time=1800, total_idle_time=200)
        ]
        frappe.db.get_value.return_value = "PS-0001"  # existing record

        compute_productivity_summary()

        frappe.db.set_value.assert_called_once()
        set_call_args = frappe.db.set_value.call_args[0]
        self.assertEqual(set_call_args[0], "Productivity Summary")
        self.assertEqual(set_call_args[1], "PS-0001")

    def test_productivity_score_calculated_correctly(self):
        """active=3600, idle=1200 → score = 3600/4800 * 100 = 75.0"""
        frappe.db.sql.return_value = [
            FrappeDict(user="carol@example.com", total_active_time=3600, total_idle_time=1200)
        ]
        frappe.db.get_value.return_value = None

        compute_productivity_summary()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertAlmostEqual(call_kwargs["productivity_score"], 75.0, places=1)

    def test_productivity_score_zero_when_total_is_zero(self):
        """active=0, idle=0 → score = 0.0 (no division by zero)."""
        frappe.db.sql.return_value = [
            FrappeDict(user="dave@example.com", total_active_time=0, total_idle_time=0)
        ]
        frappe.db.get_value.return_value = None

        compute_productivity_summary()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertEqual(call_kwargs["productivity_score"], 0.0)

    def test_productivity_score_100_when_no_idle(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="eve@example.com", total_active_time=3600, total_idle_time=0)
        ]
        frappe.db.get_value.return_value = None

        compute_productivity_summary()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertAlmostEqual(call_kwargs["productivity_score"], 100.0, places=1)

    def test_multiple_users_processed(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="user1@example.com", total_active_time=1000, total_idle_time=200),
            FrappeDict(user="user2@example.com", total_active_time=2000, total_idle_time=500),
        ]
        frappe.db.get_value.return_value = None  # no existing records

        compute_productivity_summary()

        self.assertEqual(frappe.get_doc.call_count, 2)
        frappe.db.commit.assert_called_once()

    def test_none_active_time_treated_as_zero(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="frank@example.com", total_active_time=None, total_idle_time=None)
        ]
        frappe.db.get_value.return_value = None

        compute_productivity_summary()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertEqual(call_kwargs["total_active_time"], 0)
        self.assertEqual(call_kwargs["productivity_score"], 0.0)

    def test_insert_called_with_ignore_permissions(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="greta@example.com", total_active_time=600, total_idle_time=100)
        ]
        frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        frappe.get_doc.return_value = mock_doc

        compute_productivity_summary()

        mock_doc.insert.assert_called_once_with(ignore_permissions=True)


# ---------------------------------------------------------------------------
# generate_timesheet_logs
# ---------------------------------------------------------------------------


class TestGenerateTimesheetLogs(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_no_rows_no_insert_or_update(self):
        frappe.db.sql.return_value = []
        generate_timesheet_logs()
        frappe.db.get_value.assert_not_called()
        frappe.db.set_value.assert_not_called()
        frappe.get_doc.assert_not_called()
        frappe.db.commit.assert_called_once()

    def test_creates_new_record_when_none_exists(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="alice@example.com", ref_doctype="Sales Invoice", total_seconds=7200)
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        frappe.get_doc.assert_called_once()
        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertEqual(call_kwargs["doctype"], "Timesheet Auto Log")
        self.assertEqual(call_kwargs["user"], "alice@example.com")

    def test_updates_existing_record_when_found(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="bob@example.com", ref_doctype="Purchase Order", total_seconds=1800)
        ]
        frappe.db.get_value.return_value = "TAL-0001"

        generate_timesheet_logs()

        frappe.db.set_value.assert_called_once()
        set_args = frappe.db.set_value.call_args[0]
        self.assertEqual(set_args[0], "Timesheet Auto Log")
        self.assertEqual(set_args[1], "TAL-0001")

    def test_seconds_converted_to_hours(self):
        """7200 seconds → 2.0 hours."""
        frappe.db.sql.return_value = [
            FrappeDict(user="carol@example.com", ref_doctype="Sales Invoice", total_seconds=7200)
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertAlmostEqual(call_kwargs["total_hours"], 2.0, places=4)

    def test_multiple_doctypes_for_same_user_grouped(self):
        """Two different doctypes for the same user → one Timesheet Auto Log."""
        frappe.db.sql.return_value = [
            FrappeDict(user="dave@example.com", ref_doctype="Sales Invoice", total_seconds=3600),
            FrappeDict(user="dave@example.com", ref_doctype="Purchase Order", total_seconds=1800),
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        # One record for one user
        frappe.get_doc.assert_called_once()
        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertEqual(call_kwargs["user"], "dave@example.com")
        # total_hours = 1.0 + 0.5 = 1.5
        self.assertAlmostEqual(call_kwargs["total_hours"], 1.5, places=4)

    def test_doctype_breakdown_is_valid_json(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="eve@example.com", ref_doctype="Sales Invoice", total_seconds=3600),
            FrappeDict(user="eve@example.com", ref_doctype="Unknown", total_seconds=900),
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        call_kwargs = frappe.get_doc.call_args[0][0]
        breakdown = json.loads(call_kwargs["doctype_breakdown"])
        self.assertIn("Sales Invoice", breakdown)
        self.assertIn("Unknown", breakdown)
        self.assertAlmostEqual(breakdown["Sales Invoice"], 1.0, places=4)

    def test_multiple_users_each_get_own_record(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="user1@example.com", ref_doctype="DocA", total_seconds=3600),
            FrappeDict(user="user2@example.com", ref_doctype="DocB", total_seconds=1800),
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        self.assertEqual(frappe.get_doc.call_count, 2)

    def test_none_total_seconds_treated_as_zero(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="frank@example.com", ref_doctype="Sales Invoice", total_seconds=None)
        ]
        frappe.db.get_value.return_value = None

        generate_timesheet_logs()

        call_kwargs = frappe.get_doc.call_args[0][0]
        self.assertAlmostEqual(call_kwargs["total_hours"], 0.0, places=4)

    def test_insert_called_with_ignore_permissions(self):
        frappe.db.sql.return_value = [
            FrappeDict(user="greta@example.com", ref_doctype="Quotation", total_seconds=1800)
        ]
        frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        frappe.get_doc.return_value = mock_doc

        generate_timesheet_logs()

        mock_doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_commit_always_called(self):
        generate_timesheet_logs()
        frappe.db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
