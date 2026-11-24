"""The blocking client."""

from __future__ import annotations

import io
import os
import ssl
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from types import TracebackType
from typing import Any, BinaryIO, Literal, TypeVar

import httpx

from . import _operations as ops
from ._auth import Auth, PasswordAuth
from ._base import (
    CHUNK_SIZE,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT,
    ClientCore,
    ResponseSize,
    logger,
)
from ._config import RetryPolicy
from ._protocol import RawResponse, Request, decode, file_path, parse_retry_after
from .exceptions import FrappexError, TransportError, UnexpectedResponseError
from .types import Document, Filters

T = TypeVar("T")


class Client(ClientCore):
    """Blocking client for one Frappe site.

    Use it as a context manager so connections (and a password session) are
    closed when you are done::

        with Client("https://erp.example.com", TokenAuth(key, secret)) as client:
            for todo in client.iter_list("ToDo", filters={"status": "Open"}):
                print(todo["name"])

    Args:
        base_url: Root address of the site. Must be ``https://`` unless
            ``allow_insecure_http`` is set.
        auth: A :class:`~frappex_client.TokenAuth`, :class:`~frappex_client.BearerAuth` or
            :class:`~frappex_client.PasswordAuth`. Omit it for guest access: no
            credentials are sent, so only what the site opens to guests
            works, such as :meth:`ping`, public files and methods
            whitelisted with ``allow_guest``.
        timeout: Seconds allowed per request, or an ``httpx.Timeout``.
        retry: Retry rules; defaults to :class:`~frappex_client.RetryPolicy`.
        verify: Path of a CA bundle or an ``ssl.SSLContext`` for sites with a
            private certificate. Certificate checks cannot be disabled.
        allow_insecure_http: Permit ``http://`` for a local development site.
        max_response_bytes: Largest response body accepted, after
            decompression.
        headers: Extra headers for every request, such as ``Host`` for a
            multi-site bench. ``Authorization`` and ``Cookie`` are refused.
        transport: An ``httpx`` transport to use instead of the default, for
            tests or custom networking. It then owns TLS, so ``verify`` no
            longer applies.

    Raises:
        ConfigurationError: A setting is malformed or unsafe.
    """

    def __init__(
        self,
        base_url: str,
        auth: Auth | None = None,
        *,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        retry: RetryPolicy | None = None,
        verify: ssl.SSLContext | str | os.PathLike[str] | None = None,
        allow_insecure_http: bool = False,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Validate the settings and prepare the connection pool."""
        super().__init__(
            base_url,
            auth,
            timeout=timeout,
            retry=retry,
            verify=verify,
            allow_insecure_http=allow_insecure_http,
            max_response_bytes=max_response_bytes,
            headers=headers,
        )
        self._http = httpx.Client(transport=transport, **self._http_arguments)
        self._login_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """End a password session, if any, and release connections."""
        try:
            if self._logged_in:
                self._logged_in = False
                try:
                    self._run(ops.logout())
                except FrappexError:
                    logger.debug("logout failed; the session will expire on its own")
        finally:
            self._http.close()

    def __enter__(self) -> Client:
        """Return the client itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client."""
        self.close()

    # -- transport ---------------------------------------------------------

    def _send(self, request: Request) -> RawResponse:
        try:
            with self._http.stream(
                request.method, request.path, **self._request_arguments(request)
            ) as response:
                self._check_declared_length(response.headers, self._max_response_bytes)
                size = ResponseSize(self._max_response_bytes)
                chunks: list[bytes] = []
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    size.add(len(chunk))
                    chunks.append(chunk)
                return RawResponse(response.status_code, response.headers, b"".join(chunks))
        except httpx.HTTPError as exc:
            raise self._transport_error(request, exc) from exc

    def _run(self, operation: ops.Operation[T]) -> T:
        request = operation.request
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._send(request)
            except TransportError:
                delay = self._retry.delay_after_failure(request.method, attempt)
                if delay is None:
                    raise
            else:
                logger.debug("%s %s -> %s", request.method, request.path, response.status_code)
                delay = self._retry.delay_after_response(
                    request.method,
                    attempt,
                    response.status_code,
                    parse_retry_after(response.headers),
                )
                if delay is None:
                    return operation.parse(decode(response))
            time.sleep(delay)

    def _ensure_session(self) -> None:
        """Log in once when the client uses password authentication."""
        if self._needs_login:
            with self._login_lock:
                if self._needs_login and isinstance(self._auth, PasswordAuth):
                    self._run(ops.login(self._auth.username, self._auth.password.reveal()))
                    self._logged_in = True

    def _execute(self, operation: ops.Operation[T]) -> T:
        self._ensure_session()
        return self._run(operation)

    # -- site --------------------------------------------------------------

    def ping(self) -> str:
        """Check that the site answers. Returns ``"pong"``."""
        return self._run(ops.ping())

    def get_logged_user(self) -> str:
        """Return the user the credentials belong to.

        A cheap way to confirm that the credentials work.
        """
        return self._execute(ops.get_logged_user())

    # -- documents ---------------------------------------------------------

    def get_list(
        self,
        doctype: str,
        *,
        fields: Sequence[str] | None = None,
        filters: Filters | None = None,
        or_filters: Filters | None = None,
        order_by: str | None = None,
        limit: int = 20,
        offset: int = 0,
        parent: str | None = None,
    ) -> list[Document]:
        """Return one page of documents.

        Args:
            doctype: DocType to list.
            fields: Fields to return; the site returns only ``name`` if omitted.
            filters: Conditions every row must meet.
            or_filters: Conditions of which a row must meet at least one.
            order_by: Sort clause, such as ``"modified desc"``.
            limit: Maximum rows to return.
            offset: Rows to skip.
            parent: Parent DocType, required when listing a child table.

        See :meth:`iter_list` to read every matching row.
        """
        return self._execute(
            ops.get_list(
                doctype,
                fields=fields,
                filters=filters,
                or_filters=or_filters,
                order_by=order_by,
                limit=limit,
                offset=offset,
                parent=parent,
            )
        )

    def iter_list(
        self,
        doctype: str,
        *,
        fields: Sequence[str] | None = None,
        filters: Filters | None = None,
        or_filters: Filters | None = None,
        order_by: str | None = None,
        page_size: int = ops.DEFAULT_PAGE_SIZE,
        parent: str | None = None,
    ) -> Iterator[Document]:
        """Yield every matching document, fetching ``page_size`` rows at a time.

        Rows are ordered by creation time unless ``order_by`` is given, so
        that documents edited during the iteration are not skipped or
        repeated. Rows created or deleted meanwhile can still shift pages.
        """
        offset = 0
        while True:
            page = self.get_list(
                doctype,
                fields=fields,
                filters=filters,
                or_filters=or_filters,
                order_by=order_by or ops.STABLE_ORDER,
                limit=page_size,
                offset=offset,
                parent=parent,
            )
            yield from page
            if len(page) < page_size:
                return
            offset += page_size

    def get_doc(self, doctype: str, name: str) -> Document:
        """Return one document.

        Raises:
            NotFoundError: No such document.
        """
        return self._execute(ops.get_doc(doctype, name))

    def insert(self, doctype: str, values: Mapping[str, Any]) -> Document:
        """Create a document and return it as saved.

        This request is never retried automatically, because a repeat could
        create a duplicate.
        """
        return self._execute(ops.insert(doctype, values))

    def update(self, doctype: str, name: str, values: Mapping[str, Any]) -> Document:
        """Change the given fields of a document and return it as saved."""
        return self._execute(ops.update(doctype, name, values))

    def delete(self, doctype: str, name: str) -> None:
        """Delete a document."""
        self._execute(ops.delete(doctype, name))

    def submit(self, doctype: str, name: str) -> None:
        """Submit a draft document."""
        self._execute(ops.submit(doctype, name))

    def cancel(self, doctype: str, name: str) -> None:
        """Cancel a submitted document."""
        self._execute(ops.cancel(doctype, name))

    def rename(self, doctype: str, old_name: str, new_name: str, *, merge: bool = False) -> str:
        """Rename a document and return its new name.

        Args:
            doctype: DocType of the document.
            old_name: Current name.
            new_name: Name to give it.
            merge: Merge into an existing document called ``new_name``.
        """
        return self._execute(ops.rename(doctype, old_name, new_name, merge=merge))

    def get_count(self, doctype: str, filters: Filters | None = None) -> int:
        """Return how many documents match ``filters``."""
        return self._execute(ops.get_count(doctype, filters))

    def get_value(
        self,
        doctype: str,
        fieldname: str | Sequence[str],
        filters: Filters | str | None = None,
    ) -> Document | None:
        """Return the requested fields of the first matching document.

        Args:
            doctype: DocType to read.
            fieldname: One field name or a list of them.
            filters: Conditions, or a document name.

        Returns:
            A mapping of field name to value, or ``None`` if nothing matches.
        """
        return self._execute(ops.get_value(doctype, fieldname, filters))

    def set_value(self, doctype: str, name: str, values: Mapping[str, Any]) -> Document:
        """Set fields on a document and return it as saved."""
        return self._execute(ops.set_value(doctype, name, values))

    # -- methods -----------------------------------------------------------

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        http_method: Literal["GET", "POST"] = "POST",
    ) -> Any:
        """Call a whitelisted server method and return its result.

        Args:
            method: Dotted path, such as ``"myapp.api.get_summary"``.
            params: Arguments for the method.
            http_method: ``"POST"`` (default) sends the arguments as JSON and
                is never retried. Use ``"GET"`` for a read-only method that is
                safe to repeat.
        """
        return self._execute(ops.call(method, params, http_method))

    # -- files -------------------------------------------------------------

    def upload_file(
        self,
        filename: str,
        content: bytes,
        *,
        is_private: bool = True,
        doctype: str | None = None,
        docname: str | None = None,
        fieldname: str | None = None,
        folder: str | None = None,
    ) -> Document:
        """Upload a file and return its ``File`` document.

        Files are private unless ``is_private=False`` is passed: a public
        file can be fetched by anyone who has its URL.

        Args:
            filename: Name to store the file under.
            content: File contents.
            is_private: Keep the file behind the site's permissions.
            doctype: DocType of the document to attach the file to.
            docname: Name of the document to attach the file to.
            fieldname: Attach field on that document to fill in.
            folder: Folder in the file manager; the site defaults to ``Home``.
        """
        return self._execute(
            ops.upload_file(
                filename,
                content,
                is_private=is_private,
                doctype=doctype,
                docname=docname,
                fieldname=fieldname,
                folder=folder,
            )
        )

    def download_to(self, file_url: str, target: BinaryIO, *, max_bytes: int | None = None) -> int:
        """Stream a file from the site into ``target``.

        Args:
            file_url: Site-relative location, such as ``/private/files/a.pdf``
                (the ``file_url`` field of a ``File`` document).
            target: Writable binary file object.
            max_bytes: Stop with :class:`~frappex_client.ResponseTooLargeError` after
                this many bytes; unlimited when omitted.

        Returns:
            Number of bytes written.

        A download is not retried, since part of it may already be written.
        """
        request = Request("GET", file_path(file_url))
        self._ensure_session()
        try:
            with self._http.stream("GET", request.path) as response:
                if response.status_code != 200:
                    size = ResponseSize(self._max_response_bytes)
                    body = bytearray()
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        size.add(len(chunk))
                        body += chunk
                    decode(RawResponse(response.status_code, response.headers, bytes(body)))
                    raise UnexpectedResponseError(
                        f"HTTP {response.status_code}: expected 200 for a download.",
                        status_code=response.status_code,
                    )
                self._check_declared_length(response.headers, max_bytes)
                size = ResponseSize(max_bytes)
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    size.add(len(chunk))
                    target.write(chunk)
                return size.total
        except httpx.HTTPError as exc:
            raise self._transport_error(request, exc) from exc

    def download(self, file_url: str) -> bytes:
        """Return a file's contents, up to ``max_response_bytes``.

        Use :meth:`download_to` for large files.
        """
        buffer = io.BytesIO()
        self.download_to(file_url, buffer, max_bytes=self._max_response_bytes)
        return buffer.getvalue()
