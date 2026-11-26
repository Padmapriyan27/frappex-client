# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-26

### Removed

- **Frappe 14 is no longer supported.** frappex-client now supports and
  tests the two current major versions, Frappe 15 and 16, on every change.
  Sites on Frappe 14 can keep using 0.1.1. Your own code can still run on
  Python 3.10 or later.

### Added

- `insert_many(doctype, docs, batch_size=200)` creates many documents in
  batches through `frappe.client.insert_many`. Each batch is saved
  completely or not at all, and the names come back in the order given.
- `bulk_update(doctype, {name: values}, batch_size=200)` changes many
  documents through `frappe.client.bulk_update`. Frappe saves each document
  separately; the ones it reported an error for are returned as
  `BulkUpdateFailure` items with the server's message. Frappe does not roll
  such a document back, so changes written before the error can remain.
- `BulkOperationError`, raised when a whole batch fails. It records the
  names already saved (`completed`), where to resume (`failed_at`) and the
  original exception (`error`). Like other writes, a batch is not retried
  after a network or server error.
- `run_report(report_name, filters=None)` runs a Query, Script or Custom
  Report through `frappe.desk.query_report.run` and returns a `ReportResult`:
  normalised `columns`, `rows` keyed by field name (old `"Label:Type/Options"`
  columns and list rows included), the `total_row` kept apart, the report's
  `message` and the `raw` reply. Filters you pass always apply, even to a
  Custom Report with saved filters. For a report that runs in the
  background (a prepared report), it returns the rows of the last completed
  run with the same filters and sets `prepared`.
- `PreparedReportError`, raised when a prepared report has no completed run
  for the filters, or its last run failed (on Frappe 16 the reason is in
  `error`),
  instead of returning a job status as if it were data.
- `download_pdf(doctype, name, ...)` and `download_pdf_to(doctype, name,
  target, ...)` render a document's print format as a PDF through
  `frappe.utils.print_format.download_pdf`, with optional `print_format`,
  `letterhead`, `no_letterhead` and `language`. A reply that is not
  `application/pdf`, such as an HTML page, raises `UnexpectedResponseError`
  instead of being written to the file. Like other downloads, they are not
  retried.

## [0.1.1] - 2026-11-24

### Changed

- **Renamed to `frappex-client`.** Install with `pip install frappex-client`
  and import `frappex_client`. The name `frappix` already belongs to an
  established Frappe community project by another author (Frappe on Nix), so
  this library no longer uses it. There are no other changes to the API.
- The base exception is now `FrappexError` (was `FrappixError`).
- Integration test settings are now `FRAPPEX_TEST_*` (were `FRAPPIX_TEST_*`).
- Documentation moved to <https://frappex-client.zeal.ninja>.

### Migrating from frappix 0.1.0

```bash
pip uninstall frappix
pip install frappex-client
```

Then replace `frappix` with `frappex_client` in imports and `FrappixError`
with `FrappexError`. The `frappix` 0.1.0 release on PyPI is yanked.

## [0.1.0] - 2026-11-24

First release, published under the name `frappix`.

### Added

- `Client` and `AsyncClient` with document, method, file and pagination calls.
- `TokenAuth`, `BearerAuth` and `PasswordAuth`.
- Guest access: `auth` is optional, for `ping`, public files and
  `allow_guest` methods.
- Typed exception hierarchy and `RetryPolicy`.
- Unit tests for both clients and an integration suite for a live site,
  run in CI against Frappe 14, 15 and 16.
- Property-based security tests, coverage threshold, and CI security
  scanning (CodeQL, Semgrep, Gitleaks, pip-audit, zizmor, Scorecard).

### Fixed

- `get_value` returns `None`, not an empty mapping, when nothing matches.
- An error reply containing an unpaired surrogate no longer crashes decoding.
- An unsupported `verify` value raises `ConfigurationError`.
- `exc_type` is read from Frappe 14's `exception` field when `exc_type` is
  absent.

[Unreleased]: https://github.com/Padmapriyan27/frappex-client/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Padmapriyan27/frappex-client/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Padmapriyan27/frappex-client/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Padmapriyan27/frappex-client/releases/tag/v0.1.0
