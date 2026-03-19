"""Tests for the upload example — multipart file uploads, validation, gallery."""

from pathlib import Path

import pytest

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}

UPLOADS_DIR = Path(__file__).parent / "uploads"


@pytest.fixture(autouse=True)
def _clean_uploads():
    """Remove test uploads after each test."""
    yield
    # Clean up any test files (but keep the directory)
    for f in UPLOADS_DIR.iterdir():
        if f.is_file() and f.name != ".gitkeep":
            f.unlink()


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _extract_csrf_token(response) -> str:
    text = response.text
    marker = 'name="_csrf_token" value="'
    start = text.find(marker)
    assert start != -1, "CSRF token not found"
    start += len(marker)
    end = text.find('"', start)
    return text[start:end]


def _build_multipart_body(
    title: str = "Test Photo",
    description: str = "A test image",
    filename: str = "test.jpg",
    file_content: bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100,
    file_content_type: str = "image/jpeg",
    csrf_token: str = "",
    include_file: bool = True,
) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body, content_type)."""
    boundary = "----TestBoundary123"
    parts: list[bytes] = []

    # CSRF token
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="_csrf_token"\r\n\r\n')
    parts.append(f"{csrf_token}\r\n".encode())

    # Title
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="title"\r\n\r\n')
    parts.append(f"{title}\r\n".encode())

    # Description
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="description"\r\n\r\n')
    parts.append(f"{description}\r\n".encode())

    # File
    if include_file:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {file_content_type}\r\n\r\n".encode())
        parts.append(file_content)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


class TestGalleryPage:
    """GET / shows the gallery and upload form."""

    async def test_gallery_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Photo Gallery" in response.text
            assert 'enctype="multipart/form-data"' in response.text

    async def test_empty_gallery(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "No photos yet" in response.text


class TestUploadValidation:
    """POST /upload — validates text fields and file."""

    async def test_missing_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(title="", csrf_token=token)
            response = await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_missing_file(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(csrf_token=token, include_file=False)
            response = await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "select a photo" in response.text.lower()

    async def test_invalid_file_type(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(
                csrf_token=token,
                filename="readme.txt",
                file_content=b"hello",
                file_content_type="text/plain",
            )
            response = await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "JPEG" in response.text or "allowed" in response.text.lower()


class TestUploadSuccess:
    """POST /upload — successful upload flow."""

    async def test_successful_upload_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(csrf_token=token)
            response = await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 302
            assert response.header("location") == "/"

    async def test_uploaded_photo_appears_in_gallery(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(
                title="My Sunset",
                csrf_token=token,
            )
            await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )

            gallery = await client.get("/")
            assert "My Sunset" in gallery.text

    async def test_file_saved_to_disk(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(csrf_token=token)
            await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )

            # At least one file should be in uploads dir
            files = [f for f in UPLOADS_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]
            assert len(files) >= 1


class TestPhotoDetail:
    """GET /photos/{id} — single photo view."""

    async def test_detail_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Upload a photo first
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            body, ct = _build_multipart_body(
                title="Detail Test",
                description="A lovely photo",
                csrf_token=token,
            )
            await client.post(
                "/upload",
                body=body,
                headers={"Content-Type": ct, "Cookie": f"chirp_session={cookie}"},
            )

            response = await client.get("/photos/1")
            assert response.status == 200
            assert "Detail Test" in response.text
            assert "A lovely photo" in response.text

    async def test_detail_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/photos/999")
            assert response.status == 404
