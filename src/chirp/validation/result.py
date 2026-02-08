"""Validation result — immutable container for validated data or errors."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The outcome of validating form data against a set of rules.

    ``is_valid`` is True when there are no errors.
    The result is falsy when invalid, so you can write::

        result = validate(form, rules)
        if not result:
            return Template("form.html", form=form, errors=result.errors)

    ``data`` contains the cleaned string values for all validated fields
    (only populated when there are no errors).

    ``errors`` maps field names to lists of error messages::

        {"title": ["This field is required"],
         "email": ["Must be a valid email address"]}
    """

    data: dict[str, str]
    errors: dict[str, list[str]]

    @property
    def is_valid(self) -> bool:
        """True if validation passed with no errors."""
        return not self.errors

    def __bool__(self) -> bool:
        """Falsy when invalid — enables ``if not result:`` pattern."""
        return self.is_valid
