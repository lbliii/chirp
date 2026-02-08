"""Form validation — composable rules, clean results.

Usage::

    from chirp.validation import validate, required, max_length, email

    async def create_post(request: Request):
        form = await request.form()
        result = validate(form, {
            "title": [required, max_length(200)],
            "body": [required],
            "email": [required, email],
        })
        if not result:
            return Template("form.html", form=form, errors=result.errors)
        # result.data has cleaned values
"""

from collections.abc import Mapping

from chirp.validation.result import ValidationResult
from chirp.validation.rules import (
    Validator,
    email,
    integer,
    matches,
    max_length,
    min_length,
    number,
    one_of,
    required,
    url,
)

__all__ = [
    "ValidationResult",
    "Validator",
    "email",
    "integer",
    "matches",
    "max_length",
    "min_length",
    "number",
    "one_of",
    "required",
    "url",
    "validate",
]


def validate(
    data: Mapping[str, str] | dict[str, str],
    rules: dict[str, list[Validator]],
) -> ValidationResult:
    """Validate data against a set of rules.

    Args:
        data: Any mapping of field names to string values —
            ``FormData``, ``QueryParams``, or a plain ``dict``.
        rules: A dict mapping field names to lists of validator
            functions. Each validator returns an error message string
            on failure, or ``None`` on success.

    Returns:
        A ``ValidationResult`` with ``.data`` (cleaned values) and
        ``.errors`` (field → list of error messages).

    Example::

        result = validate(form, {
            "title": [required, max_length(200)],
            "body": [required, min_length(10)],
        })
        if not result:
            # result.errors == {"body": ["Must be at least 10 characters"]}
            ...
    """
    errors: dict[str, list[str]] = {}
    cleaned: dict[str, str] = {}

    for field_name, validators in rules.items():
        value = data.get(field_name) or ""

        field_errors: list[str] = []
        for validator in validators:
            error = validator(value)
            if error is not None:
                field_errors.append(error)
                # Stop on first error for this field if it's a presence check
                # (no point running max_length on an empty string)
                if validator is required:
                    break

        if field_errors:
            errors[field_name] = field_errors
        else:
            cleaned[field_name] = value

    return ValidationResult(data=cleaned, errors=errors)
