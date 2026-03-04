"""Form-related extraction and validation helpers."""

import dataclasses
import re

from .types import ContractIssue, Severity
from .utils import closest_field

_FORM_FIELD_PATTERN = re.compile(
    r"<(?:input|select|textarea)\b[^>]*?\bname\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_FORM_EXCLUDED_FIELDS = frozenset({"_csrf_token", "csrf_token", "_method"})


def extract_form_field_names(source: str) -> set[str]:
    """Extract form field names from input/select/textarea tags."""
    names: set[str] = set()
    for match in _FORM_FIELD_PATTERN.finditer(source):
        name = match.group(1).strip()
        if not name or "{{" in name or "{%" in name:
            continue
        if name in _FORM_EXCLUDED_FIELDS:
            continue
        names.add(name)
    return names


def validate_form_contracts(
    result,
    router,
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Validate dataclass-backed form contracts against template fields."""
    issues: list[ContractIssue] = []
    for route in router.routes:
        rc = getattr(route.handler, "_chirp_contract", None)
        if rc is None or rc.form is None:
            continue
        form_contract = rc.form
        result.forms_validated += 1

        template_source = template_sources.get(form_contract.template)
        if template_source is None:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="form",
                    message=(
                        f"Route '{route.path}' FormContract references "
                        f"template '{form_contract.template}' which is not found."
                    ),
                    route=route.path,
                    template=form_contract.template,
                )
            )
            continue

        if form_contract.block is not None:
            block_match = re.search(
                rf"\{{% block {re.escape(form_contract.block)} %\}}(.*?)\{{% endblock",
                template_source,
                re.DOTALL,
            )
            if block_match:
                template_source = block_match.group(1)

        html_fields = extract_form_field_names(template_source)
        try:
            dataclass_fields = {f.name for f in dataclasses.fields(form_contract.datacls)}
        except TypeError:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="form",
                    message=(
                        f"Route '{route.path}' FormContract datacls "
                        f"'{form_contract.datacls}' is not a dataclass."
                    ),
                    route=route.path,
                )
            )
            continue

        for field_name in sorted(dataclass_fields - html_fields):
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="form",
                    message=(
                        f"Route '{route.path}' (POST) expects field "
                        f"'{field_name}' ({form_contract.datacls.__name__}.{field_name}) "
                        f"but template '{form_contract.template}'"
                        + (f" block '{form_contract.block}'" if form_contract.block else "")
                        + f' has no <input name="{field_name}">.'
                    ),
                    route=route.path,
                    template=form_contract.template,
                )
            )

        for field_name in sorted(html_fields - dataclass_fields):
            suggestion = closest_field(field_name, dataclass_fields)
            hint = f" Did you mean '{suggestion}'?" if suggestion else ""
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="form",
                    message=(
                        f"Template '{form_contract.template}'"
                        + (f" block '{form_contract.block}'" if form_contract.block else "")
                        + f' has <input name="{field_name}"> which does '
                        f"not match any field in {form_contract.datacls.__name__}.{hint}"
                    ),
                    template=form_contract.template,
                    route=route.path,
                )
            )
    return issues
