"""Image validation and normalisation.

Everything that touches an untrusted upload lives here. The order of steps
matters and is deliberate:

  1. size cap while streaming, so a huge file never lands in memory
  2. real decode, so a renamed .exe or truncated JPEG is rejected on content
     rather than on extension or Content-Type, both of which the client controls
  3. pixel-count cap, so a decompression bomb can't exhaust memory
  4. EXIF orientation fix, so phone photos aren't sideways
  5. flatten to RGB, so palette/alpha images don't turn black
  6. downscale, to bound the model's input cost
  7. re-encode from scratch, which drops all metadata including GPS
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.core.errors import (
    EmptyUploadError,
    FileTooLargeError,
    ImageTooLargeError,
    InvalidImageError,
    TooManyImagesError,
    TotalUploadTooLargeError,
    UnsupportedFormatError,
)

logger = logging.getLogger(__name__)

READ_CHUNK_BYTES = 256 * 1024

# Confirmed by Pillow's own format detection, never by the filename.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

# A 50MP ceiling is far beyond any phone camera but well below the point where
# decoding would threaten the process.
MAX_PIXELS = 50_000_000

EXIF_ORIENTATION_TAG = 0x0112


@dataclass
class PreparedImage:
    """The normalised image handed to the model, plus a record of what we did."""

    data: bytes
    mime: str
    width: int
    height: int
    operations: list[str] = field(default_factory=list)
    #: Position in the uploaded set, so the UI can pair a thumbnail with its
    #: processing record.
    index: int = 0

    @property
    def size_bytes(self) -> int:
        return len(self.data)


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, aborting as soon as it exceeds the cap.

    Reading ``await upload.read()`` wholesale would buffer the entire body
    first, which is exactly what a size limit is supposed to prevent.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(
                f"图片超过 {max_bytes // (1024 * 1024)} MB 上限。",
                hint="请在浏览器端压缩后重试，或选择尺寸更小的照片。",
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise EmptyUploadError()
    return data


def _open_and_validate(data: bytes) -> tuple[str, tuple[int, int], bool]:
    """Confirm the bytes really are a supported image.

    Returns the Pillow format name, the pixel size, and whether the file
    carried EXIF metadata (used only to report accurately what we stripped).
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                raise UnsupportedFormatError(
                    f"暂不支持这种图片格式（检测到 {fmt or '未知格式'}）。",
                    hint="请上传 JPG、PNG 或 WebP 格式的图片。",
                )

            size = probe.size
            if size[0] * size[1] > MAX_PIXELS:
                raise ImageTooLargeError(
                    f"图片分辨率过高（{size[0]}×{size[1]}）。",
                    hint="请先裁剪或缩小图片后再上传。",
                )

            has_exif = bool(probe.info.get("exif"))
            # verify() walks the file structure and catches truncation; it
            # invalidates the file object, so callers must reopen.
            probe.verify()
            return fmt, size, has_exif

    except UnidentifiedImageError as exc:
        # The common case: corrupt file, or a non-image renamed to .jpg.
        raise InvalidImageError() from exc
    except (UnsupportedFormatError, ImageTooLargeError):
        raise
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError() from exc
    except Exception as exc:
        # Truncated streams surface as assorted OSErrors from verify().
        logger.debug("图片校验失败: %s", type(exc).__name__)
        raise InvalidImageError() from exc


