"""Search — book search with GET query params and htmx.

Demonstrates GET-based forms (no POST, no CSRF needed) with query
parameter filtering. Uses ``request.query`` for reading search params,
``Page`` for automatic full-page vs fragment rendering, and htmx
for search-as-you-type with URL push.

Demonstrates:
- ``request.query`` for reading query parameters
- GET form submission (no CSRF needed)
- ``Page`` return type (full page for browser, fragment for htmx)
- ``hx-get`` with ``hx-push-url`` for live search
- Filtering and sorting logic
- Empty state handling

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Page, Request

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Sample data — a small book catalog
# ---------------------------------------------------------------------------

BOOKS = [
    {"id": 1, "title": "The Pragmatic Programmer", "author": "David Thomas & Andrew Hunt", "genre": "programming", "year": 2019, "rating": 4.7},
    {"id": 2, "title": "Clean Code", "author": "Robert C. Martin", "genre": "programming", "year": 2008, "rating": 4.4},
    {"id": 3, "title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "genre": "systems", "year": 2017, "rating": 4.8},
    {"id": 4, "title": "The Art of Computer Programming", "author": "Donald Knuth", "genre": "cs-theory", "year": 1968, "rating": 4.6},
    {"id": 5, "title": "Structure and Interpretation of Computer Programs", "author": "Abelson & Sussman", "genre": "cs-theory", "year": 1996, "rating": 4.5},
    {"id": 6, "title": "Introduction to Algorithms", "author": "Cormen, Leiserson, Rivest, Stein", "genre": "cs-theory", "year": 2009, "rating": 4.3},
    {"id": 7, "title": "Python Crash Course", "author": "Eric Matthes", "genre": "programming", "year": 2023, "rating": 4.6},
    {"id": 8, "title": "Fluent Python", "author": "Luciano Ramalho", "genre": "programming", "year": 2022, "rating": 4.7},
    {"id": 9, "title": "Site Reliability Engineering", "author": "Betsy Beyer et al.", "genre": "systems", "year": 2016, "rating": 4.3},
    {"id": 10, "title": "The Phoenix Project", "author": "Gene Kim", "genre": "systems", "year": 2013, "rating": 4.5},
    {"id": 11, "title": "Refactoring", "author": "Martin Fowler", "genre": "programming", "year": 2018, "rating": 4.5},
    {"id": 12, "title": "Don't Make Me Think", "author": "Steve Krug", "genre": "design", "year": 2014, "rating": 4.4},
    {"id": 13, "title": "The Design of Everyday Things", "author": "Don Norman", "genre": "design", "year": 2013, "rating": 4.3},
    {"id": 14, "title": "Eloquent JavaScript", "author": "Marijn Haverbeke", "genre": "programming", "year": 2018, "rating": 4.3},
    {"id": 15, "title": "Operating Systems: Three Easy Pieces", "author": "Arpaci-Dusseau", "genre": "systems", "year": 2018, "rating": 4.6},
]

GENRES = [
    ("", "All genres"),
    ("programming", "Programming"),
    ("systems", "Systems"),
    ("cs-theory", "CS Theory"),
    ("design", "Design"),
]

SORT_OPTIONS = [
    ("relevance", "Relevance"),
    ("title", "Title (A–Z)"),
    ("year-desc", "Newest first"),
    ("year-asc", "Oldest first"),
    ("rating", "Highest rated"),
]


# ---------------------------------------------------------------------------
# Filtering + sorting
# ---------------------------------------------------------------------------


def _search_books(
    query: str = "",
    genre: str = "",
    sort: str = "relevance",
) -> list[dict]:
    """Filter and sort the book catalog."""
    results = list(BOOKS)

    # Filter by genre
    if genre:
        results = [b for b in results if b["genre"] == genre]

    # Filter by search query (title or author)
    if query:
        q = query.lower()
        results = [
            b for b in results
            if q in b["title"].lower() or q in b["author"].lower()
        ]

    # Sort
    if sort == "title":
        results.sort(key=lambda b: b["title"].lower())
    elif sort == "year-desc":
        results.sort(key=lambda b: b["year"], reverse=True)
    elif sort == "year-asc":
        results.sort(key=lambda b: b["year"])
    elif sort == "rating":
        results.sort(key=lambda b: b["rating"], reverse=True)
    # "relevance" keeps the default order (or filtered order)

    return results


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def search_page(request: Request):
    """Search page with filtering and sorting."""
    query = request.query.get("q", "")
    genre = request.query.get("genre", "")
    sort = request.query.get("sort", "relevance")

    books = _search_books(query=query, genre=genre, sort=sort)

    return Page(
        "search.html", "results",
        books=books,
        query=query,
        genre=genre,
        sort=sort,
        genres=GENRES,
        sort_options=SORT_OPTIONS,
        result_count=len(books),
    )


if __name__ == "__main__":
    app.run()
