"""Tests for shared contract regex patterns."""

from chirp.contracts.patterns import (
    ID_ATTR,
    KIDA_EXPR,
    METHOD_POST,
    PATH_PARAM,
    SSE_CONNECT_TAG,
    SSE_CONNECT_TAG_BASIC,
)


class TestIdAttr:
    def test_double_quotes(self):
        m = ID_ATTR.search('<div id="main">')
        assert m
        assert m.group(1) == "main"

    def test_single_quotes(self):
        m = ID_ATTR.search("<div id='sidebar'>")
        assert m
        assert m.group(1) == "sidebar"

    def test_spaces_around_equals(self):
        m = ID_ATTR.search('<div id = "spaced">')
        assert m
        assert m.group(1) == "spaced"

    def test_hyphenated_prefix_still_matches(self):
        # \b matches between `-` and `i` since `-` is non-word
        m = ID_ATTR.search('<div data-id="nope">')
        assert m
        assert m.group(1) == "nope"

    def test_empty_id(self):
        m = ID_ATTR.search('<div id="">')
        assert m
        assert m.group(1) == ""


class TestMethodPost:
    def test_lowercase(self):
        assert METHOD_POST.search('method="post"')

    def test_uppercase(self):
        assert METHOD_POST.search('method="POST"')

    def test_single_quotes(self):
        assert METHOD_POST.search("method='post'")

    def test_get_no_match(self):
        assert METHOD_POST.search('method="get"') is None


class TestKidaExpr:
    def test_simple_variable(self):
        m = KIDA_EXPR.search("{{ name }}")
        assert m
        assert m.group() == "{{ name }}"

    def test_filter(self):
        m = KIDA_EXPR.search("{{ name|upper }}")
        assert m
        assert m.group() == "{{ name|upper }}"

    def test_empty_expression(self):
        m = KIDA_EXPR.search("{{ }}")
        assert m
        assert m.group() == "{{ }}"

    def test_no_match_single_brace(self):
        assert KIDA_EXPR.search("{ not_a_template }") is None


class TestPathParam:
    def test_simple(self):
        params = PATH_PARAM.findall("/users/{user_id}/posts/{post_id}")
        assert params == ["user_id", "post_id"]

    def test_no_params(self):
        assert PATH_PARAM.findall("/static/path") == []


class TestSseConnectTag:
    SAMPLE = '<div sse-connect="/events" hx-swap="innerHTML">'

    def test_captures_url(self):
        m = SSE_CONNECT_TAG.search(self.SAMPLE)
        assert m
        assert m.group("url") == "/events"

    def test_captures_tag(self):
        m = SSE_CONNECT_TAG.search(self.SAMPLE)
        assert m
        assert m.group("tag") == "div"

    def test_basic_no_url_group(self):
        m = SSE_CONNECT_TAG_BASIC.search(self.SAMPLE)
        assert m
        assert m.group("tag") == "div"
        # basic variant has no "url" group
        assert "url" not in m.groupdict()

    def test_case_insensitive(self):
        html = '<DIV SSE-CONNECT="/events">'
        assert SSE_CONNECT_TAG.search(html)
        assert SSE_CONNECT_TAG_BASIC.search(html)
