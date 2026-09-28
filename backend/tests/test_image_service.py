"""Image pipeline tests.

These target the failure modes a real user hits with a phone photo: a corrupt
file, a renamed non-image, something enormous, and a sideways JPEG.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.config import get_settings
from app.core.errors import (
    EmptyUploadError,
    FileTooLargeError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedFormatError,
)
from app.services import image_service
from app.services.image_service import MAX_PIXELS, prepare_image, read_upload_limited

settings = get_settings()


def make_image(
    size: tuple[int, int] = (400, 300),
    fmt: str = "JPEG",
    mode: str = "RGB",
    exif_orientation: int | None = None,
) -> bytes:
    img = Image.new(mode, size, (200, 120, 60))
    buf = io.BytesIO()
    if exif_orientation is not None:
        exif = img.getexif()
        exif[0x0112] = exif_orientation
        img.save(buf, format=fmt, exif=exif)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_jpeg_passes_through_and_is_reencoded():
    result = prepare_image(make_image(), settings)
    assert result.mime == "image/jpeg"
    assert (result.width, result.height) == (400, 300)
    assert result.size_bytes > 0


def test_png_is_accepted_and_converted():
    result = prepare_image(make_image(fmt="PNG"), settings)
    assert result.mime == "image/jpeg"
    assert any("JPEG" in op for op in result.operations)


def test_palette_png_with_transparency_is_flattened_onto_white():
    """A P-mode PNG with alpha must not come out as a black rectangle."""
    img = Image.new("P", (60, 40))
    img.putpalette([255, 255, 255] + [0, 0, 0] * 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG", transparency=0)

    result = prepare_image(buf.getvalue(), settings)
    with Image.open(io.BytesIO(result.data)) as out:
        assert out.mode == "RGB"
        # Transparent area became white. JPEG is lossy, so allow slack — the
        # property under test is "light, not black".
        assert all(channel > 240 for channel in out.getpixel((30, 20)))


# --------------------------------------------------------------------------
# Downscaling
# --------------------------------------------------------------------------


def test_oversized_image_is_scaled_to_max_edge():
    result = prepare_image(make_image((3200, 1600)), settings)
    assert max(result.width, result.height) == settings.max_image_edge
    assert result.width / result.height == pytest.approx(2.0, abs=0.01)
    assert any("缩放" in op for op in result.operations)


def test_image_within_limit_is_not_resized():
    result = prepare_image(make_image((800, 600)), settings)
    assert (result.width, result.height) == (800, 600)
    assert not any("缩放" in op for op in result.operations)


# --------------------------------------------------------------------------
# Failure modes
# --------------------------------------------------------------------------


def test_corrupt_file_raises_friendly_error():
    with pytest.raises(InvalidImageError):
        prepare_image(b"\xff\xd8\xff\xe0" + b"garbage" * 50, settings)


def test_non_image_renamed_to_jpg_is_rejected():
    """The classic case: a text or binary file with an image extension."""
    with pytest.raises(InvalidImageError):
        prepare_image(b"this is plainly not an image", settings)


def test_truncated_jpeg_is_rejected():
    good = make_image((600, 400))
    with pytest.raises(InvalidImageError):
        prepare_image(good[: len(good) // 3], settings)


def test_unsupported_format_is_rejected_with_its_own_error():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (1, 2, 3)).save(buf, format="BMP")
    with pytest.raises(UnsupportedFormatError):
        prepare_image(buf.getvalue(), settings)


def test_dimension_cap_is_enforced(monkeypatch):
    """Dimensions come from the header, so an oversized image is rejected
    before any pixel buffer is allocated."""
    monkeypatch.setattr(image_service, "MAX_PIXELS", 1_000)
    with pytest.raises(ImageTooLargeError):
        prepare_image(make_image((100, 100)), settings)  # 10_000 pixels


def test_pixel_cap_leaves_room_for_normal_photos():
    # Must comfortably clear a 48MP phone camera.
    assert MAX_PIXELS >= 48_000_000


# --------------------------------------------------------------------------
# EXIF handling
# --------------------------------------------------------------------------


def test_exif_rotation_is_applied_and_reported():
    # Orientation 6 = stored rotated, needs a 90° turn to display upright.
    result = prepare_image(make_image((400, 200), exif_orientation=6), settings)
    assert any("方向" in op for op in result.operations)
    # After correction the long edge is vertical, i.e. dimensions swapped.
    assert (result.width, result.height) == (200, 400)


def test_exif_metadata_is_stripped_from_output():
    result = prepare_image(make_image(exif_orientation=6), settings)
    with Image.open(io.BytesIO(result.data)) as out:
        assert not out.getexif()
    assert any("元数据" in op for op in result.operations)


def test_upright_image_reports_no_rotation():
    result = prepare_image(make_image((400, 300), exif_orientation=1), settings)
    assert not any("方向" in op for op in result.operations)


# --------------------------------------------------------------------------
# Streaming size cap
# --------------------------------------------------------------------------


class FakeUpload:
    """Minimal stand-in for UploadFile that yields bytes in chunks."""

    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


async def test_streaming_cap_rejects_oversized_upload():
    upload = FakeUpload(b"x" * (2 * 1024 * 1024))
    with pytest.raises(FileTooLargeError):
        await read_upload_limited(upload, max_bytes=512 * 1024)  # type: ignore[arg-type]


async def test_streaming_cap_accepts_upload_within_limit():
    data = await read_upload_limited(FakeUpload(b"x" * 1000), max_bytes=1024)  # type: ignore[arg-type]
    assert len(data) == 1000


async def test_empty_upload_is_rejected():
    with pytest.raises(EmptyUploadError):
        await read_upload_limited(FakeUpload(b""), max_bytes=1024)  # type: ignore[arg-type]
