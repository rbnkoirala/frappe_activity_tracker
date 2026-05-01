"""
Pytest configuration for frappe_activity_tracker.

Injects a lightweight mock of the ``frappe`` package into ``sys.modules``
**before** any test module imports frappe_activity_tracker code, so the full
test suite can run without a live Frappe / MariaDB installation.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# FrappeDict – mirrors frappe._dict (dict with attribute access)
# ---------------------------------------------------------------------------


class FrappeDict(dict):
    """
    Dict subclass that supports attribute-style read/write access,
    mirroring frappe._dict so code using both ``row.field`` and
    ``row["field"]`` works seamlessly in tests.
    """

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value


# ---------------------------------------------------------------------------
# Custom exception classes that mirror Frappe's public API
# ---------------------------------------------------------------------------


class FrappePermissionError(Exception):
    """Stand-in for frappe.PermissionError."""


class FrappeValidationError(Exception):
    """Stand-in for frappe.ValidationError."""


# ---------------------------------------------------------------------------
# frappe.throw – must actually raise so tests can use assertRaises
# ---------------------------------------------------------------------------


def _frappe_throw(msg, exc=None):
    raise (exc or Exception)(str(msg))


# ---------------------------------------------------------------------------
# Build the frappe mock
# ---------------------------------------------------------------------------


def _build_frappe_mock() -> MagicMock:
    mock = MagicMock(name="frappe")

    # Exception classes
    mock.PermissionError = FrappePermissionError
    mock.ValidationError = FrappeValidationError

    # Core helpers
    mock.throw = _frappe_throw
    mock._ = lambda x: x  # translation pass-through

    # @frappe.whitelist() is called with optional kwargs and must return a
    # decorator that passes the function through unchanged.
    mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)

    # Session defaults (tests override as needed)
    mock.session.user = "test@example.com"
    mock.session.sid = "testsession123"

    # generate_hash – return a short predictable string
    mock.generate_hash.return_value = "abc1234567"

    # get_roles – default to empty; tests override per scenario
    mock.get_roles.return_value = []

    # has_role – default False; tests override per scenario
    mock.has_role.return_value = False

    # logger() – return a MagicMock that absorbs .info/.warning calls
    mock.logger.return_value = MagicMock()

    # _dict – Frappe dict subclass supporting both attribute and key access.
    mock._dict = FrappeDict

    return mock


def _build_frappe_utils_mock() -> MagicMock:
    import datetime

    utils = MagicMock(name="frappe.utils")
    utils.today.return_value = "2024-06-15"
    utils.getdate.side_effect = lambda s: (
        datetime.date.fromisoformat(str(s)) if s else datetime.date.today()
    )
    utils.now_datetime.return_value = datetime.datetime(2024, 6, 15, 10, 0, 0)
    return utils


# ---------------------------------------------------------------------------
# Inject mocks into sys.modules (idempotent – safe to call multiple times)
# ---------------------------------------------------------------------------

frappe_mock = _build_frappe_mock()
frappe_utils_mock = _build_frappe_utils_mock()

sys.modules.setdefault("frappe", frappe_mock)
sys.modules.setdefault("frappe.utils", frappe_utils_mock)
sys.modules.setdefault("frappe.model", MagicMock(name="frappe.model"))
sys.modules.setdefault(
    "frappe.model.document", MagicMock(name="frappe.model.document")
)
