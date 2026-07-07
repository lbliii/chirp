"""Private HTTP QUERY media-type parsing and negotiation helpers."""

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_SF_TOKEN_RE = re.compile(r"^[A-Za-z*][!#$%&'*+\-.^_`|~0-9A-Za-z:/]*$")
_SF_KEY_RE = re.compile(r"^[a-z*][a-z0-9_.*-]*$")
_QVALUE_RE = re.compile(r"^(?:0(?:\.\d{0,3})?|1(?:\.0{0,3})?)$")


@dataclass(frozen=True, slots=True, order=True)
class _MediaRange:
    type: str
    subtype: str
    parameters: tuple[tuple[str, str], ...] = ()

    @property
    def value(self) -> str:
        base = f"{self.type}/{self.subtype}"
        return base + "".join(
            f";{name}={_serialize_http_parameter(value)}" for name, value in self.parameters
        )


def _split_quoted(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if quoted and char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            current.append(char)
            continue
        if char == delimiter and not quoted:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if quoted or escaped:
        raise ValueError("unterminated quoted string")
    parts.append("".join(current))
    return parts


def _parse_parameter_value(value: str) -> str:
    if not value:
        raise ValueError("media-type parameter value cannot be empty")
    if not value.startswith('"'):
        if not _TOKEN_RE.fullmatch(value):
            raise ValueError(f"invalid media-type parameter value {value!r}")
        return value
    if len(value) < 2 or not value.endswith('"'):
        raise ValueError("unterminated quoted media-type parameter")
    output: list[str] = []
    escaped = False
    for char in value[1:-1]:
        codepoint = ord(char)
        if escaped:
            if char not in {"\t", " "} and not 0x21 <= codepoint <= 0x7E:
                raise ValueError("invalid quoted-pair in media-type parameter")
            output.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"' or codepoint < 0x20 or codepoint == 0x7F:
            raise ValueError("invalid quoted media-type parameter")
        else:
            output.append(char)
    if escaped:
        raise ValueError("unterminated quoted-pair in media-type parameter")
    return "".join(output)


def _parse_media_range(value: str, *, allow_wildcards: bool) -> _MediaRange:
    if not isinstance(value, str):
        raise TypeError(f"media type must be a string, got {type(value).__name__}")
    if not value.strip():
        raise ValueError("media type cannot be empty")
    parts = _split_quoted(value, ";")
    base = parts[0].strip()
    if base.count("/") != 1:
        raise ValueError(f"invalid media type {value!r}; expected type/subtype")
    media_type, subtype = (part.strip().lower() for part in base.split("/", 1))
    if not _TOKEN_RE.fullmatch(media_type) or not _TOKEN_RE.fullmatch(subtype):
        raise ValueError(f"invalid media type {value!r}; expected type/subtype tokens")
    if "*" in media_type or "*" in subtype:
        valid_wildcard = (media_type, subtype) == ("*", "*") or (
            media_type != "*" and subtype == "*"
        )
        if not allow_wildcards or not valid_wildcard:
            raise ValueError(f"invalid wildcard media range {value!r}; use '*/*' or 'type/*'")

    parameters: dict[str, str] = {}
    for raw_parameter in parts[1:]:
        parameter = raw_parameter.strip()
        if not parameter or "=" not in parameter:
            raise ValueError(f"invalid media-type parameter in {value!r}")
        name, raw_value = parameter.split("=", 1)
        name = name.strip().lower()
        raw_value = raw_value.strip()
        if not _TOKEN_RE.fullmatch(name):
            raise ValueError(f"invalid media-type parameter name {name!r}")
        if name in parameters:
            raise ValueError(f"duplicate media-type parameter {name!r}")
        parsed_value = _parse_parameter_value(raw_value)
        parameters[name] = parsed_value.lower() if name == "charset" else parsed_value

    return _MediaRange(media_type, subtype, tuple(sorted(parameters.items())))


def _serialize_http_parameter(value: str) -> str:
    if value and _TOKEN_RE.fullmatch(value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _serialize_sf_bare_item(value: str) -> str:
    if _SF_TOKEN_RE.fullmatch(value):
        return value
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        raise ValueError(f"Structured Field value must be ASCII: {value!r}")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def normalize_query_media_types(values: tuple[str, ...]) -> tuple[str, ...]:
    """Validate and deterministically normalize a route declaration."""
    if not isinstance(values, tuple):
        raise TypeError("query_media_types must be a tuple of media-range strings")
    parsed: list[_MediaRange] = []
    seen: set[_MediaRange] = set()
    for value in values:
        media_range = _parse_media_range(value, allow_wildcards=True)
        for name, _ in media_range.parameters:
            if not _SF_KEY_RE.fullmatch(name):
                raise ValueError(
                    f"media-type parameter {name!r} cannot be serialized in Accept-Query"
                )
        if media_range in seen:
            raise ValueError(f"duplicate query media type after normalization: {value!r}")
        seen.add(media_range)
        parsed.append(media_range)
    return tuple(item.value for item in sorted(parsed))


def serialize_accept_query(values: tuple[str, ...]) -> str:
    """Serialize normalized media ranges as an RFC 9651 Structured Field List."""
    members: list[str] = []
    for value in values:
        media_range = _parse_media_range(value, allow_wildcards=True)
        member = _serialize_sf_bare_item(f"{media_range.type}/{media_range.subtype}")
        for name, parameter_value in media_range.parameters:
            if not _SF_KEY_RE.fullmatch(name):
                raise ValueError(
                    f"media-type parameter {name!r} cannot be serialized in Accept-Query"
                )
            member += f";{name}={_serialize_sf_bare_item(parameter_value)}"
        members.append(member)
    return ", ".join(members)


def query_content_type_supported(content_type: str, supported: tuple[str, ...]) -> bool:
    """Return whether a request Content-Type matches a declared media range."""
    received = _parse_media_range(content_type, allow_wildcards=False)
    received_parameters = dict(received.parameters)
    for value in supported:
        declared = _parse_media_range(value, allow_wildcards=True)
        if declared.type != "*" and declared.type != received.type:
            continue
        if declared.subtype != "*" and declared.subtype != received.subtype:
            continue
        if all(received_parameters.get(name) == expected for name, expected in declared.parameters):
            return True
    return False


def _parse_accept_member(value: str) -> tuple[_MediaRange, float] | None:
    try:
        parts = _split_quoted(value, ";")
    except ValueError:
        return None
    base = parts[0].strip()
    media_parameters: list[str] = []
    quality = 1.0
    saw_quality = False
    for raw_parameter in parts[1:]:
        parameter = raw_parameter.strip()
        if "=" not in parameter:
            return None
        name, raw_value = parameter.split("=", 1)
        if name.strip().lower() == "q":
            if saw_quality or not _QVALUE_RE.fullmatch(raw_value.strip()):
                return None
            quality = float(raw_value.strip())
            saw_quality = True
        elif not saw_quality:
            media_parameters.append(parameter)
        # Parameters after q are Accept extensions and do not constrain matching.
    candidate = base
    if media_parameters:
        candidate += ";" + ";".join(media_parameters)
    try:
        return _parse_media_range(candidate, allow_wildcards=True), quality
    except TypeError, ValueError:
        return None


def response_content_type_acceptable(content_type: str, accept: str | None) -> bool:
    """Apply HTTP Accept precedence to a selected response Content-Type."""
    if accept is None or not accept.strip():
        return True
    try:
        selected = _parse_media_range(content_type, allow_wildcards=False)
        members = _split_quoted(accept, ",")
    except TypeError, ValueError:
        return False
    selected_parameters = dict(selected.parameters)
    matches: list[tuple[int, int, float]] = []
    for raw_member in members:
        parsed = _parse_accept_member(raw_member)
        if parsed is None:
            continue
        media_range, quality = parsed
        if media_range.type != "*" and media_range.type != selected.type:
            continue
        if media_range.subtype != "*" and media_range.subtype != selected.subtype:
            continue
        if not all(
            selected_parameters.get(name) == expected for name, expected in media_range.parameters
        ):
            continue
        specificity = 0 if media_range.type == "*" else 1
        if media_range.subtype != "*":
            specificity += 1
        matches.append((specificity, len(media_range.parameters), quality))
    if not matches:
        return False
    best_shape = max((specificity, parameter_count) for specificity, parameter_count, _ in matches)
    return any(
        quality > 0
        for specificity, parameter_count, quality in matches
        if (specificity, parameter_count) == best_shape
    )
