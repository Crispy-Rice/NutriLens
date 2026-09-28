"""Turns a prepared image plus a provider into an AnalysisResult.

Kept separate from the routes so the same logic serves both the plain JSON
endpoint and the SSE one.

Also owns the timing breakdown. When someone reports "it's slow", the log line
below is the thing to read: it separates image preprocessing, request/upload +
prefill, and token generation, and it flags the single most common cause of a
sudden slowdown — thinking mode being on when it should be off.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.schemas import (
    DISCLAIMER_TEXT,
    AnalysisMode,
    AnalysisResult,
    MealAnalysis,
    ProcessedImage,
    UserProfile,
)
from app.services.image_service import PreparedImage
from app.services.llm.base import CallMetrics, VisionProvider, VisionRequest
from app.services.parser import extract_partial_advice, parse_model_output
from app.services.prompt_service import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

#: Above this ratio of generated tokens to visible characters, we assume the
#: model produced output the user never sees — i.e. reasoning tokens.
SUSPICIOUS_TOKEN_RATIO = 2.5


@dataclass
class Timings:
    """Where the wall-clock time went, in milliseconds."""

    prep_ms: int = 0
    request_ms: int = 0
    first_token_ms: int | None = None
    generation_ms: int = 0
    total_ms: int = 0
    output_chars: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_chars: int = 0

    def as_header(self) -> str:
        """Compact form for the X-NutriLens-Timings response header."""
        first = str(self.first_token_ms) if self.first_token_ms is not None else "n/a"
        prompt = str(self.prompt_tokens) if self.prompt_tokens is not None else "n/a"
        completion = (
            str(self.completion_tokens) if self.completion_tokens is not None else "n/a"
        )
        return (
            f"prep={self.prep_ms};request={self.request_ms};first_token={first};"
            f"gen={self.generation_ms};total={self.total_ms};out_chars={self.output_chars};"
            f"prompt_tokens={prompt};completion_tokens={completion}"
        )


@dataclass
class AnalysisOutcome:
    result: AnalysisResult
    timings: Timings


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _collect_timings(
    metrics: CallMetrics,
    *,
    prep_ms: int,
    model_ms: int,
    output_chars: int,
) -> Timings:
    usage = metrics.usage
    return Timings(
        prep_ms=prep_ms,
        request_ms=metrics.request_ms,
        first_token_ms=metrics.first_token_ms,
        generation_ms=metrics.generation_ms,
        total_ms=prep_ms + model_ms,
        output_chars=output_chars,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        reasoning_chars=metrics.reasoning_chars,
    )


def log_timings(
    timings: Timings, *, provider: str, mode: str, image_count: int = 1
) -> None:
    prompt_tokens = (
        str(timings.prompt_tokens) if timings.prompt_tokens is not None else "n/a"
    )
    completion_tokens = (
        str(timings.completion_tokens)
        if timings.completion_tokens is not None
        else "n/a"
    )
    first_token = (
        f"{timings.first_token_ms}ms" if timings.first_token_ms is not None else "n/a"
    )

    mode_breakdown = (
        f"images={image_count} prep={timings.prep_ms}ms request={timings.request_ms}ms "
        f"first_token={first_token} gen={timings.generation_ms}ms "
        f"total={timings.total_ms}ms out_chars={timings.output_chars} "
        f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens}"
    )

    # The likeliest single cause of a slow run, and the hardest to notice.
    if timings.reasoning_chars > 0:
        logger.warning(
            "识别耗时 %dms（provider=%s mode=%s）| %s",
            timings.total_ms,
            provider,
            mode,
            mode_breakdown,
        )
        logger.warning(
            "模型仍在输出思考内容（%d 字符），这会显著拖慢识别。请确认 "
            "LLM_ENABLE_THINKING=false，且 LLM_THINKING_PARAM 是当前厂商的正确"
            "参数名（Qwen 系为 enable_thinking；留空则不下发该参数）。",
            timings.reasoning_chars,
        )
        return

    if (
        timings.completion_tokens is not None
        and timings.output_chars > 0
        and timings.completion_tokens > timings.output_chars * SUSPICIOUS_TOKEN_RATIO
    ):
        logger.info(
            "识别耗时 %dms（provider=%s mode=%s）| %s",
            timings.total_ms,
            provider,
            mode,
            mode_breakdown,
        )
        logger.warning(
            "生成 token 数（%d）远高于可见输出（%d 字符），可能有未返回给用户的"
            "思考内容。请检查 LLM_ENABLE_THINKING 与 LLM_THINKING_PARAM 对该模型"
            "是否真的生效。",
            timings.completion_tokens,
            timings.output_chars,
        )
        return

    logger.info(
        "识别耗时 %dms（provider=%s mode=%s）| %s",
        timings.total_ms,
        provider,
        mode,
        mode_breakdown,
    )


def profile_in_use(profile: UserProfile | None) -> bool:
    """Whether a profile actually informed this call.

    An all-empty profile is the same as no profile, and recording  for it
    would tell the user their profile was used when it changed nothing.
    """
    return profile is not None and not profile.is_empty


def _processed_images(prepared: list[PreparedImage]) -> list[ProcessedImage]:
    return [
        ProcessedImage(
            index=image.index,
            width=image.width,
            height=image.height,
            bytes=image.size_bytes,
            mime=image.mime,
            operations=image.operations,
        )
        for image in prepared
    ]


def _build_request(
    images: list[PreparedImage],
    mode: AnalysisMode,
    note: str | None,
    profile: UserProfile | None = None,
) -> VisionRequest:
    return VisionRequest(
        images=images,
        system_prompt=build_system_prompt(mode, profile),
        user_prompt=build_user_prompt(mode, note, image_count=len(images)),
        mode=mode,
    )


def _from_meal(
    meal: MealAnalysis,
    *,
    mode: AnalysisMode,
    prepared: list[PreparedImage],
    provider_name: str,
    degraded: bool,
    profile_used: bool = False,
) -> AnalysisResult:
    return AnalysisResult(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        mode=mode,
        dish_name=meal.dish_name,
        dish_name_alternatives=meal.dish_name_alternatives[:3],
        confidence=meal.confidence,
        confidence_reason=meal.confidence_reason,
        ingredients=meal.ingredients,
        portion_estimate=meal.portion_estimate,
        nutrition=meal.nutrition,
        additional_dishes=meal.additional_dishes,
        advice=meal.advice,
        risk_notes=meal.risk_notes,
        uncertainty_notes=meal.uncertainty_notes,
        disclaimer=DISCLAIMER_TEXT,
        degraded=degraded,
        provider=provider_name,
        images=_processed_images(prepared),
        profile_used=profile_used,
    )


def _degraded_result(
    raw_text: str,
    *,
    mode: AnalysisMode,
    prepared: list[PreparedImage],
    provider_name: str,
    reasons: list[str],
    profile_used: bool = False,
) -> AnalysisResult:
    """Last-resort result: show the model's own words instead of an error.

    Better to hand the user readable text than a failure screen, as long as we
    are honest that the structure was lost.
    """
    body = raw_text.strip() or "模型这次没有返回可用内容。请重试一次。"
    return AnalysisResult(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        mode=mode,
        dish_name="无法确定菜品",
        confidence=0.0,
        confidence_reason="模型本次没有返回可解析的结构化结果。",
        ingredients=[],
        portion_estimate=None,
        advice=body,
        risk_notes=[],
        uncertainty_notes=[
            *reasons,
            "这次结果的结构已丢失，建议重新拍摄或换一张更清晰的照片再试一次。",
        ],
        disclaimer=DISCLAIMER_TEXT,
        degraded=True,
        provider=provider_name,
        images=_processed_images(prepared),
        profile_used=profile_used,
    )


def finalize(
    raw_text: str,
    *,
    mode: AnalysisMode,
    prepared: list[PreparedImage],
    provider_name: str,
    profile_used: bool = False,
) -> AnalysisResult:
    """Parse the model's raw reply into a result, degrading rather than failing."""
    outcome = parse_model_output(raw_text)

    if outcome.analysis is None:
        logger.info("识别结果降级为纯文本（provider=%s）", provider_name)
        return _degraded_result(
            outcome.raw_text or raw_text,
            mode=mode,
            prepared=prepared,
            provider_name=provider_name,
            reasons=outcome.reasons,
            profile_used=profile_used,
        )

    if outcome.degraded:
        logger.info("识别结果部分降级（provider=%s）", provider_name)

    return _from_meal(
        outcome.analysis,
        mode=mode,
        prepared=prepared,
        provider_name=provider_name,
        degraded=outcome.degraded,
        profile_used=profile_used,
    )


