"""Parser tests.

Real model output is messy: fenced, wrapped in prose, trailing commas, smart
quotes. The parser's job is to recover what it can and degrade honestly when it
cannot — never to raise and never to silently invent values.
"""

from __future__ import annotations

import json

from app.services.parser import (
    PartialFieldEmitter,
    extract_json_object,
    extract_partial_advice,
    extract_partial_string,
    parse_model_output,
)

VALID = {
    "dish_name": "番茄炒蛋",
    "confidence": 0.8,
    "advice": "搭配一份青菜会更均衡。",
    "nutrition": {"calories_kcal": 280, "basis": "按约 300g 折算"},
}


def test_plain_json_object_parses():
    outcome = parse_model_output(json.dumps(VALID, ensure_ascii=False))
    assert outcome.analysis is not None
    assert outcome.analysis.dish_name == "番茄炒蛋"
    assert outcome.degraded is False


def test_json_wrapped_in_code_fence_parses():
    text = f"```json\n{json.dumps(VALID, ensure_ascii=False)}\n```"
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.dish_name == "番茄炒蛋"


def test_json_embedded_in_prose_parses():
    text = f"好的，这是我的分析结果：\n{json.dumps(VALID, ensure_ascii=False)}\n希望有帮助。"
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.confidence == 0.8


def test_trailing_comma_is_repaired():
    text = '{"dish_name": "炒饭", "confidence": 0.7, "advice": "还好",}'
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.dish_name == "炒饭"


def test_smart_quotes_are_repaired():
    text = "{“dish_name”: “炒饭”, “confidence”: 0.7, “advice”: “少油一点”}"
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.dish_name == "炒饭"


def test_percentage_confidence_in_json_is_normalised():
    text = json.dumps({**VALID, "confidence": "82%"}, ensure_ascii=False)
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.confidence == 0.82


def test_nested_braces_inside_strings_do_not_confuse_extraction():
    payload = {**VALID, "advice": "用 {花括号} 测试一下 } 嵌套"}
    text = f"前缀 {json.dumps(payload, ensure_ascii=False)} 后缀"
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert "{花括号}" in outcome.analysis.advice


def test_missing_dish_name_is_defaulted_and_flagged_degraded():
    text = json.dumps({"confidence": 0.5, "advice": "看不清"}, ensure_ascii=False)
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.dish_name == "无法确定菜品"
    assert outcome.degraded is True


def test_unparseable_text_degrades_and_keeps_the_original():
    raw = "抱歉，我无法从这张图片中识别出具体的食物。"
    outcome = parse_model_output(raw)
    assert outcome.analysis is None
    assert outcome.degraded is True
    # The model's own words are preserved rather than discarded.
    assert outcome.raw_text == raw
    assert outcome.reasons


def test_empty_response_degrades_cleanly():
    outcome = parse_model_output("")
    assert outcome.analysis is None
    assert outcome.degraded is True


def test_unknown_nutrients_stay_null_rather_than_zero():
    text = json.dumps(
        {**VALID, "nutrition": {"calories_kcal": None, "basis": "无法估算"}},
        ensure_ascii=False,
    )
    outcome = parse_model_output(text)
    assert outcome.analysis is not None
    assert outcome.analysis.nutrition.calories_kcal is None
    assert outcome.analysis.nutrition.protein_g is None


def test_extract_json_object_returns_none_for_prose_only():
    assert extract_json_object("这里没有任何 JSON") is None


# --------------------------------------------------------------------------
# Partial advice extraction — drives the SSE long-reply streaming
# --------------------------------------------------------------------------


def test_partial_advice_extracted_from_complete_json():
    text = json.dumps(VALID, ensure_ascii=False)
    assert extract_partial_advice(text) == "搭配一份青菜会更均衡。"


def test_partial_advice_grows_as_more_text_arrives():
    full = json.dumps(VALID, ensure_ascii=False)
    cut = full.index('"advice"') + len('"advice": "') + 4
    assert extract_partial_advice(full[:cut]) == "搭配一份"


def test_partial_advice_decodes_escapes():
    text = '{"advice": "第一行\\n第二行\\t制表"}'
    assert extract_partial_advice(text) == "第一行\n第二行\t制表"


def test_partial_advice_handles_escaped_quotes():
    text = '{"advice": "他说\\"好吃\\"然后走了"}'
    assert extract_partial_advice(text) == '他说"好吃"然后走了'


def test_partial_advice_holds_back_incomplete_escape():
    """A trailing backslash may be half of an escape; don't emit it yet."""
    text = '{"advice": "第一行\\'
    assert extract_partial_advice(text) == "第一行"


def test_partial_advice_holds_back_incomplete_unicode_escape():
    text = '{"advice": "\\u4e'
    assert extract_partial_advice(text) == ""


def test_partial_advice_decodes_unicode_escape():
    text = '{"advice": "\\u4e2d\\u6587"}'
    assert extract_partial_advice(text) == "中文"


def test_partial_advice_empty_before_advice_key_arrives():
    assert extract_partial_advice('{"dish_name": "番茄') == ""


def test_partial_advice_stops_at_closing_quote():
    text = '{"advice": "内容", "risk_notes": ["不该出现"]}'
    assert extract_partial_advice(text) == "内容"


# --------------------------------------------------------------------------
# extract_partial_string — generalised beyond advice
# --------------------------------------------------------------------------


def test_partial_string_extracts_any_field():
    text = '{"dish_name": "番茄炒蛋", "advice": "建议"}'
    assert extract_partial_string(text, "dish_name") == "番茄炒蛋"
    assert extract_partial_string(text, "advice") == "建议"


def test_partial_string_returns_empty_for_absent_field():
    assert extract_partial_string('{"advice": "x"}', "dish_name") == ""


def test_partial_string_does_not_match_a_longer_key():
    """`dish_name_alternatives` must not be mistaken for `dish_name`."""
    text = '{"dish_name_alternatives": ["西红柿炒鸡蛋"]}'
    assert extract_partial_string(text, "dish_name") == ""


def test_partial_string_handles_a_partially_written_value():
    text = '{"dish_name": "番茄炒'
    assert extract_partial_string(text, "dish_name") == "番茄炒"


# --------------------------------------------------------------------------
# PartialFieldEmitter — per-field incremental deltas
# --------------------------------------------------------------------------


def test_emitter_reports_only_new_text_per_field():
    emitter = PartialFieldEmitter(("dish_name", "advice"))

    first = emitter.feed('{"dish_name": "番茄')
    assert first == [("dish_name", "番茄")]

    # Nothing new for either field yet.
    assert emitter.feed('{"dish_name": "番茄') == []

    second = emitter.feed('{"dish_name": "番茄炒蛋", "advice": "少')
    assert second == [("dish_name", "炒蛋"), ("advice", "少")]


def test_emitter_tracks_fields_independently():
    emitter = PartialFieldEmitter(("dish_name", "advice"))
    emitter.feed('{"dish_name": "番茄炒蛋", "advice": "第一段')
    deltas = emitter.feed('{"dish_name": "番茄炒蛋", "advice": "第一段第二段')
    assert deltas == [("advice", "第二段")]


def test_emitter_emits_nothing_before_a_field_starts():
    emitter = PartialFieldEmitter(("dish_name", "advice"))
    assert emitter.feed('{"conf') == []
