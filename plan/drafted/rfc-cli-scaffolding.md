# RFC: CLI and Project Scaffolding

**Status**: Implemented  
**Date**: 2026-02-10  
**Scope**: New `chirp.cli` module, `Template.inline()`, `pyproject.toml` scripts  
**Related**: Gap Analysis — Kida/Chirp Strategic Plan

---

## Problem

Chirp's time-to-hello-world requires creating a project directory, a templates
directory, a base template, and an app file. FastHTML achieves a working app in
5 lines. While Chirp's explicit structure is the right production choice, the
onboarding friction is a barrier to adoption.

Today there is:
- No `chirp` CLI command (`pyproject.toml` has no `[project.scripts]`)
- No project scaffolding (`chirp new`)
- No CLI wrapper for `app.check()` (validation requires importing the app)
- No way to prototype without template files

### Evidence

**No console scripts** (`pyproject.toml`): No `[project.scripts]` section exists.

**`app.check()` requires Python** (`src/chirp/app.py:604-622`):
```python
def check(self) -> None:
    from chirp.contracts import check_hypermedia_surface
    result = check_hypermedia_surface(self)
    print(format_check_result(result, color=None))
    if not result.ok:
        raise SystemExit(1)
```

To validate contracts, developers must write a script that imports the app and
calls `app.check()`. A `chirp check myapp:app` command would be simpler.

**Comments reference a CLI that doesn't exist** (`src/chirp/contracts.py:20`,
`src/chirp/server/terminal_checks.py:13`): Internal documentation mentions
"chirp check" as a command, but no implementation exists.

---

## Goals

1. A `chirp` CLI with `new`, `run`, and `check` subcommands.
2. Project templates that generate readable, self-documenting code.
3. `Template.inline()` for prototyping without template files.
4. Zero new dependencies — use stdlib `argparse` or existing `click` if already
   in the dep tree.

### Non-Goals

- Framework-within-a-framework CLI (no `chirp generate model`, no migrations).
- Plugin system for CLI extensions.
- Interactive prompts or wizards.

---

## Design

### CLI Commands

#### `chirp new <name> [--minimal]`

Generates a project directory:

```
chirp new myapp
```

Produces:

```
myapp/
├── app.py
├── templates/
│   ├── base.html
│   └── index.html
├── static/
│   └── style.css
└── tests/
    └── test_app.py
```

With `--minimal`:

```
myapp/
├── app.py
└── templates/
    └── index.html
```

The generated `app.py` for `--minimal`:

```python
from chirp import App, Request
from chirp.templating import Template

app = App()

@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")

if __name__ == "__main__":
    app.run()
```

The generated `templates/index.html` for `--minimal`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{{ greeting }}</title>
</head>
<body>
    <h1>{{ greeting }}</h1>
</body>
</html>
```

No hidden config. No magic. Everything generated is visible and editable.

#### `chirp run <app> [--host HOST] [--port PORT]`

Resolves an import string and starts the dev server:

```bash
chirp run myapp:app
chirp run myapp:app --port 3000
```

Implementation: resolve the import string, call `app.run()`. This wraps the
existing `run_dev_server()` in `src/chirp/server/dev.py:15-60` with CLI
argument parsing.

#### `chirp check <app>`

Validates the hypermedia surface:

```bash
chirp check myapp:app
```

Implementation: resolve the import string, call `app.check()`. This wraps
the existing `App.check()` method (`src/chirp/app.py:604-622`).

### CLI Implementation

Use stdlib `argparse` — no new dependency. Chirp's philosophy is minimal
dependencies, and a CLI does not justify adding `click` or `typer`.

```python
# src/chirp/cli/__init__.py

def main() -> None:
    parser = argparse.ArgumentParser(prog="chirp")
    subparsers = parser.add_subparsers(dest="command")

    # chirp new
    new_parser = subparsers.add_parser("new", help="Create a new project")
    new_parser.add_argument("name")
    new_parser.add_argument("--minimal", action="store_true")

    # chirp run
    run_parser = subparsers.add_parser("run", help="Start dev server")
    run_parser.add_argument("app", help="Import string (e.g. myapp:app)")
    run_parser.add_argument("--host", default=None)
    run_parser.add_argument("--port", type=int, default=None)

    # chirp check
    check_parser = subparsers.add_parser("check", help="Validate contracts")
    check_parser.add_argument("app", help="Import string (e.g. myapp:app)")

    args = parser.parse_args()
    ...
```

Register in `pyproject.toml`:

```toml
[project.scripts]
chirp = "chirp.cli:main"
```

### App Import Resolution

A shared utility resolves `"module:attribute"` import strings:

```python
# src/chirp/cli/_resolve.py

def resolve_app(import_string: str) -> App:
    """Resolve 'module:attribute' to a chirp App instance."""
    module_path, _, attr_name = import_string.partition(":")
    if not attr_name:
        attr_name = "app"  # Default: mymodule → mymodule:app
    module = importlib.import_module(module_path)
    app = getattr(module, attr_name)
    if not isinstance(app, App):
        raise TypeError(f"{import_string} is not a chirp.App instance")
    return app
```

Default attribute is `app` — `chirp run myapp` resolves to `myapp:app`. This
is a common convention (Flask, FastAPI, Starlette all use it) and is the one
piece of "convention" in the CLI.

### `Template.inline()` — Prototyping Shortcut

Add a class method to `Template` that renders from a string instead of a file:

```python
@dataclass(frozen=True, slots=True)
class Template:
    name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, /, **context: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "context", context)

    @staticmethod
    def inline(source: str, /, **context: Any) -> InlineTemplate:
        """Create a template from a string. For prototyping only.

        Usage::

            return Template.inline("<h1>{{ title }}</h1>", title="Hello")
        """
        return InlineTemplate(source, context)


@dataclass(frozen=True, slots=True)
class InlineTemplate:
    """A template rendered from a string source. For prototyping."""
    source: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, source: str, /, **context: Any) -> None:
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "context", context)
```

The content negotiation layer (`src/chirp/server/negotiation.py`) adds an
`isinstance(result, InlineTemplate)` check that compiles and renders the
string via `kida.Environment.from_string()`.

`InlineTemplate` is a separate type so that:
1. It's distinguishable in the negotiation pipeline.
2. `app.check()` can warn about inline templates in production code.
3. It's obvious in code review that this is a prototyping shortcut.

### Project Templates

Templates are stored as plain Python strings in `src/chirp/cli/_templates.py`
— no template engine for the scaffolding itself (that would be circular).
Simple `str.format()` substitution:

```python
APP_PY = """\
from chirp import App, Request
from chirp.templating import Template

app = App()


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


if __name__ == "__main__":
    app.run()
"""
```

---

## Testing Strategy

1. **CLI tests**: Invoke `chirp new`, verify directory structure and file contents.
2. **`chirp run` tests**: Verify import resolution and server startup (mock pounce).
3. **`chirp check` tests**: Verify contract validation via CLI.
4. **`Template.inline()` tests**: Verify rendering from string, verify
   `app.check()` warns about inline templates.
5. **Import resolution tests**: Edge cases — missing module, missing attribute,
   wrong type, default attribute name.

---

## Future Considerations

1. **`chirp routes`**: List all registered routes with their methods and return types.
2. **`chirp templates`**: List all templates with their blocks and dependencies.
3. **Cookiecutter / copier integration**: For more complex project templates
   (with database, auth, etc.) — but this is a separate package concern.
