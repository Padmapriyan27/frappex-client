# Developer guide

For people changing frappix itself. To *use* the library, read the
[README](../README.md).

## Setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.10 or newer.

```bash
git clone <repository-url> && cd frappix
uv sync
```

Run everything CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pip-audit
```

## How the code is organised

The Frappe API rules are written once, as plain functions that never touch
the network. The two clients are thin layers that send what those functions
describe. This is why the sync and async clients cannot drift apart.

```
src/frappix/
  __init__.py        Public names. Anything not exported here is private.
  exceptions.py      Public exception tree.
  types.py           Public type aliases (Document, Filters).
  _auth.py           Secret wrapper and the three auth strategies.
  _config.py         base_url validation, extra-header checks, RetryPolicy.
  _protocol.py       Wire format: Request, RawResponse, safe URL paths, decode().
  _operations.py     One function per API call, returning an Operation.
  _base.py           ClientCore: settings shared by both clients.
  _client.py         Client (blocking).
  _async_client.py   AsyncClient (asyncio).
```

Modules starting with `_` are internal and may change in any release.

### Life of a call

`client.get_doc("ToDo", "T1")` goes through these steps:

1. `_operations.get_doc` builds an `Operation`: a `Request` (method, encoded
   path, query, body) plus a `parse` function for the reply.
2. `Client._execute` logs in first if the client uses `PasswordAuth`.
3. `Client._run` sends the request with `_send`, which streams the body and
   enforces the size limit, returning a `RawResponse`.
4. `RetryPolicy` decides whether to wait and try again.
5. `_protocol.decode` turns the `RawResponse` into the JSON object, or raises
   the matching exception.
6. The operation's `parse` picks the result out of that object.

Steps 1, 4, 5 and 6 are pure and shared. Only steps 2 and 3 differ between
the two clients.

## Adding an API call

1. Add a function to `_operations.py` that returns an `Operation`. Build
   paths with `resource_path` or `method_path`; never format a name into a
   URL yourself.
2. Add a method with the same name and arguments to `Client` **and**
   `AsyncClient`. Each is one line: `return self._execute(ops.<name>(...))`,
   with `await` in the async client.
3. Add a test to `tests/unit/test_clients.py` using the `site` fixture. It
   runs once per client automatically.
4. Add a case to `tests/integration/test_live_site.py` if the call's server
   behaviour is not obvious.
5. Add the method to the table in the README and a line to `CHANGELOG.md`.

## Security rules for contributors

These are requirements, not preferences. A change that weakens one needs a
stated reason and a test.

- Never add an option that disables TLS verification.
- Never follow redirects.
- Never put a `Secret`'s value in a log line, `repr`, or exception message.
  Call `.reveal()` only where the value goes on the wire.
- Never include query strings, headers or request bodies in log lines or
  transport error messages; they can hold personal data.
- Every name that becomes part of a URL goes through `_protocol`.
- Do not retry writes. `RetryPolicy` is the only place that decides retries.
- New runtime dependencies need a strong reason; the library has one.

## Tests

| Kind | Location | Needs |
|---|---|---|
| Pure logic | `tests/unit/test_pure.py` | Nothing |
| Both clients against a fake site | `tests/unit/test_clients.py` | Nothing |
| Real Frappe site | `tests/integration/` | A site and an API key |

The `site` fixture in `tests/unit/conftest.py` records every request and
replies from a queue. `site.run(lambda c: c.some_method(...))` runs the call
on the sync or the async client and returns the result either way.

### Integration tests

They are skipped unless these variables are set:

```bash
export FRAPPIX_TEST_URL=http://localhost:8000
export FRAPPIX_TEST_API_KEY=...
export FRAPPIX_TEST_API_SECRET=...
export FRAPPIX_TEST_HOST_HEADER=mysite.localhost   # only for a multi-site bench
export FRAPPIX_TEST_USERNAME=Administrator         # optional: password-login tests
export FRAPPIX_TEST_PASSWORD=...                   # optional
uv run pytest -m integration
```

Use a disposable or development site, never production. The API user needs
the **System Manager** role.

What the tests write, and how it is removed:

| Written | Removed by |
|---|---|
| `ToDo` documents whose description holds a unique marker | The `marker` fixture, after each test |
| `File` documents attached during upload tests | The test itself, in a `finally` block |
| One custom DocType named `Frappix Test <id>` and its documents | The `doctype` fixture, at the end of the run |

The custom DocType is submittable and lets the caller choose document names,
which is what makes the submit, cancel, rename and awkward-name tests
possible on a site with only Frappe installed.

| File | Covers |
|---|---|
| `tests/integration/conftest.py` | Settings, the shared client, the `marker` and `doctype` fixtures |
| `tests/integration/test_documents.py` | CRUD, filters, paging, awkward names, submit, cancel, rename, error mapping |
| `tests/integration/test_methods_files_auth.py` | Method calls, uploads, downloads, wrong credentials, password login, the async client |

Known server behaviour the tests allow for: the development server
(`bench serve`) answers HTTP 500 for a missing static file, where a
production site behind nginx answers 404.

## Style

- Code and docstrings follow PEP 8 and PEP 257, with Google-style docstring
  sections. `ruff` enforces both.
- Public functions are fully type-annotated; `mypy --strict` must pass.
- Commits and pull request titles follow
  [Conventional Commits](https://www.conventionalcommits.org), such as
  `feat(client): add get_meta` or `fix(protocol): encode '#' in names`.

## Releasing

1. Update `version` in `pyproject.toml` and move the `Unreleased` entries in
   `CHANGELOG.md` under the new version.
2. Run the full checks and the integration tests.
3. Merge to `main`, then publish a GitHub release with the tag `v<version>`.
   This step needs a GitHub mirror of the repository: PyPI Trusted Publishing
   does not support a self-hosted GitLab.
4. The `Release` workflow builds the package and publishes it to PyPI through
   Trusted Publishing. No PyPI token is stored anywhere.

One-time setup: on PyPI, register the repository and `release.yml` as a
trusted publisher for the `frappix` project, with the environment `pypi`.
