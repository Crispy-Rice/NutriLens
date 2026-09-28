"""Logging with a redaction pass.

The privacy requirement is "backend logs must not contain image content,
base64 blobs, API keys, or user-sensitive data". Rather than trusting every
call site to be careful, we filter at the logging layer so anything that slips
through still gets scrubbed before it reaches a file or the console.
"""

from __future__ import annotations

import logging
import re
import sys

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # Profile fields, by name. The app never logs the profile on purpose, but
    # if one ever leaks into a message — a stray repr, an error payload — this
    # is the backstop. Matches both list and scalar values, quoted or not.
    (
        re.compile(
            r"(?i)[\"']?(allergies|avoidances|preferences|dietary_pattern"
            r"|health_notes|age_band)[\"']?\s*[:=]\s*"
            r"(\[[^\]]*\]|\{[^}]*\}|\"[^\"]*\"|'[^']*'|[^\s,}]+)"
        ),
        r"\1=<REDACTED>",
    ),
    # data:image/jpeg;base64,AAAA....
    (
        re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=%\s]*"),
        "data:image/...;base64,<REDACTED>",
    ),
    # Key-shaped values, caught by shape rather than by label. DashScope,
    # OpenAI and most compatible vendors all issue sk-... credentials, and
    # this fires even when someone logs `key=sk-...` with no useful label.
    (
        re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
        "sk-<REDACTED>",
    ),
    # Must run before the labelled rule below, otherwise that rule matches
    # "Authorization: Bearer" and redacts the word "Bearer" while leaving the
    # actual credential in place.
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
        "Bearer <REDACTED>",
    ),
    # key/token/authorization assignments, quoted or bare
    (
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|authorization|access[_-]?token|auth[_-]?token"
            r"|bearer|secret|password|passwd)"
            r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)"
        ),
        r"\1\2<REDACTED>",
    ),
    # any long base64-ish run: almost certainly an encoded image
    (
        re.compile(r"\b[A-Za-z0-9+/]{200,}={0,2}\b"),
        "<REDACTED-BLOB>",
    ),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_arg(value: object) -> object:
    # Only touch strings. Coercing everything to str breaks %d/%f placeholders
    # and makes logging itself raise.
    return redact(value) if isinstance(value, str) else value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {k: _redact_arg(v) for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(a) for a in record.args)
        return True


def configure_logging(debug: bool = False) -> None:
    stream = sys.stdout
    # Windows consoles default to a legacy codepage, which turns Chinese log
    # messages into mojibake the moment output is redirected to a file.
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # httpx logs every request line; keep it to warnings unless debugging.
    logging.getLogger("httpx").setLevel(logging.DEBUG if debug else logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(RedactionFilter())
