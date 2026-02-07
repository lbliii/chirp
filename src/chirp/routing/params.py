"""Path parameter parsing and type conversion.

Built-in converters for route path segments like ``{id:int}``.
"""


# (regex_pattern, python_type) for each supported converter
CONVERTERS: dict[str, tuple[str, type]] = {
    "str": (r"[^/]+", str),
    "int": (r"\d+", int),
    "float": (r"\d+(?:\.\d+)?", float),
    "path": (r".+", str),
}


def convert_param(value: str, param_type: str) -> str | int | float:
    """Convert a captured path parameter string to the target type.

    Raises ``ValueError`` if the string cannot be converted.
    Raises ``KeyError`` if *param_type* is not a registered converter.
    """
    _, target_type = CONVERTERS[param_type]
    return target_type(value)
