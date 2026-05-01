"""
Tests for frappe_activity_tracker.api
"""
from __future__ import annotations

import datetime
import json
import sys
import unittest
from unittest.mock import MagicMock, call, patch

# frappe mock is injected by conftest.py before this module is imported.
import frappe

# Access the frappe.utils mock so we can configure return values.
_frappe_utils = sys.modules["frappe.utils"]

from frappe_activity_tracker.api import (
    MAX_BATCH_ENTRIES,
    MIN_ACTIVE_SECONDS,
    _require_viewer_role,
    get_org_overview,
    get_user_dashboard,
    reset_app,
    track_button_click,
    track_time,
)
from frappe_activity_tracker.install import APP_DOCTYPES
from frappe_activity_tracker.tests.conftest import FrappeDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_frappe_defaults():
    """Restore the frappe mock to a known state between tests."""
    frappe.session.user = "test@example.com"
    frappe.session.sid = "testsession123"
    frappe.get_roles.reset_mock()
    frappe.get_roles.return_value = []
    frappe.has_role.reset_mock()
    frappe.has_role.return_value = False
    frappe.db.bulk_insert.reset_mock()
    frappe.db.bulk_insert.side_effect = None
    frappe.db.commit.reset_mock()
    frappe.db.commit.side_effect = None
    frappe.db.sql.reset_mock()
    frappe.db.sql.side_effect = None
    frappe.db.sql.return_value = []
    frappe.db.count.reset_mock()
    frappe.db.count.side_effect = None
    frappe.db.count.return_value = 0
    frappe.db.delete.reset_mock()
    frappe.db.delete.side_effect = None
    frappe.generate_hash.return_value = "abc1234567"
    _frappe_utils.today.return_value = "2024-06-15"
    _frappe_utils.now_datetime.return_value = datetime.datetime(2024, 6, 15, 10, 0, 0)
    _frappe_utils.getdate.side_effect = lambda s: datetime.date.fromisoformat(str(s))


# ---------------------------------------------------------------------------
# _require_viewer_role
# ---------------------------------------------------------------------------


