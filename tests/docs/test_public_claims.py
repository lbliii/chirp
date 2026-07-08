"""Machine-check the public evidence ledger introduced by #621."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/design/public-claims.json"


class TestPublicClaims:
    ACTIVE_PUBLIC_DOCS: ClassVar[tuple[Path, ...]] = tuple(
        ROOT / path
        for path in (
            "README.md",
            "site/content/_index.md",
            "site/content/docs/about/thread-safety.md",
            "site/content/docs/build-apps/html-fragments/rendering.md",
            "site/content/docs/build-apps/streaming-updates/reactive-system.md",
            "site/content/docs/quality/deployment/production.md",
            "benchmarks/README.md",
        )
    )
    RISKY_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"\bfree-thread(?:ed|ing)\b", re.IGNORECASE),
        re.compile(r"\b(?:fully )?thread-safe\b", re.IGNORECASE),
        re.compile(r"data races?[^.]*\bimpossible\b", re.IGNORECASE),
        re.compile(r"\bzero[- ]downtime\b", re.IGNORECASE),
        re.compile(r"\brolling reload\b", re.IGNORECASE),
        re.compile(r"\d+(?:\.\d+)?k?\s*req/s", re.IGNORECASE),
    )

    def _ledger(self) -> dict[str, object]:
        return json.loads(LEDGER.read_text(encoding="utf-8"))

    def test_claim_entries_reference_existing_public_files_and_proof(self) -> None:
        ledger = self._ledger()
        assert ledger["version"] == 1
        claims = ledger["claims"]
        assert isinstance(claims, list)
        seen: set[str] = set()
        for claim in claims:
            assert isinstance(claim, dict)
            assert set(claim) == {"id", "type", "status", "files", "patterns", "proof", "notes"}
            claim_id = claim["id"]
            assert isinstance(claim_id, str)
            assert claim_id not in seen
            seen.add(claim_id)
            files = [ROOT / path for path in claim["files"]]
            assert files, claim_id
            assert all(path.is_file() for path in files), claim_id
            proof = claim["proof"]
            assert proof, claim_id
            for item in proof:
                assert item.startswith("https://") or (ROOT / item).exists(), item
            combined = "\n".join(path.read_text(encoding="utf-8") for path in files).lower()
            for pattern in claim["patterns"]:
                assert pattern.lower() in combined, f"stale claim pattern {claim_id}: {pattern}"

    @pytest.mark.issue(621)
    def test_risky_public_claims_are_registered(self) -> None:
        ledger = self._ledger()
        allowed: dict[Path, list[str]] = {}
        for claim in ledger["claims"]:
            for relative in claim["files"]:
                allowed.setdefault(ROOT / relative, []).extend(claim["patterns"])
        for item in ledger["allowlist"]:
            allowed.setdefault(ROOT / item["file"], []).append(item["pattern"])

        failures: list[str] = []
        for path in self.ACTIVE_PUBLIC_DOCS:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not any(pattern.search(line) for pattern in self.RISKY_PATTERNS):
                    continue
                if any(token.lower() in line.lower() for token in allowed.get(path, [])):
                    continue
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

        assert failures == []
