"""
Upload ingestion.

Every uploaded file is:
  1. streamed to a temp file with a hard byte cap (never buffered whole in RAM),
  2. decoded and verified by Pillow — `content_type` is a client-supplied
     header and proves nothing about the bytes,
  3. stored under an extension derived from the *detected* format.

Step 3 matters: v1 took the extension from the client's filename, so a file
named "x.html" with `Content-Type: image/png` was written as photo.html and
served back from /uploads as text/html — script execution on the app's origin.
"""

import logging
import os
import tempfile
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.config import MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES
from app.services import storage
from app.utils.http import bad_request, too_large

log = logging.getLogger(__name__)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
CHUNK = 1024 * 1024


@dataclass
class SavedImage:
    key: str
    width: int
    height: int
    fmt: str
    bytes_written: int


async def _stream_to_temp(upload: UploadFile) -> tuple[str, int]:
    """Stream to a temp file, aborting as soon as the cap is exceeded."""
    fd, tmp_path = tempfile.mkstemp(prefix="bb_upload_")
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise ValueError("too_large")
                out.write(chunk)
    except ValueError:
        os.unlink(tmp_path)
        too_large(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            "Please use a smaller image."
        )
    except Exception:
        os.unlink(tmp_path)
        raise
    return tmp_path, total


async def save_upload_image(
    upload: UploadFile,
    key_stem: str,
    max_side: int | None = None,
) -> SavedImage:
    """
    Validate an uploaded image and store it at `<key_stem><detected ext>`.

    `max_side` optionally downscales very large photos. Badges top out around
    1800 px at 300 DPI, so keeping a 6000 px original buys nothing and makes
    every later render slower.
    """
    tmp_path, total = await _stream_to_temp(upload)
    if total == 0:
        os.unlink(tmp_path)
        bad_request("The uploaded file is empty.")

    try:
        with Image.open(tmp_path) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                bad_request(
                    f"Unsupported image format{f' ({fmt})' if fmt else ''}. "
                    "Please upload a JPEG, PNG or WebP."
                )
            probe.verify()  # structural check; invalidates the handle

        with Image.open(tmp_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.width < 8 or img.height < 8:
                bad_request("That image is too small to make a badge from.")

            if max_side and max(img.width, img.height) > max_side:
                scale = max_side / max(img.width, img.height)
                img = img.resize(
                    (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                    Image.LANCZOS,
                )

            ext = storage.FORMAT_EXT[fmt]
            key = f"{key_stem}{ext}"
            dest = storage.ensure_parent(key)

            # Re-encode rather than copying the original bytes: this strips
            # EXIF (which carries GPS and is baked in above anyway) and
            # guarantees what lands on disk is exactly what Pillow parsed.
            if fmt == "JPEG":
                img.convert("RGB").save(dest, "JPEG", quality=95, optimize=True)
            elif fmt == "PNG":
                img.save(dest, "PNG", optimize=True)
            else:
                img.save(dest, "WEBP", quality=95)

            width, height = img.width, img.height
    except Image.DecompressionBombError:
        bad_request("That image has too many pixels to process safely.")
    except OSError as exc:
        log.warning("rejected upload: %s", exc)
        bad_request("That file could not be read as an image. Please try another photo.")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return SavedImage(key=key, width=width, height=height, fmt=fmt, bytes_written=total)
