"""The provider contract.

Providers are pure transport: they receive prompts and an image, return text,
and record what the call cost into ``request.metrics``. Prompt policy lives in
prompt_service, parsing lives in parser, so adding a new vendor (or a second
model to vote with) means adding one class here and nothing else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from app.schemas import AnalysisMode
from app.services.image_service import PreparedImage


@dataclass
class TokenUsage:
    """Token counts as reported by the vendor, when it reports them at all."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class CallMetrics:
    """Where the time went inside one model call, in milliseconds.

    Providers fill this in as they go; the caller turns it into a log line.
    Kept on the request object so provider signatures stay simple.
    """

    #: Call start until response headers arrived — i.e. connect + upload + prefill.
    request_ms: int = 0
    #: Call start until the first content token. Streaming only.
    first_token_ms: int | None = None
    #: First content token until the stream ended. Streaming only.
    generation_ms: int = 0
    usage: TokenUsage | None = None
    #: Characters of reasoning/thinking output the vendor sent. Non-zero is
    #: proof that thinking mode is active — a far more reliable signal than
    #: inferring it from token counts.
    reasoning_chars: int = 0


@dataclass
class ChatTurn:
    """One earlier message in a conversation, replayed to the model.

    Text only: earlier turns' images are gone by design, and a turn that had
    them says so in its text instead.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass
class VisionRequest:
    #: The images for *this* turn. In a conversation, earlier turns' images are
    #: never re-sent — they no longer exist.
    images: list[PreparedImage]
    system_prompt: str
    user_prompt: str
    mode: AnalysisMode
    #: Earlier turns, oldest first. Empty for a single-shot analysis.
    history: list[ChatTurn] = field(default_factory=list)
    metrics: CallMetrics = field(default_factory=CallMetrics)


@runtime_checkable
class VisionProvider(Protocol):
    #: Short identifier surfaced to the client and stored with each result.
    name: str

    async def analyze(self, request: VisionRequest) -> str:
        """Return the model's full raw response text."""
        ...

    def astream(self, request: VisionRequest) -> AsyncIterator[str]:
        """Yield raw response text incrementally.

        Yields text fragments, not parsed structures — the caller accumulates
        them and feeds the result to the parser.
        """
        ...
