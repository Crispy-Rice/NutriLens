"""Analysis endpoints.

Both the plain and the streaming endpoint share the same pre-flight: read the
upload with a hard size cap, validate and normalise the image. Doing that work
before the response starts means a bad image produces a normal JSON error with
a real status code, instead of a 200 stream that immediately reports failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.api.common import SSE_PING_SECONDS, frame, parse_profile
from app.config import Settings, get_settings
from app.core.errors import AppError, InvalidModeError
from app.db.repository import AnalysisRepository
from app.db.session import SessionLocal
from app.schemas import AnalysisMode, AnalysisResult
from app.services.analysis_service import run_analysis, stream_analysis
from app.services.image_service import PreparedImage, prepare_images
from app.services.llm.factory import get_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])

MAX_NOTE_LENGTH = 300
VALID_MODES = ("quick", "detailed")

#: Carries the timing breakdown on /api/analyze responses.
TIMING_HEADER = "X-NutriLens-Timings"

def _validate_mode(mode: str) -> AnalysisMode:
    if mode not in VALID_MODES:
        raise InvalidModeError()
    return cast(AnalysisMode, mode)


def _clean_note(note: str | None) -> str | None:
    if not note:
        return None
    # The note goes into the prompt, so bound its length.
    trimmed = note.strip()[:MAX_NOTE_LENGTH]
    return trimmed or None


async def _prepare(
    files: list[UploadFile], settings: Settings
) -> tuple[list[PreparedImage], int]:
    """Read, validate and normalise the uploads. Returns the images and how long
    that took, since it is one of the terms in the timing breakdown."""
    started = time.perf_counter()
    prepared = await prepare_images(files, settings)
    return prepared, int((time.perf_counter() - started) * 1000)


def _persist(result: AnalysisResult) -> None:
    """Store the result. History is best-effort — never fail the request over it."""
    db = SessionLocal()
    try:
        AnalysisRepository(db).save(result)
    except Exception:
        logger.exception("保存分析结果失败（不影响本次返回）")
    finally:
        db.close()


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    response: Response,
    files: list[UploadFile] = File(..., description="食物照片，JPG/PNG/WebP，最多 4 张"),
    mode: str = Form("quick"),
    note: str | None = Form(None),
    profile: str | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> AnalysisResult:
    analysis_mode = _validate_mode(mode)
    profile_obj = parse_profile(profile)
    prepared, prep_ms = await _prepare(files, settings)
    provider = get_provider(settings)

    outcome = await run_analysis(
        prepared,
        mode=analysis_mode,
        note=_clean_note(note),
        provider=provider,
        prep_ms=prep_ms,
        profile=profile_obj,
    )

    # Surfacing the breakdown as a header makes it checkable with a single curl
    # without touching the response schema.
    response.headers[TIMING_HEADER] = outcome.timings.as_header()

    _persist(outcome.result)
    return outcome.result


@router.post("/analyze/stream")
async def analyze_stream(
    files: list[UploadFile] = File(..., description="食物照片，JPG/PNG/WebP，最多 4 张"),
    mode: str = Form("quick"),
    note: str | None = Form(None),
    profile: str | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    analysis_mode = _validate_mode(mode)
    profile_obj = parse_profile(profile)
    # Validation and preprocessing happen before the stream opens, so failures
    # here surface as ordinary HTTP errors.
    prepared, prep_ms = await _prepare(files, settings)
    provider = get_provider(settings)
    clean_note = _clean_note(note)

    async def event_source():
        try:
            async for event, payload in stream_analysis(
                prepared,
                mode=analysis_mode,
                note=clean_note,
                provider=provider,
                prep_ms=prep_ms,
                profile=profile_obj,
            ):
                if event == "result":
                    # Persist before handing it over, so the history entry and
                    # the returned result are the same object.
                    try:
                        _persist(AnalysisResult.model_validate(payload))
                    except Exception:
                        logger.exception("流式结果保存失败（不影响本次返回）")
                yield frame(event, payload)
        except AppError as exc:
            logger.warning("[%s] 流式分析失败: %s", exc.code, exc.message)
            yield frame(
                "error", {"code": exc.code, "message": exc.message, "hint": exc.hint}
            )
        except asyncio.CancelledError:
            # Client navigated away or hit cancel; nothing to report.
            raise
        except Exception:
            logger.exception("流式分析出现未处理异常")
            yield frame(
                "error",
                {
                    "code": "internal_error",
                    "message": "分析过程中出现意外错误。",
                    "hint": "请重试一次。",
                },
            )

    return EventSourceResponse(event_source(), ping=SSE_PING_SECONDS)

