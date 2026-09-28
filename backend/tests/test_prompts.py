"""Prompt guard-rail tests.

These assert that the product's safety constraints are actually stated to the
model. They are not testing model behaviour — they are a tripwire so that a
future edit to the prompt can't quietly drop "don't grade the user's body" or
"don't invent a health score".
"""

from __future__ import annotations

import json

from app.services.llm import mock
from app.services.parser import parse_model_output
from app.services.prompt_service import build_system_prompt, build_user_prompt


def test_prompt_forbids_health_scores():
    text = build_system_prompt("quick")
    assert "健康评分" in text or "评分" in text
    assert "分数" in text


def test_prompt_forbids_judging_the_person():
    text = build_system_prompt("quick")
    for term in ("体型", "体重", "减肥", "节食"):
        assert term in text, f"提示词必须禁止评价用户的{term}"


def test_prompt_forbids_medical_diagnosis():
    text = build_system_prompt("quick")
    assert "诊断" in text


def test_prompt_demands_lower_confidence_when_unsure():
    text = build_system_prompt("quick")
    assert "confidence" in text
    assert "不确定" in text
    # The specific behaviours we rely on for the "please confirm" UI.
    assert "0.6" in text


def test_prompt_requires_nutrition_basis():
    assert "basis" in build_system_prompt("quick")


def test_prompt_requires_null_instead_of_zero_for_unknown_values():
    text = build_system_prompt("quick")
    assert "null" in text
    assert "不要编造" in text


def test_prompt_asks_for_json_only():
    assert "只输出一个 JSON 对象" in build_system_prompt("detailed")


def test_detailed_mode_differs_from_quick_mode():
    quick = build_system_prompt("quick")
    detailed = build_system_prompt("detailed")
    assert quick != detailed
    assert "详细分析" in detailed
    assert "快速识别" in quick


def test_user_prompt_frames_the_note_as_context_not_instruction():
    prompt = build_user_prompt("quick", "这是两人份")
    assert "这是两人份" in prompt
    # Untrusted text must not read as a command to follow.
    assert "不是指令" in prompt


def test_user_prompt_omits_note_when_absent():
    prompt = build_user_prompt("quick", None)
    assert "补充说明" not in prompt
    prompt_blank = build_user_prompt("quick", "   ")
    assert "补充说明" not in prompt_blank


def test_advice_is_requested_before_the_bulky_fields():
    """advice drives the streaming view via partial-advice extraction.

    If it were requested after ingredients and nutrition, the user would see an
    empty streaming panel until most of the JSON had already been generated,
    which makes the whole SSE path pointless.
    """
    text = build_system_prompt("detailed")
    advice_at = text.index('"advice"')
    for later in ('"ingredients"', '"portion_estimate"', '"nutrition"'):
        assert advice_at < text.index(later), f"advice 必须排在 {later} 之前"


def test_prompt_tells_the_model_not_to_restate_estimates_in_advice():
    """Numbers in prose can drift from the nutrition block; keep them in one place."""
    assert "不要复述" in build_system_prompt("detailed")


def test_mock_emits_advice_before_the_bulky_fields():
    for payload in (mock._PAYLOAD_QUICK, mock._PAYLOAD_DETAILED):
        keys = list(payload)
        assert keys.index("advice") < keys.index("ingredients")
        assert keys.index("advice") < keys.index("nutrition")


def test_mock_key_order_tracks_the_prompt_order():
    """The mock ignores the prompt text entirely, so nothing else keeps demo
    mode streaming the way a real call does. If these drift apart, demo mode
    would show advice only at the very end and mask a regression in the real
    streaming path."""
    prompt = build_system_prompt("detailed")
    for payload in (mock._PAYLOAD_QUICK, mock._PAYLOAD_DETAILED):
        keys = list(payload)
        positions = [prompt.index(f'"{key}"') for key in keys]
        assert positions == sorted(positions), f"mock 字段顺序与提示词不一致: {keys}"


def test_user_prompt_mentions_the_image_count_when_multiple():
    prompt = build_user_prompt("quick", None, image_count=3)
    assert "3 张照片" in prompt


def test_user_prompt_omits_the_count_for_a_single_image():
    assert "张照片" not in build_user_prompt("quick", None, image_count=1)


def test_multi_dish_rules_are_stated():
    """The model has to know when to emit additional_dishes, and when not to."""
    text = build_system_prompt("detailed")
    assert "additional_dishes" in text
    # Multi-angle photos of one dish must not become several dishes.
    assert "同一道菜的不同角度" in text
    assert "最多 4 道" in text
    assert "空数组" in text


def test_mock_returns_additional_dishes_for_multi_image():
    from app.services.image_service import PreparedImage
    from app.services.llm.base import VisionRequest
    from app.services.llm.mock import MockProvider

    def request_for(count: int) -> VisionRequest:
        images = [
            PreparedImage(data=b"x", mime="image/jpeg", width=10, height=10, index=i)
            for i in range(count)
        ]
        return VisionRequest(
            images=images, system_prompt="s", user_prompt="u", mode="detailed"
        )

    provider = MockProvider()

    single = parse_model_output(provider._render(request_for(1)))
    assert single.analysis is not None
    assert single.analysis.additional_dishes == []

    multi = parse_model_output(provider._render(request_for(3)))
    assert multi.analysis is not None
    assert len(multi.analysis.additional_dishes) == 1
    assert multi.analysis.additional_dishes[0].dish_name == "米饭"
    assert any("3 张照片" in note for note in multi.analysis.uncertainty_notes)


def test_mock_returns_prose_when_there_are_no_images():
    """A conversation follow-up carries no images, so the reply is chat, not JSON."""
    from app.services.llm.base import VisionRequest
    from app.services.llm.mock import MockProvider

    request = VisionRequest(
        images=[], system_prompt="s", user_prompt="u", mode="quick"
    )
    text = MockProvider()._render(request)

    assert not text.lstrip().startswith("{")
    # The mock has to model the same honesty the prompt demands.
    assert "看不到你之前上传的照片" in text


def test_mock_json_is_parseable_and_complete():
    """The mock must satisfy the same contract the parser validates."""
    for payload in (mock._PAYLOAD_QUICK, mock._PAYLOAD_DETAILED):
        outcome = parse_model_output(json.dumps(payload, ensure_ascii=False))
        assert outcome.analysis is not None
        assert outcome.degraded is False
        assert outcome.analysis.nutrition.basis
