"""Form data parsing — URL-encoded and multipart.

Implements ``MultiValueMapping`` for consistent access across
``Headers``, ``QueryParams``, and ``FormData``.

``python-multipart`` is an optional dependency (``pip install chirp[forms]``).
URL-encoded forms use stdlib ``urllib.parse`` — no extra dependency.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class UploadFile:
    """An uploaded file from a multipart form submission.

    Immutable metadata with lazy content access. The file content
    is held in memory as bytes (suitable for typical web uploads).

    For large file handling, read the raw body via ``request.stream()``.
    """

    filename: str
    content_type: str
    size: int
    _content: bytes

    async def read(self) -> bytes:
        """Return the file content as bytes."""
        return self._content

    async def save(self, path: Path) -> None:
        """Write the file content to disk.

        Args:
            path: Destination file path. Parent directories must exist.
        """
        path.write_bytes(self._content)

    def __repr__(self) -> str:
        return f"UploadFile({self.filename!r}, {self.content_type!r}, {self.size} bytes)"


class FormData(Mapping[str, str]):
    """Immutable parsed form data.

    Implements ``Mapping[str, str]`` and the ``MultiValueMapping`` protocol.
    Holds both string field values and uploaded files.

    ``__getitem__`` returns the first value for a key (string fields only).
    ``get_list`` returns all values for a key.
    ``files`` provides access to uploaded files by field name.

    Usage::

        form = await request.form()
        username = form["username"]
        avatar = form.files.get("avatar")  # UploadFile or None
    """

    __slots__ = ("_data", "_files")

    def __init__(
        self,
        data: dict[str, list[str]],
        files: dict[str, UploadFile] | None = None,
    ) -> None:
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_files", files or {})

    @property
    def files(self) -> Mapping[str, UploadFile]:
        """Uploaded files by field name."""
        return self._files

    def __getitem__(self, key: str) -> str:
        return self._data[key][0]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        items = ", ".join(f"{k!r}: {self[k]!r}" for k in self)
        return f"FormData({{{items}}})"

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        """Return the first value for *key*, or *default* if missing."""
        values = self._data.get(key)
        if values:
            return values[0]
        return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for *key* (checkboxes, multi-selects)."""
        return list(self._data.get(key, []))


async def parse_form_data(
    body: bytes,
    content_type: str,
) -> FormData:
    """Parse form body into FormData.

    Supports:
    - ``application/x-www-form-urlencoded`` (stdlib, no extra dependency)
    - ``multipart/form-data`` (requires ``python-multipart``)

    Args:
        body: Raw request body bytes.
        content_type: The Content-Type header value.

    Returns:
        Parsed FormData instance.

    Raises:
        ConfigurationError: If multipart parsing is needed but
            ``python-multipart`` is not installed.
        ValueError: If content type is not a supported form encoding.
    """
    ct_lower = content_type.lower().split(";")[0].strip()

    if ct_lower == "application/x-www-form-urlencoded":
        return _parse_urlencoded(body)

    if ct_lower == "multipart/form-data":
        return await _parse_multipart(body, content_type)

    msg = f"Unsupported form content type: {content_type!r}"
    raise ValueError(msg)


def _parse_urlencoded(body: bytes) -> FormData:
    """Parse URL-encoded form data using stdlib."""
    from urllib.parse import parse_qs

    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return FormData(parsed)


async def _parse_multipart(body: bytes, content_type: str) -> FormData:
    """Parse multipart form data using python-multipart.

    Raises ``ConfigurationError`` if ``python-multipart`` is not installed.
    """
    from chirp.errors import ConfigurationError

    try:
        from multipart.multipart import parse_options_header
    except ImportError:
        msg = (
            "Multipart form parsing requires the 'python-multipart' package. "
            "Install it with: pip install chirp[forms]"
        )
        raise ConfigurationError(msg) from None

    # Extract boundary from content type
    _, options = parse_options_header(content_type.encode("latin-1"))
    boundary = options.get(b"boundary")
    if boundary is None:
        msg = "Multipart form data missing boundary parameter"
        raise ValueError(msg)

    # Use multipart parser
    from multipart.multipart import MultipartParser

    data: dict[str, list[str]] = {}
    files: dict[str, UploadFile] = {}

    # Track current part state
    current_headers: dict[str, str] = {}
    current_data = bytearray()
    current_field_name: str | None = None
    current_filename: str | None = None

    def on_part_begin() -> None:
        nonlocal current_headers, current_data, current_field_name, current_filename
        current_headers = {}
        current_data = bytearray()
        current_field_name = None
        current_filename = None

    def on_part_data(data_chunk: bytes, start: int, end: int) -> None:
        current_data.extend(data_chunk[start:end])

    def on_part_end() -> None:
        nonlocal current_field_name, current_filename
        if current_field_name is None:
            return

        if current_filename is not None:
            # File upload
            ct = current_headers.get("content-type", "application/octet-stream")
            content = bytes(current_data)
            files[current_field_name] = UploadFile(
                filename=current_filename,
                content_type=ct,
                size=len(content),
                _content=content,
            )
        else:
            # Regular field
            value = current_data.decode("utf-8", errors="replace")
            data.setdefault(current_field_name, []).append(value)

    def on_header_field(hdata: bytes, start: int, end: int) -> None:
        # Header field name — store temporarily
        current_headers["_pending_field"] = hdata[start:end].decode("latin-1").lower()

    def on_header_value(hdata: bytes, start: int, end: int) -> None:
        nonlocal current_field_name, current_filename
        field = current_headers.pop("_pending_field", "")
        value = hdata[start:end].decode("latin-1")
        current_headers[field] = value

        # Extract field name and filename from Content-Disposition
        if field == "content-disposition":
            _, params = parse_options_header(value.encode("latin-1"))
            name = params.get(b"name")
            if name is not None:
                current_field_name = name.decode("utf-8")
            fname = params.get(b"filename")
            if fname is not None:
                current_filename = fname.decode("utf-8")

    callbacks: dict[str, Any] = {
        "on_part_begin": on_part_begin,
        "on_part_data": on_part_data,
        "on_part_end": on_part_end,
        "on_header_field": on_header_field,
        "on_header_value": on_header_value,
    }

    parser = MultipartParser(boundary, callbacks)
    parser.write(body)
    parser.finalize()

    return FormData(data, files)
