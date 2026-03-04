"""InlineTemplate usage warning checks."""

import inspect

from chirp.routing.router import Router
from chirp.templating.returns import InlineTemplate

from .types import CheckResult, ContractIssue, Severity


def check_inline_templates(router: Router, result: CheckResult) -> None:
    """Warn when route return annotation uses InlineTemplate."""
    for route in router.routes:
        hints = inspect.get_annotations(route.handler, eval_str=False)
        return_hint = hints.get("return")
        if return_hint is None:
            continue
        check_types = (return_hint,)
        origin = getattr(return_hint, "__args__", None)
        if origin is not None:
            check_types = origin
        for annotation in check_types:
            if annotation is InlineTemplate or (
                isinstance(annotation, type) and issubclass(annotation, InlineTemplate)
            ):
                result.issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="inline_template",
                        message=(
                            f"Route '{route.path}' returns InlineTemplate — "
                            "replace with a file-based Template before production."
                        ),
                        route=route.path,
                    )
                )
                break
