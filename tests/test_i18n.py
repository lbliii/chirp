"""Tests for the i18n system."""

import json
import tempfile
from pathlib import Path

import pytest

from chirp.i18n import get_locale, set_locale, t
from chirp.i18n.catalog import MessageCatalog
from chirp.i18n.detection import detect_from_cookie, detect_from_header, detect_from_url_prefix
from chirp.i18n.formatting import format_number
from chirp.i18n.middleware import LocaleMiddleware


class FakeRequest:
    def __init__(self, headers=None, cookies=None, path="/"):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.path = path


# -- Catalog tests --


def test_catalog_basic():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "es.json").write_text(json.dumps({"Hello": "Hola"}))
        catalog = MessageCatalog(d)
        assert catalog.translate("es", "Hello") == "Hola"


def test_catalog_missing_key():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "en.json").write_text(json.dumps({}))
        catalog = MessageCatalog(d)
        assert catalog.translate("en", "Missing") == "Missing"


def test_catalog_interpolation():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "es.json").write_text(json.dumps({"Hello, {name}!": "\u00a1Hola, {name}!"}))
        catalog = MessageCatalog(d)
        result = catalog.translate("es", "Hello, {name}!", name="Alice")
        assert result == "\u00a1Hola, Alice!"


def test_catalog_missing_locale():
    with tempfile.TemporaryDirectory() as d:
        catalog = MessageCatalog(d)
        assert catalog.translate("xx", "Hello") == "Hello"


# -- Detection tests --


def test_detect_from_header():
    req = FakeRequest(headers={"accept-language": "es-ES,es;q=0.9,en;q=0.8"})
    assert detect_from_header(req, ("en", "es")) == "es"


def test_detect_from_header_no_match():
    req = FakeRequest(headers={"accept-language": "ja"})
    assert detect_from_header(req, ("en", "es")) is None


def test_detect_from_cookie():
    req = FakeRequest(cookies={"chirp_locale": "ja"})
    assert detect_from_cookie(req, "chirp_locale") == "ja"


def test_detect_from_url_prefix():
    req = FakeRequest(path="/es/about")
    assert detect_from_url_prefix(req, ("en", "es")) == "es"


def test_detect_from_url_prefix_no_match():
    req = FakeRequest(path="/about")
    assert detect_from_url_prefix(req, ("en", "es")) is None


# -- Middleware tests --


@pytest.mark.asyncio
async def test_locale_middleware_header():
    mw = LocaleMiddleware(supported_locales=("en", "es"), default_locale="en")

    detected = None

    async def capture_next(request):
        nonlocal detected
        from chirp.i18n.middleware import _locale_var

        detected = _locale_var.get()
        from chirp.http.response import Response

        return Response("ok")

    req = FakeRequest(headers={"accept-language": "es"})
    await mw(req, capture_next)
    assert detected == "es"


@pytest.mark.asyncio
async def test_locale_middleware_default():
    mw = LocaleMiddleware(supported_locales=("en", "es"), default_locale="en")

    detected = None

    async def capture_next(request):
        nonlocal detected
        from chirp.i18n.middleware import _locale_var

        detected = _locale_var.get()
        from chirp.http.response import Response

        return Response("ok")

    req = FakeRequest(headers={})
    await mw(req, capture_next)
    assert detected == "en"


# -- Formatting tests --


def test_format_number_en():
    assert format_number(1234567) == "1,234,567"


def test_format_number_de():
    assert format_number(1234567, locale="de") == "1.234.567"


def test_format_number_float():
    assert format_number(1234.56) == "1,234.56"


# -- Public API tests --


def test_get_locale_default():
    assert get_locale() == "en"


def test_set_locale():
    set_locale("ja")
    assert get_locale() == "ja"
    # Reset
    set_locale("en")


def test_t_without_catalog():
    assert t("Hello") == "Hello"
    assert t("Hello, {name}!", name="World") == "Hello, World!"


# -- {% trans %} block integration tests --


