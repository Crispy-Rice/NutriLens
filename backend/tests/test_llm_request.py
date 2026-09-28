"""Request-construction tests.

The thinking-mode flag is the highest-leverage setting in the app: omitting it
means "use the vendor default", and several Qwen models default to thinking ON,
which makes识别 an order of magnitude slower. These tests pin down that the
field is sent explicitly in both directions.
"""

from __future__ import annotations

from app.config import Settings
from app.schemas import AnalysisMode
from app.services.image_service import PreparedImage
from app.services.llm.base import VisionRequest
from app.services.llm.openai_compat import OpenAICompatProvider

TEST_KEY = "sk-test-not-a-real-key"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "llm_api_key": TEST_KEY,
        "llm_provider": "openai_compat",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_request(mode: AnalysisMode = "quick", image_count: int = 1) -> VisionRequest:
    images = [
        PreparedImage(
            data=b"fake-jpeg-bytes", mime="image/jpeg", width=10, height=10, index=i
        )
        for i in range(image_count)
    ]
    return VisionRequest(
        images=images, system_prompt="sys", user_prompt="usr", mode=mode
    )


def build_body(
    settings: Settings, *, stream: bool = False, image_count: int = 1
) -> dict:
    provider = OpenAICompatProvider(settings)
    return provider._body(make_request(image_count=image_count), stream=stream)


# --------------------------------------------------------------------------
# Thinking mode
# --------------------------------------------------------------------------


def test_thinking_flag_is_sent_explicitly_as_false():
    """The regression this whole change exists for.

    Not mentioning the field lets the vendor decide. Sending false is the only
    way to actually turn thinking off on models that default to it.
    """
    body = build_body(make_settings(llm_enable_thinking=False))
    assert "enable_thinking" in body
    assert body["enable_thinking"] is False


def test_thinking_flag_is_true_when_enabled():
    body = build_body(make_settings(llm_enable_thinking=True))
    assert body["enable_thinking"] is True


def test_thinking_param_name_is_configurable():
    body = build_body(
        make_settings(llm_enable_thinking=False, llm_thinking_param="thinking")
    )
    assert body["thinking"] is False
    assert "enable_thinking" not in body


def test_blank_thinking_param_omits_the_field_entirely():
    """Escape hatch for vendors that reject unknown keys."""
    body = build_body(make_settings(llm_thinking_param=""))
    assert "enable_thinking" not in body
    assert "thinking" not in body


def test_blank_thinking_param_is_tolerated_even_with_whitespace():
    body = build_body(make_settings(llm_thinking_param="   "))
    assert "enable_thinking" not in body


# --------------------------------------------------------------------------
# Usage reporting
# --------------------------------------------------------------------------


def test_stream_options_requested_when_usage_enabled():
    body = build_body(make_settings(llm_request_usage=True), stream=True)
    assert body["stream_options"] == {"include_usage": True}


def test_stream_options_omitted_when_usage_disabled():
    body = build_body(make_settings(llm_request_usage=False), stream=True)
    assert "stream_options" not in body


def test_stream_options_not_sent_on_non_streaming_calls():
    """usage arrives by default without streaming; the field is stream-only."""
    body = build_body(make_settings(llm_request_usage=True), stream=False)
    assert "stream_options" not in body


# --------------------------------------------------------------------------
# Otherwise-standard request shape
# --------------------------------------------------------------------------


def test_stream_flag_is_reflected():
    assert build_body(make_settings(), stream=True)["stream"] is True
    assert build_body(make_settings(), stream=False)["stream"] is False


def test_json_mode_can_be_disabled():
    assert "response_format" in build_body(make_settings(llm_json_mode=True))
    assert "response_format" not in build_body(make_settings(llm_json_mode=False))


def test_image_is_sent_as_a_data_url_alongside_the_text():
    body = build_body(make_settings())
    content = body["messages"][1]["content"]
    kinds = [part["type"] for part in content]
    assert kinds == ["text", "image_url"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_each_image_gets_its_own_part_in_order():
    body = build_body(make_settings(), image_count=3)
    content = body["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url", "image_url", "image_url"]
    # The text prompt still comes first, once.
    assert content[0]["text"] == "usr"


def test_text_only_turn_sends_no_image_parts():
    """A conversation follow-up has no new photo; the photos are gone."""
    body = build_body(make_settings(), image_count=0)
    content = body["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text"]


def test_system_and_user_prompts_are_carried_through():
    body = build_body(make_settings())
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1]["content"][0]["text"] == "usr"


def test_provider_refuses_to_build_without_a_key():
    import pytest

    from app.core.errors import LLMNotConfiguredError

    with pytest.raises(LLMNotConfiguredError):
        OpenAICompatProvider(make_settings(llm_api_key=""))
