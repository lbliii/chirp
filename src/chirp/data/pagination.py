"""Pagination primitives for chirp.data.

Offset-based pagination that composes with ``Query``. One method call
replaces the manual count-query + offset-math + total-pages-calc pattern.

Usage::

    from chirp.data import Query, PageResult

    result: PageResult[Todo] = await (
        Query(Todo, "todos")
        .where("done = ?", False)
        .order_by("id DESC")
        .paginate(db, page=2, per_page=20)
    )

    result.items        # list[Todo] — rows for this page
    result.total_pages  # 5
    result.has_next     # True
    result.page_range() # [1, 2, 3, 4]

Free-threading safety:
    - Frozen dataclass — immutable after creation
    - No shared mutable state
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    """A page of results with pagination metadata.

    Constructed by ``Query.paginate()`` — not typically created directly.
    """

    items: list[T]
    page: int
    per_page: int
    total: int

    @property
    def total_pages(self) -> int:
        """Total number of pages. Always >= 1."""
        if self.total == 0:
            return 1
        return math.ceil(self.total / self.per_page)

    @property
    def has_prev(self) -> bool:
        """Whether a previous page exists."""
        return self.page > 1

    @property
    def has_next(self) -> bool:
        """Whether a next page exists."""
        return self.page < self.total_pages

    @property
    def prev_page(self) -> int:
        """Previous page number, clamped to 1."""
        return max(self.page - 1, 1)

    @property
    def next_page(self) -> int:
        """Next page number, clamped to total_pages."""
        return min(self.page + 1, self.total_pages)

    @property
    def offset(self) -> int:
        """The SQL OFFSET for this page."""
        return (self.page - 1) * self.per_page

    def page_range(self, window: int = 2) -> list[int]:
        """Page numbers around the current page for navigation.

        Returns up to ``2 * window + 1`` page numbers centered on
        the current page, clamped to [1, total_pages].

        ::

            PageResult(items=[], page=5, per_page=10, total=100).page_range(2)
            # [3, 4, 5, 6, 7]

            PageResult(items=[], page=1, per_page=10, total=100).page_range(2)
            # [1, 2, 3]
        """
        start = max(1, self.page - window)
        end = min(self.total_pages, self.page + window)
        return list(range(start, end + 1))
