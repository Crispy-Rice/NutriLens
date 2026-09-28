"""Conversation endpoints.

Creating a conversation and running its first turn are separate calls on
purpose: the first turn takes a while (the model has to see the photo), and
returning a conversation id immediately lets the UI stream that turn with
visible progress instead of blocking on one long request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.common import SSE_PING_SECONDS, frame, parse_profile, validate_mode
from app.config import Settings, get_settings
from app.core.errors import AppError, NotFoundError
from app.db.repository import ConversationRepository
from app.db.session import SessionLocal, get_db
from app.schemas import (
    AnalysisResult,
    Conversation,
    ConversationPage,
    ConversationSummary,
    ProcessedImage,
)
from app.services.conversation_service import stream_turn
from app.services.image_service import PreparedImage, prepare_images
from app.services.llm.factory import get_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])

#: How long a conversation title may get before it's cut for the list.
TITLE_MAX = 60


class ConversationCreate(BaseModel):
    mode: str = "quick"


def _repo(db=Depends(get_db)) -> ConversationRepository:
    return ConversationRepository(db)


def _title_from(analysis: AnalysisResult | None, fallback: str) -> str:
    if analysis is None or not analysis.dish_name:
        return fallback
    return analysis.dish_name.strip()[:TITLE_MAX] or fallback


@router.post("/conversations", response_model=ConversationSummary)
def create_conversation(
    payload: ConversationCreate, repo: ConversationRepository = Depends(_repo)
) -> ConversationSummary:
    mode = validate_mode(payload.mode)
    record = repo.create(mode=mode)
    return ConversationSummary(
        id=record.id,
        title=record.title,
        mode=mode,
        created_at=record.created_at,
        updated_at=record.updated_at,
        turn_count=0,
    )


@router.get("/conversations", response_model=ConversationPage)
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: ConversationRepository = Depends(_repo),
) -> ConversationPage:
    return repo.list_page(limit=limit, offset=offset)


@router.get("/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(
    conversation_id: str, repo: ConversationRepository = Depends(_repo)
) -> Conversation:
    conversation = repo.get(conversation_id)
    if conversation is None:
        raise NotFoundError("未找到这段对话。", hint="它可能已被删除。")
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, repo: ConversationRepository = Depends(_repo)
) -> None:
    if not repo.delete(conversation_id):
        raise NotFoundError("未找到这段对话。", hint="它可能已被删除。")


@router.post("/conversations/{conversation_id}/turns/stream")
async def create_turn(
    conversation_id: str,
    files: list[UploadFile] | None = File(None, description="本轮新增的照片，可留空"),
    message: str = Form("", description="用户这一轮的文字"),
    profile: str | None = Form(None),
    settings: Settings = Depends(get_settings),
    repo: ConversationRepository = Depends(_repo),
) -> EventSourceResponse:
    conversation = repo.get(conversation_id)
    if conversation is None:
        raise NotFoundError("未找到这段对话。", hint="它可能已被删除。")

    user_text = (message or "").strip()
    if len(user_text) > settings.max_turn_text_chars:
        raise AppError(
            "这条消息太长了。",
            hint=f"请控制在 {settings.max_turn_text_chars} 字以内。",
            code="message_too_long",
            status=400,
        )

    uploads = [f for f in (files or []) if f is not None and (f.filename or "")]
    if not uploads and not user_text:
        raise AppError(
            "这一轮没有内容。",
            hint="请输入一个问题，或附上一张照片。",
            code="empty_turn",
            status=400,
        )

    profile_obj = parse_profile(profile)

    # Validation and preprocessing happen before the stream opens, so a bad
    # image surfaces as an ordinary HTTP error rather than a 200 stream.
    started = time.perf_counter()
    prepared: list[PreparedImage] = []
    if uploads:
        prepared = await prepare_images(uploads, settings)
    prep_ms = int((time.perf_counter() - started) * 1000)

    provider = get_provider(settings)

    async def event_source():
        try:
            async for event, payload in stream_turn(
                conversation,
                images=prepared,
                user_text=user_text,
                profile=profile_obj,
                provider=provider,
                history_limit=settings.max_history_turns,
                prep_ms=prep_ms,
            ):
                if event != "completed":
                    yield frame(event, payload)
                    continue

                # Persist both sides of the turn together, so a failed turn
                # doesn't leave a question with no answer in the history.
                assistant = _persist_turn(
                    conversation.id,
                    user_text=user_text,
                    prepared=prepared,
                    assistant_text=payload["assistant_text"],
                    analysis_payload=payload["analysis"],
                    profile_used=payload["profile_used"],
                    is_first_turn=not conversation.messages,
                )
                if assistant is None:
                    yield frame(
                        "error",
                        {
                            "code": "storage_error",
                            "message": "这一轮没能保存下来。",
                            "hint": "请重试一次。",
                        },
                    )
                    continue

                yield frame("result", assistant.model_dump(mode="json"))

        except AppError as exc:
            logger.warning("[%s] 会话轮次失败: %s", exc.code, exc.message)
            yield frame(
                "error", {"code": exc.code, "message": exc.message, "hint": exc.hint}
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("会话轮次出现未处理异常")
            yield frame(
                "error",
                {
                    "code": "internal_error",
                    "message": "这一轮出现了意外错误。",
                    "hint": "请重试一次。",
                },
            )

    return EventSourceResponse(event_source(), ping=SSE_PING_SECONDS)


def _persist_turn(
    conversation_id: str,
    *,
    user_text: str,
    prepared: list[PreparedImage],
    assistant_text: str,
    analysis_payload: dict[str, Any] | None,
    profile_used: bool,
    is_first_turn: bool,
):
    """Store the user message and the reply. Returns the stored reply.

    Uses its own session because the generator outlives the request-scoped
    dependency.
    """
    db = SessionLocal()
    try:
        repo = ConversationRepository(db)

        # Metadata only — the bytes are already gone by the time we store this.
        images = [
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

        seq = repo.next_seq(conversation_id)
        repo.append_message(
            conversation_id,
            role="user",
            text=user_text,
            seq=seq,
            images=images,
        )

        analysis = (
            AnalysisResult.model_validate(analysis_payload) if analysis_payload else None
        )
        assistant = repo.append_message(
            conversation_id,
            role="assistant",
            text=assistant_text,
            seq=seq + 1,
            analysis=analysis,
            profile_used=profile_used,
        )

        if is_first_turn:
            repo.rename(conversation_id, _title_from(analysis, "新的对话"))

        return assistant
    except Exception:
        logger.exception("保存会话轮次失败")
        db.rollback()
        return None
    finally:
        db.close()
