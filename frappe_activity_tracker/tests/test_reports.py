"""
Tests for all report modules in frappe_activity_tracker.

Each report has three parts we test:
    1. get_columns() – returns a well-formed list of column dicts.
    2. build_conditions() – pure-Python logic that builds SQL WHERE fragments.
    3. execute() – integration of get_columns + get_data via mocked frappe.db.sql.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

# frappe mock seeded by conftest.py
import frappe

_frappe_utils = sys.modules["frappe.utils"]

# ---------------------------------------------------------------------------
# Import all report modules
# ---------------------------------------------------------------------------

from frappe_activity_tracker.frappe_activity_tracker.report.time_per_doctype import (
    time_per_doctype,
)
from frappe_activity_tracker.frappe_activity_tracker.report.time_per_user import (
    time_per_user,
)
from frappe_activity_tracker.frappe_activity_tracker.report.time_per_report import (
    time_per_report,
)
from frappe_activity_tracker.frappe_activity_tracker.report.user_activity_timeline import (
    user_activity_timeline,
)
from frappe_activity_tracker.frappe_activity_tracker.report.most_clicked_actions import (
    most_clicked_actions,
)
from frappe_activity_tracker.frappe_activity_tracker.report.most_used_buttons import (
    most_used_buttons,
)
from frappe_activity_tracker.frappe_activity_tracker.report.org_active_users_today import (
    org_active_users_today,
)
from frappe_activity_tracker.frappe_activity_tracker.report.productivity_score_per_user import (
    productivity_score_per_user,
)
from frappe_activity_tracker.frappe_activity_tracker.report.system_usage_heatmap import (
    system_usage_heatmap,
)
from frappe_activity_tracker.frappe_activity_tracker.report.user_button_click_frequency import (
    user_button_click_frequency,
)
from frappe_activity_tracker.frappe_activity_tracker.report.user_idle_active_breakdown import (
    user_idle_active_breakdown,
)
from frappe_activity_tracker.frappe_activity_tracker.report.user_interaction_count import (
    user_interaction_count,
)
from frappe_activity_tracker.frappe_activity_tracker.report.actions_per_doctype import (
    actions_per_doctype,
)
from frappe_activity_tracker.frappe_activity_tracker.report.daily_work_hours import (
    daily_work_hours,
)

# Import the FrappeDict helper from conftest so tests can return rows that
# support both dict-key and attribute access (like frappe._dict).
from frappe_activity_tracker.tests.conftest import FrappeDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_sql():
    frappe.db.sql.reset_mock()
    frappe.db.sql.side_effect = None
    frappe.db.sql.return_value = []


def _assert_column_structure(test_case, columns):
    """Assert that each column is a dict with at least label, fieldname, fieldtype."""
    test_case.assertIsInstance(columns, list)
    test_case.assertGreater(len(columns), 0)
    for col in columns:
        test_case.assertIsInstance(col, dict)
        test_case.assertIn("label", col)
        test_case.assertIn("fieldname", col)
        test_case.assertIn("fieldtype", col)


# ===========================================================================
# 1. Time Per Doctype
# ===========================================================================


class TestTimePerDoctype(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    # --- get_columns ---------------------------------------------------------

    def test_get_columns_returns_valid_structure(self):
        cols = time_per_doctype.get_columns()
        _assert_column_structure(self, cols)

    def test_get_columns_includes_ref_doctype(self):
        fieldnames = [c["fieldname"] for c in time_per_doctype.get_columns()]
        self.assertIn("ref_doctype", fieldnames)

    def test_get_columns_includes_active_time(self):
        fieldnames = [c["fieldname"] for c in time_per_doctype.get_columns()]
        self.assertIn("active_time", fieldnames)

    # --- build_conditions ----------------------------------------------------

    def test_no_filters_empty_conditions(self):
        cond, vals = time_per_doctype.build_conditions({})
        self.assertEqual(cond, "")
        self.assertEqual(vals, {})

    def test_user_filter_adds_condition(self):
        cond, vals = time_per_doctype.build_conditions({"user": "alice@example.com"})
        self.assertIn("user", cond)
        self.assertEqual(vals["user"], "alice@example.com")

    def test_from_date_filter_adds_condition(self):
        cond, vals = time_per_doctype.build_conditions({"from_date": "2024-01-01"})
        self.assertIn("from_date", cond)
        self.assertIn("from_date", vals)

    def test_to_date_filter_adds_condition(self):
        cond, vals = time_per_doctype.build_conditions({"to_date": "2024-12-31"})
        self.assertIn("to_date", cond)
        self.assertIn("to_date", vals)

    def test_all_filters_combined(self):
        filters = {"user": "u@e.com", "from_date": "2024-01-01", "to_date": "2024-12-31"}
        cond, vals = time_per_doctype.build_conditions(filters)
        self.assertIn("user", cond)
        self.assertIn("from_date", cond)
        self.assertIn("to_date", cond)

    # --- execute -------------------------------------------------------------

    def test_execute_returns_two_element_tuple(self):
        result = time_per_doctype.execute()
        self.assertEqual(len(result), 2)

    def test_execute_columns_valid(self):
        columns, _ = time_per_doctype.execute()
        _assert_column_structure(self, columns)

    def test_execute_data_is_list(self):
        _, data = time_per_doctype.execute()
        self.assertIsInstance(data, list)


# ===========================================================================
# 2. Time Per User
# ===========================================================================


class TestTimePerUser(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, time_per_user.get_columns())

    def test_get_columns_has_productivity_score(self):
        fieldnames = [c["fieldname"] for c in time_per_user.get_columns()]
        self.assertIn("productivity_score", fieldnames)

    def test_no_filters(self):
        cond, vals = time_per_user.build_conditions({})
        self.assertEqual(cond, "")
        self.assertEqual(vals, {})

    def test_user_filter(self):
        cond, vals = time_per_user.build_conditions({"user": "bob@example.com"})
        self.assertIn("user", cond)
        self.assertEqual(vals["user"], "bob@example.com")

    def test_from_date_filter(self):
        cond, vals = time_per_user.build_conditions({"from_date": "2024-01-01"})
        self.assertIn("from_date", vals)

    def test_to_date_filter(self):
        cond, vals = time_per_user.build_conditions({"to_date": "2024-06-30"})
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = time_per_user.execute()
        _assert_column_structure(self, cols)
        self.assertIsInstance(data, list)


# ===========================================================================
# 3. Time Per Report
# ===========================================================================


class TestTimePerReport(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, time_per_report.get_columns())

    def test_get_columns_has_docname(self):
        fieldnames = [c["fieldname"] for c in time_per_report.get_columns()]
        self.assertIn("docname", fieldnames)

    def test_no_filters(self):
        cond, vals = time_per_report.build_conditions({})
        self.assertEqual(cond, "")
        self.assertEqual(vals, {})

    def test_user_filter(self):
        cond, vals = time_per_report.build_conditions({"user": "carol@example.com"})
        self.assertIn("user", cond)

    def test_date_range_filters(self):
        cond, vals = time_per_report.build_conditions({
            "from_date": "2024-01-01",
            "to_date": "2024-01-31",
        })
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = time_per_report.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 4. User Activity Timeline
# ===========================================================================


class TestUserActivityTimeline(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, user_activity_timeline.get_columns())

    def test_get_columns_has_hour_of_day(self):
        fieldnames = [c["fieldname"] for c in user_activity_timeline.get_columns()]
        self.assertIn("hour_of_day", fieldnames)

    def test_no_date_filter_uses_today(self):
        """When no date filter, should default to today."""
        cond, vals = user_activity_timeline.build_conditions({})
        self.assertIn("date", vals)

    def test_date_filter_applied(self):
        cond, vals = user_activity_timeline.build_conditions({"date": "2024-06-01"})
        self.assertIn("date", vals)

    def test_user_filter_applied(self):
        cond, vals = user_activity_timeline.build_conditions({"user": "alice@example.com"})
        self.assertIn("user", cond)
        self.assertEqual(vals["user"], "alice@example.com")

    def test_view_type_filter_applied(self):
        cond, vals = user_activity_timeline.build_conditions({"view_type": "Form"})
        self.assertIn("view_type", cond)
        self.assertEqual(vals["view_type"], "Form")

    def test_all_filters_combined(self):
        cond, vals = user_activity_timeline.build_conditions({
            "user": "u@e.com",
            "date": "2024-06-15",
            "view_type": "List",
        })
        self.assertIn("user", cond)
        self.assertIn("view_type", cond)
        self.assertIn("date", vals)

    def test_execute_returns_tuple(self):
        cols, data = user_activity_timeline.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 5. Most Clicked Actions
# ===========================================================================


class TestMostClickedActions(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, most_clicked_actions.get_columns())

    def test_get_columns_has_action_type(self):
        fieldnames = [c["fieldname"] for c in most_clicked_actions.get_columns()]
        self.assertIn("action_type", fieldnames)

    def test_no_filters(self):
        cond, vals = most_clicked_actions.build_conditions({})
        self.assertEqual(cond, "")
        self.assertEqual(vals, {})

    def test_user_filter(self):
        cond, vals = most_clicked_actions.build_conditions({"user": "dave@example.com"})
        self.assertIn("user", cond)

    def test_date_range(self):
        cond, vals = most_clicked_actions.build_conditions({
            "from_date": "2024-01-01",
            "to_date": "2024-01-31",
        })
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = most_clicked_actions.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 6. Most Used Buttons
# ===========================================================================


class TestMostUsedButtons(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, most_used_buttons.get_columns())

    def test_get_columns_has_label(self):
        fieldnames = [c["fieldname"] for c in most_used_buttons.get_columns()]
        self.assertIn("label", fieldnames)

    def test_no_filters(self):
        cond, vals = most_used_buttons.build_conditions({})
        self.assertEqual(cond, "")

    def test_user_filter(self):
        cond, vals = most_used_buttons.build_conditions({"user": "eve@example.com"})
        self.assertIn("user", cond)

    def test_execute_returns_tuple(self):
        cols, data = most_used_buttons.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 7. Org Active Users Today
# ===========================================================================


class TestOrgActiveUsersToday(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, org_active_users_today.get_columns())

    def test_get_columns_has_button_clicks(self):
        fieldnames = [c["fieldname"] for c in org_active_users_today.get_columns()]
        self.assertIn("button_clicks", fieldnames)

    def test_execute_with_empty_results(self):
        frappe.db.sql.side_effect = [[], []]  # activity + clicks both empty
        cols, data = org_active_users_today.execute()
        _assert_column_structure(self, cols)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_execute_enriches_rows_with_button_clicks(self):
        """Rows from activity SQL are enriched with click count from button SQL."""
        activity_row = FrappeDict(
            user="frank@example.com",
            sessions=3,
            active_hours=2.5,
            idle_hours=0.5,
            productivity_score=83.33,
            pages_visited=10,
            doctypes_accessed=4,
        )
        click_row = FrappeDict(user="frank@example.com", cnt=42)

        frappe.db.sql.side_effect = [
            [activity_row],  # first call: activity
            [click_row],     # second call: clicks
        ]

        _, data = org_active_users_today.execute()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["button_clicks"], 42)

    def test_execute_uses_filter_date(self):
        frappe.db.sql.side_effect = [[], []]  # activity + clicks
        org_active_users_today.execute(filters={"date": "2024-05-01"})
        calls = frappe.db.sql.call_args_list
        for c in calls:
            params = c[0][1] if len(c[0]) > 1 else {}
            if isinstance(params, dict) and "date" in params:
                self.assertEqual(params["date"], "2024-05-01")

    def test_execute_defaults_to_today(self):
        _frappe_utils.today.return_value = "2024-06-15"
        frappe.db.sql.side_effect = [[], []]  # activity + clicks
        org_active_users_today.execute(filters={})
        calls = frappe.db.sql.call_args_list
        for c in calls:
            params = c[0][1] if len(c[0]) > 1 else {}
            if isinstance(params, dict) and "date" in params:
                self.assertEqual(params["date"], "2024-06-15")

    def test_user_without_clicks_gets_zero(self):
        activity_row = FrappeDict(
            user="greta@example.com",
            sessions=1,
            active_hours=1.0,
            idle_hours=0.0,
            productivity_score=100.0,
            pages_visited=5,
            doctypes_accessed=2,
        )
        frappe.db.sql.side_effect = [
            [activity_row],  # activity
            [],              # no clicks
        ]
        _, data = org_active_users_today.execute()
        self.assertEqual(data[0]["button_clicks"], 0)


# ===========================================================================
# 8. Productivity Score Per User
# ===========================================================================


class TestProductivityScorePerUser(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, productivity_score_per_user.get_columns())

    def test_get_columns_has_productivity_score(self):
        fieldnames = [c["fieldname"] for c in productivity_score_per_user.get_columns()]
        self.assertIn("productivity_score", fieldnames)

    def test_no_filters(self):
        cond, vals = productivity_score_per_user.build_conditions({})
        self.assertEqual(cond, "")

    def test_user_filter(self):
        cond, vals = productivity_score_per_user.build_conditions({"user": "h@e.com"})
        self.assertIn("user", cond)

    def test_from_date_filter(self):
        cond, vals = productivity_score_per_user.build_conditions({"from_date": "2024-01-01"})
        self.assertIn("from_date", vals)

    def test_to_date_filter(self):
        cond, vals = productivity_score_per_user.build_conditions({"to_date": "2024-06-30"})
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = productivity_score_per_user.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 9. System Usage Heatmap
# ===========================================================================


class TestSystemUsageHeatmap(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, system_usage_heatmap.get_columns())

    def test_get_columns_has_day_of_week(self):
        fieldnames = [c["fieldname"] for c in system_usage_heatmap.get_columns()]
        self.assertIn("day_of_week", fieldnames)

    def test_no_filters_has_default_from_date(self):
        """When from_date is not supplied, a 90-day default is applied."""
        cond, vals = system_usage_heatmap.build_conditions({})
        self.assertIn("from_date", vals)

    def test_explicit_from_date_overrides_default(self):
        cond, vals = system_usage_heatmap.build_conditions({"from_date": "2024-01-01"})
        self.assertIn("from_date", vals)

    def test_user_filter(self):
        cond, vals = system_usage_heatmap.build_conditions({"user": "ivan@example.com"})
        self.assertIn("user", cond)

    def test_to_date_filter(self):
        cond, vals = system_usage_heatmap.build_conditions({"to_date": "2024-12-31"})
        self.assertIn("to_date", vals)

    def test_execute_translates_dow_num_to_label(self):
        """DOW numbers must be translated to day names like 'Monday'."""
        frappe.db.sql.return_value = [
            {"dow_num": 2, "hour_of_day": 9, "sessions": 5, "unique_users": 3, "active_hours": 1.5}
        ]
        _, data = system_usage_heatmap.execute()
        self.assertEqual(data[0]["day_of_week"], "Monday")

    def test_execute_unknown_dow_num_falls_back_to_string(self):
        frappe.db.sql.return_value = [
            {"dow_num": 99, "hour_of_day": 9, "sessions": 1, "unique_users": 1, "active_hours": 0.5}
        ]
        _, data = system_usage_heatmap.execute()
        self.assertEqual(data[0]["day_of_week"], "99")

    def test_execute_returns_tuple(self):
        cols, data = system_usage_heatmap.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 10. User Button Click Frequency
# ===========================================================================


class TestUserButtonClickFrequency(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, user_button_click_frequency.get_columns())

    def test_get_columns_has_total_clicks(self):
        fieldnames = [c["fieldname"] for c in user_button_click_frequency.get_columns()]
        self.assertIn("total_clicks", fieldnames)

    def test_no_filters(self):
        cond, vals = user_button_click_frequency.build_conditions({})
        self.assertEqual(cond, "")

    def test_user_filter(self):
        cond, vals = user_button_click_frequency.build_conditions({"user": "j@e.com"})
        self.assertIn("user", cond)

    def test_date_range(self):
        cond, vals = user_button_click_frequency.build_conditions({
            "from_date": "2024-01-01",
            "to_date": "2024-03-31",
        })
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = user_button_click_frequency.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 11. User Idle Active Breakdown
# ===========================================================================


class TestUserIdleActiveBreakdown(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, user_idle_active_breakdown.get_columns())

    def test_get_columns_has_active_pct(self):
        fieldnames = [c["fieldname"] for c in user_idle_active_breakdown.get_columns()]
        self.assertIn("active_pct", fieldnames)

    def test_no_filters_has_default_from_date(self):
        """When from_date is absent, a 30-day default is applied."""
        cond, vals = user_idle_active_breakdown.build_conditions({})
        self.assertIn("from_date", vals)

    def test_explicit_from_date_overrides_default(self):
        cond, vals = user_idle_active_breakdown.build_conditions({"from_date": "2024-05-01"})
        self.assertIn("from_date", vals)

    def test_to_date_filter(self):
        cond, vals = user_idle_active_breakdown.build_conditions({"to_date": "2024-05-31"})
        self.assertIn("to_date", vals)

    def test_user_filter(self):
        cond, vals = user_idle_active_breakdown.build_conditions({"user": "kate@example.com"})
        self.assertIn("user", cond)

    def test_execute_returns_tuple(self):
        cols, data = user_idle_active_breakdown.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 12. User Interaction Count
# ===========================================================================


class TestUserInteractionCount(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, user_interaction_count.get_columns())

    def test_get_columns_has_total_clicks(self):
        fieldnames = [c["fieldname"] for c in user_interaction_count.get_columns()]
        self.assertIn("total_clicks", fieldnames)

    def test_no_filters(self):
        cond, vals = user_interaction_count.build_conditions({})
        self.assertEqual(cond, "")

    def test_user_filter(self):
        cond, vals = user_interaction_count.build_conditions({"user": "leo@example.com"})
        self.assertIn("user", cond)

    def test_date_range(self):
        cond, vals = user_interaction_count.build_conditions({
            "from_date": "2024-01-01",
            "to_date": "2024-01-31",
        })
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = user_interaction_count.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 13. Actions Per Doctype
# ===========================================================================


class TestActionsPerDoctype(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, actions_per_doctype.get_columns())

    def test_get_columns_has_action_type(self):
        fieldnames = [c["fieldname"] for c in actions_per_doctype.get_columns()]
        self.assertIn("action_type", fieldnames)

    def test_no_filters(self):
        cond, vals = actions_per_doctype.build_conditions({})
        self.assertEqual(cond, "")

    def test_user_filter(self):
        cond, vals = actions_per_doctype.build_conditions({"user": "maya@example.com"})
        self.assertIn("user", cond)

    def test_date_range(self):
        cond, vals = actions_per_doctype.build_conditions({
            "from_date": "2024-02-01",
            "to_date": "2024-02-28",
        })
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = actions_per_doctype.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# 14. Daily Work Hours
# ===========================================================================


class TestDailyWorkHours(unittest.TestCase):

    def setUp(self):
        _reset_sql()

    def test_get_columns_valid(self):
        _assert_column_structure(self, daily_work_hours.get_columns())

    def test_get_columns_has_total_hours(self):
        fieldnames = [c["fieldname"] for c in daily_work_hours.get_columns()]
        self.assertIn("total_hours", fieldnames)

    def test_get_columns_has_doctype_breakdown(self):
        fieldnames = [c["fieldname"] for c in daily_work_hours.get_columns()]
        self.assertIn("doctype_breakdown", fieldnames)

    def test_no_filters(self):
        cond, vals = daily_work_hours.build_conditions({})
        self.assertEqual(cond, "")
        self.assertEqual(vals, {})

    def test_user_filter(self):
        cond, vals = daily_work_hours.build_conditions({"user": "nina@example.com"})
        self.assertIn("user", cond)
        self.assertEqual(vals["user"], "nina@example.com")

    def test_from_date_filter(self):
        cond, vals = daily_work_hours.build_conditions({"from_date": "2024-03-01"})
        self.assertIn("from_date", vals)

    def test_to_date_filter(self):
        cond, vals = daily_work_hours.build_conditions({"to_date": "2024-03-31"})
        self.assertIn("to_date", vals)

    def test_all_filters(self):
        cond, vals = daily_work_hours.build_conditions({
            "user": "oliver@example.com",
            "from_date": "2024-01-01",
            "to_date": "2024-01-31",
        })
        self.assertIn("user", cond)
        self.assertIn("from_date", vals)
        self.assertIn("to_date", vals)

    def test_execute_returns_tuple(self):
        cols, data = daily_work_hours.execute()
        _assert_column_structure(self, cols)


# ===========================================================================
# Cross-report: system_usage_heatmap DOW label mapping
# ===========================================================================


class TestDowLabelMapping(unittest.TestCase):
    """Verify all day-of-week numbers map to the correct label."""

    _expected = {
        1: "Sunday",
        2: "Monday",
        3: "Tuesday",
        4: "Wednesday",
        5: "Thursday",
        6: "Friday",
        7: "Saturday",
    }

    def setUp(self):
        _reset_sql()

    def _run_for_dow(self, dow_num):
        frappe.db.sql.return_value = [
            {"dow_num": dow_num, "hour_of_day": 10, "sessions": 1, "unique_users": 1, "active_hours": 0.5}
        ]
        _, data = system_usage_heatmap.execute()
        return data[0]["day_of_week"]

    def test_sunday(self):
        self.assertEqual(self._run_for_dow(1), "Sunday")

    def test_monday(self):
        self.assertEqual(self._run_for_dow(2), "Monday")

    def test_tuesday(self):
        self.assertEqual(self._run_for_dow(3), "Tuesday")

    def test_wednesday(self):
        self.assertEqual(self._run_for_dow(4), "Wednesday")

    def test_thursday(self):
        self.assertEqual(self._run_for_dow(5), "Thursday")

    def test_friday(self):
        self.assertEqual(self._run_for_dow(6), "Friday")

    def test_saturday(self):
        self.assertEqual(self._run_for_dow(7), "Saturday")


if __name__ == "__main__":
    unittest.main()
