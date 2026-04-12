# RFC: Pagination for chirp.data

**Status**: Draft
**Created**: 2026-04-12
**Target**: 0.5.0
**Estimated Effort**: 6–10h
**Dependencies**: None (Query class shipped in 0.4.0)
**Source**: Pokedex example has 30 lines of hand-rolled pagination boilerplate; PBP forum plan identifies pagination as a critical framework gap.

---

## Why This Matters

Every app that displays a list needs pagination. Chirp's `Query` class has the building
blocks (`.take()`, `.skip()`, `.count()`) but every app must manually:

1. Clamp the page number (`max(page, 1)`)
2. Calculate the offset (`(page - 1) * per_page`)
3. Run two queries — one for count, one for results (with identical WHERE clauses)
4. Calculate total pages (`math.ceil(total / per_page)`)
5. Pass 4+ context variables to the template (`items`, `page`, `total`, `total_pages`)
6. Build prev/next URLs with query string preservation

### Evidence

**Pokedex example** (`examples/standalone/pokedex/app.py:123-150`):
```python
async def _query_pokemon(*, page=1, per_page=20, type_filter="", search=""):
    offset = (page - 1) * per_page
    query = ALL_POKEMON
    count_query = Query(Pokemon, "pokemon")  # duplicate WHERE clauses
    if type_filter:
        query = query.where(...)
        count_query = count_query.where(...)  # duplicated
    if search:
        query = query.where(...)
        count_query = count_query.where(...)  # duplicated
    total = await count_query.count(app.db)
    results = await query.take(per_page).skip(offset).fetch(app.db)
    total_pages = max(math.ceil(total / per_page), 1)
    return results, total, total_pages
```

The count query duplicates every WHERE clause from the main query. This is fragile — add
a filter to one and forget the other, and your page counts are wrong. `Query.count()`
already strips ORDER BY/LIMIT/OFFSET; a `paginate()` method would use the same Query
for both, eliminating the duplication entirely.

**Other examples** (contacts, search, hackernews, kanban): No pagination at all — they
return full lists because implementing it is too much boilerplate for an example.

### Evidence Table

| Finding | Proposal Impact |
|---------|-----------------|
| Pokedex duplicates WHERE clauses across query + count_query (30 LOC) | FIXES — single Query, `paginate()` runs both |
| 5 other list examples skip pagination entirely | FIXES — one-liner makes it trivial |
| Template pagination requires 4+ context vars (page, total, total_pages, has_next) | FIXES — single `PageResult` object carries all metadata |
| `qs` filter exists for URL building but pagination links are still manual | MITIGATES — `page_range()` method provides the numbers, `qs` builds the URLs |

### Invariants

1. **Query stays immutable**: `paginate()` must not mutate the Query — it chains `.take().skip()` and returns a new result.
2. **No template coupling**: The pagination module is data-only. Template components are a pattern, not a framework feature.
3. **Existing tests pass**: Adding `paginate()` to Query must not change any existing behavior.

---

## Target API

### PageResult dataclass

```python
from chirp.data import PageResult

result: PageResult[Pokemon] = await query.paginate(db, page=2, per_page=20)

result.items        # list[Pokemon] — the rows for this page
result.page         # 2
result.per_page     # 20
result.total        # 157
result.total_pages  # 8
result.has_prev     # True
result.has_next     # True
result.prev_page    # 1
result.next_page    # 3
result.page_range() # [1, 2, 3, 4] — window around current page
```

### Query.paginate() method

```python
# Before (pokedex pattern — 30 LOC):
offset = (page - 1) * per_page
count_query = Query(Pokemon, "pokemon")
if type_filter:
    query = query.where(...)
    count_query = count_query.where(...)
total = await count_query.count(app.db)
results = await query.take(per_page).skip(offset).fetch(app.db)
total_pages = max(math.ceil(total / per_page), 1)
return Page("page.html", "grid", pokemon=results, page=page, total=total, total_pages=total_pages)

# After (1 line):
result = await query.paginate(app.db, page=page, per_page=12)
return Page("page.html", "grid", result=result)
```

