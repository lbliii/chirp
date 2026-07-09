"""Complex search with experimental HTTP QUERY and a native GET fallback.

The normal form submits only a compact, bookmarkable GET subset. When htmx is
available, the same submit sends the advanced facets in a QUERY body and swaps
the named results block from the same template. The catalog and search logic
stay in this module so the transport boundary is easy to inspect.

Run:
    PYTHONPATH=src python examples/standalone/query_search/app.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, HTTPError, Page, Request, ValidationError

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(
    template_dir=TEMPLATES_DIR,
    htmx=True,
    csp_nonce_enabled=True,
)
app = App(config)


@dataclass(frozen=True, slots=True)
class Paper:
    """One immutable catalog record used by the example search."""

    title: str
    authors: str
    topics: tuple[str, ...]
    year: int
    citations: int
    open_access: bool
    summary: str


@dataclass(frozen=True, slots=True)
class SearchFields:
    """Raw browser fields retained for rendering and validation feedback."""

    q: str = ""
    topic: str = ""
    topics: tuple[str, ...] = ()
    year_from: str = ""
    year_to: str = ""
    min_citations: str = ""
    terms: str = ""
    open_access: bool = False


@dataclass(frozen=True, slots=True)
class SearchSpec:
    """Validated, typed search input shared by GET and QUERY."""

    q: str
    topics: tuple[str, ...]
    year_from: int | None
    year_to: int | None
    min_citations: int
    terms: tuple[str, ...]
    open_access: bool


TOPICS = (
    ("python", "Python"),
    ("web", "Web systems"),
    ("security", "Security"),
    ("data", "Data systems"),
    ("testing", "Testing"),
)
_TOPIC_KEYS = frozenset(key for key, _label in TOPICS)
_BAD_PERCENT_ESCAPE = re.compile(rb"%(?![0-9a-fA-F]{2})")

PAPERS = (
    Paper(
        "Hypermedia-Native Python Applications",
        "A. Rivera and M. Chen",
        ("python", "web"),
        2025,
        42,
        True,
        "Server-rendered HTML fragments, typed response intent, and progressive enhancement.",
    ),
    Paper(
        "Nonce-Safe Conditional HTML",
        "S. Okafor",
        ("security", "web"),
        2026,
        18,
        True,
        "Content security policy nonces, validators, browser caches, and dynamic HTML.",
    ),
    Paper(
        "Deterministic HTML Contract Testing",
        "J. Park",
        ("testing", "web"),
        2026,
        0,
        True,
        "Contract checks for fragments, full pages, empty states, and falsy values.",
    ),
    Paper(
        "Free-Threaded Query Engines",
        "N. Mensah and R. Singh",
        ("python", "data"),
        2024,
        31,
        False,
        "Concurrent Python query planning and immutable result publication without a global interpreter lock.",
    ),
    Paper(
        "Faceted Search Without a SPA",
        "L. Novak",
        ("web", "data"),
        2023,
        57,
        True,
        "Large structured filters transported in request content with server-rendered results.",
    ),
    Paper(
        "Property Tests for Protocol Parsers",
        "D. Ibrahim",
        ("testing", "security"),
        2022,
        73,
        False,
        "Malformed input, bounded parsing, protocol state machines, and reproducible failures.",
    ),
    Paper(
        "Streaming Relational Results in Python",
        "K. Tanaka",
        ("python", "data"),
        2021,
        96,
        True,
        "Cursor ownership, bounded batches, backpressure, and ordered database result streams.",
    ),
)


def _parse_integer(
    name: str,
    raw: str,
    errors: dict[str, list[str]],
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        errors[name] = ["Enter a whole number."]
        return None
    if value < minimum or value > maximum:
        errors[name] = [f"Enter a value from {minimum} to {maximum}."]
        return None
    return value


def _validate(fields: SearchFields) -> tuple[SearchSpec | None, dict[str, list[str]]]:
    errors: dict[str, list[str]] = {}
    q = fields.q.strip()
    if len(q) > 120:
        errors["q"] = ["Keep the text query to 120 characters or fewer."]

    requested_topics = tuple(
        dict.fromkeys((fields.topic, *fields.topics) if fields.topic else fields.topics)
    )
    invalid_topics = sorted(set(requested_topics) - _TOPIC_KEYS)
    if invalid_topics:
        errors["topics"] = [f"Unknown topic: {invalid_topics[0]}."]

    year_from = _parse_integer(
        "year_from",
        fields.year_from,
        errors,
        minimum=1900,
        maximum=2100,
    )
    year_to = _parse_integer(
        "year_to",
        fields.year_to,
        errors,
        minimum=1900,
        maximum=2100,
    )
    if year_from is not None and year_to is not None and year_from > year_to:
        errors["year_to"] = ["The ending year must be at or after the starting year."]

    min_citations = _parse_integer(
        "min_citations",
        fields.min_citations,
        errors,
        minimum=0,
        maximum=100_000,
    )
    terms = tuple(term.strip().lower() for term in fields.terms.splitlines() if term.strip())
    if len(terms) > 12:
        errors["terms"] = ["Use at most 12 required abstract terms."]
    elif any(len(term) > 80 for term in terms):
        errors["terms"] = ["Each required term must be 80 characters or fewer."]

    if errors:
        return None, errors
    return (
        SearchSpec(
            q=q.lower(),
            topics=requested_topics,
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations or 0,
            terms=terms,
            open_access=fields.open_access,
        ),
        {},
    )


def _search(spec: SearchSpec) -> tuple[Paper, ...]:
    matches: list[Paper] = []
    required_topics = set(spec.topics)
    for paper in PAPERS:
        searchable = f"{paper.title} {paper.authors} {paper.summary}".lower()
        if spec.q and spec.q not in searchable:
            continue
        if required_topics and not required_topics.issubset(paper.topics):
            continue
        if spec.year_from is not None and paper.year < spec.year_from:
            continue
        if spec.year_to is not None and paper.year > spec.year_to:
            continue
        if paper.citations < spec.min_citations:
            continue
        if spec.open_access and not paper.open_access:
            continue
        if spec.terms and not all(term in paper.summary.lower() for term in spec.terms):
            continue
        matches.append(paper)
    return tuple(matches)


def _criteria(spec: SearchSpec) -> str:
    parts = []
    if spec.q:
        parts.append(f"text “{spec.q}”")
    if spec.topics:
        parts.append("topics " + ", ".join(spec.topics))
    if spec.year_from is not None or spec.year_to is not None:
        parts.append(f"years {spec.year_from or 'any'}-{spec.year_to or 'any'}")
    if spec.min_citations:
        parts.append(f"at least {spec.min_citations} citations")
    if spec.terms:
        parts.append(f"{len(spec.terms)} required abstract terms")
    if spec.open_access:
        parts.append("open access only")
    return "; ".join(parts) if parts else "all papers"


async def _request_fields(request: Request) -> SearchFields:
    if request.method == "GET":
        return SearchFields(
            q=request.query.get("q", ""),
            topic=request.query.get("topic", ""),
        )

    raw = await request.body()
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPError(400, "Malformed QUERY body: expected UTF-8 form data.") from exc
    if _BAD_PERCENT_ESCAPE.search(raw):
        raise HTTPError(400, "Malformed QUERY body: invalid percent escape in form data.")

    form = await request.form()
    return SearchFields(
        q=form.get("q", ""),
        topic=form.get("topic", ""),
        topics=tuple(form.get_list("topics")),
        year_from=form.get("year_from", ""),
        year_to=form.get("year_to", ""),
        min_citations=form.get("min_citations", ""),
        terms=form.get("terms", ""),
        open_access=form.get("open_access", "") == "1",
    )


@app.route(
    "/",
    methods=["GET", "QUERY"],
    name="search",
    query_media_types=("application/x-www-form-urlencoded",),
)
async def search(request: Request):
    """Render one full page or named results block from validated search input."""
    fields = await _request_fields(request)
    spec, errors = _validate(fields)
    if spec is None:
        return ValidationError(
            "search.html",
            "results",
            errors=errors,
            fields=fields,
            papers=(),
            result_count=0,
            criteria="invalid query",
            method=request.method,
        )

    papers = _search(spec)
    return Page(
        "search.html",
        "results",
        errors={},
        fields=fields,
        papers=papers,
        result_count=len(papers),
        criteria=_criteria(spec),
        method=request.method,
        topics=TOPICS,
    )


if __name__ == "__main__":
    app.run()