def _to_rgb(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white instead of letting it render black."""
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return img.convert("RGB")


def _decode_and_normalise(
    data: bytes, settings: Settings, operations: list[str], max_edge: int
) -> tuple[bytes, tuple[int, int]]:
    """Second pass: apply orientation, flatten, downscale, re-encode.

    Split out from :func:`prepare_image` so the caller can turn any decode
    failure into a friendly error in one place. ``verify()`` in the first pass
    is shallow for JPEG, so genuine truncation only shows up here.
    """
    with Image.open(io.BytesIO(data)) as img:
        # Multi-frame images (animated WebP, APNG): the model only ever sees
        # one frame, so pin it to the first explicitly.
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
            operations.append("动图仅取第一帧")

        try:
            orientation = (img.getexif() or {}).get(EXIF_ORIENTATION_TAG)
        except Exception:
            orientation = None

        img = ImageOps.exif_transpose(img)
        if orientation and orientation != 1:
            operations.append("已修正拍摄方向")

        img = _to_rgb(img)

        longest = max(img.size)
        if longest > max_edge:
            scale = max_edge / longest
            new_size = (
                max(1, round(img.width * scale)),
                max(1, round(img.height * scale)),
            )
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            operations.append(f"已缩放至 {new_size[0]}×{new_size[1]}")

        buffer = io.BytesIO()
        img.save(
            buffer,
            format="JPEG",
            quality=settings.jpeg_quality,
            optimize=True,
        )
        return buffer.getvalue(), img.size


def prepare_image(
    data: bytes, settings: Settings, max_edge: int | None = None
) -> PreparedImage:
    """Validate, normalise and re-encode one upload for model consumption.

    ``max_edge`` overrides the configured single-image limit; multi-image
    requests pass a smaller edge because prefill cost grows with the number of
    images.
    """
    edge = max_edge if max_edge is not None else settings.max_image_edge
    fmt, (orig_w, orig_h), has_exif = _open_and_validate(data)
    operations: list[str] = []

    try:
        prepared_bytes, final_size = _decode_and_normalise(
            data, settings, operations, edge
        )
    except (OSError, ValueError, SyntaxError) as exc:
        # Truncated or structurally broken pixel data.
        logger.debug("图片解码失败: %s", type(exc).__name__)
        raise InvalidImageError() from exc

    if has_exif:
        operations.append("已移除照片元数据（含定位信息）")
    if fmt != "JPEG":
        operations.append("已统一转为 JPEG")

    prepared = PreparedImage(
        data=prepared_bytes,
        mime="image/jpeg",
        width=final_size[0],
        height=final_size[1],
        operations=operations,
    )

    # Log only shape, never content.
    logger.info(
        "图片已处理 %s %dx%d -> %dx%d %d bytes",
        fmt,
        orig_w,
        orig_h,
        prepared.width,
        prepared.height,
        prepared.size_bytes,
    )
    return prepared


async def prepare_images(
    files: Sequence[UploadFile], settings: Settings
) -> list[PreparedImage]:
    """Validate and normalise a set of uploads for one analysis.

    Applies two budgets beyond the per-file cap: a maximum count, and a shared
    total-bytes limit so four files can't each be at the per-file ceiling. When
    more than one image is present the per-image edge shrinks, because prefill
    cost grows roughly linearly with image count.
    """
    uploads = [f for f in files if f is not None and (f.filename or "")]
    if not uploads:
        raise EmptyUploadError()

    if len(uploads) > settings.max_images:
        raise TooManyImagesError(
            f"一次最多上传 {settings.max_images} 张图片，本次收到 {len(uploads)} 张。",
            hint=f"请减少到 {settings.max_images} 张以内再试。",
        )

    # UploadFile.size is known once the multipart body has been parsed, so the
    # budget can be checked before pulling anything into memory.
    declared = [u.size or 0 for u in uploads]
    if sum(declared) > settings.max_total_upload_bytes:
        raise TotalUploadTooLargeError(
            f"这批图片合计超过 {settings.max_total_upload_mb:g} MB 上限。",
            hint="请减少张数，或换用小一些的照片。",
        )

    edge = (
        settings.max_image_edge
        if len(uploads) == 1
        else settings.multi_image_max_edge
    )

    prepared: list[PreparedImage] = []
    for index, upload in enumerate(uploads):
        # The reader re-checks the cap while streaming, so a bogus .size can't
        # get past us.
        data = await read_upload_limited(upload, settings.max_upload_bytes)
        image = await asyncio.to_thread(prepare_image, data, settings, edge)
        image.index = index
        prepared.append(image)

    return prepared