### Template usage (pattern, not shipped component)

```html
{% for pokemon in result.items %}
  {# render item #}
{% end %}

{% if result.total_pages > 1 %}
<nav aria-label="Page navigation">
  <a {% if result.has_prev %}hx-get="{{ path | qs(page=result.prev_page) }}"{% end %}
     {% if not result.has_prev %}aria-disabled="true"{% end %}>
    Previous
  </a>
  {% for p in result.page_range(2) %}
    <a hx-get="{{ path | qs(page=p) }}"
       {% if p == result.page %}aria-current="page"{% end %}>{{ p }}</a>
  {% end %}
  <a {% if result.has_next %}hx-get="{{ path | qs(page=result.next_page) }}"{% end %}
     {% if not result.has_next %}aria-disabled="true"{% end %}>
    Next
  </a>
</nav>
{% end %}
```

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 1 | PageResult + Query.paginate() + tests | 4–6h | Low | Yes |
| 2 | Update pokedex example + document pattern | 2–4h | Low | Yes |

---

## Sprint 1: PageResult + Query.paginate()

**Goal**: Ship the pagination primitive in `chirp.data`.

### Task 1.1 — PageResult dataclass

Create `src/chirp/data/pagination.py` with a frozen `PageResult[T]` dataclass.

**Fields**: `items: list[T]`, `page: int`, `per_page: int`, `total: int`
**Properties**: `total_pages`, `has_prev`, `has_next`, `prev_page`, `next_page`, `offset`
**Methods**: `page_range(window=2)` — returns list of page numbers around current page

**Acceptance**: `PageResult(items=[], page=1, per_page=20, total=0).total_pages == 1`

### Task 1.2 — Query.paginate() method

Add `paginate(db, *, page=1, per_page=20) -> PageResult[T]` to `Query`.

Implementation:
1. Clamp page to >= 1
2. `total = await self.count(db)`
3. `items = await self.take(per_page).skip((page - 1) * per_page).fetch(db)`
4. Return `PageResult(items=items, page=page, per_page=per_page, total=total)`

**Acceptance**: `uv run pytest tests/test_pagination.py` passes. Query with 50 rows, page=3, per_page=10 returns items[20:30] and total_pages=5.

### Task 1.3 — Export from chirp.data

Add `PageResult` to `chirp.data.__init__.__all__`.

**Acceptance**: `from chirp.data import PageResult` works.

### Task 1.4 — Tests

- `PageResult` property calculations (total_pages, has_prev/next, page_range, edge cases)
- `Query.paginate()` integration with in-memory SQLite
- Edge cases: page 0 → clamped to 1, page beyond total → empty items, per_page=1, total=0

---

## Sprint 2: Pokedex Migration + Pattern Documentation

**Goal**: Prove the API by simplifying a real example.

### Task 2.1 — Migrate pokedex example

Replace `_query_pokemon()` with `Query.paginate()`. Eliminate the duplicated count_query.

**Acceptance**: `uv run pytest examples/standalone/pokedex/test_app.py` passes. `rg 'count_query' examples/standalone/pokedex/` returns zero hits.

### Task 2.2 — Document pagination pattern in pokedex README

Show the before/after and the template pagination pattern.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Two queries (count + fetch) are slower than a single query with window function | Low | Low | COUNT + LIMIT/OFFSET is the standard pattern. Window functions are PostgreSQL-only and harder to compose. Can add a `paginate_window()` later if needed. |
| PageResult properties don't cover all template needs | Medium | Low | PageResult is a frozen dataclass — users can extend it or access raw fields. `page_range()` covers the most common navigation pattern. |

---

## Success Metrics

| Metric | Current | After Sprint 1 | After Sprint 2 |
|--------|---------|----------------|----------------|
| LOC for paginated query (pokedex) | 30 | 30 (unchanged) | 3 (90% reduction) |
| Examples with pagination | 1 (pokedex, hand-rolled) | 1 | 1 (using framework) |
| Framework pagination support | 0 LOC | ~80 LOC (module + method) | ~80 LOC |

---

## Changelog

- 2026-04-12: Initial draft.
