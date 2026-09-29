"""Meal-overall tests.

This is the feature closest to becoming a judgement, so the tests below pin
down both the shape (no score anywhere) and the prompt rules that keep a
dimension description from drifting into a grade or a lecture.
"""

from __future__ import annotations

import json

import pytest

from app.schemas import (
    ASPECT_MAX,
    ASPECT_LABEL_CHARS,
    ASPECT_NOTE_CHARS,
    OVERALL_SUMMARY_CHARS,
    AnalysisResult,
    MealAnalysis,
    MealAspect,
    MealOverall,
    Nutrition,
)
from app.services.analysis_service import _from_meal
from app.services.image_service import PreparedImage
from app.services.llm.mock import _PAYLOAD_DETAILED, _PAYLOAD_QUICK
from app.services.parser import parse_model_output
from app.services.prompt_service import build_system_prompt


def sample_overall() -> MealOverall:
    return MealOverall(
        summary="以蛋白质为主，配菜偏少。",
        aspects=[
            MealAspect(label="蔬菜", level="偏少", note="只有番茄，没有绿叶菜。"),
            MealAspect(label="蛋白质", level="偏多", note="鸡蛋是主要来源。"),
        ],
    )


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_aspect_fields_are_trimmed_and_capped():
    aspect = MealAspect(label="  " + "蔬" * 40, level="  偏少  ", note="备" * 300)
    assert len(aspect.label) == ASPECT_LABEL_CHARS
    assert aspect.level == "偏少"
    assert len(aspect.note) == ASPECT_NOTE_CHARS


def test_blank_level_becomes_none():
    assert MealAspect(label="烹调方式", level="  ").level is None
    assert MealAspect(label="烹调方式").level is None


def test_summary_is_capped():
    assert len(MealOverall(summary="长" * 500).summary) == OVERALL_SUMMARY_CHARS


def test_aspect_count_is_capped():
    overall = MealOverall(aspects=[{"label": f"维度{i}"} for i in range(20)])
    assert len(overall.aspects) == ASPECT_MAX


def test_unusable_aspect_entries_are_dropped_not_fatal():
    """A malformed entry shouldn't sink the whole result."""
    overall = MealOverall(aspects=[{"label": "蔬菜"}, "nonsense", 42, None])
    assert [a.label for a in overall.aspects] == ["蔬菜"]


def test_empty_detection():
    assert MealOverall().is_empty
    assert MealOverall(aspects=[{"label": "蔬菜"}]).is_empty is False
    assert MealOverall(summary="一句话").is_empty is False


def test_schema_has_no_score_like_field():
    """The guard rail: there is nowhere to put a grade."""
    fields = set(MealAspect.model_fields) | set(MealOverall.model_fields)
    forbidden = {"score", "grade", "rating", "stars", "rank", "health_score", "level_score"}
    assert not (fields & forbidden)


# --------------------------------------------------------------------------
# Compatibility
# --------------------------------------------------------------------------


def test_result_defaults_to_no_overall():
    result = AnalysisResult(id="a", dish_name="x", confidence=0.5)
    assert result.overall is None
    assert result.edited is False


def test_payload_without_overall_still_parses():
    """Records written before this feature must keep loading."""
    payload = {"dish_name": "番茄炒蛋", "confidence": 0.8, "advice": "还好"}
    outcome = parse_model_output(json.dumps(payload, ensure_ascii=False))
    assert outcome.analysis is not None
    assert outcome.analysis.overall.is_empty


def test_empty_overall_is_stored_as_none():
    meal = MealAnalysis(dish_name="番茄炒蛋", confidence=0.8)
    result = _from_meal(
        meal,
        mode="quick",
        prepared=[PreparedImage(data=b"x", mime="image/jpeg", width=10, height=10)],
        provider_name="mock",
        degraded=False,
    )
    assert result.overall is None


def test_populated_overall_survives_into_the_result():
    meal = MealAnalysis(
        dish_name="番茄炒蛋",
        confidence=0.8,
        nutrition=Nutrition(calories_kcal=285, basis="按约 300g 折算"),
        overall=sample_overall(),
    )
    result = _from_meal(
        meal,
        mode="quick",
        prepared=[PreparedImage(data=b"x", mime="image/jpeg", width=10, height=10)],
        provider_name="mock",
        degraded=False,
    )
    assert result.overall is not None
    assert [a.label for a in result.overall.aspects] == ["蔬菜", "蛋白质"]


# --------------------------------------------------------------------------
# Prompt rules — the part that keeps this descriptive
# --------------------------------------------------------------------------


def test_prompt_asks_for_the_overall_field():
    prompt = build_system_prompt("detailed")
    assert '"overall"' in prompt
    assert '"aspects"' in prompt


def test_overall_is_requested_after_nutrition():
    """The model should have worked out the composition before characterising
    the meal."""
    prompt = build_system_prompt("detailed")
    assert prompt.index('"nutrition"') < prompt.index('"overall"')
    assert prompt.index('"overall"') < prompt.index('"additional_dishes"')


def test_prompt_forbids_scores_and_quality_words():
    prompt = build_system_prompt("quick")
    for term in ("评分", "等级", "星级", "排名", "不健康", "推荐"):
        assert term in prompt, f"提示词必须点名禁止「{term}」"


def test_prompt_forbids_preaching_from_the_level():
    prompt = build_system_prompt("quick")
    assert "说教" in prompt
    assert "你应该多吃" in prompt


def test_prompt_forbids_characterising_the_person():
    prompt = build_system_prompt("quick")
    assert "对用户的评价" in prompt


def test_prompt_limits_level_to_quantity_words():
    prompt = build_system_prompt("quick")
    for word in ("偏少", "适中", "偏多"):
        assert word in prompt


# --------------------------------------------------------------------------
# Mock
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [_PAYLOAD_QUICK, _PAYLOAD_DETAILED])
def test_mock_payload_carries_an_overall(payload):
    assert "overall" in payload
    assert payload["overall"]["aspects"]


@pytest.mark.parametrize("payload", [_PAYLOAD_QUICK, _PAYLOAD_DETAILED])
def test_mock_overall_parses_into_the_schema(payload):
    outcome = parse_model_output(json.dumps(payload, ensure_ascii=False))
    assert outcome.analysis is not None
    overall = outcome.analysis.overall
    assert not overall.is_empty
    assert all(a.label for a in overall.aspects)
