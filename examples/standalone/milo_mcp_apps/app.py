"""Milo MCP Apps named-block resource rendering for Chirp issue #578.

Run with ``python app.py`` to view the ordinary Chirp page. The same
``work_items.html`` template supplies the browser page, an htmx fragment, the
Milo MCP tool result, and the ``ui://`` MCP App resource HTML.
"""

from pathlib import Path
from typing import TypedDict

from milo import CLI, MCPAppToolMeta

from chirp import App, AppConfig, Fragment, Page
from chirp.ext.milo import MiloMCPAppAdapter, use_milo

TEMPLATES = Path(__file__).parent / "templates"
RESOURCE_URI = "ui://chirp/work-items/create"


class WorkItemReceipt(TypedDict):
    title: str
    created: bool


cli = CLI(name="work-items")
work_items = cli.group("work-items", description="Work item operations")


@cli.ui_resource(RESOURCE_URI, name="Create work item")
def create_work_item_resource() -> str:
    return adapter.render_resource("work-items.create")


@work_items.command(
    "create",
    description="Create a work item",
    ui=MCPAppToolMeta(RESOURCE_URI),
)
def create_work_item(title: str) -> WorkItemReceipt:
    return {"title": title, "created": True}


def resource_context() -> dict[str, str]:
    """Return the application-owned read model for each resource read."""
    return {"heading": "Create a work item"}


app = App(AppConfig(template_dir=TEMPLATES))
adapter: MiloMCPAppAdapter = use_milo(app, cli, allowlist=("work-items.create",))
adapter.bind(
    "work-items.create",
    template="work_items.html",
    block="create_tool",
    context=resource_context,
)


@app.route("/")
def index() -> Page:
    return Page(
        "work_items.html",
        "page_root",
        heading="Milo MCP Apps named-block resource",
    )


@app.route("/create-tool")
def create_tool_surface() -> Page:
    """Same template/block as the MCP App resource, negotiated for browser/htmx."""
    return Page(
        "work_items.html",
        "create_tool",
        heading=resource_context()["heading"],
    )


@app.route("/create-tool/fragment")
def create_tool_fragment() -> Fragment:
    return Fragment(
        "work_items.html",
        "create_tool",
        heading=resource_context()["heading"],
    )


if __name__ == "__main__":
    app.run()
