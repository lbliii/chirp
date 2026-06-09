"""Static-streaming contract check — bound static-file RAM use (#178).

``StaticFiles`` serves file bodies via :class:`~chirp.http.response.FileResponse`,
which streams from disk once a file reaches the configured ``stream_threshold``.
A threshold set to ``0`` or a negative value, or one set absurdly high, defeats
that protection: every static GET would read the whole file into memory, the
same unbounded-RAM DoS class as unbounded uploads.

Category:
- ``static_streaming``: a ``StaticFiles`` middleware is wired with a threshold
  that effectively disables chunked streaming.

This check is advisory and **env-independent** — it always emits ``WARNING``
(never ERROR), since a large threshold may be a deliberate choice for a
known-small asset directory.

Middleware presence is detected by class **name** (``type(mw).__name__``), not
``isinstance``, matching ``rules_security_stack`` — this avoids importing
``StaticFiles`` into the contracts layer and keeps the dependency direction
clean. The trade-off is that a user subclass is only recognised when it keeps
the same class name.
"""

from typing import Any

from chirp.contracts.types import ContractIssue, Severity

_STATIC_MIDDLEWARE = "StaticFiles"

# At/above this threshold value, chunked streaming effectively never engages for
# realistic files — treat it as "unbounded" and warn.
_EFFECTIVELY_UNBOUNDED = 1024 * 1024 * 1024  # 1 GiB


def check_static_streaming(middleware_list: list[Any]) -> list[ContractIssue]:
    """Flag ``StaticFiles`` middleware with a misconfigured stream threshold.

    WARNING when the threshold is ``<= 0`` (chunked path unreachable; full file
    always buffered) or ``>= 1 GiB`` (effectively unbounded). No issue when the
    middleware is absent or configured with a sane threshold.
    """
    issues: list[ContractIssue] = []

    for mw in middleware_list:
        if type(mw).__name__ != _STATIC_MIDDLEWARE:
            continue
        threshold = getattr(mw, "_stream_threshold", None)
        if not isinstance(threshold, int):
            continue
        if threshold <= 0:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="static_streaming",
                    message=(
                        f"StaticFiles is wired with static_stream_threshold={threshold} "
                        "(<= 0). Files are always read fully into memory, risking "
                        "unbounded worker RSS on large static GETs. Set a positive "
                        "threshold (default 1 MiB) so large files stream from disk."
                    ),
                )
            )
        elif threshold >= _EFFECTIVELY_UNBOUNDED:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="static_streaming",
                    message=(
                        f"StaticFiles is wired with static_stream_threshold={threshold} "
                        "bytes (>= 1 GiB), which effectively disables chunked "
                        "streaming. Large static GETs will buffer the whole file in "
                        "memory. Lower the threshold unless the asset directory is "
                        "known-small."
                    ),
                )
            )

    return issues
