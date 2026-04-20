"""Bare jsDelivr Alpine CDN URL detection.

A bare ``https://cdn.jsdelivr.net/npm/alpinejs@<version>`` (without an
explicit ``/dist/cdn.min.js`` subpath) resolves to ``dist/module.cjs.js`` —
a CommonJS module that throws ``ReferenceError: module is not defined`` in
the browser. The error is silent: CORS masks it as ``"Script error."`` so
nothing in the console points to the cause and every Alpine-powered
component just stops working.

Chirp's own ``alpine_snippet`` always emits the explicit subpath; this
rule guards against app developers pasting bare URLs into their own
templates. Promotes the regression test in ``tests/test_alpine.py`` to a
startup-time contract check.
"""

import re

from .types import ContractIssue, Severity

# Match jsDelivr Alpine script src that lacks the /dist/... suffix.
# Examples that match (BAD):
#   https://cdn.jsdelivr.net/npm/alpinejs@3.15.8
#   https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.15.8
#   https://cdn.jsdelivr.net/npm/alpinejs@3.15.8?foo=bar
# Examples that don't match (GOOD):
#   https://cdn.jsdelivr.net/npm/alpinejs@3.15.8/dist/cdn.min.js
#   https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.15.8/dist/cdn.min.js
_BARE_ALPINE_CDN = re.compile(
    r"https?://cdn\.jsdelivr\.net/npm/(?:@alpinejs/[A-Za-z0-9_-]+|alpinejs)@[A-Za-z0-9._+-]+(?![A-Za-z0-9._+/-])",
)


def check_alpine_cdn_urls(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Flag bare jsDelivr Alpine CDN URLs in template sources.

    A bare ``alpinejs@<version>`` URL (no ``/dist/cdn.min.js``) loads the
    CommonJS build, which throws ``ReferenceError: module is not defined``
    in the browser and is silenced by CORS. Every Alpine-powered component
    will quietly stop working.
    """
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        seen: set[str] = set()
        for match in _BARE_ALPINE_CDN.finditer(source):
            url = match.group(0)
            if url in seen:
                continue
            seen.add(url)
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="alpine_cdn_url",
                    message=(
                        f"Bare jsDelivr Alpine CDN URL '{url}' resolves to "
                        "the CommonJS build (dist/module.cjs.js) which throws "
                        "'ReferenceError: module is not defined' in the browser. "
                        "CORS masks the error as 'Script error.', so all "
                        "Alpine-powered components silently break. "
                        "Append '/dist/cdn.min.js' to the URL."
                    ),
                    template=template_name,
                )
            )
    return issues
