# Security policy

## Reporting a vulnerability

Please report security problems privately through the repository's
"Report a vulnerability" form (GitHub Security Advisories), not in a public
issue. Include the affected version, what an attacker can do, and steps to
reproduce. You will get an acknowledgement, and a fix is released before the
details are published.

## Supported versions

Only the latest release receives security fixes.

## What frappix guarantees

- Credentials are sent only to the host given in `base_url`: requests use
  site-relative paths and redirects are never followed.
- `http://` is refused unless `allow_insecure_http=True` is passed.
- TLS certificate verification cannot be turned off through the client's
  arguments. A caller who supplies their own `transport` takes over TLS.
- Secrets are not written to logs, `repr()` output or exception messages.
- DocType names, document names and file paths are encoded or rejected so
  they cannot address a different endpoint.

## Out of scope

frappix does not sanitise the data a site returns. Server messages and
document fields can contain HTML written by other users; escape them before
rendering.
