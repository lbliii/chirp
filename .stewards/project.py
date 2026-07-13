"""Render compact AGENTS.md maps from the Chirp steward manifest."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

MARKER = "<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->"
BACKING = {"machine": "machine-backed", "manual": "manual", "none": "none"}


def load_manifest(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _proof(invariant: dict, checks: dict[str, dict]) -> str:
    if invariant.get("verification") == "machine":
        check_id = invariant.get("enforced_by", "?")
        invoke = checks.get(check_id, {}).get("invoke")
        if invoke:
            return f"`{invoke.replace('|', '\\|')}` (`{check_id}`)"
        return f"`{check_id}`"
    if invariant.get("evidence_file"):
        anchor = invariant.get("anchor", "")
        return f"{invariant['evidence_file']} · `{anchor}`"
    return "—"


def _bullets(output: list[str], heading: str, items: list[str]) -> None:
    if items:
        output.extend(["", f"## {heading}", ""])
        output.extend(f"- {item}" for item in items)


def render_node(
    steward: dict,
    invariants: list[dict],
    checks: dict[str, dict],
    judgment: dict,
) -> str:
    output = [
        MARKER,
        "",
        f"# Steward: {steward['id']}",
        "",
        steward.get("point_of_view", ""),
        "",
        "Ordinary work: use this map directly with the root map and run only affected checks.",
        "Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.",
        "",
        "## Protects",
        "",
        "| Invariant | Sev | Backing | Proof / anchor |",
        "| --- | --- | --- | --- |",
    ]
    for invariant in invariants:
        statement = invariant["statement"].replace("|", "\\|")
        output.append(
            f"| {statement} | {invariant.get('severity', '')} | "
            f"{BACKING.get(invariant.get('verification'), 'none')} | {_proof(invariant, checks)} |"
        )
    _bullets(output, "Guardrails", steward.get("guardrails", []))
    edges = steward.get("edges", [])
    if edges:
        output.extend(["", "## Edges", ""])
        output.extend(
            f"- {edge.get('type', '?')} → **{edge.get('to')}** ({edge.get('what', '')})"
            for edge in edges
        )
    owns = steward.get("owns", {})
    if owns:
        output.extend(["", "## Owns", ""])
        for key in ("code", "tests", "docs"):
            if owns.get(key):
                values = ", ".join(f"`{value}`" for value in owns[key])
                output.append(f"- **{key}:** {values}")
    _bullets(output, "Advocate", judgment.get("advocate", []))
    _bullets(output, "Do Not", judgment.get("do_not", []))
    _bullets(output, "Serves", judgment.get("serves", []))
    return "\n".join(output).rstrip() + "\n"


def render_root(data: dict, stewards: list[dict], grouped: dict[str, list[dict]]) -> str:
    output = [
        MARKER,
        "",
        f"# Agent Constitution — {data.get('network', 'repository')}",
        "",
        "Ordinary work: use this root map plus only scoped maps on the target path.",
        "Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.",
        "",
        "## Pillars",
        "",
    ]
    output.extend(f"- {pillar}" for pillar in data.get("pillars", []))
    _bullets(output, "Search Discipline", data.get("search_policy", []))
    _bullets(output, "Operating Rules", data.get("operating_rules", []))
    output.extend(
        [
            "",
            "## Network",
            "",
            "| Steward | Map | Invariants | Automated backing |",
            "| --- | --- | --- | --- |",
        ]
    )
    for steward in sorted(stewards, key=lambda item: item["id"]):
        invariants = grouped.get(steward["id"], [])
        machine = sum(item.get("verification") == "machine" for item in invariants)
        percent = f"{100 * machine // len(invariants)}%" if invariants else "—"
        output.append(f"| {steward['id']} | `{steward['path']}` | {len(invariants)} | {percent} |")
    root_invariants = grouped.get("root", [])
    if root_invariants:
        output.extend(
            [
                "",
                "## Protects (constitution)",
                "",
                "| Invariant | Sev | Backing | Proof / anchor |",
                "| --- | --- | --- | --- |",
            ]
        )
        for invariant in root_invariants:
            statement = invariant["statement"].replace("|", "\\|")
            output.append(
                f"| {statement} | {invariant.get('severity', '')} | "
                f"{BACKING.get(invariant.get('verification'), 'none')} | "
                f"{_proof(invariant, data.get('check', {}))} |"
            )
    _bullets(output, "Stop & Ask", data.get("stop_and_ask", []))
    _bullets(output, "Done Criteria", data.get("done_criteria", []))
    output.extend(
        [
            "",
            "---",
            "",
            "Explicit review/audit only: [.stewards/PROTOCOL.md](.stewards/PROTOCOL.md). "
            "Steward maintenance only: [.stewards/manifest.toml](.stewards/manifest.toml), "
            "then `python .stewards/verify.py --coverage`.",
        ]
    )
    return "\n".join(output).rstrip() + "\n"


def build_maps(data: dict) -> dict[str, str]:
    stewards = data.get("steward", [])
    grouped: dict[str, list[dict]] = {}
    for invariant in data.get("invariant", []):
        grouped.setdefault(invariant.get("steward", ""), []).append(invariant)
    maps: dict[str, str] = {}
    for steward in stewards:
        if steward["id"] == "root":
            maps[steward["path"]] = render_root(data, stewards, grouped)
        else:
            maps[steward["path"]] = render_node(
                steward,
                grouped.get(steward["id"], []),
                data.get("check", {}),
                data.get("judgment", {}).get(steward["id"], {}),
            )
    return maps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print", dest="print_id")
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest = args.manifest or repo / ".stewards" / "manifest.toml"
    data = load_manifest(manifest)
    maps = build_maps(data)
    if args.print_id:
        steward = next(
            (item for item in data.get("steward", []) if item["id"] == args.print_id), None
        )
        if not steward:
            print(f"unknown steward: {args.print_id}", file=sys.stderr)
            return 2
        sys.stdout.write(maps[steward["path"]])
        return 0
    stale = [
        path
        for path, content in maps.items()
        if not (repo / path).exists() or (repo / path).read_text() != content
    ]
    if args.check:
        if stale:
            print("STALE maps: " + ", ".join(stale))
            return 1
        print(f"OK all {len(maps)} maps current.")
        return 0
    for path, content in maps.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"projected {len(maps)} maps ({len(stale)} changed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
