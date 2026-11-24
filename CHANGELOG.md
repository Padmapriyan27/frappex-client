# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/Padmapriyan27/frappex-client/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Padmapriyan27/frappex-client/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Padmapriyan27/frappex-client/releases/tag/v0.1.0
