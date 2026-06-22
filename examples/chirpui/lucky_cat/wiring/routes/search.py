"""Command palette search — GET /search."""

from command_palette import palette_results
from feed import get_feed

from chirp import Fragment, Request

from wiring.app_factory import app

_PALETTE_TEMPLATE = "_components/command_palette.html"


def register(app_instance) -> None:
    @app_instance.route("/search", referenced=True)
    def search(request: Request):
        query = (request.query.get("q") or "").strip()
        groups = palette_results(get_feed().markets(), query)
        return Fragment(
            _PALETTE_TEMPLATE,
            "palette_results_body",
            groups=groups,
            query=query,
        )
