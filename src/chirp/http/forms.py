"""Form data parsing and binding — URL-encoded and multipart.

Implements ``MultiValueMapping`` for consistent access across
``Headers``, ``QueryParams``, and ``FormData``.

``form_from()`` provides lightweight dataclass binding: define a
frozen dataclass, pass it to ``form_from(request, MyForm)``, and get
a populated instance. No magic validation — just binding with type
coercion for ``str``, ``int``, ``float``, ``bool``, ``datetime.date``,
``datetime.datetime`` (ISO 8601), ``decimal.Decimal``, ``uuid.UUID``,
``enum.Enum`` subclasses, and ``list[T]`` for repeated fields such as
checkbox groups and multi-selects.

``python-multipart`` is an optional dependency (``pip install chirp[forms]``).
URL-encoded forms use stdlib ``urllib.parse`` — no extra dependency.
"""

import contextlib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from dataclasses import fields as dc_fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import (
    IO,
    Annotated,
    Any,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)
from uuid import UUID

from chirp.templating.returns import ValidationError
from chirp.validation import Validator, validate

# Default spool threshold: bytes an UploadFile keeps in memory before spilling
# to a real temp file on disk. Mirrors AppConfig.upload_spool_threshold so the
# parser has a sane bound even when called directly (tests, library use).
DEFAULT_SPOOL_THRESHOLD = 1024 * 1024  # 1 MB

# Chunk size used when streaming an UploadFile to disk in save().
_SAVE_CHUNK_SIZE = 64 * 1024  # 64 KB


def _sanitize_upload_filename(filename: str) -> str:
    """Reduce an attacker-influenced filename to a safe basename.

    Strips directory components (POSIX ``/`` and Windows ``\\``), removes NUL
    bytes, and rejects traversal so a multipart ``filename="../../etc/passwd"``
    cannot escape a chosen directory. Returns ``"upload"`` when nothing usable
    remains (e.g. ``".."`` or all separators).
    """
    # Drop NUL and normalize Windows separators to POSIX before taking basename.
    cleaned = filename.replace("\x00", "").replace("\\", "/")
    base = cleaned.rsplit("/", 1)[-1].strip()
    if base in ("", ".", ".."):
        return "upload"
    return base


