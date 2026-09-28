"""OpenAI-compatible chat-completions provider.

Works with any vendor that exposes the ``/chat/completions`` shape with image
support: DashScope's compatible mode (Qwen-VL), OpenAI itself, and most
self-hosted gateways. Swapping vendors is a base_url + model change in .env.

The API key never leaves this module's headers, and is never logged.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.core.errors import LLMError, LLMNotConfiguredError, LLMTimeoutError
from app.services.llm.base import CallMetrics, TokenUsage, VisionRequest

logger = logging.getLogger(__name__)

# Where vendors put thinking output when it isn't in `content`.
_REASONING_KEYS = ("reasoning_content", "reasoning")


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _parse_usage(raw: Any) -> TokenUsage | None:
    if not isinstance(raw, dict):
        return None
    return TokenUsage(
        prompt_tokens=raw.get("prompt_tokens"),
        completion_tokens=raw.get("completion_tokens"),
        total_tokens=raw.get("total_tokens"),
    )


def _reasoning_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _REASONING_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_configured:
            raise LLMNotConfiguredError()
        self.settings = settings
        self.endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"

    # ---- request construction ----

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def _body(self, request: VisionRequest, *, stream: bool) -> dict[str, Any]:
        # One image_url part per image. A text-only turn (a conversation
        # follow-up with no new photo) simply omits the parts.
        content: list[dict[str, Any]] = [{"type": "text", "text": request.user_prompt}]
        for image in request.images:
            encoded = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.mime};base64,{encoded}"},
                }
            )

        # Earlier turns go in as real user/assistant messages so the model gets
        # the conversational structure, not a flattened transcript.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt}
        ]
        messages.extend(
            {"role": turn.role, "content": turn.text} for turn in request.history
        )
        messages.append({"role": "user", "content": content})

        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "max_tokens": self.settings.llm_max_tokens,
            "temperature": self.settings.llm_temperature,
            "stream": stream,
        }

        if self.settings.llm_json_mode:
            body["response_format"] = {"type": "json_object"}

        # Thinking mode is sent explicitly in BOTH directions. Omitting the
        # field means "use the vendor default", and several Qwen models default
        # to thinking ON — which is the slow path we are trying to avoid. An
        # empty LLM_THINKING_PARAM means "never mention the field", for vendors
        # that reject unknown keys.
        thinking_param = self.settings.llm_thinking_param.strip()
        if thinking_param:
            body[thinking_param] = self.settings.llm_enable_thinking

        # Ask for token counts at the end of a stream. The counts are what tell
        # us whether thinking mode is secretly on, so they are worth the extra
        # field; set LLM_REQUEST_USAGE=false for vendors that reject it.
        if stream and self.settings.llm_request_usage:
            body["stream_options"] = {"include_usage": True}

        return body

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.settings.llm_timeout_seconds, connect=15.0)

    # ---- error translation ----

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        status = response.status_code
        # Body may carry a vendor error message; it never contains our key.
        try:
            detail = response.json()
        except Exception:
            detail = None

        vendor_message = ""
        if isinstance(detail, dict):
            error = detail.get("error")
            if isinstance(error, dict):
                vendor_message = str(error.get("message") or "")
            elif isinstance(error, str):
                vendor_message = error

        lowered = vendor_message.lower()

        if status in (401, 403):
            logger.warning("模型服务拒绝了鉴权（HTTP %s）", status)
            raise LLMError(
                "模型服务拒绝了这次请求，通常是 API Key 无效或没有该模型的权限。",
                hint="请检查 backend/.env 中的 LLM_API_KEY 与 LLM_MODEL 是否正确。",
                code="llm_unauthorized",
                status=502,
            )
        if status == 429:
            raise LLMError(
                "模型服务当前请求过多，已被限流。",
                hint="请稍等片刻再试，或降低使用频率。",
                code="llm_rate_limited",
                status=503,
            )
        if status == 400 and "response_format" in lowered:
            raise LLMError(
                "当前模型不支持强制 JSON 输出。",
                hint="请在 backend/.env 中设置 LLM_JSON_MODE=false 后重启后端。",
                code="llm_json_mode_unsupported",
                status=502,
            )
        if status == 400 and ("stream_options" in lowered or "enable_thinking" in lowered):
            raise LLMError(
                "当前模型不接受请求中的扩展参数。",
                hint=(
                    "请在 backend/.env 中设置 LLM_REQUEST_USAGE=false；"
                    "若仍失败，再把 LLM_THINKING_PARAM 留空。"
                ),
                code="llm_unsupported_param",
                status=502,
            )

        logger.warning("模型服务返回 HTTP %s: %s", status, vendor_message[:300])
        raise LLMError(
            f"模型服务返回了错误（HTTP {status}）。",
            hint="请稍后重试；如果持续失败，请检查 backend/.env 中的模型配置。",
        )

    # ---- calls ----

    async def analyze(self, request: VisionRequest) -> str:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    self.endpoint,
                    headers=self._headers(),
                    json=self._body(request, stream=False),
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning("调用模型服务失败: %s", type(exc).__name__)
            raise LLMError(
                "无法连接到模型服务。",
                hint="请检查网络，以及 backend/.env 中的 LLM_BASE_URL 是否正确。",
                code="llm_unreachable",
                status=502,
            ) from exc

        request.metrics.request_ms = _ms_since(started)
        self._raise_for_status(response)

        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("模型响应结构不符合预期")
            raise LLMError(
                "模型返回的内容无法读取。",
                hint="请重试；如果持续失败，可能是当前模型与 OpenAI 兼容接口不完全一致。",
                code="llm_bad_response",
                status=502,
            ) from exc

        request.metrics.usage = _parse_usage(payload.get("usage"))
        request.metrics.reasoning_chars = len(_reasoning_text(message))
        return str(message.get("content") or "")

    async def astream(self, request: VisionRequest) -> AsyncIterator[str]:
        started = time.perf_counter()
        first_token_at: float | None = None
        reasoning_seen = 0

        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers=self._headers(),
                    json=self._body(request, stream=True),
                ) as response:
                    request.metrics.request_ms = _ms_since(started)

                    # Errors arrive before the stream starts; surface them with
                    # the same translation as the non-streaming path.
                    if not response.is_success:
                        await response.aread()
                        self._raise_for_status(response)

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue

                        # The usage-bearing chunk usually has an empty choices
                        # array, so read usage before filtering choices out.
                        usage = _parse_usage(chunk.get("usage"))
                        if usage is not None:
                            request.metrics.usage = usage

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        reasoning_seen += len(_reasoning_text(delta))

                        piece = delta.get("content")
                        if not piece:
                            continue

                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                            request.metrics.first_token_ms = _ms_since(started)
                        yield str(piece)

        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning("流式调用模型服务失败: %s", type(exc).__name__)
            raise LLMError(
                "无法连接到模型服务。",
                hint="请检查网络，以及 backend/.env 中的 LLM_BASE_URL 是否正确。",
                code="llm_unreachable",
                status=502,
            ) from exc
        finally:
            request.metrics.reasoning_chars = reasoning_seen
            if first_token_at is not None:
                request.metrics.generation_ms = int(
                    (time.perf_counter() - first_token_at) * 1000
                )
