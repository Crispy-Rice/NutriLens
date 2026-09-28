"""Multi-image upload tests.

Two budgets sit on top of the per-file cap — a maximum count and a shared
total-bytes limit — and the per-image edge shrinks as images are added, because
prefill cost grows with image count.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.config import Settings
from app.core.errors import (
    EmptyUploadError,
    TooManyImagesError,
    TotalUploadTooLargeError,
)
from app.services.image_service import prepare_images


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"_env_file": None}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def jpeg(size: tuple[int, int] = (3200, 1600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 120, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeUpload:
    """Stands in for FastAPI's UploadFile: filename, size and chunked read."""

    def __init__(self, payload: bytes, filename: str = "photo.jpg") -> None:
        self._buffer = io.BytesIO(payload)
        self.filename = filename
        self.size = len(payload)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def uploads(count: int, size: tuple[int, int] = (3200, 1600)) -> list[FakeUpload]:
    return [FakeUpload(jpeg(size), f"photo{i}.jpg") for i in range(count)]


# --------------------------------------------------------------------------
# Resolution budget
# --------------------------------------------------------------------------


async def test_single_image_keeps_the_full_edge():
    settings = make_settings(max_image_edge=1600, multi_image_max_edge=1024)
    prepared = await prepare_images(uploads(1), settings)  # type: ignore[arg-type]
    assert max(prepared[0].width, prepared[0].height) == 1600


async def test_multiple_images_use_the_smaller_edge():
    """Prefill cost scales with image count, so each image is shrunk to pay for
    the others."""
    settings = make_settings(max_image_edge=1600, multi_image_max_edge=1024)
    prepared = await prepare_images(uploads(3), settings)  # type: ignore[arg-type]
    assert len(prepared) == 3
    for image in prepared:
        assert max(image.width, image.height) == 1024


async def test_indexes_are_assigned_in_upload_order():
    settings = make_settings()
    prepared = await prepare_images(uploads(3), settings)  # type: ignore[arg-type]
    assert [image.index for image in prepared] == [0, 1, 2]


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------


async def test_too_many_images_rejected():
    settings = make_settings(max_images=2)
    with pytest.raises(TooManyImagesError) as exc:
        await prepare_images(uploads(3), settings)  # type: ignore[arg-type]
    assert "最多" in exc.value.message


async def test_exactly_the_maximum_is_allowed():
    settings = make_settings(max_images=2)
    prepared = await prepare_images(uploads(2), settings)  # type: ignore[arg-type]
    assert len(prepared) == 2


async def test_shared_total_bytes_budget_is_enforced():
    """Four files each under the per-file cap must still not add up to a huge
    request."""
    settings = make_settings(max_total_upload_mb=0.001)  # ~1 KB
    with pytest.raises(TotalUploadTooLargeError):
        await prepare_images(uploads(3), settings)  # type: ignore[arg-type]


async def test_no_files_rejected():
    with pytest.raises(EmptyUploadError):
        await prepare_images([], make_settings())  # type: ignore[arg-type]


async def test_blank_filenames_are_ignored():
    """Browsers send an empty part for a file input the user left untouched."""
    settings = make_settings()
    payload = jpeg()
    files = [FakeUpload(payload, ""), FakeUpload(payload, "real.jpg")]
    prepared = await prepare_images(files, settings)  # type: ignore[arg-type]
    assert len(prepared) == 1
