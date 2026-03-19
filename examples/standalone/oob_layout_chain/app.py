"""OOB Layout Chain — dori-style root layout wrapping page that extends inner layout.

Demonstrates full-page composition with layout chain: root_layout wraps a page
that extends _page_layout. OOB regions (sidebar_oob) are suppressed on full-page
to avoid orphaned fragments; they appear in fragment responses for HTMX swaps.

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition

PAGES_DIR = Path(__file__).parent / "pages"

app = App(AppConfig(template_dir=PAGES_DIR, debug=True))

layout_chain = LayoutChain(
    layouts=(LayoutInfo(template_name="_layout.html", target="body", depth=0),)
)


@app.route("/")
def home() -> PageComposition:
    return PageComposition(
        template="page.html",
        fragment_block="page_content",
        page_block="page_content",
        context={},
        layout_chain=layout_chain,
    )


if __name__ == "__main__":
    app.run()
