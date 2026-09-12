"""
Storage-key helpers.

The database stores *storage-relative* keys ("sessions/<id>/photo.png"), never
absolute filesystem paths. That keeps rows portable across dev / container /
S3 and stops server paths leaking through the API.
"""

import os
import shutil

from app.config import UPLOAD_DIR

# Extension is always derived from the format Pillow actually detected,
# never from the client-supplied filename (that is a stored-XSS vector).
FORMAT_EXT = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
}
FORMAT_MEDIA_TYPE = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


def abs_path(key: str) -> str:
    """Resolve a storage key to an absolute path, refusing traversal."""
    if not key:
        raise ValueError("empty storage key")
    normalized = os.path.normpath(key).replace("\\", "/")
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise ValueError(f"unsafe storage key: {key!r}")
    full = os.path.normpath(os.path.join(UPLOAD_DIR, normalized))
    if not full.startswith(os.path.normpath(UPLOAD_DIR)):
        raise ValueError(f"storage key escapes upload dir: {key!r}")
    return full


def public_url(key: str) -> str:
    """Public URL for a storage key."""
    return f"/uploads/{key.replace(os.sep, '/').lstrip('/')}"


def ensure_parent(key: str) -> str:
    """Create the parent directory for a key and return its absolute path."""
    full = abs_path(key)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


def exists(key: str | None) -> bool:
    if not key:
        return False
    try:
        return os.path.exists(abs_path(key))
    except ValueError:
        return False


def session_key(session_id: str, filename: str) -> str:
    return f"sessions/{session_id}/{filename}"


def template_key(template_id: str, filename: str) -> str:
    return f"templates/{template_id}/{filename}"


def remove_session_dir(session_id: str) -> None:
    """Delete a session's whole directory. Never raises."""
    try:
        shutil.rmtree(abs_path(f"sessions/{session_id}"), ignore_errors=True)
    except ValueError:
        pass


def remove_template_dir(template_id: str) -> None:
    try:
        shutil.rmtree(abs_path(f"templates/{template_id}"), ignore_errors=True)
    except ValueError:
        pass


def migrate_legacy_path(stored: str | None) -> str | None:
    """
    v1 stored OS paths like './uploads/sessions/<id>/photo.png'.
    Convert such a value to a storage key so old rows keep working.
    """
    if not stored:
        return None
    value = stored.replace("\\", "/")
    marker = "/uploads/"
    if marker in value:
        return value.split(marker, 1)[1]
    if value.startswith("uploads/"):
        return value[len("uploads/") :]
    return value.lstrip("./")
