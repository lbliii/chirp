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
        Path(d, "es.json").write_text(
            json.dumps({"Hello, {name}!": "\u00a1Hola, {name}!"})
        )
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
