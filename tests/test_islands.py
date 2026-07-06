"""Tests for islands runtime and template helpers."""

import html
import json
import re
from pathlib import Path

import pytest
from kida import Environment

from chirp import App
from chirp.config import AppConfig
from chirp.contracts.rules_islands import check_island_mounts
from chirp.server.islands import islands_snippet
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS, optimistic_attrs
from chirp.testing import TestClient


def _make_env() -> Environment:
    env = Environment(autoescape=True)
    env.update_filters(BUILTIN_FILTERS)
    for name, value in BUILTIN_GLOBALS.items():
        env.add_global(name, value)
    return env


class TestIslandsSnippet:
    def test_runtime_has_lifecycle_events(self) -> None:
        s = islands_snippet("1")
        assert 'data-chirp="islands"' in s
        assert "chirp:island:mount" in s
        assert "chirp:island:unmount" in s
        assert "chirp:island:remount" in s
        assert "chirp:island:error" in s
        assert "chirp:island:state" in s
        assert "chirp:island:action" in s
        assert "register: register" in s
        assert "import(payload.src)" in s

    @pytest.mark.issue(466)
    def test_ensure_adapter_falls_back_to_register_only_modules(self) -> None:
        """Register-only adapters must mount on first load, not only after remount."""
        s = islands_snippet("1")
        assert "normalizeAdapter(mod) || adapters.get(payload.name)" in s

    def test_default_is_unnonced(self) -> None:
        assert "nonce=" not in islands_snippet("1")

    def test_nonce_kwarg_adds_attr(self) -> None:
        s = islands_snippet("1", nonce="ISLNONCE")
        assert '<script data-chirp="islands" nonce="ISLNONCE">' in s


