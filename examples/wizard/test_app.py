"""Tests for the wizard example — multi-step form with session persistence."""

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _get_latest_cookie(response, prev_cookie: str, name: str = "chirp_session") -> str:
    """Return the newest session cookie, falling back to the previous one."""
    new = _extract_cookie(response, name)
    return new if new else prev_cookie



class TestStepNavigation:
    """Step guards redirect to the correct step."""

    async def test_index_redirects_to_step1(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 302
            assert "/step/1" in response.header("location", "")

    async def test_step2_requires_step1(self, example_app) -> None:
        """Accessing step 2 without completing step 1 redirects back."""
        async with TestClient(example_app) as client:
            response = await client.get("/step/2")
            assert response.status == 302
            assert "/step/1" in response.header("location", "")

    async def test_step3_requires_step2(self, example_app) -> None:
        """Accessing step 3 without completing step 2 redirects back."""
        async with TestClient(example_app) as client:
            # Complete step 1 first
            r1 = await client.get("/step/1")
            cookie = _extract_cookie(r1) or ""

            r2 = await client.post(
                "/step/1",
                body=b"first_name=Jane&last_name=Doe&email=jane%40example.com&phone=",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            cookie = _get_latest_cookie(r2, cookie)

            # Try step 3 — should redirect to step 2
            r3 = await client.get(
                "/step/3",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r3.status == 302
            assert "/step/2" in r3.header("location", "")


class TestStep1Validation:
    """POST /step/1 — personal info validation."""

    async def test_empty_fields(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r1 = await client.get("/step/1")
            cookie = _extract_cookie(r1) or ""

            response = await client.post(
                "/step/1",
                body=b"first_name=&last_name=&email=&phone=",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_invalid_email(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r1 = await client.get("/step/1")
            cookie = _extract_cookie(r1) or ""

            response = await client.post(
                "/step/1",
                body=b"first_name=Jane&last_name=Doe&email=bad&phone=",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "valid email" in response.text.lower()

    async def test_valid_step1_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r1 = await client.get("/step/1")
            cookie = _extract_cookie(r1) or ""

            response = await client.post(
                "/step/1",
                body=b"first_name=Jane&last_name=Doe&email=jane%40example.com&phone=",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 302
            assert "/step/2" in response.header("location", "")


class TestStep2Validation:
    """POST /step/2 — shipping address validation."""

    async def _complete_step1(self, client) -> str:
        """Complete step 1 and return the session cookie."""
        r1 = await client.get("/step/1")
        cookie = _extract_cookie(r1) or ""

        r2 = await client.post(
            "/step/1",
            body=b"first_name=Jane&last_name=Doe&email=jane%40example.com&phone=",
            headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
        )
        return _get_latest_cookie(r2, cookie)

    async def test_empty_address_fields(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await self._complete_step1(client)

            response = await client.post(
                "/step/2",
                body=b"address=&city=&state=&zip_code=",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_invalid_zip(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await self._complete_step1(client)

            response = await client.post(
                "/step/2",
                body=b"address=123+Main+St&city=LA&state=CA&zip_code=bad",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "zip" in response.text.lower()

    async def test_valid_step2_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await self._complete_step1(client)

            response = await client.post(
                "/step/2",
                body=b"address=123+Main+St&city=San+Francisco&state=CA&zip_code=94102",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 302
            assert "/step/3" in response.header("location", "")


class TestReviewAndConfirm:
    """Step 3 review and POST /confirm."""

    async def _complete_steps(self, client) -> str:
        """Complete steps 1 and 2, return session cookie."""
        r1 = await client.get("/step/1")
        cookie = _extract_cookie(r1) or ""

        r2 = await client.post(
            "/step/1",
            body=b"first_name=Jane&last_name=Doe&email=jane%40example.com&phone=555-1234",
            headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
        )
        cookie = _get_latest_cookie(r2, cookie)

        r3 = await client.post(
            "/step/2",
            body=b"address=123+Main+St&city=San+Francisco&state=CA&zip_code=94102",
            headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
        )
        return _get_latest_cookie(r3, cookie)

    async def test_review_shows_all_data(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await self._complete_steps(client)

            response = await client.get(
                "/step/3",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 200
            assert "Jane" in response.text
            assert "Doe" in response.text
            assert "jane@example.com" in response.text
            assert "123 Main St" in response.text
            assert "San Francisco" in response.text
            assert "94102" in response.text

    async def test_confirm_shows_confirmation(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await self._complete_steps(client)

            response = await client.post(
                "/confirm",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 200
            assert "Order Confirmed" in response.text
            assert "Jane" in response.text
            assert "94102" in response.text

    async def test_confirm_clears_session(self, example_app) -> None:
        """After confirmation, going to step 3 redirects back to step 1."""
        async with TestClient(example_app) as client:
            cookie = await self._complete_steps(client)

            r1 = await client.post(
                "/confirm",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            cookie = _get_latest_cookie(r1, cookie)

            # Step 3 should redirect — session data is cleared
            r2 = await client.get(
                "/step/3",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.status == 302
            assert "/step/1" in r2.header("location", "")

    async def test_step1_preserves_data_on_back(self, example_app) -> None:
        """Going back to step 1 shows previously entered data."""
        async with TestClient(example_app) as client:
            cookie = await self._complete_steps(client)

            response = await client.get(
                "/step/1",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 200
            assert "Jane" in response.text
            assert "jane@example.com" in response.text
