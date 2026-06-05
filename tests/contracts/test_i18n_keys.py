"""Missing-translation-key contract (#161)."""

from chirp.config import AppConfig
from chirp.contracts.rules_i18n import check_translation_keys


def test_missing_key_warns(tmp_path) -> None:
    (tmp_path / "en.json").write_text('{"greeting": "Hello"}', encoding="utf-8")
    cfg = AppConfig(
        i18n_enabled=True,
        i18n_directory=str(tmp_path),
        i18n_supported_locales=("en",),
    )
    sources = {"page.html": '<h1>{{ t("greeting") }}</h1><p>{{ t("tagline") }}</p>'}
    issues = check_translation_keys(sources, cfg)
    assert [i.category for i in issues] == ["i18n_missing_key"]
    assert "tagline" in issues[0].message
    # the present key never warns
    assert all("greeting" not in i.message for i in issues)


def test_disabled_is_noop() -> None:
    cfg = AppConfig(i18n_enabled=False)
    assert check_translation_keys({"page.html": '{{ t("x") }}'}, cfg) == []


def test_empty_catalog_is_noop(tmp_path) -> None:
    # No catalog file at all -> setup state, not a missing-key error.
    cfg = AppConfig(
        i18n_enabled=True,
        i18n_directory=str(tmp_path),
        i18n_supported_locales=("en",),
    )
    assert check_translation_keys({"page.html": '{{ t("x") }}'}, cfg) == []


def test_dynamic_keys_skipped(tmp_path) -> None:
    (tmp_path / "en.json").write_text('{"greeting": "Hello"}', encoding="utf-8")
    cfg = AppConfig(
        i18n_enabled=True,
        i18n_directory=str(tmp_path),
        i18n_supported_locales=("en",),
    )
    # t(var) has no string literal -> not statically checkable -> skipped.
    sources = {"page.html": "{{ t(key_var) }}"}
    assert check_translation_keys(sources, cfg) == []


def test_multiple_locales_reports_each_missing(tmp_path) -> None:
    (tmp_path / "en.json").write_text('{"greeting": "Hello"}', encoding="utf-8")
    (tmp_path / "es.json").write_text('{"greeting": "Hola", "bye": "Adios"}', encoding="utf-8")
    cfg = AppConfig(
        i18n_enabled=True,
        i18n_directory=str(tmp_path),
        i18n_supported_locales=("en", "es"),
    )
    sources = {"page.html": '{{ t("bye") }}'}
    issues = check_translation_keys(sources, cfg)
    # 'bye' is present in es but missing in en — the missing-list names en only.
    assert len(issues) == 1
    assert "catalog(s): en." in issues[0].message