@dataclass(frozen=True, slots=True)
class UploadFile:
    """An uploaded file from a multipart form submission.

    Metadata (``filename``, ``content_type``, ``size``) is **immutable** — this
    is a frozen dataclass, so rebinding any of those attributes raises
    ``dataclasses.FrozenInstanceError``. The content is backed by a stdlib
    :class:`~tempfile.SpooledTemporaryFile` held in the private ``_spool``
    field: small files stay in memory, larger ones spill to a temp file on disk
    past ``spool_threshold`` bytes — so a multi-GB upload never lands wholly in
    RAM. (A frozen dataclass forbids *rebinding* fields, not mutating the object
    a field points to, so the spool's IO position/buffer remains usable while
    the metadata stays locked.)

    ``read()`` returns the full bytes; ``save()`` streams to disk in chunks and
    sanitizes the destination basename against path traversal.
    """

    filename: str
    content_type: str
    size: int
    _spool: IO[bytes]

    @classmethod
    def from_bytes(
        cls,
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> UploadFile:
        """Build an in-memory UploadFile from bytes (compat / tests).

        The content stays in memory regardless of size — this is the
        convenience constructor for small fixtures and direct callers.
        """
        spool: IO[bytes] = SpooledTemporaryFile(max_size=len(content) + 1)  # noqa: SIM115 — spool outlives this scope
        spool.write(content)
        spool.seek(0)
        return cls(
            filename=filename,
            content_type=content_type,
            size=len(content),
            _spool=spool,
        )

    async def read(self) -> bytes:
        """Return the full file content as bytes."""
        self._spool.seek(0)
        return self._spool.read()

    async def save(self, path: Path) -> None:
        """Write the file content to ``path``, streaming in fixed-size chunks.

        The destination is the *sink* for attacker-influenced bytes, so it is
        hardened against path traversal: any ``..`` component anywhere in
        ``path`` is rejected, and the final *basename* is sanitized (directory
        separators, NUL, and bare ``.``/``..`` stripped). The caller's chosen
        directory is otherwise authoritative. This makes the common sink
        ``await upload.save(upload_dir / upload.filename)`` safe even when
        ``upload.filename`` is ``"../../etc/passwd"``. Works identically for
        in-memory and spilled-to-disk uploads (no whole-file buffering).

        Args:
            path: Destination file path. Parent directories must exist.

        Raises:
            ValueError: If ``path`` contains a ``..`` traversal component.
        """
        path = Path(path)
        if ".." in path.parts:
            msg = (
                f"Refusing to save upload to a path with a '..' traversal component: {path!r}. "
                "Sanitize the upload filename or choose an explicit destination directory."
            )
            raise ValueError(msg)
        safe_name = _sanitize_upload_filename(path.name)
        dest = path.with_name(safe_name)
        self._spool.seek(0)
        with open(dest, "wb") as out:
            while True:
                chunk = self._spool.read(_SAVE_CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)

    @property
    def spilled_to_disk(self) -> bool:
        """True if the backing spool has rolled over to a real temp file.

        Useful in tests to assert large uploads are not held in RAM.
        """
        rolled = getattr(self._spool, "_rolled", None)
        if rolled is not None:
            return bool(rolled)
        # Defensive / version-robustness fallback only: on CPython 3.14
        # SpooledTemporaryFile always exposes ``_rolled``, so this branch is
        # unreachable today. It guards against a future CPython that drops or
        # renames the private attribute — a SpooledTemporaryFile exposes a real
        # fileno() only once it has rolled to disk.
        try:
            self._spool.fileno()
        except OSError, ValueError:
            return False
        return True

    def close(self) -> None:
        """Close the backing spool, releasing any temp file on disk.

        Idempotent and exception-safe — called by the request teardown to
        avoid leaking file descriptors / temp files after the response.
        """
        with contextlib.suppress(Exception):
            self._spool.close()

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
    _data: dict[str, list[str]]
    _files: dict[str, UploadFile]

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

    @overload
    def get(self, key: str, default: None = None) -> str | None: ...

    @overload
    def get[T](self, key: str, default: T) -> str | T: ...

    def get(self, key: str, default: object = None) -> object:
        """Return the first value for *key*, or *default* if missing."""
        values = self._data.get(key)
        if values:
            return values[0]
        return default

    def get_list(self, key: str) -> list[str]:
        """Return all values for *key* (checkboxes, multi-selects)."""
        return list(self._data.get(key, []))

    def close(self) -> None:
        """Close all uploaded-file spools (request teardown hook)."""
        for upload in self._files.values():
            upload.close()


class FormBindingError(Exception):
    """Raised when form data cannot be bound to a dataclass.

    Attributes:
        errors: Dict mapping field names to lists of error messages.
    """

    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        fields = ", ".join(sorted(errors))
        super().__init__(f"Form binding failed for: {fields}")


def _coerce_decimal(value: str) -> Decimal:
    """Coerce a string to ``Decimal``, normalizing failure to ``ValueError``.

    ``Decimal("nope")`` raises ``InvalidOperation`` (an ``ArithmeticError``),
    not ``ValueError`` — so without this the existing
    ``except ValueError, TypeError`` path in ``form_from`` would miss it and
    the error would escape as an uncaught exception instead of a
    ``FormBindingError``.
    """
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid Decimal: {value!r}") from exc


# Type coercion map for form_from(). Each entry maps a target field type to a
# callable that turns a raw form string into that type. Callables must signal
# bad input by raising ``ValueError`` or ``TypeError`` (the pair caught in
# ``form_from``); coercions whose stdlib constructor raises something else are
# wrapped to normalize the failure.
_COERCIONS: dict[type, Callable[[str], Any]] = {
    str: lambda v: v.strip(),
    int: int,
    float: float,
    bool: lambda v: v.lower() in ("true", "1", "yes", "on"),
    date: date.fromisoformat,
    datetime: datetime.fromisoformat,
    Decimal: _coerce_decimal,
    UUID: UUID,
}


def _coerce_enum(enum_cls: type[Enum], value: str) -> Enum:
    """Coerce a raw form string to an ``Enum`` member.

    Tries by *value* first (``EnumCls(value)`` — the common case for forms whose
    ``<option value=...>`` carries the member value), then falls back to by
    *name* (``EnumCls[value]``) which is handy for string enums declared as
    ``RED = "red"`` but submitted by member name. Unknown inputs raise
    ``ValueError`` so ``form_from`` reports a ``FormBindingError`` naming the
    field — consistent with the int/float path. ``EnumCls(value)`` may raise
    ``KeyError`` for some enum shapes, so that is caught too.
    """
    try:
        return enum_cls(value)
    except ValueError, KeyError:
        pass
    try:
        return enum_cls[value]
    except KeyError as exc:
        raise ValueError(f"invalid {enum_cls.__name__}: {value!r}") from exc


def _resolve_coercion(target_type: Any) -> Callable[[str], Any]:
    """Return the coercion callable for a field's resolved target type.

    Looks up the fixed ``_COERCIONS`` table first, then special-cases ``Enum``
    subclasses (each subclass is a distinct type, so it cannot be a static table
    key). Falls back to calling the type directly (mirrors the prior behavior
    for unknown types such as plain custom classes).
    """
    coerce = _COERCIONS.get(target_type)
    if coerce is not None:
        return coerce
    if isinstance(target_type, type) and issubclass(target_type, Enum):
        enum_cls = target_type
        return lambda v: _coerce_enum(enum_cls, v)
    return target_type


async def form_from[T](request: Any, datacls: type[T]) -> T:
    """Bind form data from a request to a dataclass instance.

    Reads ``request.form()`` and populates the given dataclass.
    Fields with defaults are optional; fields without defaults are required.
    String fields are stripped of whitespace by default.

    Supports ``str``, ``int``, ``float``, ``bool``, ``datetime.date`` and
    ``datetime.datetime`` (ISO 8601), ``decimal.Decimal``, ``uuid.UUID``,
    ``enum.Enum`` subclasses (coerced by member value, then by name), and
    ``list[T]`` type coercion. Missing list fields bind to ``[]`` because
    browsers omit unchecked checkbox groups entirely. Raises ``FormBindingError``
    with a dict of errors for missing or invalid fields.

    Usage::

        @dataclass(frozen=True, slots=True)
        class TaskForm:
            title: str
            description: str = ""
            priority: str = "medium"

        @app.route("/tasks", methods=["POST"])
        async def add_task(request: Request):
            form = await form_from(request, TaskForm)
            # form.title, form.description, form.priority are populated

    Args:
        request: A Chirp Request object (anything with an async ``.form()`` method).
        datacls: A dataclass class to bind form data into.

    Returns:
        An instance of ``datacls`` populated from the form.

    Raises:
        FormBindingError: If required fields are missing or type coercion fails.
    """
    from dataclasses import MISSING

    form = await request.form()
    hints = get_type_hints(datacls)
    field_defs = dc_fields(datacls)

    errors: dict[str, list[str]] = {}
    values: dict[str, Any] = {}

    for f in field_defs:
        hint = hints.get(f.name, str)
        base_type = _unwrap_optional(hint)
        list_item_type = _list_item_type(base_type)
        raw = form.get(f.name)

        if raw is None:
            # Field missing from form data entirely
            if list_item_type is not None:
                values[f.name] = []
            elif f.default is not MISSING:
                values[f.name] = f.default
            elif f.default_factory is not MISSING:
                values[f.name] = f.default_factory()
            else:
                errors.setdefault(f.name, []).append(f"{f.name} is required.")
            continue

        # Coerce to target type
        if list_item_type is not None:
            item_coerce = _resolve_coercion(list_item_type)
            try:
                values[f.name] = [item_coerce(item) for item in form.get_list(f.name)]
            except ValueError, TypeError:
                errors.setdefault(f.name, []).append(
                    f"Invalid value for {f.name}: expected list[{_type_name(list_item_type)}]."
                )
            continue

        coerce = _resolve_coercion(base_type)

        try:
            values[f.name] = coerce(raw)
        except ValueError, TypeError:
            errors.setdefault(f.name, []).append(
                f"Invalid value for {f.name}: expected {_type_name(base_type)}."
            )

    if errors:
        raise FormBindingError(errors)

    return datacls(**values)


def _extract_field_rules(datacls: type) -> dict[str, list[Validator]]:
    """Collect ``chirp.validation`` rules attached via ``Annotated`` metadata.

    A field declared as ``Annotated[str, required, max_length(100)]`` carries
    its validation rules in the type-hint metadata. This walks the dataclass
    fields, resolves hints with ``include_extras=True`` (so ``Annotated`` is
    preserved rather than stripped — note ``form_from`` resolves them *without*
    extras, which is why those rules are otherwise never run), and gathers the
    **callable** metadata items as validators. Non-callable metadata (doc
    strings, sentinels, etc.) is ignored, so ``Annotated`` can be shared with
    other tooling.

    ``Optional`` nesting is unwrapped to find the ``Annotated`` layer in either
    order — both ``Annotated[str | None, required]`` (metadata on the outer
    wrapper) and ``Optional[Annotated[str, required]]`` /
    ``Annotated[str, required] | None`` (metadata on a union member) yield the
    same rules. Only fields with at least one rule appear in the returned map;
    a plain dataclass with no ``Annotated`` rules yields ``{}``, so binding
    behavior is unchanged.
    """
    hints = get_type_hints(datacls, include_extras=True)
    rules: dict[str, list[Validator]] = {}

    for f in dc_fields(datacls):
        hint = hints.get(f.name)
        if hint is None:
            continue

        metadata = _annotated_metadata(hint)
        if metadata is None:
            # Optional[Annotated[...]] / Annotated[...] | None — unwrap the
            # union (PEP 604 ``types.UnionType`` or ``typing.Union``) to find
            # an Annotated member carrying the metadata.
            for arg in get_args(hint):
                if arg is type(None):
                    continue
                metadata = _annotated_metadata(arg)
                if metadata is not None:
                    break

        if not metadata:
            continue

        field_rules = [cast(Validator, m) for m in metadata if callable(m)]
        if field_rules:
            rules[f.name] = field_rules

    return rules


def _annotated_metadata(hint: Any) -> tuple[Any, ...] | None:
    """Return the ``Annotated`` metadata tuple for *hint*, else ``None``.

    The metadata lives directly on the ``Annotated`` wrapper regardless of the
    base type's own optionality (``Annotated[str | None, required]`` still
    exposes ``__metadata__`` here).
    """
    if get_origin(hint) is Annotated or hasattr(hint, "__metadata__"):
        return tuple(getattr(hint, "__metadata__", ()))
    return None


async def form_or_errors[T](
    request: Any,
    datacls: type[T],
    template_name: str,
    block_name: str,
    /,
    *,
    retarget: str | None = None,
    **extra_context: Any,
) -> T | ValidationError:
    """Bind form data or return a ValidationError for re-rendering.

    Combines ``form_from()`` and ``ValidationError`` into a single call.
    On success, returns the populated dataclass. On binding failure,
    returns a ``ValidationError`` with the errors and the raw form values
    for re-population.

    Usage::

        result = await form_or_errors(request, TaskForm, "tasks.html", "form")
        if isinstance(result, ValidationError):
            return result
        # result is TaskForm — proceed with validated data

    Args:
        request: A Chirp Request object (anything with an async ``.form()`` method).
        datacls: A dataclass class to bind form data into.
        template_name: Template name for the error response.
        block_name: Block name for the error response.
        retarget: Optional ``HX-Retarget`` header value.
        **extra_context: Additional template context passed to ``ValidationError``.

    Returns:
        An instance of ``datacls`` on success, or a ``ValidationError`` on failure.

    Notes:
        Fields declared with ``Annotated`` rules from ``chirp.validation`` (e.g.
        ``Annotated[str, required, max_length(100)]``) are validated in the same
        pass as binding. Rule errors and binding errors are merged per field
        (message lists concatenated), so one declarative schema yields either the
        typed instance or a ``ValidationError`` carrying every field's messages.
    """
    rules = _extract_field_rules(datacls)
    raw = await request.form()
    rule_errors = validate(raw, rules).errors if rules else {}

    bound: tuple[T] | None
    try:
        # Wrap in a 1-tuple so a successful bind of ``None`` (a valid bound
        # value) stays distinguishable from "binding failed".
        bound = (await form_from(request, datacls),)
        binding_errors: dict[str, list[str]] = {}
    except FormBindingError as e:
        bound = None
        binding_errors = e.errors

    merged: dict[str, list[str]] = {}
    for field_errors in (rule_errors, binding_errors):
        for name, messages in field_errors.items():
            merged.setdefault(name, []).extend(messages)

    if merged or bound is None:
        return ValidationError(
            template_name,
            block_name,
            retarget=retarget,
            errors=merged,
            form=dict(raw),
            **extra_context,
        )

    return bound[0]


def form_values(form: Any) -> dict[str, str]:
    """Extract form field values as strings for template re-population.

    Accepts a dataclass instance or a ``Mapping``. Returns a flat
    ``dict[str, str]`` suitable for passing as ``form=...`` context
    to ``ValidationError``.

    Args:
        form: A dataclass instance or a ``Mapping``.

    Returns:
        A dict of field names to string values.
    """
    if hasattr(form, "__dataclass_fields__"):
        return {
            f.name: str(v) if v is not None else ""
            for f in dc_fields(form)
            for v in (getattr(form, f.name),)
        }
    if isinstance(form, Mapping):
        return {k: str(v) for k, v in form.items()}
    return {}


def _unwrap_optional(hint: Any) -> Any:
    """Extract the base type from ``X | None`` or plain ``X``."""
    import types

    if isinstance(hint, types.UnionType):
        # e.g. str | None → pick the non-None type
        args = [a for a in hint.__args__ if a is not type(None)]
        if args:
            return args[0]
    return hint if isinstance(hint, type) or get_origin(hint) is not None else str


def _list_item_type(hint: Any) -> type | None:
    """Return the item type for ``list[T]`` hints."""
    origin = get_origin(hint)
    if origin is not list:
        return None
    args = get_args(hint)
    if not args:
        return str
    item_type = _unwrap_optional(args[0])
    return item_type if isinstance(item_type, type) else str


def _type_name(value: Any) -> str:
    """Best-effort type name for binding errors."""
    return getattr(value, "__name__", str(value))


async def parse_form_data(
    body: bytes,
    content_type: str,
    *,
    max_parts: int | None = None,
    max_total_size: int | None = None,
    spool_threshold: int | None = None,
) -> FormData:
    """Parse form body into FormData.

    Supports:
    - ``application/x-www-form-urlencoded`` (stdlib, no extra dependency)
    - ``multipart/form-data`` (requires ``python-multipart``)

    Args:
        body: Raw request body bytes.
        content_type: The Content-Type header value.
        max_parts: Optional cap on the number of multipart parts. Exceeding it
            raises ``PayloadTooLarge`` (413) — the multipart-bomb guard.
            ``None`` (default) means unbounded for back-compat.
        max_total_size: Optional cap on the total accumulated size of multipart
            parts (the multipart-specific upload ceiling, distinct from the
            general request-body cap). Exceeding it raises ``PayloadTooLarge``
            (413). ``None`` (default) means unbounded for back-compat.
        spool_threshold: Bytes a file part keeps in memory before spilling to a
            temp file on disk. Defaults to ``DEFAULT_SPOOL_THRESHOLD``.

    Returns:
        Parsed FormData instance.

    Raises:
        ConfigurationError: If multipart parsing is needed but
            ``python-multipart`` is not installed.
        PayloadTooLarge: If ``max_parts`` or ``max_total_size`` is exceeded.
        ValueError: If content type is not a supported form encoding.
    """
    ct_lower = content_type.lower().split(";")[0].strip()

    if ct_lower == "application/x-www-form-urlencoded":
        return _parse_urlencoded(body)

    if ct_lower == "multipart/form-data":
        return await _parse_multipart(
            body,
            content_type,
            max_parts=max_parts,
            max_total_size=max_total_size,
            spool_threshold=spool_threshold
            if spool_threshold is not None
            else DEFAULT_SPOOL_THRESHOLD,
        )

    msg = (
        f"Unsupported form content type: {content_type!r}. "
        "Chirp form parsing supports 'application/x-www-form-urlencoded' and "
        "'multipart/form-data'. Use request.body for JSON or another custom payload."
    )
    raise ValueError(msg)


def _parse_urlencoded(body: bytes) -> FormData:
    """Parse URL-encoded form data using stdlib."""
    from urllib.parse import parse_qs

    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return FormData(parsed)


async def _parse_multipart(
    body: bytes,
    content_type: str,
    *,
    max_parts: int | None = None,
    max_total_size: int | None = None,
    spool_threshold: int = DEFAULT_SPOOL_THRESHOLD,
) -> FormData:
    """Parse multipart form data using python-multipart.

    File parts are streamed into a :class:`~tempfile.SpooledTemporaryFile`
    (spilling to disk past ``spool_threshold``) rather than buffered whole in a
    ``bytearray``. ``max_parts`` caps the number of parts to defend against a
    multipart bomb; ``max_total_size`` caps the cumulative byte size of all
    parts (the multipart-specific upload ceiling).

    Raises ``ConfigurationError`` if ``python-multipart`` is not installed and
    ``PayloadTooLarge`` if ``max_parts`` or ``max_total_size`` is exceeded.
    """
    from chirp.errors import ConfigurationError, PayloadTooLarge

    try:
        from python_multipart.multipart import parse_options_header
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
        msg = (
            "Multipart form data missing boundary parameter. "
            "Set Content-Type to 'multipart/form-data; boundary=...'; browsers do "
            "this automatically for normal file-upload forms."
        )
        raise ValueError(msg)

    # Use multipart parser
    from python_multipart.multipart import MultipartParser

    data: dict[str, list[str]] = {}
    files: dict[str, UploadFile] = {}

    # Track current part state. File parts stream into a spool; non-file
    # fields are small, so they accumulate in a bytearray.
    current_headers: dict[str, str] = {}
    current_data = bytearray()
    current_spool: IO[bytes] | None = None
    current_size = 0
    current_field_name: str | None = None
    current_filename: str | None = None
    part_count = 0
    total_size = 0

    def on_part_begin() -> None:
        nonlocal current_headers, current_data, current_spool, current_size
        nonlocal current_field_name, current_filename, part_count
        part_count += 1
        if max_parts is not None and part_count > max_parts:
            raise PayloadTooLarge(f"Multipart form exceeds the maximum of {max_parts} parts.")
        current_headers = {}
        current_data = bytearray()
        current_spool = None
        current_size = 0
        current_field_name = None
        current_filename = None

    def on_part_data(data_chunk: bytes, start: int, end: int) -> None:
        nonlocal current_spool, current_size, total_size
        piece = data_chunk[start:end]
        current_size += len(piece)
        total_size += len(piece)
        if max_total_size is not None and total_size > max_total_size:
            raise PayloadTooLarge(
                f"Multipart upload exceeds the maximum total size of {max_total_size} bytes."
            )
        if current_filename is not None:
            # File part: stream into the spool (rolls to disk past threshold).
            if current_spool is None:
                current_spool = SpooledTemporaryFile(max_size=spool_threshold)  # noqa: SIM115 — spool outlives callback
            current_spool.write(piece)
        else:
            current_data.extend(piece)

    def on_part_end() -> None:
        nonlocal current_field_name, current_filename, current_spool
        if current_field_name is None:
            return

        if current_filename is not None:
            # File upload — back the UploadFile with the streamed spool.
            ct = current_headers.get("content-type", "application/octet-stream")
            spool = current_spool
            if spool is None:
                spool = SpooledTemporaryFile(max_size=spool_threshold)  # noqa: SIM115 — spool outlives callback
            spool.seek(0)
            files[current_field_name] = UploadFile(
                filename=current_filename,
                content_type=ct,
                size=current_size,
                _spool=spool,
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

    # MultipartCallbacks is TypedDict under TYPE_CHECKING only — not importable at runtime.
    parser = MultipartParser(boundary, cast(Any, callbacks))
    parser.write(body)
    parser.finalize()

    return FormData(data, files)