class TestIslandsInjection:
    async def test_injected_when_enabled(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Hi</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="islands"' in response.text

    async def test_not_injected_on_fragment_request(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert 'data-chirp="islands"' not in response.text

    async def test_not_injected_on_json_response(self) -> None:
        app = App(config=AppConfig(islands=True))

        @app.route("/api")
        def api():
            return {"ok": True}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert 'data-chirp="islands"' not in response.text


class TestIslandHelpers:
    def test_island_props_filter_escapes_json(self) -> None:
        env = _make_env()
        tpl = env.from_string("{{ payload | island_props }}")
        rendered = tpl.render({"payload": {"x": "<tag>", "items": [1, 2]}})
        assert "&quot;" in rendered
        assert "<tag>" not in rendered

    def test_island_attrs_global_renders_mount_attrs(self) -> None:
        env = _make_env()
        tpl = env.from_string(
            '<div{{ island_attrs("editor", props=payload, mount_id="editor-root", src="/static/editor.js") }}></div>'
        )
        rendered = tpl.render({"payload": {"doc_id": 42}})
        assert 'data-island="editor"' in rendered
        assert 'id="editor-root"' in rendered
        assert 'data-island-src="/static/editor.js"' in rendered
        assert "data-island-props=" in rendered

    def test_primitive_attrs_global_renders_primitive_metadata(self) -> None:
        env = _make_env()
        tpl = env.from_string(
            '<div{{ primitive_attrs("wizard_state", props=payload, mount_id="wizard-root") }}></div>'
        )
        rendered = tpl.render({"payload": {"stateKey": "signup", "steps": ["account"]}})
        assert 'data-island="wizard_state"' in rendered
        assert 'data-island-primitive="wizard_state"' in rendered
        assert 'id="wizard-root"' in rendered


class TestOptimisticApplyGuardrail:
    """Issue #153: the blessed optimistic_apply primitive holds ZERO per-client
    server view state. The bright line is enforced by two complementary gates —
    Gate A scans the shipped adapter (client-only), Gate B proves the server
    adds no per-client optimistic state. The end-to-end confirm/revert behavior
    is browser-verified in examples/standalone/optimistic_apply/test_browser_smoke.py."""

    _START = "// >>> optimistic_apply adapter"
    _END = "// <<< optimistic_apply adapter"

    @pytest.mark.issue(153)
    def test_runtime_adapter_is_client_only_canary(self) -> None:
        """Gate A — a best-effort canary over the marker-delimited adapter block:
        it is blessed (self-registers), uses the htmx request lifecycle, and
        opens no transport of its own / persists nothing across the
        client/server boundary. A literal-token denylist is not a formal proof
        (an obfuscated bypass is conceivable); it is the cheap, deterministic
        tripwire for the obvious regressions, paired with Gate B."""
        src = islands_snippet("1")

        # Blessed + self-registers before the first scan.
        assert 'register("optimistic_apply"' in src
        assert "/* baseline: client-only */" in src
        # Exactly one marker pair — a decoy/duplicate block can't shrink the scan.
        assert src.count(self._START) == 1
        assert src.count(self._END) == 1

        # Correlated via the htmx request lifecycle the adapter actually uses.
        for token in (
            "htmx:beforeRequest",
            "htmx:before:request",
            "htmx:afterSwap",
            "htmx:after:swap",
            "htmx:afterRequest",
            "htmx:after:request",
        ):
            assert token in src, f"runtime missing {token!r}"
        assert "onHtmxLifecycle" in src
        assert "detail.ctx" in src
        # Runtime-owned correlation registry, keyed by the htmx request object.
        assert "optimisticInflight" in src

        # NEGATIVE SPACE over the adapter block: no transport of its own, no
        # cross-boundary persistence, no server-correlation token. (htmx's own
        # request object is reached via evt.detail.xhr, matching none of these.)
        block = src.split(self._START)[1].split(self._END)[0]
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "new WebSocket",
            "EventSource",
            "BroadcastChannel",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "cookieStore",
            "document.cookie",
            "navigator.sendBeacon",
            "setRequestHeader",
            "hx-headers",
            "import(",
            "globalThis",
            "X-Optimistic",
            "optimisticId",
            "connectionId",
            "clientId",
            "window.",
        ):
            assert forbidden not in block, (
                f"optimistic_apply adapter must not reference {forbidden!r} — "
                "the rollback baseline is the client's own snapshot, with no "
                "server correlation and no transport of its own."
            )

    def test_runtime_snippet_is_pure(self) -> None:
        """The shipped runtime is a pure function of (version, nonce): it carries
        no per-client server-injected state. Nonce is the only per-request
        variation and is a CSP nonce, not optimistic state."""
        assert islands_snippet("1") == islands_snippet("1")
        assert islands_snippet("1", nonce="N1") != islands_snippet("1", nonce="N2")
        # Removing the (only) per-request token yields identical runtimes.
        a = islands_snippet("1", nonce="NONCE_TOKEN")
        b = islands_snippet("1", nonce="OTHER_TOKEN")
        assert a.replace("NONCE_TOKEN", "X") == b.replace("OTHER_TOKEN", "X")

    @pytest.mark.issue(153)
    def test_no_server_side_optimistic_store_in_source(self) -> None:
        """Gate B (structural tripwire) — the blessed primitive adds ZERO
        server-side optimistic state. Scans the shipped Python source and fails
        if any module assigns a container (dict/set/{}/Store/Lock/Weak*) to a
        name mentioning ``optimistic`` — i.e. a per-client optimistic store.
        ``server/islands.py`` is excluded for its client-side JS string."""
        import chirp

        root = Path(chirp.__file__).resolve().parent
        islands_js = root / "server" / "islands.py"
        # An optimistic-named target bound to a stateful container.
        store = re.compile(
            r"\w*optimistic\w*\s*[:=]\s*(?:\{|\[|set\(|dict\(|defaultdict|Store|Lock|Weak)",
            re.IGNORECASE,
        )
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            if path == islands_js:
                continue  # the JS string legitimately names client-side maps
            text = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(root)}: {m.group(0).strip()}" for m in store.finditer(text)
            )
        assert not offenders, (
            "server-side optimistic state store(s) found — the optimistic_apply "
            "primitive must hold ZERO per-client server view state:\n  " + "\n  ".join(offenders)
        )
        # And the framework defines no optimistic-signal request-header constant.
        assert not any(
            re.search(r'["\']x-[\w-]*optimistic', path.read_text(encoding="utf-8"), re.IGNORECASE)
            for path in sorted(root.rglob("*.py"))
        ), "framework must not define an optimistic-signal header constant"

    @pytest.mark.issue(153)
    async def test_server_does_not_branch_on_optimistic_signal(self) -> None:
        """Gate B (behavioral) — serving an optimistic_apply mount returns only
        authoritative fragments; the server never branches on an optimistic
        signal header and exposes no per-client optimistic surface across many
        clients. (It cannot branch: Gate B's source check proves no such header
        is even defined.)"""
        app = App(config=AppConfig(islands=True))
        page = (
            "<button id='like-1' hx-post='/like' hx-swap='outerHTML'"
            + str(optimistic_attrs([{"op": "toggleClass", "value": "liked"}], mount_id="like-1"))
            + ">Like</button>"
        )

        @app.route("/")
        def index():
            return f"<html><body>{page}</body></html>"

        @app.route("/like", methods=["POST"])
        def like():
            return "<button id='like-1' class='liked'>1</button>"

        leak = re.compile(r"optimistic", re.IGNORECASE)
        assert not {n for n in (set(dir(app)) | set(dir(app._mutable_state))) if leak.search(n)}

        bodies: list[str] = []
        async with TestClient(app) as client:
            home = await client.get("/")
            assert 'data-island-primitive="optimistic_apply"' in home.text
            for _ in range(4):
                signalled = await client.post("/like", headers={"X-Chirp-Optimistic": "1"})
                plain = await client.post("/like")
                assert signalled.status == 200
                assert signalled.text == plain.text
                assert "optimistic" not in str(signalled.headers).lower()
                bodies.append(signalled.text)
        assert len(set(bodies)) == 1

        after = {n for n in (set(dir(app)) | set(dir(app._mutable_state))) if leak.search(n)}
        assert not after, f"server grew an optimistic state surface: {sorted(after)}"