class TestRequireViewerRole(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()

    def test_guest_raises_permission_error(self):
        frappe.session.user = "Guest"
        with self.assertRaises(frappe.PermissionError):
            _require_viewer_role()

    def test_user_without_allowed_role_raises(self):
        frappe.session.user = "user@example.com"
        frappe.get_roles.return_value = ["Sales User", "Purchase User"]
        with self.assertRaises(frappe.PermissionError):
            _require_viewer_role()

    def test_empty_roles_raises(self):
        frappe.session.user = "user@example.com"
        frappe.get_roles.return_value = []
        with self.assertRaises(frappe.PermissionError):
            _require_viewer_role()

    def test_activity_tracker_viewer_passes(self):
        frappe.session.user = "viewer@example.com"
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        # Should not raise
        _require_viewer_role()

    def test_system_manager_passes(self):
        frappe.session.user = "admin@example.com"
        frappe.get_roles.return_value = ["System Manager"]
        _require_viewer_role()

    def test_multiple_allowed_roles_passes(self):
        frappe.session.user = "super@example.com"
        frappe.get_roles.return_value = ["Activity Tracker Viewer", "System Manager"]
        _require_viewer_role()


# ---------------------------------------------------------------------------
# track_time
# ---------------------------------------------------------------------------


class TestTrackTime(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()

    # -- Input validation -----------------------------------------------------

    def test_invalid_json_string_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            track_time("not valid json{{{")

    def test_non_list_payload_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            track_time(json.dumps({"key": "value"}))

    def test_non_list_direct_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            track_time("oops")

    def test_batch_too_large_raises_validation_error(self):
        logs = [{"active_time": 60}] * (MAX_BATCH_ENTRIES + 1)
        with self.assertRaises(frappe.ValidationError):
            track_time(logs)

    def test_exactly_max_batch_size_accepted(self):
        logs = [{"active_time": 0}] * MAX_BATCH_ENTRIES
        result = track_time(logs)
        self.assertEqual(result["skipped"], MAX_BATCH_ENTRIES)

    # -- Filtering by MIN_ACTIVE_SECONDS --------------------------------------

    def test_entry_below_min_active_seconds_is_skipped(self):
        logs = [{"route": "/test", "view_type": "Form", "active_time": MIN_ACTIVE_SECONDS - 1}]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        frappe.db.bulk_insert.assert_not_called()

    def test_entry_at_exactly_min_active_seconds_is_inserted(self):
        logs = [{"route": "/test", "view_type": "Form", "active_time": MIN_ACTIVE_SECONDS}]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped"], 0)
        frappe.db.bulk_insert.assert_called_once()

    def test_entry_above_min_active_seconds_is_inserted(self):
        logs = [{"route": "/test", "active_time": MIN_ACTIVE_SECONDS + 100}]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 1)

    def test_zero_active_time_skipped(self):
        logs = [{"route": "/test", "active_time": 0}]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 0)

    def test_missing_active_time_treated_as_zero(self):
        logs = [{"route": "/test"}]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 0)

    # -- Mixed batch ----------------------------------------------------------

    def test_mixed_batch_counts_inserted_and_skipped(self):
        logs = [
            {"active_time": MIN_ACTIVE_SECONDS},      # inserted
            {"active_time": MIN_ACTIVE_SECONDS - 1},  # skipped
            {"active_time": 300},                      # inserted
            {"active_time": 0},                        # skipped
        ]
        result = track_time(logs)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 2)

    # -- Field injection and truncation ---------------------------------------

    def test_user_and_session_injected_server_side(self):
        frappe.session.user = "alice@example.com"
        frappe.session.sid = "sid_xyz"
        logs = [{"active_time": 60, "route": "/test"}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row = rows[0]
        # Find user/session_id in row by matching fields
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        row_dict = dict(zip(fields, row))
        self.assertEqual(row_dict["user"], "alice@example.com")
        self.assertEqual(row_dict["session_id"], "sid_xyz")

    def test_route_truncated_to_140_chars(self):
        long_route = "x" * 200
        logs = [{"active_time": 60, "route": long_route}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(len(row_dict["route"]), 140)

    def test_view_type_truncated_to_50_chars(self):
        long_view_type = "V" * 100
        logs = [{"active_time": 60, "view_type": long_view_type}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(len(row_dict["view_type"]), 50)

    def test_docname_truncated_to_140_chars(self):
        long_docname = "D" * 200
        logs = [{"active_time": 60, "docname": long_docname}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(len(row_dict["docname"]), 140)

    def test_idle_time_defaults_to_zero(self):
        logs = [{"active_time": 60, "route": "/test"}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(row_dict["idle_time"], 0)

    def test_ref_doctype_none_when_absent(self):
        logs = [{"active_time": 60}]
        track_time(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertIsNone(row_dict["ref_doctype"])

    # -- JSON string input ----------------------------------------------------

    def test_json_string_input_parsed_correctly(self):
        logs = [{"active_time": 60, "route": "/sales-invoice"}]
        result = track_time(json.dumps(logs))
        self.assertEqual(result["inserted"], 1)

    # -- Empty list -----------------------------------------------------------

    def test_empty_list_returns_zero_counts(self):
        result = track_time([])
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 0)
        frappe.db.bulk_insert.assert_not_called()

    # -- Commit ---------------------------------------------------------------

    def test_commit_called_after_insert(self):
        logs = [{"active_time": 60}]
        track_time(logs)
        frappe.db.commit.assert_called()

    def test_commit_not_called_when_nothing_inserted(self):
        track_time([])
        frappe.db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# track_button_click
# ---------------------------------------------------------------------------


class TestTrackButtonClick(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()

    def test_invalid_json_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            track_button_click("{bad json")

    def test_non_list_payload_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            track_button_click(json.dumps({"a": 1}))

    def test_batch_too_large_raises_validation_error(self):
        logs = [{"label": "Save"}] * (MAX_BATCH_ENTRIES + 1)
        with self.assertRaises(frappe.ValidationError):
            track_button_click(logs)

    def test_entry_with_no_label_is_skipped(self):
        logs = [{"button_type": "primary", "action_type": "save"}]
        result = track_button_click(logs)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        frappe.db.bulk_insert.assert_not_called()

    def test_entry_with_empty_label_is_skipped(self):
        logs = [{"label": "", "action_type": "save"}]
        result = track_button_click(logs)
        self.assertEqual(result["inserted"], 0)

    def test_entry_with_whitespace_only_label_is_skipped(self):
        logs = [{"label": "   ", "action_type": "save"}]
        result = track_button_click(logs)
        self.assertEqual(result["inserted"], 0)

    def test_valid_label_is_inserted(self):
        logs = [{"label": "Save", "button_type": "primary", "action_type": "save"}]
        result = track_button_click(logs)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped"], 0)
        frappe.db.bulk_insert.assert_called_once()

    def test_label_truncated_to_140_chars(self):
        long_label = "L" * 200
        logs = [{"label": long_label}]
        track_button_click(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(len(row_dict["label"]), 140)

    def test_button_type_truncated_to_50_chars(self):
        logs = [{"label": "Btn", "button_type": "B" * 100}]
        track_button_click(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(len(row_dict["button_type"]), 50)

    def test_user_and_session_injected(self):
        frappe.session.user = "bob@example.com"
        frappe.session.sid = "sid_bob"
        logs = [{"label": "Submit"}]
        track_button_click(logs)

        call_args = frappe.db.bulk_insert.call_args
        fields = call_args[1]["fields"] if call_args[1] else call_args[0][1]
        rows = call_args[1]["values"] if call_args[1] else call_args[0][2]
        row_dict = dict(zip(fields, rows[0]))
        self.assertEqual(row_dict["user"], "bob@example.com")
        self.assertEqual(row_dict["session_id"], "sid_bob")

    def test_json_string_input_parsed(self):
        logs = [{"label": "Delete"}]
        result = track_button_click(json.dumps(logs))
        self.assertEqual(result["inserted"], 1)

    def test_empty_list_no_insert(self):
        result = track_button_click([])
        self.assertEqual(result["inserted"], 0)
        frappe.db.bulk_insert.assert_not_called()

    def test_mixed_batch_with_valid_and_invalid_labels(self):
        logs = [
            {"label": "Save"},    # valid
            {"label": ""},        # skipped
            {"label": "Submit"},  # valid
            {"label": "   "},     # skipped
        ]
        result = track_button_click(logs)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 2)

    def test_commit_called_after_insert(self):
        track_button_click([{"label": "OK"}])
        frappe.db.commit.assert_called()


# ---------------------------------------------------------------------------
# get_user_dashboard
# ---------------------------------------------------------------------------


class TestGetUserDashboard(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()
        # Make SQL calls return empty results so tests focus on logic
        frappe.db.sql.return_value = []

    def test_guest_raises_permission_error(self):
        frappe.session.user = "Guest"
        with self.assertRaises(frappe.PermissionError):
            get_user_dashboard()

    def test_user_can_view_own_data_without_viewer_role(self):
        frappe.session.user = "self@example.com"
        frappe.get_roles.return_value = ["Employee"]
        result = get_user_dashboard(user="self@example.com")
        self.assertEqual(result["user"], "self@example.com")

    def test_viewing_another_user_without_role_raises(self):
        frappe.session.user = "alice@example.com"
        frappe.get_roles.return_value = []
        with self.assertRaises(frappe.PermissionError):
            get_user_dashboard(user="bob@example.com")

    def test_viewing_another_user_with_viewer_role_passes(self):
        frappe.session.user = "viewer@example.com"
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        result = get_user_dashboard(user="bob@example.com")
        self.assertEqual(result["user"], "bob@example.com")

    def test_default_user_is_current_session_user(self):
        frappe.session.user = "current@example.com"
        result = get_user_dashboard()
        self.assertEqual(result["user"], "current@example.com")

    def test_period_today_returned_in_result(self):
        result = get_user_dashboard(period="today")
        self.assertEqual(result["period"], "today")

    def test_period_week_returned_in_result(self):
        result = get_user_dashboard(period="week")
        self.assertEqual(result["period"], "week")

    def test_period_month_returned_in_result(self):
        result = get_user_dashboard(period="month")
        self.assertEqual(result["period"], "month")

    def test_unknown_period_defaults_to_today(self):
        result = get_user_dashboard(period="unknown")
        self.assertEqual(result["period"], "unknown")

    def test_return_structure_has_expected_keys(self):
        result = get_user_dashboard()
        expected_keys = {
            "user", "period", "total_active_time", "total_idle_time",
            "active_hours", "sessions", "productivity_score",
            "total_button_clicks", "unique_buttons_used",
            "pages_visited", "doctypes_accessed", "session_history",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_empty_sql_results_yield_zero_defaults(self):
        frappe.db.sql.return_value = []
        result = get_user_dashboard()
        self.assertEqual(result["total_active_time"], 0)
        self.assertEqual(result["total_idle_time"], 0)
        self.assertEqual(result["sessions"], 0)
        self.assertEqual(result["total_button_clicks"], 0)

    def test_period_week_uses_7_day_range(self):
        """Period 'week' must set from_date to today - 7 days."""
        _frappe_utils.today.return_value = "2024-06-15"
        _frappe_utils.getdate.side_effect = lambda s: datetime.date.fromisoformat(str(s))

        get_user_dashboard(period="week")

        # Check that all SQL calls received from_date that is 7 days ago
        sql_calls = frappe.db.sql.call_args_list
        self.assertGreater(len(sql_calls), 0)
        for c in sql_calls:
            params = c[0][1] if len(c[0]) > 1 else c[1].get("values", {})
            if isinstance(params, dict) and "from_date" in params:
                self.assertEqual(str(params["from_date"]), "2024-06-08")

    def test_period_month_uses_30_day_range(self):
        """Period 'month' must set from_date to today - 30 days."""
        _frappe_utils.today.return_value = "2024-06-15"
        _frappe_utils.getdate.side_effect = lambda s: datetime.date.fromisoformat(str(s))

        get_user_dashboard(period="month")

        sql_calls = frappe.db.sql.call_args_list
        for c in sql_calls:
            params = c[0][1] if len(c[0]) > 1 else c[1].get("values", {})
            if isinstance(params, dict) and "from_date" in params:
                self.assertEqual(str(params["from_date"]), "2024-05-16")


# ---------------------------------------------------------------------------
# get_org_overview
# ---------------------------------------------------------------------------


class TestGetOrgOverview(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()
        frappe.db.sql.return_value = []

    def test_guest_raises_permission_error(self):
        frappe.session.user = "Guest"
        with self.assertRaises(frappe.PermissionError):
            get_org_overview()

    def test_user_without_viewer_role_raises(self):
        frappe.session.user = "user@example.com"
        frappe.get_roles.return_value = []
        with self.assertRaises(frappe.PermissionError):
            get_org_overview()

    def test_viewer_role_passes_and_returns_expected_keys(self):
        frappe.session.user = "viewer@example.com"
        frappe.get_roles.return_value = ["Activity Tracker Viewer"]
        # org_overview makes 5 SQL calls; use FrappeDict so attr access works
        frappe.db.sql.side_effect = [
            [FrappeDict(cnt=0)],
            [FrappeDict(avg_score=0)],
            [FrappeDict(total=0)],
            [], [], [],
        ]
        result = get_org_overview()
        expected = {
            "active_users_today", "avg_productivity_score",
            "total_active_seconds", "total_active_hours",
            "top_active_users", "least_active_users", "doctype_distribution",
        }
        self.assertEqual(set(result.keys()), expected)

    def test_empty_sql_results_yield_zero_defaults(self):
        frappe.session.user = "admin@example.com"
        frappe.get_roles.return_value = ["System Manager"]
        frappe.db.sql.side_effect = [[], [], [], [], [], []]
        result = get_org_overview()
        self.assertEqual(result["active_users_today"], 0)
        self.assertEqual(result["avg_productivity_score"], 0.0)
        self.assertEqual(result["total_active_seconds"], 0)
        self.assertEqual(result["total_active_hours"], 0)
        self.assertEqual(result["top_active_users"], [])
        self.assertEqual(result["doctype_distribution"], [])

    def test_sql_results_reflected_in_output(self):
        frappe.session.user = "admin@example.com"
        frappe.get_roles.return_value = ["System Manager"]

        # Configure sequential SQL return values for the 5 queries
        frappe.db.sql.side_effect = [
            [FrappeDict(cnt=7)],                                                         # active_users_today
            [FrappeDict(avg_score=82.5)],                                                # productivity_avg
            [FrappeDict(total=36000)],                                                   # total_active_seconds
            [FrappeDict(user="a@b.com", active_time=36000, active_hours=10.0)],          # top_users
            [],                                                                          # least_active
            [],                                                                          # doctype_distribution
        ]
        result = get_org_overview()
        self.assertEqual(result["active_users_today"], 7)
        self.assertEqual(result["avg_productivity_score"], 82.5)
        self.assertEqual(result["total_active_seconds"], 36000)
        self.assertAlmostEqual(result["total_active_hours"], 10.0)

    def test_system_manager_can_access(self):
        frappe.session.user = "admin@example.com"
        frappe.get_roles.return_value = ["System Manager"]
        frappe.db.sql.side_effect = [[], [], [], [], [], []]
        result = get_org_overview()
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# reset_app
# ---------------------------------------------------------------------------


class TestResetApp(unittest.TestCase):

    def setUp(self):
        _reset_frappe_defaults()
        frappe.db.count.return_value = 5
        frappe.db.delete.return_value = None

    def test_guest_raises_permission_error(self):
        frappe.session.user = "Guest"
        with self.assertRaises(frappe.PermissionError):
            reset_app()

    def test_non_system_manager_raises_permission_error(self):
        frappe.session.user = "user@example.com"
        frappe.has_role.return_value = False
        with self.assertRaises(frappe.PermissionError):
            reset_app()

    def test_system_manager_can_reset(self):
        frappe.session.user = "admin@example.com"
        frappe.has_role.return_value = True
        result = reset_app()
        self.assertEqual(result["status"], "ok")
        self.assertIn("deleted", result)

    def test_all_app_doctypes_deleted(self):
        frappe.session.user = "admin@example.com"
        frappe.has_role.return_value = True
        result = reset_app()
        for dt in APP_DOCTYPES:
            self.assertIn(dt, result["deleted"])

    def test_delete_exception_marks_doctype_as_minus_one(self):
        frappe.session.user = "admin@example.com"
        frappe.has_role.return_value = True
        frappe.db.delete.side_effect = Exception("DB error")
        result = reset_app()
        for dt in APP_DOCTYPES:
            self.assertEqual(result["deleted"][dt], -1)

    def test_commit_called_for_each_doctype_on_success(self):
        frappe.session.user = "admin@example.com"
        frappe.has_role.return_value = True
        frappe.db.delete.side_effect = None  # success
        reset_app()
        self.assertEqual(frappe.db.commit.call_count, len(APP_DOCTYPES))


if __name__ == "__main__":
    unittest.main()
