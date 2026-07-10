"""Milo MCP Apps registration preview for Chirp issue #577.

Run with ``python app.py`` to view the ordinary Chirp page. The example proves
the setup/freeze binding only; issue #578 owns MCP App resource rendering.
"""

from pathlib import Path
from typing import TypedDict

from milo import CLI, MCPAppToolMeta

from chirp import App, AppConfig, Page
from chirp.ext.milo import use_milo

TEMPLATES = Path(__file__).parent / "templates"
RESOURCE_URI = "ui://chirp/work-items/create"


class WorkItemReceipt(TypedDict):
    title: str
    created: bool


cli = CLI(name="work-items")
work_items = cli.group("work-items", description="Work item operations")


@cli.ui_resource(RESOURCE_URI, name="Create work item")
def create_work_item_resource() -> str:
    raise NotImplementedError("Chirp named-block resource rendering is tracked by issue #578")


@work_items.command(
    "create",
    description="Create a work item",
    ui=MCPAppToolMeta(RESOURCE_URI),
)
def create_work_item(title: str) -> WorkItemReceipt:
    return {"title": title, "created": True}


def resource_context() -> dict[str, str]:
    """Return the application-owned read model for a later resource read."""
    return {"heading": "Create a work item"}


app = App(AppConfig(template_dir=TEMPLATES))
adapter = use_milo(app, cli, allowlist=("work-items.create",))
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
        heading="Milo MCP Apps registration preview",
    )


if __name__ == "__main__":
    app.run()