class TestOptimisticAttrsHelper:
    """The optimistic_attrs template global emits a valid mount and refuses, at
    render time, anything that would grow per-client server view state."""

    def test_emits_optimistic_primitive_mount(self) -> None:
        env = _make_env()
        tpl = env.from_string(
            "<button{{ optimistic_attrs("
            '[{"op": "toggleClass", "value": "liked"}, {"op": "disable"}],'
            ' mount_id="like-1") }}>x</button>'
        )
        rendered = tpl.render({})
        assert 'data-island="optimistic_apply"' in rendered
        assert 'data-island-primitive="optimistic_apply"' in rendered
        assert 'id="like-1"' in rendered
        assert "toggleClass" in rendered

    def test_accepts_single_op_dict(self) -> None:
        out = optimistic_attrs({"op": "addClass", "value": "done"})
        assert 'data-island-primitive="optimistic_apply"' in out

    def test_rejects_unknown_op(self) -> None:
        with pytest.raises(ValueError, match="unknown op"):
            optimistic_attrs([{"op": "setHtml", "value": "<b>x</b>"}])

    def test_rejects_server_correlation_key(self) -> None:
        with pytest.raises(ValueError, match="server-correlation"):
            optimistic_attrs([{"op": "toggleClass", "value": "x", "mergeUrl": "/m"}])

    def test_rejects_empty_ops(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            optimistic_attrs([])


class TestOptimisticApplyContract:
    """The islands metadata contract validates optimistic_apply mounts by
    default (issue #153 sub-task 2: the guarantee is default-on, not gated
    behind islands_contract_strict)."""

    @staticmethod
    def _mount(props: dict[str, object]) -> dict[str, str]:
        payload = html.escape(json.dumps(props), quote=True)
        return {
            "page.html": (
                '<button id="b" data-island="optimistic_apply" '
                'data-island-primitive="optimistic_apply" '
                f'data-island-props="{payload}"></button>'
            )
        }

    @staticmethod
    def _errors(issues: list) -> list[str]:
        return [i.message for i in issues if i.severity.name == "ERROR"]

    def test_valid_mount_passes(self) -> None:
        issues = check_island_mounts(
            self._mount({"ops": [{"op": "toggleClass", "value": "liked"}]}), strict=False
        )
        assert self._errors(issues) == []

    def test_missing_ops_errors_without_double_reporting(self) -> None:
        errors = self._errors(check_island_mounts(self._mount({}), strict=False))
        assert any("missing required props" in e for e in errors)
        assert not any("non-empty 'ops'" in e for e in errors)

    def test_empty_ops_errors(self) -> None:
        errors = self._errors(check_island_mounts(self._mount({"ops": []}), strict=False))
        assert any("non-empty 'ops'" in e for e in errors)

    def test_unknown_op_errors(self) -> None:
        errors = self._errors(
            check_island_mounts(self._mount({"ops": [{"op": "frobnicate"}]}), strict=False)
        )
        assert any("unknown op" in e for e in errors)

    def test_malformed_op_field_errors(self) -> None:
        errors = self._errors(
            check_island_mounts(self._mount({"ops": [{"op": "addClass"}]}), strict=False)
        )
        assert any("needs a 'value'" in e for e in errors)

    def test_server_correlation_key_errors(self) -> None:
        errors = self._errors(
            check_island_mounts(
                self._mount({"ops": [{"op": "toggleClass", "value": "x"}], "connectionId": "c"}),
                strict=False,
            )
        )
        assert any("server-correlation" in e for e in errors)

    def test_server_correlation_key_inside_op_errors(self) -> None:
        # A forbidden key nested INSIDE an op is caught too (the static contract
        # and the render-time helper share validate_optimistic_op).
        errors = self._errors(
            check_island_mounts(
                self._mount({"ops": [{"op": "toggleClass", "value": "x", "mergeUrl": "/m"}]}),
                strict=False,
            )
        )
        assert any("server-correlation" in e for e in errors)

    def test_settext_invalid_expr_errors(self) -> None:
        # expr must be '+1'/'-1'; an arbitrary expr the runtime cannot apply is
        # an ERROR, not a silent no-op.
        errors = self._errors(
            check_island_mounts(
                self._mount({"ops": [{"op": "setText", "expr": "*2"}]}), strict=False
            )
        )
        assert any("expr must be" in e for e in errors)
        # value-based setText still passes.
        assert (
            self._errors(
                check_island_mounts(
                    self._mount({"ops": [{"op": "setText", "value": "Saved"}]}), strict=False
                )
            )
            == []
        )

    def test_checks_run_by_default_not_only_in_strict(self) -> None:
        # The metadata guarantee is enforced at strict=False (default) — flipping
        # islands_contract_strict only adds advisory mount-id/version WARNINGs.
        bad = self._mount({"ops": [{"op": "frobnicate"}]})
        assert self._errors(check_island_mounts(bad, strict=False))
        assert self._errors(check_island_mounts(bad, strict=True))
