# frappex-client: product requirements

| | |
|---|---|
| Status | Draft for review |
| Version covered | 0.1.x (first public releases) |
| Last updated | 2026-11-23 |

## 1. Summary

frappex-client is a Python library for talking to a Frappe or ERPNext site over its
REST API. It offers a blocking client and an `asyncio` client with the same
methods, typed results and errors, automatic pagination, and security rules
that are on by default.

It is for developers whose code runs **outside** a Frappe site and needs to
read or write its data: backend services, scripts, scheduled jobs, bots and
data pipelines.

## 2. Problem

Frappe ships a REST API, but there is no maintained, modern Python client for
it on PyPI.

| Package | State on 2026-11-23 |
|---|---|
| `frappe/frappe-client` (GitHub, official) | Archived. Never published to PyPI; a request to publish it has been open since 2021. |
| `frappe-client` (PyPI) | A third party's development build from December 2021, never updated. About 7,600 downloads a month. |
| `frappe-connector` (PyPI) | Maintained (v0.2.0, October 2026). Sync only, built on `requests`. About 40 downloads a month. |

Developers therefore either install an abandoned build or write raw HTTP
calls by hand. In both cases they solve the same problems again each time:

- No `asyncio` support, so the client cannot be used well from FastAPI, bots
  or any async program.
- No pagination: the API returns 20 rows by default, and reading everything
  means writing a loop.
- Errors arrive as Frappe's own JSON shape and must be decoded by hand.
- No guidance on what is safe to retry, so a retried insert can create a
  duplicate document.
- Security is left to the caller: TLS verification is commonly switched off,
  and credentials end up in logs.

## 3. Goals

1. One library that covers everyday REST use of a Frappe site from Python.
2. The same interface for sync and async code.
3. Safe by default: a developer who follows the quick start gets HTTPS,
   certificate checks, no credential leaks and no unsafe retries without
   configuring anything.
4. Fully typed, so editors and type checkers help the caller.
5. Small and auditable: one runtime dependency.

## 4. Non-goals

- Running inside a Frappe site (server-side code already has `frappe.*`).
- A typed model per DocType, or code generation from DocType definitions.
- The `/api/v2` routes. Planned for a later release.
- Socket.IO / realtime events, reports that run in the background (prepared reports), print formats and PDF generation.
- A command-line tool or an MCP server.
- Managing Frappe sites, benches or users.

## 5. Users

| User | What they need |
|---|---|
| Backend developer integrating another service with ERPNext | Reliable reads and writes, clear errors, async support. |
| Script or data author | A few lines to pull every row of a DocType. |
| Team running scheduled jobs | Timeouts, safe retries, credentials that stay out of logs. |
| Frappe app developer writing external tests or tools | A typed way to call their own whitelisted methods. |

## 6. Requirements

### 6.1 Functional

| ID | Requirement | In 0.1.0 |
|---|---|---|
| F1 | Sync `Client` and async `AsyncClient` with identical methods. | Yes |
| F2 | Authentication by API key and secret, OAuth bearer token, or username and password; guest access without credentials. | Yes |
| F3 | Document calls: list, get, insert, update, delete, submit, cancel, rename. | Yes |
| F4 | `get_count`, `get_value`, `set_value`. | Yes |
| F5 | Call any whitelisted method by `GET` or `POST`. | Yes |
| F6 | Upload a file, optionally attached to a document; download a file. | Yes |
| F7 | `iter_list` returns every matching row, page by page, in a stable order. | Yes |
| F8 | A distinct exception per failure class, carrying status, server exception type and server messages. | Yes |
| F9 | Configurable timeout and retry policy. | Yes |
| F10 | `/api/v2` routes (count, DocType meta, document copy). | No, later |
| F11 | Bulk insert and bulk update helpers. | Yes (0.2.0) |
| F12 | Run Query, Script and Custom Reports as columns and rows. | Yes (0.2.0) |

### 6.2 Security

| ID | Requirement |
|---|---|
| S1 | `http://` is refused unless the caller opts in explicitly. |
| S2 | TLS certificate verification cannot be disabled through client arguments. A private CA is supported. |
| S3 | Credentials are sent only to the configured host. Redirects are never followed. |
| S4 | Secrets never appear in `repr`, log output or exception messages. |
| S5 | DocType names, document names, method names and file paths cannot address a different endpoint. |
| S6 | Downloads accept only site-relative paths. |
| S7 | Uploaded files are private unless the caller says otherwise. |
| S8 | A write is never retried after a network failure or 5xx response. |
| S9 | Every request has a timeout, and response bodies have a size limit. |
| S10 | Server tracebacks are available for debugging but kept out of error text. |
| S11 | Releases are published through PyPI Trusted Publishing, with CI actions pinned by commit hash. |

Each of S1–S10 has at least one automated test.

### 6.3 Quality

- Python 3.10 to 3.14.
- Frappe v15 and v16 on the `/api/resource` and `/api/method` routes,
  verified by the integration suite in CI. Frappe v14 was supported up to
  0.1.1.
- `mypy --strict` and `ruff` clean; public names documented.
- Unit tests run without a network. Integration tests run against a real
  site and touch only data they create.

## 7. Success measures (proposed, to be confirmed)

| Measure | How it is read |
|---|---|
| Adoption | Monthly downloads on pypistats.org, compared with `frappe-client` (about 7,600) and `frappe-connector` (about 40). |
| Correctness | Integration suite green on each supported Frappe version before every release. |
| Trust | No open security report older than 30 days. |
| Community | Listed in a Frappe community resource; issues and pull requests from people outside the team. |

No numeric adoption target has been set yet.

## 8. Risks

| Risk | Effect | Response |
|---|---|---|
| Frappe publishes an official client. | frappex-client becomes an alternative, not the default. | Keep the scope small and the quality high; offer the code upstream. |
| `frappe-connector` adds async support. | The main differentiator narrows. | Compete on security defaults, typing and pagination. |
| Audience is limited to Frappe developers. | Download ceiling is modest. | Accepted; it was chosen for provable demand over reach. |
| Frappe changes REST behaviour between versions. | Calls break on a new version. | Integration tests per supported version. |
| The name resembles the Frappe trademark. | A rename could be requested. | The name does not contain "Frappe"; the README states the project is independent. |

## 9. Release plan

| Step | State |
|---|---|
| Library, unit tests, lint and type checks | Done |
| Integration tests written | Done |
| Integration tests run against Frappe v15 (15.112.0) | Done, 2026-11-23 |
| Integration tests run against Frappe v16 (16.0.0-dev) | Done, 2026-11-23 |
| Integration tests in CI on Frappe v15 and v16 | Workflow added; see the Integration badge for the current state |
| Security scanning in CI | Done |
| Public repository on GitHub (canonical) and GitLab (mirror) | Done |
| PyPI project and Trusted Publisher configured | Pending decision |
| 0.1.0 published to PyPI as `frappix` | Done, 2026-11-24; yanked after the rename |
| Renamed to `frappex-client` (the name `frappix` belongs to an existing Frappe community project) | Done, 2026-11-24 |
| 0.1.1 published as `frappex-client` | In progress |
| Announced on the Frappe forum | Pending |

## 10. Open questions

1. Resolved: GitHub is the canonical repository (required for PyPI Trusted
   Publishing); the self-hosted GitLab is a mirror.
2. Who owns the PyPI project and receives security reports?
3. Should `submit` and `cancel` return the updated document? They return nothing in 0.1.0.
4. Which release adds `/api/v2` support?
