"""Load, validate, and render the authoritative example inventory."""

from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = REPO_ROOT / "examples"
INVENTORY_PATH = EXAMPLES_ROOT / "inventory.toml"

LANES = frozenset({"standalone", "chirpui"})
STATUSES = frozenset({"canonical", "supporting", "experimental"})
NETWORK_REQUIREMENTS = frozenset({"none", "optional", "required"})
README_STATUSES = frozenset({"present", "missing"})
CAPABILITIES = frozenset(
    {
        "accessibility",
        "ai",
        "api",
        "app-shell",
        "auth",
        "chirpui",
        "contracts",
        "csrf",
        "data",
        "docs",
        "forms",
        "fragments",
        "freeze",
        "islands",
        "middleware",
        "mutations",
        "no-js",
        "oob",
        "pages",
        "passkeys",
        "reactive",
        "routing",
        "security",
        "sessions",
        "sse",
        "static-files",
        "streaming",
        "suspense",
        "tools",
        "uploads",
        "validation",
        "view-transitions",
    }
)


class InventoryError(ValueError):
    """The example inventory disagrees with its schema or the repository."""


@dataclass(frozen=True, slots=True)
class ExampleEntry:
    """One stable, machine-readable example catalog entry."""

    path: str
    lane: str
    status: str
    tier: int
    extras: tuple[str, ...]
    network: str
    capabilities: tuple[str, ...]
    readme: str
    test_entrypoint: str