class TestTransBlockIntegration:
    """Kida {% trans %} blocks wired through chirp's i18n catalog."""

    def test_trans_block_renders_translation(self, tmp_path):
        """{% trans %} uses chirp's catalog for lookups."""
        from chirp.config import AppConfig
        from chirp.i18n import init_catalog
        from chirp.i18n.middleware import _locale_var
        from chirp.templating.integration import create_environment

        locale_dir = tmp_path / "locales"
        locale_dir.mkdir()
        (locale_dir / "es.json").write_text(json.dumps({"Hello": "Hola"}))

        init_catalog(str(locale_dir))
        config = AppConfig(template_dir=str(tmp_path), i18n_enabled=True)
        env = create_environment(config, filters={}, globals_={})

        # Wire gettext callables (normally done by AppCompiler.freeze)
        from chirp.i18n import get_catalog, get_locale

        def _gettext(message):
            catalog = get_catalog()
            if catalog is None:
                return message
            return catalog.translate(get_locale(), message)

        def _ngettext(singular, plural, n):
            return singular if n == 1 else plural

        env.install_gettext_callables(_gettext, _ngettext)

        (tmp_path / "page.html").write_text("{% trans %}Hello{% endtrans %}")

        _locale_var.set("es")
        try:
            html = env.get_template("page.html").render()
            assert html == "Hola"
        finally:
            _locale_var.set("en")

    def test_trans_block_falls_back_to_source(self, tmp_path):
        """{% trans %} returns source string when no translation exists."""
        from chirp.config import AppConfig
        from chirp.i18n import init_catalog
        from chirp.templating.integration import create_environment

        locale_dir = tmp_path / "locales"
        locale_dir.mkdir()
        (locale_dir / "en.json").write_text(json.dumps({}))

        init_catalog(str(locale_dir))
        config = AppConfig(template_dir=str(tmp_path), i18n_enabled=True)
        env = create_environment(config, filters={}, globals_={})

        from chirp.i18n import get_catalog, get_locale

        def _gettext(message):
            catalog = get_catalog()
            if catalog is None:
                return message
            return catalog.translate(get_locale(), message)

        def _ngettext(singular, plural, n):
            return singular if n == 1 else plural

        env.install_gettext_callables(_gettext, _ngettext)

        (tmp_path / "page.html").write_text("{% trans %}Welcome{% endtrans %}")
        html = env.get_template("page.html").render()
        assert html == "Welcome"

    def test_trans_and_t_coexist(self, tmp_path):
        """{% trans %} blocks and t() function work in the same template."""
        from chirp.config import AppConfig
        from chirp.i18n import init_catalog
        from chirp.i18n.middleware import _locale_var
        from chirp.templating.integration import create_environment

        locale_dir = tmp_path / "locales"
        locale_dir.mkdir()
        (locale_dir / "es.json").write_text(json.dumps({"Hello": "Hola", "Goodbye": "Adi\u00f3s"}))

        init_catalog(str(locale_dir))
        config = AppConfig(template_dir=str(tmp_path), i18n_enabled=True)
        env = create_environment(config, filters={}, globals_={})

        from chirp.i18n import get_catalog, get_locale

        def _gettext(message):
            catalog = get_catalog()
            if catalog is None:
                return message
            return catalog.translate(get_locale(), message)

        def _ngettext(singular, plural, n):
            return singular if n == 1 else plural

        env.install_gettext_callables(_gettext, _ngettext)
        env.add_global("t", t)

        (tmp_path / "page.html").write_text("{% trans %}Hello{% endtrans %} {{ t('Goodbye') }}")

        _locale_var.set("es")
        try:
            html = env.get_template("page.html").render()
            assert "Hola" in html
            assert "Adi\u00f3s" in html
        finally:
            _locale_var.set("en")


class TestTransBlockFreezePipeline:
    """Integration: {% trans %} wired automatically through App._freeze()."""

    def test_freeze_wires_gettext_for_trans_blocks(self, tmp_path):
        """App._freeze() installs gettext so {% trans %} works without manual setup."""
        from chirp import App
        from chirp.config import AppConfig
        from chirp.i18n.middleware import _locale_var
        from chirp.templating.returns import Template

        # Set up locale directory with a Spanish translation
        locale_dir = tmp_path / "locales"
        locale_dir.mkdir()
        (locale_dir / "es.json").write_text(json.dumps({"Hello": "Hola"}))

        # Create template that uses {% trans %}
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "greeting.html").write_text("{% trans %}Hello{% endtrans %}")

        config = AppConfig(
            template_dir=str(tpl_dir),
            i18n_enabled=True,
            i18n_directory=str(locale_dir),
            i18n_supported_locales=("en", "es"),
            i18n_default_locale="en",
        )
        app = App(config=config)

        # Add a dummy route so the app can freeze
        @app.route("/")
        def index():
            return "ok"

        app._freeze()

        # Render through the app — gettext was wired by freeze(), not manually
        _locale_var.set("es")
        try:
            html = app.render(Template("greeting.html"))
            assert html == "Hola"
        finally:
            _locale_var.set("en")
