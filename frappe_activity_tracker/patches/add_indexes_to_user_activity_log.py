"""
Patch: add_indexes_to_user_activity_log
Add composite and single-column indexes to `tabUser Activity Log`
to support fast aggregation queries.
"""
from __future__ import unicode_literals

import frappe


def execute():
	table = "tabUser Activity Log"

	indexes = [
		("idx_ual_user_creation", ["user", "creation"]),
		("idx_ual_ref_doctype",   ["ref_doctype"]),
		("idx_ual_route",         ["route(140)"]),
	]

	existing = {
		row[0]
		for row in frappe.db.sql(
			f"SHOW INDEX FROM `{table}`",  # noqa: S608
		)
	}

	for index_name, cols in indexes:
		if index_name not in existing:
			col_list = ", ".join(f"`{c}`" for c in cols)
			frappe.db.sql(
				f"CREATE INDEX `{index_name}` ON `{table}` ({col_list})"  # noqa: S608
			)

	frappe.db.commit()
