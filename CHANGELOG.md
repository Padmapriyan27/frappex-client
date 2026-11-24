# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-24

First release.

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

[Unreleased]: https://github.com/Padmapriyan27/frappix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Padmapriyan27/frappix/releases/tag/v0.1.0
