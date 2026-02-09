"""Tests for the search example — GET forms, query params, filtering, htmx."""

from chirp.testing import TestClient, assert_fragment_contains, assert_is_fragment


class TestSearchPage:
    """GET / renders the search page with all books."""

    async def test_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Book Search" in response.text
            assert "15 books found" in response.text

    async def test_has_search_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'name="q"' in response.text
            assert 'name="genre"' in response.text
            assert 'name="sort"' in response.text

    async def test_fragment_request(self, example_app) -> None:
        """htmx request returns just the results fragment."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert_is_fragment(response)
            assert "15 books found" in response.text
            # Fragment should not include the full page shell
            assert "<h1>" not in response.text


class TestTextSearch:
    """GET /?q= — filter by title or author."""

    async def test_search_by_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=pragmatic")
            assert response.status == 200
            assert "Pragmatic Programmer" in response.text
            assert "1 book" in response.text

    async def test_search_by_author(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=knuth")
            assert response.status == 200
            assert "Art of Computer Programming" in response.text

    async def test_search_case_insensitive(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=PYTHON")
            assert response.status == 200
            assert "Python Crash Course" in response.text
            assert "Fluent Python" in response.text

    async def test_search_no_results(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=zzzznonexistent")
            assert response.status == 200
            assert "0 books found" in response.text
            assert "No books match" in response.text

    async def test_search_fragment(self, example_app) -> None:
        """htmx search returns only the results div."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/?q=clean")
            assert_is_fragment(response)
            assert_fragment_contains(response, "Clean Code")


class TestGenreFilter:
    """GET /?genre= — filter by genre."""

    async def test_filter_programming(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?genre=programming")
            assert response.status == 200
            assert "Pragmatic Programmer" in response.text
            assert "Designing Data" not in response.text

    async def test_filter_systems(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?genre=systems")
            assert response.status == 200
            assert "Designing Data" in response.text
            assert "Clean Code" not in response.text

    async def test_filter_design(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?genre=design")
            assert response.status == 200
            assert "Make Me Think" in response.text
            assert "2 books found" in response.text

    async def test_filter_empty_genre_shows_all(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?genre=")
            assert response.status == 200
            assert "15 books found" in response.text


class TestSorting:
    """GET /?sort= — sort results."""

    async def test_sort_by_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?sort=title")
            text = response.text
            # "Clean Code" should come before "The Pragmatic Programmer"
            assert text.index("Clean Code") < text.index("Pragmatic Programmer")

    async def test_sort_newest_first(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?sort=year-desc")
            text = response.text
            # 2023 book should come before 1968 book
            assert text.index("Python Crash Course") < text.index("Art of Computer Programming")

    async def test_sort_oldest_first(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?sort=year-asc")
            text = response.text
            # 1968 book should come first
            assert text.index("Art of Computer Programming") < text.index("Python Crash Course")

    async def test_sort_highest_rated(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?sort=rating")
            text = response.text
            # 4.8 rated book should come before 4.3 rated books
            assert text.index("Designing Data") < text.index("Introduction to Algorithms")


class TestCombinedFilters:
    """GET /?q=...&genre=...&sort=... — combined filtering and sorting."""

    async def test_search_with_genre(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=python&genre=programming")
            assert response.status == 200
            assert "Python Crash Course" in response.text
            assert "Fluent Python" in response.text
            assert "2 books found" in response.text

    async def test_search_with_genre_and_sort(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?genre=programming&sort=year-desc")
            text = response.text
            # Newest programming book first
            assert text.index("Python Crash Course") < text.index("Clean Code")

    async def test_no_results_combined(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=python&genre=design")
            assert response.status == 200
            assert "0 books found" in response.text
