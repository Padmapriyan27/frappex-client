# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `Client` and `AsyncClient` with document, method, file and pagination calls.
- `TokenAuth`, `BearerAuth` and `PasswordAuth`.
- Typed exception hierarchy and `RetryPolicy`.
- Unit tests for both clients and an integration suite for a live site,
  verified against Frappe 15 and 16.
- Property-based security tests, coverage threshold, and CI security
  scanning (CodeQL, Semgrep, Gitleaks, pip-audit, zizmor, Scorecard).

### Fixed

- `get_value` returns `None`, not an empty mapping, when nothing matches.
- An error reply containing an unpaired surrogate no longer crashes decoding.
- An unsupported `verify` value raises `ConfigurationError`.
