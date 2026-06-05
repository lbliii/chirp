"""i18n missing-translation-key contract.

When i18n is enabled and JSON catalogs are present, a ``t("key")`` reference to
a key missing from a catalog silently returns the key string at runtime. This
check surfaces that statically (category ``i18n_missing_key``, WARNING) — a
fail-loud guarantee Django's runtime-fallback model does not give.

Scope is the key-coverage contract only. Chirp does NOT build gettext .po/.mo
or an ICU pluralization engine into core; ICU formatting is deferred to babel
alongside (see the i18n decision record).
"""

import re
from typing import Any

from chirp.contracts.types import ContractIssue, Severity

# Match a standalone t("key") / t('key') call with a string-literal first
# argument. The negative lookbehind excludes identifier chars AND '.', so
# member-access calls in inline JS/Alpine (e.g. el.t("foo"), obj.t("bar"))
# do not match. Dynamic keys — t(var) / t(f"...") — are skipped (not static).
_T_CALL_RE = re.compile(r"""(?<![\w.])t\(\s*(["'])(?P<key>(?:(?!\1).)+)\1""")


def check_translation_keys(
    template_sources: dict[str, str],
    config: Any,
) -> list[ContractIssue]:
    """Warn when a template references a translation key missing from catalogs.

    Gated on ``i18n_enabled``. For each supported locale, loads its catalog and
    flags ``t("…")`` literal keys that the catalog does not define. Only fires
    when a catalog for the locale actually exists (an empty/absent catalog is a
    setup state, not a missing-key error).
    """
    if not getattr(config, "i18n_enabled", False):
        return []

    from chirp.i18n.catalog import MessageCatalog

    directory = getattr(config, "i18n_directory", "locales")
    locales = tuple(getattr(config, "i18n_supported_locales", ("en",)))
    catalog = MessageCatalog(directory)

    # Load each locale; only check locales whose catalog is non-empty so we do
    # not spam warnings before any translations exist.
    loaded = {loc: catalog.load(loc) for loc in locales}
    active = {loc: msgs for loc, msgs in loaded.items() if msgs}
    if not active:
        return []

    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        seen: set[str] = set()
        for match in _T_CALL_RE.finditer(source):
            key = match.group("key")
            if key in seen:
                continue
            seen.add(key)
            missing_in = sorted(loc for loc, msgs in active.items() if key not in msgs)
            if missing_in:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="i18n_missing_key",
                        message=(
                            f"Translation key {key!r} (referenced in "
                            f"'{template_name}') is missing from catalog(s): "
                            f"{', '.join(missing_in)}. Add it to the locale "
                            f"JSON file(s) under '{directory}/' or remove the "
                            f"t() call."
                        ),
                        template=template_name,
                    )
                )

    return issues
