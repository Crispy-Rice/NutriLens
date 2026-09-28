"""Provider selection.

One place decides which implementation serves a request, so adding a second
model (or a voting ensemble across providers) is a change here and nowhere else.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import Settings, get_settings
from app.services.llm.base import VisionProvider
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


@lru_cache
def _build(resolved_provider: str) -> VisionProvider:
    settings = get_settings()
    if resolved_provider == "mock":
        return MockProvider()
    return OpenAICompatProvider(settings)


def get_provider(settings: Settings | None = None) -> VisionProvider:
    settings = settings or get_settings()
    # resolved_provider raises when a real provider was demanded without a key,
    # which is the intended fail-loud behaviour.
    resolved = settings.resolved_provider
    provider = _build(resolved)
    logger.debug("使用识别提供方: %s", provider.name)
    return provider
