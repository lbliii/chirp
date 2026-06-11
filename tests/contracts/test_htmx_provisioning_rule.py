"""Page-level htmx provisioning contract rule (#185).

``check_htmx_provisioned`` warns when a template emits ``hx-*``/``sse-*``
attributes but htmx is not provisioned via ``AppConfig(htmx=True)`` nor an htmx
``<script>`` marker in the scanned template sources.
"""

from chirp.contracts.rules_htmx_provisioned import check_htmx_provisioned
from chirp.contracts.types import Severity


class TestHtmxProvisioningRule:
    def test_hx_attr_without_provisioning_is_flagged(self) -> None:
        sources = {
            "page.html": '<button hx-get="/data" hx-target="#out">Load</button>',
        }
        issues = check_htmx_provisioned(sources, htmx_config_enabled=False)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "htmx_provisioned"
        assert issue.template == "page.html"
        assert "AppConfig(htmx=True)" in issue.message

    def test_sse_attr_without_provisioning_is_flagged(self) -> None:
        sources = {
            "page.html": '<div sse-connect="/events" sse-swap="msg"></div>',
        }
        issues = check_htmx_provisioned(sources, htmx_config_enabled=False)
        assert [i.category for i in issues] == ["htmx_provisioned"]

    def test_silent_when_config_enabled(self) -> None:
        # Negative control: AppConfig(htmx=True) -> Chirp injects htmx, provisioned.
        sources = {
            "page.html": '<button hx-post="/save">Save</button>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=True) == []

    def test_silent_when_data_chirp_marker_present(self) -> None:
        # Negative control: layout ships the Chirp htmx dedup marker.
        sources = {
            "layout.html": '<script data-chirp="htmx" src="/static/htmx.js"></script>',
            "page.html": '<button hx-get="/data">Load</button>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_silent_when_htmx_org_cdn_script_present(self) -> None:
        # Negative control: layout ships its own htmx <script> from the CDN.
        sources = {
            "layout.html": '<script src="https://unpkg.com/htmx.org@2.0.4"></script>',
            "page.html": '<button hx-get="/data">Load</button>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_silent_when_htmx_min_js_script_present(self) -> None:
        sources = {
            "layout.html": '<script src="/static/vendor/htmx.min.js"></script>',
            "page.html": '<button hx-delete="/x">Del</button>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_silent_for_template_without_htmx_attrs(self) -> None:
        # Negative control: no hx-*/sse-* attributes at all.
        sources = {
            "page.html": '<div class="card"><a href="/next">Next</a></div>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_does_not_match_data_hx_substring(self) -> None:
        # Negative control: ``data-hx-foo`` and prose must not match a real
        # hx-* attribute token.
        sources = {
            "page.html": '<div data-hx-thing="x">text about hx-get usage</div>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_framework_templates_are_skipped(self) -> None:
        sources = {
            "chirp/alpine.html": '<button hx-get="/x"></button>',
            "chirpui/modal.html": '<div sse-connect="/e"></div>',
        }
        assert check_htmx_provisioned(sources, htmx_config_enabled=False) == []

    def test_one_issue_per_offending_template(self) -> None:
        sources = {
            "a.html": '<button hx-get="/a">A</button>',
            "b.html": '<div hx-swap-oob="true" id="x"></div>',
            "c.html": "<p>clean</p>",
        }
        issues = check_htmx_provisioned(sources, htmx_config_enabled=False)
        assert {i.template for i in issues} == {"a.html", "b.html"}
