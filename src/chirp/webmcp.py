"""Experimental declarative WebMCP form projection.

This module implements only the attribute vocabulary from the WebMCP
declarative proposal pinned by RFC 014.  It does not register imperative
browser tools or change form submission behavior.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import MISSING, dataclass
from types import MappingProxyType
from typing import Any, ClassVar, cast, get_args, get_type_hints

from kida.template import Markup

from chirp.errors import ConfigurationError
from chirp.templating.filters import html_attrs

_WEBMCP_PROPOSAL_COMMIT = "0b676d27a08aafd3b4f8a709756eeeab342fd9bd"

_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_TEXT_CONTROLS = frozenset({"email", "search", "tel", "text", "url"})
_SUPPORTED_CONTROLS = _TEXT_CONTROLS | {"number"}
_TEXT_CONSTRAINTS = frozenset({"min_length", "max_length", "pattern"})
_NUMBER_CONSTRAINTS = frozenset({"min", "max", "step"})
_METADATA_KEYS = frozenset(
    {
        "webmcp_control",
        "webmcp_description",
        "webmcp_min",
        "webmcp_max",
        "webmcp_step",
        "webmcp_min_length",
        "webmcp_max_length",
        "webmcp_pattern",
    }
)


@dataclass(frozen=True, slots=True)
class WebMCPForm:
    """Explicit experimental projection of a real form as a browser tool.

    ``tool_name`` is the stable operation identity.  ``autosubmit`` is allowed
    only for safe-method routes; mutation forms always require human review.
    """

    proposal_commit: ClassVar[str] = _WEBMCP_PROPOSAL_COMMIT

    tool_name: str
    description: str
    autosubmit: bool = False

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.tool_name):
            msg = (
                "WebMCP tool_name must start with a letter and contain only "
                f"letters, digits, dots, dashes, or underscores; got {self.tool_name!r}."
            )
            raise ConfigurationError(msg)
        if not self.description.strip():
            raise ConfigurationError(
                f"WebMCP tool {self.tool_name!r} requires a non-empty description."
            )


@dataclass(frozen=True, slots=True)
class _CompiledControl:
    name: str
    description: str
    control: str
    required: bool
    default: str | int | float | None
    constraints: tuple[tuple[str, str | int | float], ...]


@dataclass(frozen=True, slots=True)
class _CompiledForm:
    declaration: WebMCPForm
    route: str
    methods: tuple[str, ...]
    controls: Mapping[str, _CompiledControl]


class WebMCPRegistry:
    """Immutable setup-time compilation of opted-in form projections."""

    __slots__ = ("_forms",)

    def __init__(self, forms: Mapping[str, _CompiledForm]) -> None:
        self._forms = MappingProxyType(dict(forms))

    def form_attrs(self, tool_name: str) -> Markup:
        """Render escaped declarative attributes for one real ``<form>``."""
        form = self._get_form(tool_name)
        return cast(
            Markup,
            html_attrs(
                {
                    "toolname": form.declaration.tool_name,
                    "tooldescription": form.declaration.description,
                    "toolautosubmit": form.declaration.autosubmit,
                }
            ),
        )

    def control_attrs(self, tool_name: str, field_name: str) -> Markup:
        """Render native and WebMCP attributes for one dataclass field."""
        form = self._get_form(tool_name)
        try:
            control = form.controls[field_name]
        except KeyError as exc:
            available = ", ".join(sorted(form.controls)) or "(none)"
            msg = (
                f"WebMCP tool {tool_name!r} has no field {field_name!r}. "
                f"Available fields: {available}."
            )
            raise ConfigurationError(msg) from exc

        attrs: dict[str, Any] = {
            "type": control.control,
            "name": control.name,
            "required": control.required,
            "toolparamdescription": control.description,
        }
        if control.default is not None:
            attrs["value"] = control.default
        attrs.update(_html_constraint_name(item) for item in control.constraints)
        return cast(Markup, html_attrs(attrs))

    def _get_form(self, tool_name: str) -> _CompiledForm:
        try:
            return self._forms[tool_name]
        except KeyError as exc:
            available = ", ".join(sorted(self._forms)) or "(none)"
            msg = (
                f"Unknown WebMCP tool {tool_name!r}. "
                f"Declare it on FormContract(webmcp=...) before app freeze. "
                f"Available tools: {available}."
            )
            raise ConfigurationError(msg) from exc


def compile_webmcp_registry(routes: Iterable[Any]) -> WebMCPRegistry | None:
    """Compile route form declarations into immutable template helpers."""
    forms: dict[str, _CompiledForm] = {}
    for route in routes:
        route_contract = getattr(route.handler, "_chirp_contract", None)
        form_contract = getattr(route_contract, "form", None)
        declaration = getattr(form_contract, "webmcp", None)
        if declaration is None:
            continue
        if form_contract is None:
            raise ConfigurationError(
                f"Route {route.path!r} declares WebMCP metadata without a FormContract."
            )
        if not isinstance(declaration, WebMCPForm):
            msg = (
                f"Route {route.path!r} FormContract.webmcp must be a WebMCPForm, "
                f"got {type(declaration).__name__}."
            )
            raise ConfigurationError(msg)
        if declaration.tool_name in forms:
            first = forms[declaration.tool_name]
            msg = (
                f"Duplicate WebMCP tool {declaration.tool_name!r} on routes "
                f"{first.route!r} and {route.path!r}; tool names must be unique."
            )
            raise ConfigurationError(msg)

        methods = tuple(sorted(str(method).upper() for method in route.methods))
        if declaration.autosubmit and any(method not in _SAFE_METHODS for method in methods):
            msg = (
                f"WebMCP tool {declaration.tool_name!r} on mutation route "
                f"{route.path!r} cannot enable autosubmit. Omit autosubmit so the "
                "browser requires human review before submission."
            )
            raise ConfigurationError(msg)

        controls = _compile_controls(
            form_contract.datacls,
            tool_name=declaration.tool_name,
            route=route.path,
        )
        forms[declaration.tool_name] = _CompiledForm(
            declaration=declaration,
            route=route.path,
            methods=methods,
            controls=MappingProxyType(controls),
        )

    return WebMCPRegistry(forms) if forms else None


def _compile_controls(datacls: type, *, tool_name: str, route: str) -> dict[str, _CompiledControl]:
    try:
        fields = dataclasses.fields(datacls)
    except TypeError as exc:
        msg = (
            f"WebMCP tool {tool_name!r} on route {route!r} requires a dataclass "
            "FormContract so parameters can be compiled."
        )
        raise ConfigurationError(msg) from exc

    hints = get_type_hints(datacls)
    controls: dict[str, _CompiledControl] = {}
    for field in fields:
        metadata = field.metadata
        description = str(metadata.get("webmcp_description", "")).strip()
        if not description:
            msg = (
                f"WebMCP tool {tool_name!r} field {datacls.__name__}.{field.name} "
                "requires dataclasses.field(metadata={'webmcp_description': '...'})."
            )
            raise ConfigurationError(msg)

        control = str(metadata.get("webmcp_control", "text")).strip().lower()
        if control not in _SUPPORTED_CONTROLS:
            supported = ", ".join(sorted(_SUPPORTED_CONTROLS))
            msg = (
                f"WebMCP tool {tool_name!r} field {datacls.__name__}.{field.name} "
                f"uses unsupported control {control!r}. Supported controls: {supported}; "
                "file, select, textarea, checkbox, and radio need a separately designed contract."
            )
            raise ConfigurationError(msg)

        hint = _unwrap_optional(hints.get(field.name, str))
        _validate_control_type(tool_name, datacls.__name__, field.name, control, hint)
        constraints = _compile_constraints(
            tool_name, datacls.__name__, field.name, control, metadata
        )
        required = field.default is MISSING and field.default_factory is MISSING
        default = _compile_default(tool_name, datacls.__name__, field)
        _validate_default_type(tool_name, datacls.__name__, field.name, control, default)
        controls[field.name] = _CompiledControl(
            name=field.name,
            description=description,
            control=control,
            required=required,
            default=default,
            constraints=constraints,
        )
    return controls


def _unwrap_optional(hint: Any) -> Any:
    args = get_args(hint)
    if args and type(None) in args:
        remaining = tuple(value for value in args if value is not type(None))
        if len(remaining) == 1:
            return remaining[0]
    return hint


def _validate_control_type(
    tool_name: str,
    dataclass_name: str,
    field_name: str,
    control: str,
    hint: Any,
) -> None:
    expected = (int, float) if control == "number" else (str,)
    if hint not in expected:
        expected_names = "int or float" if control == "number" else "str"
        actual = getattr(hint, "__name__", str(hint))
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} uses "
            f"control {control!r}, which requires {expected_names}; got {actual}."
        )
        raise ConfigurationError(msg)


def _compile_constraints(
    tool_name: str,
    dataclass_name: str,
    field_name: str,
    control: str,
    metadata: Mapping[str, Any],
) -> tuple[tuple[str, str | int | float], ...]:
    unknown = sorted(
        str(key) for key in metadata if str(key).startswith("webmcp_") and key not in _METADATA_KEYS
    )
    if unknown:
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} has "
            f"unsupported metadata: {', '.join(unknown)}."
        )
        raise ConfigurationError(msg)

    allowed = _NUMBER_CONSTRAINTS if control == "number" else _TEXT_CONSTRAINTS
    incompatible = sorted(
        key
        for key in _METADATA_KEYS
        if key.startswith("webmcp_")
        and key.removeprefix("webmcp_") in (_TEXT_CONSTRAINTS | _NUMBER_CONSTRAINTS)
        and key.removeprefix("webmcp_") not in allowed
        and key in metadata
    )
    if incompatible:
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} uses "
            f"constraint(s) {', '.join(incompatible)} that do not apply to "
            f"control {control!r}."
        )
        raise ConfigurationError(msg)
    constraints: list[tuple[str, str | int | float]] = []
    for name in sorted(allowed):
        key = f"webmcp_{name}"
        if key not in metadata:
            continue
        value = metadata[key]
        if not isinstance(value, str | int | float):
            msg = (
                f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} "
                f"constraint {key!r} must be a string or number."
            )
            raise ConfigurationError(msg)
        _validate_constraint_value(tool_name, dataclass_name, field_name, key, value)
        constraints.append((name, value))
    return tuple(constraints)


def _compile_default(
    tool_name: str,
    dataclass_name: str,
    field: dataclasses.Field[Any],
) -> str | int | float | None:
    if field.default_factory is not MISSING:
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field.name} uses a "
            "default_factory, which the declarative preview cannot expose safely. "
            "Use a scalar default or leave the field required."
        )
        raise ConfigurationError(msg)
    if field.default is MISSING or field.default is None:
        return None
    if not isinstance(field.default, str | int | float):
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field.name} default "
            "must be a string or number in the declarative preview."
        )
        raise ConfigurationError(msg)
    return field.default


def _validate_default_type(
    tool_name: str,
    dataclass_name: str,
    field_name: str,
    control: str,
    default: str | int | float | None,
) -> None:
    if default is None:
        return
    valid = type(default) in {int, float} if control == "number" else isinstance(default, str)
    if not valid:
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} default "
            f"{default!r} is incompatible with control {control!r}."
        )
        raise ConfigurationError(msg)


def _validate_constraint_value(
    tool_name: str,
    dataclass_name: str,
    field_name: str,
    key: str,
    value: str | int | float,
) -> None:
    valid = True
    if key in {"webmcp_min_length", "webmcp_max_length"}:
        valid = type(value) is int and value >= 0
    elif key == "webmcp_pattern":
        valid = isinstance(value, str) and bool(value)
    elif key in {"webmcp_min", "webmcp_max"}:
        valid = isinstance(value, int | float) and not isinstance(value, bool)
    elif key == "webmcp_step":
        valid = isinstance(value, int | float) and not isinstance(value, bool) and value > 0
    if not valid:
        msg = (
            f"WebMCP tool {tool_name!r} field {dataclass_name}.{field_name} has "
            f"invalid {key}={value!r}."
        )
        raise ConfigurationError(msg)


def _html_constraint_name(
    item: tuple[str, str | int | float],
) -> tuple[str, str | int | float]:
    name, value = item
    return name.replace("_", ""), value


__all__ = ["WebMCPForm"]
