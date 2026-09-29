"""Turn whatever the model wrote into a validated structure, or degrade.

Models wrap JSON in prose, in code fences, with trailing commas, with smart
quotes. The contract here is that the user always ends up with *something*:
the happy path yields a validated ``MealAnalysis``; anything unrecoverable is
reported as ``degraded`` with the raw text preserved rather than thrown away.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.schemas import MealAnalysis, MealOverall

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f"}


@dataclass
class ParseOutcome:
    analysis: MealAnalysis | None
    degraded: bool
    raw_text: str = ""
    reasons: list[str] = field(default_factory=list)


def _balanced_object(text: str) -> str | None:
    """Slice out the first complete ``{...}``, ignoring braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _candidates(text: str) -> list[str]:
    """Progressively more aggressive slices of the response worth trying."""
    out: list[str] = []
    stripped = text.strip()
    if stripped:
        out.append(stripped)

    fenced = _FENCE.search(text)
    if fenced:
        out.append(fenced.group(1).strip())

    balanced = _balanced_object(text)
    if balanced:
        out.append(balanced)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _loads_with_repair(candidate: str) -> dict | None:
    """Try the raw slice, then repair the usual suspects in increasing order."""
    attempts = [
        candidate,
        _TRAILING_COMMA.sub(r"\1", candidate),
        _TRAILING_COMMA.sub(r"\1", candidate).translate(_SMART_QUOTES),
    ]
    for attempt in attempts:
        try:
            parsed = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def extract_json_object(text: str) -> dict | None:
    for candidate in _candidates(text):
        parsed = _loads_with_repair(candidate)
        if parsed is not None:
            return parsed
    return None


def parse_model_output(text: str) -> ParseOutcome:
    """Parse and validate the model's reply into a MealAnalysis."""
    if not text or not text.strip():
        return ParseOutcome(
            analysis=None, degraded=True, raw_text="", reasons=["模型返回了空内容"]
        )

    payload = extract_json_object(text)
    if payload is None:
        logger.warning("模型输出无法解析为 JSON，将降级为纯文本展示")
        return ParseOutcome(
            analysis=None,
            degraded=True,
            raw_text=text.strip(),
            reasons=["模型输出不是有效的 JSON"],
        )

    # A missing dish_name is the one field we can't invent a value for.
    if not str(payload.get("dish_name") or "").strip():
        payload["dish_name"] = "无法确定菜品"
        reasons = ["模型未给出菜品名称"]
    else:
        reasons = []

    try:
        analysis = MealAnalysis.model_validate(payload)
    except ValidationError as exc:
        # Validation is lenient by design (every field has a default), so
        # getting here means the shape is badly wrong. Keep what we can.
        logger.warning("模型输出未通过校验: %s", exc.error_count())
        salvaged = _salvage(payload, text)
        if salvaged is not None:
            return ParseOutcome(
                analysis=salvaged,
                degraded=True,
                raw_text=text.strip(),
                reasons=["部分字段格式不正确，已尽力保留可用内容"],
            )
        return ParseOutcome(
            analysis=None,
            degraded=True,
            raw_text=text.strip(),
            reasons=["模型输出结构不正确"],
        )

    return ParseOutcome(
        analysis=analysis, degraded=bool(reasons), raw_text=text.strip(), reasons=reasons
    )


def _salvage(payload: dict, raw_text: str) -> MealAnalysis | None:
    """Keep the pieces that do validate and drop the rest."""
    try:
        return MealAnalysis.model_construct(
            dish_name=str(payload.get("dish_name") or "无法确定菜品"),
            dish_name_alternatives=[],
            confidence=0.3,
            confidence_reason=None,
            ingredients=[],
            portion_estimate=None,
            additional_dishes=[],
            overall=MealOverall(),
            advice=raw_text.strip()[:4000],
            risk_notes=[],
            uncertainty_notes=["模型返回的结构不完整，建议重新拍摄后再试一次。"],
        )
    except Exception:
        return None


def extract_partial_string(buffer: str, key: str) -> str:
    """Pull one string field out of a partially-streamed JSON object.

    Streaming raw JSON at the user would be unreadable, so the SSE layer feeds
    accumulating model output through this and emits only the field's text as it
    grows. Incomplete escapes at the tail are held back until more arrives.

    Works on ``dish_name`` as well as ``advice``: the model writes fields in the
    order we ask for, so the dish name is known long before the JSON closes, and
    showing it early lets the progress view name the dish instead of showing an
    empty skeleton.
    """
    match = re.compile(rf'"{re.escape(key)}"\s*:\s*"').search(buffer)
    if not match:
        return ""

    chars: list[str] = []
    index = match.end()

    while index < len(buffer):
        char = buffer[index]

        if char == "\\":
            if index + 1 >= len(buffer):
                break  # escape split across chunks; wait for the rest
            nxt = buffer[index + 1]
            if nxt == "u":
                hex_digits = buffer[index + 2 : index + 6]
                if len(hex_digits) < 4:
                    break
                try:
                    chars.append(chr(int(hex_digits, 16)))
                except ValueError:
                    pass
                index += 6
                continue
            chars.append(_ESCAPES.get(nxt, nxt))
            index += 2
            continue

        if char == '"':
            break  # closing quote reached

        chars.append(char)
        index += 1

    return "".join(chars)


def extract_partial_advice(buffer: str) -> str:
    return extract_partial_string(buffer, "advice")


class PartialFieldEmitter:
    """Tracks what has already been sent for each streamed field.

    Model output grows monotonically, so each poll re-extracts the whole field;
    this keeps only the new tail per field, and keeps that bookkeeping out of
    both streaming services.
    """

    def __init__(self, fields: tuple[str, ...]) -> None:
        self._fields = fields
        self._sent: dict[str, int] = {field: 0 for field in fields}

    def feed(self, buffer: str) -> list[tuple[str, str]]:
        """Return ``(field, new_text)`` for anything that grew since last time."""
        deltas: list[tuple[str, str]] = []
        for field in self._fields:
            value = extract_partial_string(buffer, field)
            already = self._sent[field]
            if len(value) > already:
                deltas.append((field, value[already:]))
                self._sent[field] = len(value)
        return deltas
