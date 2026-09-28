"""Helpers shared by the analyze and conversation routes."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import ValidationError

from app.core.errors import InvalidModeError, InvalidProfileError
from app.schemas import AnalysisMode, UserProfile

#: Comment-frame interval, so proxies don't drop an idle SSE connection.
SSE_PING_SECONDS = 15

VALID_MODES = ("quick", "detailed")


def validate_mode(mode: str) -> AnalysisMode:
    if mode not in VALID_MODES:
        raise InvalidModeError()
    return cast(AnalysisMode, mode)


def frame(event: str, payload: dict[str, Any]) -> dict[str, str]:
    """Build one SSE frame for sse-starlette."""
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def parse_profile(raw: str | None) -> UserProfile | None:
    """Validate the profile the frontend sent.

    The profile arrives per request and is used for the prompt only — it is
    never persisted, and must never be logged. The errors below are therefore
    deliberately generic: they must not echo the payload back.
    """
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise InvalidProfileError() from exc
    if not isinstance(payload, dict):
        raise InvalidProfileError()
    try:
        return UserProfile.model_validate(payload)
    except ValidationError as exc:
        raise InvalidProfileError(
            "画像里有内容不符合要求。",
            hint="请检查过敏原、忌口等条目是否过长或过多，然后重新保存。",
        ) from exc
