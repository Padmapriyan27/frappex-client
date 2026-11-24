"""Credentials and the three ways a client proves who it is.

Secrets are wrapped in :class:`Secret` the moment they enter the library, so
no ``repr``, log line or traceback frame can print them by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exceptions import ConfigurationError

__all__ = ["Auth", "BearerAuth", "PasswordAuth", "Secret", "TokenAuth"]


class Secret:
    """A string that never shows its value unless asked to.

    ``repr`` and ``str`` return a mask. Call :meth:`reveal` at the single
    point where the value has to go on the wire.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str | Secret) -> None:
        """Wrap ``value``; wrapping a :class:`Secret` again is harmless."""
        raw = value.reveal() if isinstance(value, Secret) else value
        if not isinstance(raw, str) or not raw:
            raise ConfigurationError("A credential must be a non-empty string.")
        if any(ch in raw for ch in "\r\n\x00"):
            raise ConfigurationError("A credential must not contain control characters.")
        self._value = raw

    def reveal(self) -> str:
        """Return the wrapped value."""
        return self._value

    def __repr__(self) -> str:
        """Return a mask, never the value."""
        return "Secret('********')"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        """Compare by value with another :class:`Secret` only."""
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        """Hash by value, consistent with ``__eq__``."""
        return hash(self._value)


@dataclass(frozen=True, init=False)
class TokenAuth:
    """Authenticate with a user's API key and API secret.

    This is the recommended method for server-to-server use: generate the
    pair under *User > Settings > API Access* on the Frappe site.
    """

    api_key: str
    api_secret: Secret = field(repr=False)

    def __init__(self, api_key: str, api_secret: str | Secret) -> None:
        """Validate and wrap the key pair."""
        if not api_key or any(ch in api_key for ch in "\r\n\x00: "):
            raise ConfigurationError("api_key is empty or contains illegal characters.")
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "api_secret", Secret(api_secret))

    def headers(self) -> dict[str, str]:
        """Return the ``Authorization`` header for this key pair."""
        return {"Authorization": f"token {self.api_key}:{self.api_secret.reveal()}"}


@dataclass(frozen=True, init=False)
class BearerAuth:
    """Authenticate with an OAuth 2 access token issued by the Frappe site."""

    token: Secret = field(repr=False)

    def __init__(self, token: str | Secret) -> None:
        """Validate and wrap the access token."""
        object.__setattr__(self, "token", Secret(token))

    def headers(self) -> dict[str, str]:
        """Return the ``Authorization`` header for this token."""
        return {"Authorization": f"Bearer {self.token.reveal()}"}


@dataclass(frozen=True, init=False)
class PasswordAuth:
    """Authenticate with a username and password (cookie session).

    The client logs in on its first request and logs out when closed. Prefer
    :class:`TokenAuth` for unattended programs: it needs no login round trip
    and the key can be revoked without changing the user's password.
    """

    username: str
    password: Secret = field(repr=False)

    def __init__(self, username: str, password: str | Secret) -> None:
        """Validate and wrap the login details."""
        if not username:
            raise ConfigurationError("username must not be empty.")
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "password", Secret(password))

    def headers(self) -> dict[str, str]:
        """Return no headers: the session cookie carries the identity."""
        return {}


Auth = TokenAuth | BearerAuth | PasswordAuth
"""Any of the supported authentication strategies."""
