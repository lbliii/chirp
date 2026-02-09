"""Tests for the survey example — multi-field form, checkboxes, validation."""

from urllib.parse import urlencode

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _build_survey_body(
    name: str = "Jane Doe",
    age: str = "28",
    interests: list[str] | None = None,
    experience: str = "intermediate",
    country: str = "us",
    comments: str = "",
) -> bytes:
    """Build URL-encoded survey form body.

    Uses a list of tuples to support multiple values for checkboxes.
    """
    if interests is None:
        interests = ["coding", "design"]

    pairs: list[tuple[str, str]] = [
        ("name", name),
        ("age", age),
    ]
    for interest in interests:
        pairs.append(("interests", interest))
    pairs.append(("experience", experience))
    pairs.append(("country", country))
    pairs.append(("comments", comments))

    return urlencode(pairs).encode()


class TestSurveyPage:
    """GET / renders the survey form."""

    async def test_survey_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Developer Survey" in response.text

    async def test_has_all_field_types(self, example_app) -> None:
        """Form includes text, number, checkbox, radio, select, textarea."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            text = response.text
            assert 'type="text"' in text
            assert 'type="number"' in text
            assert 'type="checkbox"' in text
            assert 'type="radio"' in text
            assert "<select" in text
            assert "<textarea" in text


class TestSurveyValidation:
    """POST /submit — validation for all field types."""

    async def test_empty_name_required(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(name="")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_invalid_age(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(age="abc")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "number" in response.text.lower()

    async def test_age_out_of_range(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(age="200")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "between" in response.text.lower()

    async def test_no_interests_selected(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(interests=[])
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "interest" in response.text.lower()

    async def test_invalid_experience(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(experience="hacker")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "one of" in response.text.lower()

    async def test_invalid_country(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(country="xx")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "one of" in response.text.lower()

    async def test_empty_country_required(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(country="")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "required" in response.text.lower()


class TestSurveySuccess:
    """POST /submit — valid submission shows results."""

    async def test_valid_submission(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body()
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Jane Doe" in response.text
            assert "28" in response.text

    async def test_interests_displayed(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(interests=["coding", "music", "travel"])
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Coding" in response.text
            assert "Music" in response.text
            assert "Travel" in response.text

    async def test_experience_displayed(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(experience="expert")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Expert" in response.text

    async def test_country_displayed(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(country="jp")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Japan" in response.text

    async def test_comments_displayed(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(comments="Great survey!")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Great survey!" in response.text

    async def test_optional_comments_omitted(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = _build_survey_body(comments="")
            response = await client.post("/submit", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Comments" not in response.text
