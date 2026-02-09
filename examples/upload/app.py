"""Upload — photo gallery with multipart file uploads.

Demonstrates chirp's multipart form handling: ``UploadFile``, ``form.files``,
``file.save()``, validation of text fields alongside file uploads, and serving
uploaded files via ``StaticFiles`` middleware.

Requires: ``pip install chirp[forms]`` (python-multipart).

Demonstrates:
- ``request.form()`` with ``multipart/form-data``
- ``form.files.get("photo")`` to access ``UploadFile``
- ``upload_file.save(path)`` to write files to disk
- ``upload_file.filename``, ``.content_type``, ``.size``
- ``validate()`` for text fields alongside file uploads
- ``CSRFMiddleware`` for form protection
- ``StaticFiles`` middleware to serve uploaded images

Run:
    pip install chirp[forms]
    python app.py
"""

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Redirect, Request, Template, ValidationError
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, csrf_field
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.middleware.static import StaticFiles
from chirp.validation import max_length, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"
UPLOADS_DIR = Path(__file__).parent / "uploads"

# Ensure uploads directory exists
UPLOADS_DIR.mkdir(exist_ok=True)

_ALLOWED_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")

app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(StaticFiles(directory=str(UPLOADS_DIR), prefix="/uploads"))

app.template_global("csrf_field")(csrf_field)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Photo:
    id: int
    title: str
    description: str
    filename: str
    content_type: str
    size: int


# ---------------------------------------------------------------------------
# In-memory storage
# ---------------------------------------------------------------------------

_photos: list[Photo] = []
_lock = threading.Lock()
_next_id = 1


def _get_photos() -> list[Photo]:
    with _lock:
        return list(reversed(_photos))


def _get_photo(photo_id: int) -> Photo | None:
    with _lock:
        for p in _photos:
            if p.id == photo_id:
                return p
        return None


def _add_photo(title: str, description: str, filename: str, content_type: str, size: int) -> Photo:
    global _next_id
    with _lock:
        photo = Photo(
            id=_next_id,
            title=title,
            description=description,
            filename=filename,
            content_type=content_type,
            size=size,
        )
        _next_id += 1
        _photos.append(photo)
        return photo


def _delete_photo(photo_id: int) -> Photo | None:
    with _lock:
        for i, p in enumerate(_photos):
            if p.id == photo_id:
                _photos.pop(i)
                return p
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_filename(original: str) -> str:
    """Generate a unique filename to avoid collisions."""
    stem = Path(original).stem
    suffix = Path(original).suffix
    timestamp = int(time.time() * 1000)
    return f"{stem}_{timestamp}{suffix}"


# No custom filesize filter needed — Kida ships ``filesizeformat`` built-in.


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def gallery():
    """Show the photo gallery with upload form."""
    photos = _get_photos()
    return Template("gallery.html", photos=photos)


@app.route("/upload", methods=["POST"])
async def upload_photo(request: Request):
    """Handle photo upload with validation."""
    form = await request.form()

    form_values = {
        "title": form.get("title", ""),
        "description": form.get("description", ""),
    }

    # Validate text fields
    result = validate(form, {
        "title": [required, max_length(100)],
        "description": [max_length(500)],
    })

    errors = dict(result.errors) if not result else {}

    # Validate file
    upload = form.files.get("photo")
    if upload is None or not upload.filename:
        errors["photo"] = ["Please select a photo to upload"]
    elif upload.content_type not in _ALLOWED_TYPES:
        errors["photo"] = ["Only JPEG, PNG, GIF, and WebP images are allowed"]
    elif upload.size > _MAX_FILE_SIZE:
        errors["photo"] = ["File must be smaller than 5 MB"]

    if errors:
        return ValidationError(
            "gallery.html", "upload_form",
            errors=errors,
            form=form_values,
            photos=_get_photos(),
        )

    # Save to disk
    assert upload is not None
    filename = _unique_filename(upload.filename)
    await upload.save(UPLOADS_DIR / filename)

    # Store metadata
    _add_photo(
        title=form_values["title"],
        description=form_values["description"],
        filename=filename,
        content_type=upload.content_type,
        size=upload.size,
    )

    return Redirect("/")


@app.route("/photos/{photo_id}")
def photo_detail(photo_id: int):
    """Show a single photo."""
    photo = _get_photo(photo_id)
    if photo is None:
        return ("Photo not found", 404)
    return Template("detail.html", photo=photo)


@app.route("/photos/{photo_id}", methods=["DELETE"])
def delete_photo_route(photo_id: int):
    """Delete a photo and its file."""
    photo = _delete_photo(photo_id)
    if photo is not None:
        file_path = UPLOADS_DIR / photo.filename
        if file_path.exists():
            file_path.unlink()
    return Redirect("/")


if __name__ == "__main__":
    app.run()
