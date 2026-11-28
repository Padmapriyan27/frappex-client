"""Give documents one creation timestamp, directly in a test site's database.

The API refuses to change ``creation`` (it is a constant), but the keyset
paging tests need many rows that share one. Run with the site's Python from
the bench ``sites`` directory:

    python set_creation.py <site> <doctype> <timestamp> <name> [<name> ...]
"""

import sys

import frappe


def main(site: str, doctype: str, timestamp: str, names: list[str]) -> None:
    """Set ``creation`` on the named documents and commit."""
    frappe.init(site=site, sites_path=".")
    frappe.connect()
    try:
        frappe.db.set_value(
            doctype, {"name": ("in", names)}, "creation", timestamp, update_modified=False
        )
        frappe.db.commit()
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