async def run_analysis(
    prepared: list[PreparedImage],
    *,
    mode: AnalysisMode,
    note: str | None,
    provider: VisionProvider,
    prep_ms: int = 0,
    profile: UserProfile | None = None,
) -> AnalysisOutcome:
    """Non-streaming path: one request, one result."""
    request = _build_request(prepared, mode, note, profile)
    used_profile = profile_in_use(profile)

    started = time.perf_counter()
    raw_text = await provider.analyze(request)
    model_ms = _ms_since(started)

    result = finalize(
        raw_text,
        mode=mode,
        prepared=prepared,
        provider_name=provider.name,
        profile_used=used_profile,
    )
    timings = _collect_timings(
        request.metrics, prep_ms=prep_ms, model_ms=model_ms, output_chars=len(raw_text)
    )
    log_timings(
        timings, provider=provider.name, mode=mode, image_count=len(prepared)
    )

    return AnalysisOutcome(result=result, timings=timings)


async def stream_analysis(
    prepared: list[PreparedImage],
    *,
    mode: AnalysisMode,
    note: str | None,
    provider: VisionProvider,
    prep_ms: int = 0,
    profile: UserProfile | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Streaming path: yields ``(event_name, payload)`` SSE events.

    Only the ``advice`` field is emitted as ``partial`` text — streaming raw
    JSON at the user would be unreadable. The prompt asks for ``advice`` early
    in the object precisely so this text starts flowing after only a handful of
    fields, instead of after the whole JSON body.

    The complete, validated structure arrives in a single ``result`` event.
    """
    request = _build_request(prepared, mode, note, profile)
    used_profile = profile_in_use(profile)

    yield ("status", {"stage": "calling_model", "message": "正在识别菜品与食材…"})

    collected: list[str] = []
    emitted_length = 0
    started = time.perf_counter()

    async for piece in provider.astream(request):
        collected.append(piece)
        advice_so_far = extract_partial_advice("".join(collected))
        if len(advice_so_far) > emitted_length:
            yield ("partial", {"text": advice_so_far[emitted_length:]})
            emitted_length = len(advice_so_far)

    model_ms = _ms_since(started)
    raw_text = "".join(collected)

    yield ("status", {"stage": "parsing", "message": "正在整理分析结果…"})

    result = finalize(
        raw_text,
        mode=mode,
        prepared=prepared,
        provider_name=provider.name,
        profile_used=used_profile,
    )
    log_timings(
        _collect_timings(
            request.metrics,
            prep_ms=prep_ms,
            model_ms=model_ms,
            output_chars=len(raw_text),
        ),
        provider=provider.name,
        mode=mode,
        image_count=len(prepared),
    )

    yield ("result", result.model_dump(mode="json"))
