"""Verify the Chirp steward graph, evidence, checks, coverage, and map budgets."""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import tomllib
from pathlib import Path


def _load_projector(path: Path):
    spec = importlib.util.spec_from_file_location("steward_projector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load steward projector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ancestor_maps(path: str, steward_paths: set[str]) -> list[str]:
    target = Path(path).parent
    chain = ["AGENTS.md"] if "AGENTS.md" in steward_paths else []
    for candidate in sorted(steward_paths):
        if candidate in chain or candidate == path:
            continue
        parent = Path(candidate).parent
        if parent != Path(".") and (parent == target or parent in target.parents):
            chain.append(candidate)
    if path not in chain:
        chain.append(path)
    return chain


def verify(repo: Path, manifest_path: Path, coverage: bool) -> list[str]:
    with manifest_path.open("rb") as stream:
        data = tomllib.load(stream)
    errors: list[str] = []
    stewards = data.get("steward", [])
    checks = data.get("check", {})
    invariants = data.get("invariant", [])
    ids = [item.get("id") for item in stewards]
    paths = [item.get("path") for item in stewards]
    if len(ids) != len(set(ids)):
        errors.append("duplicate steward id")
    if len(paths) != len(set(paths)):
        errors.append("duplicate steward path")
    steward_ids = set(ids)
    steward_paths = set(paths)
    if "root" not in steward_ids or "AGENTS.md" not in steward_paths:
        errors.append("root steward must own AGENTS.md")

    for steward in stewards:
        errors.extend(
            f"{steward['id']}: unknown edge target {edge.get('to')}"
            for edge in steward.get("edges", [])
            if edge.get("to") not in steward_ids
        )

    for check_id, check in checks.items():
        invoke = check.get("invoke")
        if not invoke:
            errors.append(f"check {check_id}: missing invoke")
        else:
            for token in shlex.split(invoke):
                looks_local = token in {".", "tests", "examples"} or token.startswith(
                    ("tests/", "examples/", "src/", "docs/", "changelog.d/")
                )
                if looks_local and not (repo / token).exists():
                    errors.append(f"check {check_id}: command path does not exist: {token}")
        location = check.get("location")
        if not location or not (repo / location).exists():
            errors.append(f"check {check_id}: missing location {location}")
        proof = check.get("proof_contains")
        if (
            proof
            and location
            and (repo / location).exists()
            and proof not in (repo / location).read_text(encoding="utf-8", errors="ignore")
        ):
            errors.append(f"check {check_id}: proof text not found in {location}: {proof}")

    invariant_ids: set[str] = set()
    for invariant in invariants:
        invariant_id = invariant.get("id", "?")
        if invariant_id in invariant_ids:
            errors.append(f"duplicate invariant id: {invariant_id}")
        invariant_ids.add(invariant_id)
        if invariant.get("steward") not in steward_ids:
            errors.append(f"{invariant_id}: unknown steward {invariant.get('steward')}")
        verification = invariant.get("verification")
        if verification not in {"machine", "manual", "none"}:
            errors.append(f"{invariant_id}: invalid verification {verification}")
        if verification == "machine" and invariant.get("enforced_by") not in checks:
            errors.append(f"{invariant_id}: unknown check {invariant.get('enforced_by')}")
        evidence = invariant.get("evidence_file")
        anchor = invariant.get("anchor")
        if verification == "manual" and not evidence:
            errors.append(f"{invariant_id}: manual invariant needs evidence_file")
        if evidence:
            evidence_path = repo / evidence
            if not evidence_path.exists():
                errors.append(f"{invariant_id}: missing evidence {evidence}")
            elif anchor and anchor not in evidence_path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                errors.append(f"{invariant_id}: missing anchor in {evidence}: {anchor}")

    if coverage:
        for root_name in data.get("coverage_roots", []):
            root = repo / root_name
            if not root.is_dir():
                errors.append(f"coverage root missing: {root_name}")
                continue
            for child in sorted(item for item in root.iterdir() if item.is_dir()):
                if not any(child.rglob("*.py")):
                    continue
                relative_map = f"{child.relative_to(repo).as_posix()}/AGENTS.md"
                if relative_map not in steward_paths:
                    errors.append(f"uncovered code domain: {child.relative_to(repo)}")

    projector = _load_projector(Path(__file__).with_name("project.py"))
    maps = projector.build_maps(data)
    max_bytes = int(data.get("max_active_bytes", 24576))
    for path, expected in maps.items():
        target = repo / path
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            errors.append(f"stale generated map: {path}")
        chain = _ancestor_maps(path, set(maps))
        active_bytes = sum(len(maps[item].encode()) for item in chain)
        if active_bytes > max_bytes:
            errors.append(f"active map chain exceeds budget: {path} ({active_bytes} > {max_bytes})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest = args.manifest or repo / ".stewards" / "manifest.toml"
    errors = verify(repo, manifest, args.coverage)
    if errors:
        print("Steward verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    with manifest.open("rb") as stream:
        data = tomllib.load(stream)
    invariants = data.get("invariant", [])
    machine = sum(item.get("verification") == "machine" for item in invariants)
    manual = sum(item.get("verification") == "manual" for item in invariants)
    none = sum(item.get("verification") == "none" for item in invariants)
    print(
        f"OK {len(data.get('steward', []))} stewards, {len(invariants)} invariants "
        f"({machine} machine, {manual} manual, {none} none)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
