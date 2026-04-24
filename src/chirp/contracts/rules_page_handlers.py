"""Page-handler contract check.

A ``page.py`` without a recognised HTTP method handler (``get``/``post``/
``put``/``delete``/``patch``/``head``/``options``, or ``handler`` as a
fallback) registers no routes. Hitting it at runtime yields a 404 or a 500
depending on the surrounding layout, with no startup signal that the file
was misconfigured.

This check promotes :class:`PageHandlerFinding` diagnostics produced during
page discovery into ``page_handlers`` contract issues:

- ``kind="missing"`` → ``Severity.ERROR`` — the file defines no handler at
  all; ship-blocker.
- ``kind="typo"`` → ``Severity.WARNING`` — a handler-shaped function
  (``handle``, ``GET``, ``index`` …) was defined but not recognised.

Severity can be tuned with
``app.override_contract_severity("page_handlers", Severity.ERROR)``.
"""

from chirp.pages.types import PageHandlerFinding

from .types import ContractIssue, Severity

_HTTP_METHOD_NAMES = "get, post, put, delete, patch, head, options"


def check_page_handlers(
    findings: list[PageHandlerFinding],
) -> list[ContractIssue]:
    """Turn page-discovery handler findings into contract issues."""
    issues: list[ContractIssue] = []
    for finding in findings:
        if finding.kind == "missing":
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="page_handlers",
                    message=(
                        f"Page {finding.file!r} has no recognised HTTP method "
                        f"handler. Chirp expects one of: {_HTTP_METHOD_NAMES}, "
                        f"or 'handler' as a fallback. Without one, requests to "
                        f"{finding.url_path!r} will not be served."
                    ),
                    route=finding.url_path,
                )
            )
        elif finding.kind == "typo":
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="page_handlers",
                    message=(
                        f"Page {finding.file!r} defines function "
                        f"{finding.function_name!r} which looks like a handler "
                        f"but is not recognised. Chirp expects lowercase HTTP "
                        f"method names ({_HTTP_METHOD_NAMES}) or 'handler' as "
                        f"a fallback."
                    ),
                    route=finding.url_path,
                )
            )
    return issues
