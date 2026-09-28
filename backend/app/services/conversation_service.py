"""Multi-turn conversation turns.

A turn comes in two shapes, decided by whether the user attached new photos:

* **analysis turn** — new images, so the model is asked for the structured JSON
  and we produce an ``AnalysisResult`` exactly as the single-shot path does.
* **chat turn** — no images, so the model answers in prose and nothing is parsed.

That split matches what a user expects: attaching a photo gets you a card,
asking a question gets you an answer.

The conversation's earlier turns are replayed as real user/assistant messages.
Their images are *not* replayed — they were discarded after their turn, and the
system prompt says so explicitly, because a model that believes it can still see
an old photo will invent details about it.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.schemas import (
    AnalysisResult,
    Conversation,
    ConversationMessage,
    UserProfile,
)
from app.services.analysis_service import Timings, log_timings, profile_in_use, finalize
from app.services.image_service import PreparedImage
from app.services.llm.base import ChatTurn, VisionProvider, VisionRequest
from app.services.parser import extract_partial_advice
from app.services.prompt_service import (
    build_chat_system_prompt,
    build_chat_user_prompt,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

#: Fields that only matter for rendering, dropped before the analysis goes back
#: into the prompt as context. Keeps the replayed history small.
_CONTEXT_DROP_FIELDS = (
    "id",
    "created_at",
    "disclaimer",
    "images",
    "profile_used",
    "provider",
    "degraded",
)


def _compact_analysis(result: AnalysisResult) -> str:
    payload = result.model_dump(mode="json")
    for field in _CONTEXT_DROP_FIELDS:
        payload.pop(field, None)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_message(message: ConversationMessage) -> str:
    """Flatten one stored message into the text the model will see."""
    if message.role == "user":
        parts = []
        if message.text:
            parts.append(message.text)
        if message.images:
            parts.append(f"（本轮附了 {len(message.images)} 张照片）")
        return "\n".join(parts) or "（用户没有输入文字）"

    if message.analysis is not None:
        return f"我完成了识别，结构化结果如下：\n{_compact_analysis(message.analysis)}"

    return message.text or "（无内容）"


def build_history(messages: list[ConversationMessage], limit: int) -> list[ChatTurn]:
    """Earlier turns to replay, oldest first.

    The first analysis is always kept — it is the anchor the rest of the
    conversation refers back to — and the most recent ``limit`` messages are
    kept alongside it.
    """
    if not messages:
        return []

    anchor = next(
        (m for m in messages if m.role == "assistant" and m.analysis is not None), None
    )
    recent = messages[-limit:] if limit > 0 else list(messages)

    selected = {m.id: m for m in recent}
    if anchor is not None:
        selected.setdefault(anchor.id, anchor)

    ordered = sorted(selected.values(), key=lambda m: m.seq)
    return [ChatTurn(role=m.role, text=render_message(m)) for m in ordered]


async def stream_turn(
    conversation: Conversation,
    *,
    images: list[PreparedImage],
    user_text: str,
    profile: UserProfile | None,
    provider: VisionProvider,
    history_limit: int,
    prep_ms: int = 0,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yields ``(event, payload)`` for one turn.

    Emits ``status`` and ``partial`` as it goes, then a single ``completed``
    event carrying what should be stored. Persistence is the caller's job, so
    this module stays free of database concerns.
    """
    is_analysis = len(images) > 0
    history = build_history(conversation.messages, history_limit)

    if is_analysis:
        request = VisionRequest(
            images=images,
            system_prompt=build_system_prompt(
                conversation.mode, profile, in_conversation=True
            ),
            user_prompt=build_user_prompt(
                conversation.mode, None, image_count=len(images)
            ),
            mode=conversation.mode,
            history=history,
        )
    else:
        request = VisionRequest(
            images=[],
            system_prompt=build_chat_system_prompt(profile, in_conversation=True),
            user_prompt=build_chat_user_prompt(user_text),
            mode=conversation.mode,
            history=history,
        )

    yield (
        "status",
        {
            "stage": "calling_model",
            "message": "正在识别菜品与食材…" if is_analysis else "正在回答…",
        },
    )

    collected: list[str] = []
    emitted = 0
    started = time.perf_counter()

    async for piece in provider.astream(request):
        collected.append(piece)
        raw = "".join(collected)
        # An analysis turn streams only the advice field; a chat turn streams
        # its whole reply, already in the form the user will read.
        so_far = extract_partial_advice(raw) if is_analysis else raw
        if len(so_far) > emitted:
            yield ("partial", {"text": so_far[emitted:]})
            emitted = len(so_far)

    model_ms = int((time.perf_counter() - started) * 1000)
    raw_text = "".join(collected)

    yield ("status", {"stage": "parsing", "message": "正在整理结果…"})

    profile_used = profile_in_use(profile)
    analysis: AnalysisResult | None = None
    if is_analysis:
        analysis = finalize(
            raw_text,
            mode=conversation.mode,
            prepared=images,
            provider_name=provider.name,
            profile_used=profile_used,
        )
        assistant_text = ""
    else:
        assistant_text = raw_text.strip() or "抱歉，我这次没能给出回答，请再试一次。"

    timings = Timings(
        prep_ms=prep_ms,
        request_ms=request.metrics.request_ms,
        first_token_ms=request.metrics.first_token_ms,
        generation_ms=request.metrics.generation_ms,
        total_ms=prep_ms + model_ms,
        output_chars=len(raw_text),
        prompt_tokens=request.metrics.usage.prompt_tokens if request.metrics.usage else None,
        completion_tokens=(
            request.metrics.usage.completion_tokens if request.metrics.usage else None
        ),
        reasoning_chars=request.metrics.reasoning_chars,
    )
    log_timings(
        timings,
        provider=provider.name,
        mode=conversation.mode,
        image_count=len(images),
    )

    yield (
        "completed",
        {
            "assistant_text": assistant_text,
            "analysis": analysis.model_dump(mode="json") if analysis else None,
            "profile_used": profile_used,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
