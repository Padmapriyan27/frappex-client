# frappix

A typed REST client for [Frappe](https://frappe.io/framework) and ERPNext sites,
with a blocking client and an `asyncio` client that share one implementation.

frappix is an independent community project. It is not affiliated with or
endorsed by Frappe Technologies.

- Sync (`Client`) and async (`AsyncClient`) with identical methods
- API key, OAuth bearer token and username/password authentication
- Automatic pagination with `iter_list`
- A typed exception for each kind of failure
- Retries only where repeating a request is safe
- Secure defaults: HTTPS only, certificate checks always on, no redirects
  followed, credentials never printed
- Fully type-annotated; one dependency (`httpx`)

Requires Python 3.10+. Uses the `/api/resource` and `/api/method` routes.
Tested against Frappe v15 and v16; v14 exposes the same routes but has not
been tested yet.

## Install

```bash
pip install frappix
```

## Quick start

```python
from frappix import Client, TokenAuth

with Client("https://erp.example.com", TokenAuth("api_key", "api_secret")) as client:
    print(client.get_logged_user())

    todo = client.insert("ToDo", {"description": "Call the supplier"})
    client.update("ToDo", todo["name"], {"status": "Closed"})

    for row in client.iter_list("ToDo", fields=["name", "status"], filters={"status": "Open"}):
        print(row["name"])
```

The async client is the same, awaited:

```python
import asyncio
from frappix import AsyncClient, TokenAuth


async def main() -> None:
    async with AsyncClient("https://erp.example.com", TokenAuth("key", "secret")) as client:
        async for row in client.iter_list("Customer", fields=["name"]):
            print(row["name"])


asyncio.run(main())
```

## Authentication

| Class | Use it for |
|---|---|
| `TokenAuth(api_key, api_secret)` | Servers, scripts and jobs. Recommended. |
| `BearerAuth(token)` | An OAuth 2 access token issued by the site. |
| `PasswordAuth(username, password)` | A cookie session. Logs in on first use, logs out on close. |

Read credentials from the environment or a secret store, never from source code.

## Methods

| Method | What it does |
|---|---|
| `ping()` | Check the site answers. |
| `get_logged_user()` | Return the authenticated user. |
| `get_list(doctype, fields=, filters=, or_filters=, order_by=, limit=, offset=)` | One page of documents. |
| `iter_list(doctype, ..., page_size=)` | Every matching document, page by page. |
| `get_doc(doctype, name)` | One document. |
| `insert(doctype, values)` | Create a document. |
| `update(doctype, name, values)` | Change fields. |
| `delete(doctype, name)` | Delete a document. |
| `submit(doctype, name)` / `cancel(doctype, name)` | Submit or cancel. |
| `rename(doctype, old_name, new_name, merge=)` | Rename; returns the new name. |
| `get_count(doctype, filters)` | Count matching documents. |
| `get_value(doctype, fieldname, filters)` / `set_value(doctype, name, values)` | Read or set fields. |
| `call(method, params, http_method=)` | Call a whitelisted method. |
| `upload_file(filename, content, is_private=, doctype=, docname=)` | Upload a file. |
| `download(file_url)` / `download_to(file_url, target)` | Fetch a file. |

## Errors

```python
from frappix import NotFoundError, PermissionDeniedError, ValidationError, FrappixError

try:
    client.get_doc("Customer", "CUST-0001")
except NotFoundError:
    ...
except PermissionDeniedError:
    ...
except FrappixError as error:  # everything frappix raises
    ...
```

| Exception | When |
|---|---|
| `AuthenticationError` | 401: bad or expired credentials |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409: duplicate or conflicting write |
| `ValidationError` | 417 and other 4xx |
| `RateLimitError` | 429; `retry_after` holds the advised wait |
| `ServerError` | 5xx |
| `TransportError`, `RequestTimeoutError` | No response was received |
| `UnexpectedResponseError` | Redirect or non-JSON reply (usually a wrong `base_url`) |
| `ResponseTooLargeError` | Body above `max_response_bytes` |
| `ConfigurationError` | An unsafe or malformed argument |

`APIError` subclasses carry `status_code`, `exc_type`, `server_messages` and
`traceback`. The server traceback is deliberately left out of `str(error)`.

## Security behaviour

- `http://` is refused unless you pass `allow_insecure_http=True` (local development only).
- TLS verification cannot be disabled. For a private CA, pass `verify="/path/ca.pem"` or an `ssl.SSLContext`.
- Redirects are never followed, so credentials cannot be forwarded to another host.
- DocType and document names are percent-encoded; `.` and `..` are rejected.
- `download` accepts only site-relative paths.
- Uploads are private by default.
- Writes are never retried after a network error or 5xx. `GET` requests and HTTP 429 replies are.
- Secrets are masked in `repr()` and never logged.

See [SECURITY.md](SECURITY.md) to report a vulnerability.

## Retries and timeouts

```python
from frappix import Client, RetryPolicy, TokenAuth

client = Client(
    "https://erp.example.com",
    TokenAuth("key", "secret"),
    timeout=10,
    retry=RetryPolicy(max_attempts=5, backoff_base=1.0),
)
```

`RetryPolicy(max_attempts=1)` turns retries off.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

Integration tests run against a live development site and are skipped unless
these are set. They remove everything they create. See the
[developer guide](docs/DEVELOPMENT.md#integration-tests) for the full list of
settings and the permissions the API user needs:

```bash
export FRAPPIX_TEST_URL=http://localhost:8000
export FRAPPIX_TEST_API_KEY=...
export FRAPPIX_TEST_API_SECRET=...
uv run pytest -m integration
```

## Documentation

- [Developer guide](docs/DEVELOPMENT.md): architecture, adding a call, tests, releasing
- [Product requirements](docs/PRD.md): goals, scope and requirements
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

MIT
