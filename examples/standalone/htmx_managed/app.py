"""Chirp-managed htmx — Mode A provisioning with ``AppConfig(htmx=True)``.

This example writes ``hx-*`` attributes in its template and ships **no** htmx
``<script>`` tag of its own. ``AppConfig(htmx=True)`` makes Chirp the single htmx
authority: the inject middleware appends the htmx runtime before ``</body>`` on
every full-page response (with a per-request CSP nonce, dedup'd on
``data-chirp="htmx"``), so the buttons below actually fire.

Because ``htmx=True`` provisions htmx app-wide, ``app.check()`` stays clean even
though the template uses ``hx-post``. Flip the flag off and the same template
trips the ``htmx_provisioned`` contract (a ``WARNING``): the attributes would be
inert and the UI silently dead, with no console error to point at the cause. The
other provisioning path is to ship your own htmx ``<script>`` in the layout
chain — either satisfies the contract.

Run:
    PYTHONPATH=src python examples/standalone/htmx_managed/app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Fragment, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

# htmx=True → Chirp injects the htmx runtime. No hand-rolled <script> anywhere.
config = AppConfig(template_dir=TEMPLATES_DIR, htmx=True)
app = App(config=config)

# A trivial in-process counter so the example is fully runnable and stateful
# without any external store. (Single-process demo state — not for production.)
_state = {"count": 0}


@app.route("/")
def index():
    """Render the page shell. Chirp injects htmx before </body>."""
    return Template("counter.html", count=_state["count"])


@app.route("/increment", methods=["POST"])
def increment():
    """Bump the counter and return just the updated counter block.

    htmx swaps this fragment into ``#counter`` — no full page reload. The page
    never declares an htmx ``<script>``; Chirp's Mode A injection is what makes
    the ``hx-post`` on the button work at all.
    """
    _state["count"] += 1
    return Fragment("counter.html", "counter", count=_state["count"])


if __name__ == "__main__":
    app.run()
