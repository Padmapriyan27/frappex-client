"""Give the Administrator of a throwaway site an API key for the tests.

Run with the Frappe environment's Python from the bench ``sites`` directory:

    python provision_site.py <site> <port> <env-file>

Writes ``NAME=value`` lines for the FRAPPEX_TEST_* settings to ``env-file``.
"""

import os
import sys

import frappe


def main(site: str, port: str, env_file: str) -> None:
    """Create the key pair and write the test settings."""
    frappe.init(site=site, sites_path=".")
    frappe.connect()
    user = frappe.get_doc("User", "Administrator")
    secret = frappe.generate_hash(length=15)
    user.api_key = user.api_key or frappe.generate_hash(length=15)
    user.api_secret = secret
    user.save(ignore_permissions=True)
    frappe.db.commit()

    settings = {
        "FRAPPEX_TEST_URL": f"http://127.0.0.1:{port}",
        "FRAPPEX_TEST_HOST_HEADER": site,
        "FRAPPEX_TEST_API_KEY": user.api_key,
        "FRAPPEX_TEST_API_SECRET": secret,
        "FRAPPEX_TEST_USERNAME": "Administrator",
    }
    # These are credentials for a site that exists only for one test run. The
    # file is readable by the owner alone and is deleted with the runner.
    descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.writelines(f"{name}={value}\n" for name, value in settings.items())


if __name__ == "__main__":
    main(*sys.argv[1:4])