def _string_tuple(raw: object, *, field: str, example: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise InventoryError(f"{example}: {field} must be an array of strings")
    return tuple(raw)


def load_inventory(path: Path = INVENTORY_PATH) -> tuple[ExampleEntry, ...]:
    """Read inventory TOML into immutable entries."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise InventoryError(f"{path}: expected inventory version 1")

    raw_entries = data.get("examples")
    if not isinstance(raw_entries, list):
        raise InventoryError(f"{path}: expected [[examples]] entries")

    entries: list[ExampleEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise InventoryError(f"{path}: each [[examples]] item must be a table")
        example = str(raw.get("path", "<missing path>"))
        try:
            entry = ExampleEntry(
                path=raw["path"],
                lane=raw["lane"],
                status=raw["status"],
                tier=raw["tier"],
                extras=_string_tuple(raw["extras"], field="extras", example=example),
                network=raw["network"],
                capabilities=_string_tuple(
                    raw["capabilities"], field="capabilities", example=example
                ),
                readme=raw["readme"],
                test_entrypoint=raw["test_entrypoint"],
            )
        except KeyError as exc:
            raise InventoryError(f"{example}: missing required field {exc.args[0]!r}") from exc
        entries.append(entry)
    return tuple(entries)


def discover_runnable_examples() -> frozenset[str]:
    """Return every lane directory containing an executable ``app.py``."""
    return frozenset(
        app.parent.relative_to(EXAMPLES_ROOT).as_posix()
        for lane in sorted(LANES)
        for app in (EXAMPLES_ROOT / lane).glob("*/app.py")
    )


def _configured_extras() -> frozenset[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return frozenset(data["project"]["optional-dependencies"])


def validate_inventory(entries: tuple[ExampleEntry, ...]) -> None:
    """Fail loudly when inventory metadata or repository coverage drifts."""
    paths = [entry.path for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise InventoryError(f"duplicate example paths: {', '.join(duplicates)}")
    if paths != sorted(paths):
        raise InventoryError("inventory entries must be sorted by path")

    discovered = discover_runnable_examples()
    recorded = frozenset(paths)
    missing = sorted(discovered - recorded)
    stale = sorted(recorded - discovered)
    if missing or stale:
        parts = []
        if missing:
            parts.append(f"missing runnable examples: {', '.join(missing)}")
        if stale:
            parts.append(f"stale inventory entries: {', '.join(stale)}")
        raise InventoryError("; ".join(parts))

    configured_extras = _configured_extras()
    for entry in entries:
        example_dir = EXAMPLES_ROOT / entry.path
        expected_lane = entry.path.partition("/")[0]
        if entry.lane not in LANES or entry.lane != expected_lane:
            raise InventoryError(
                f"{entry.path}: lane {entry.lane!r} must match its parent directory"
            )
        if entry.status not in STATUSES:
            raise InventoryError(f"{entry.path}: unknown status {entry.status!r}")
        if entry.tier not in {1, 2, 3}:
            raise InventoryError(f"{entry.path}: tier must be 1, 2, or 3")
        if entry.network not in NETWORK_REQUIREMENTS:
            raise InventoryError(f"{entry.path}: unknown network requirement {entry.network!r}")
        if entry.readme not in README_STATUSES:
            raise InventoryError(f"{entry.path}: unknown README status {entry.readme!r}")

        actual_readme = "present" if (example_dir / "README.md").is_file() else "missing"
        if entry.readme != actual_readme:
            raise InventoryError(
                f"{entry.path}: README is {actual_readme}, inventory says {entry.readme}"
            )

        if entry.extras != tuple(sorted(set(entry.extras))):
            raise InventoryError(f"{entry.path}: extras must be unique and sorted")
        unknown_extras = sorted(set(entry.extras) - configured_extras)
        if unknown_extras:
            raise InventoryError(
                f"{entry.path}: unknown pyproject extras: {', '.join(unknown_extras)}"
            )

        if not entry.capabilities:
            raise InventoryError(f"{entry.path}: capabilities must not be empty")
        if entry.capabilities != tuple(sorted(set(entry.capabilities))):
            raise InventoryError(f"{entry.path}: capabilities must be unique and sorted")
        unknown_capabilities = sorted(set(entry.capabilities) - CAPABILITIES)
        if unknown_capabilities:
            raise InventoryError(
                f"{entry.path}: unknown capabilities: {', '.join(unknown_capabilities)}"
            )

        test_path = REPO_ROOT / entry.test_entrypoint
        if not test_path.exists():
            raise InventoryError(
                f"{entry.path}: test entrypoint does not exist: {entry.test_entrypoint}"
            )
        if example_dir not in (test_path, *test_path.parents):
            raise InventoryError(
                f"{entry.path}: test entrypoint must live inside the example directory"
            )
        candidates = test_path.glob("test_*.py") if test_path.is_dir() else (test_path,)
        if not any(
            candidate.is_file() and candidate.name.startswith("test_") for candidate in candidates
        ):
            raise InventoryError(f"{entry.path}: test entrypoint contains no test_*.py files")


def _display(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "—"


def render_catalog(entries: tuple[ExampleEntry, ...]) -> str:
    """Render the complete human-facing inventory table."""
    lines = [
        "<!-- example-inventory:catalog:start -->",
        "| Example | Lane | Status | Tier | Extras | Network | Capabilities | README | Tests |",
        "| --- | --- | --- | :---: | --- | --- | --- | :---: | --- |",
    ]
    for entry in entries:
        name = entry.path.partition("/")[2]
        readme = "yes" if entry.readme == "present" else "missing"
        lines.append(
            f"| [`{entry.path}`]({entry.path}/) | {entry.lane} | {entry.status} | "
            f"{entry.tier} | {_display(entry.extras)} | {entry.network} | "
            f"{_display(entry.capabilities)} | {readme} | "
            f"[`{name}`](../{entry.test_entrypoint}) |"
        )
    lines.append("<!-- example-inventory:catalog:end -->")
    return "\n".join(lines)


def render_lane(entries: tuple[ExampleEntry, ...], lane: str) -> str:
    """Render one lane's compact README inventory."""
    lines = [f"<!-- example-inventory:{lane}:start -->"]
    for entry in entries:
        if entry.lane != lane:
            continue
        name = entry.path.partition("/")[2]
        lines.append(f"- [`{name}`]({name}/) — {entry.status}, tier {entry.tier}")
    lines.append(f"<!-- example-inventory:{lane}:end -->")
    return "\n".join(lines)


def _replace_block(text: str, start: str, end: str, replacement: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise InventoryError(f"README must contain exactly one generated block {start!r} / {end!r}")
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise InventoryError(f"README is missing generated block markers {start!r} / {end!r}")
    end_index += len(end)
    return f"{text[:start_index]}{replacement}{text[end_index:]}"


def expected_readmes(entries: tuple[ExampleEntry, ...]) -> dict[Path, str]:
    """Return README contents with generated inventory blocks refreshed."""
    replacements = {
        EXAMPLES_ROOT / "README.md": render_catalog(entries),
        EXAMPLES_ROOT / "standalone" / "README.md": render_lane(entries, "standalone"),
        EXAMPLES_ROOT / "chirpui" / "README.md": render_lane(entries, "chirpui"),
    }
    expected: dict[Path, str] = {}
    for path, replacement in replacements.items():
        text = path.read_text(encoding="utf-8")
        start, end = replacement.splitlines()[0], replacement.splitlines()[-1]
        expected[path] = _replace_block(text, start, end, replacement)
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when inventory metadata or generated README tables drift",
    )
    args = parser.parse_args()

    entries = load_inventory()
    validate_inventory(entries)
    expected = expected_readmes(entries)
    drifted = [path for path, text in expected.items() if path.read_text(encoding="utf-8") != text]
    if args.check and drifted:
        rendered = ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in drifted)
        raise SystemExit(
            f"example inventory README output is stale: {rendered}; "
            "run `python -m examples.inventory`"
        )
    if not args.check:
        for path, text in expected.items():
            path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
