"""User profile tests.

Two things matter here beyond parsing: the profile must never reach storage,
and the prompt must state the limits that keep it from turning into a health
assessment. Both are asserted rather than assumed.
"""

from __future__ import annotations

import json

import pytest

from app.api.common import parse_profile as _parse_profile
from app.core.errors import InvalidProfileError
from app.core.logging import redact
from app.db.models import AnalysisRecord
from app.schemas import (
    PROFILE_MAX_HEALTH_NOTES,
    PROFILE_MAX_ITEMS,
    PROFILE_MAX_ITEM_CHARS,
    AgeBand,
    AnalysisResult,
    MealAnalysis,
    Sex,
    UserProfile,
)
from app.services.analysis_service import profile_in_use, _from_meal
from app.services.image_service import PreparedImage
from app.services.prompt_service import build_profile_block, build_system_prompt

SAMPLE_NOTES = "血脂偏高，医生建议少油"


def sample_profile(**overrides: object) -> UserProfile:
    base: dict[str, object] = {
        "allergies": ["花生", "虾"],
        "avoidances": ["香菜"],
        "preferences": ["偏清淡"],
        "dietary_pattern": "素食",
        "age_band": AgeBand.B30_39,
        "sex": Sex.FEMALE,
        "health_notes": SAMPLE_NOTES,
    }
    base.update(overrides)
    return UserProfile(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Parsing and bounds
# --------------------------------------------------------------------------


def test_blank_profile_is_empty():
    assert UserProfile().is_empty
    assert UserProfile(allergies=["  ", ""]).is_empty


def test_non_empty_profile_is_not_empty():
    assert not sample_profile().is_empty


def test_list_items_are_trimmed_and_deduplicated():
    profile = UserProfile(allergies=["  花生 ", "花生", "", "虾"])
    assert profile.allergies == ["花生", "虾"]


def test_comma_separated_string_is_accepted():
    """A simple form may send one string instead of a list."""
    assert UserProfile(avoidances="香菜， 洋葱").avoidances == ["香菜", "洋葱"]


def test_list_length_is_capped():
    profile = UserProfile(allergies=[f"item{i}" for i in range(50)])
    assert len(profile.allergies) == PROFILE_MAX_ITEMS


def test_item_length_is_capped():
    profile = UserProfile(allergies=["x" * 200])
    assert len(profile.allergies[0]) == PROFILE_MAX_ITEM_CHARS


def test_health_notes_are_truncated():
    profile = UserProfile(health_notes="长" * 500)
    assert profile.health_notes is not None
    assert len(profile.health_notes) == PROFILE_MAX_HEALTH_NOTES


def test_blank_scalars_become_none():
    profile = UserProfile(dietary_pattern="   ", health_notes="  ")
    assert profile.dietary_pattern is None
    assert profile.health_notes is None


# --------------------------------------------------------------------------
# Transport: the profile arrives as a JSON form field
# --------------------------------------------------------------------------


def test_profile_field_round_trips():
    raw = json.dumps(sample_profile().model_dump(mode="json"), ensure_ascii=False)
    parsed = _parse_profile(raw)
    assert parsed is not None
    assert parsed.allergies == ["花生", "虾"]
    assert parsed.age_band is AgeBand.B30_39


def test_absent_or_blank_profile_field_is_none():
    assert _parse_profile(None) is None
    assert _parse_profile("") is None
    assert _parse_profile("   ") is None


def test_malformed_profile_json_is_rejected_without_echoing_it():
    with pytest.raises(InvalidProfileError) as exc:
        _parse_profile("{not json at all")
    # The error must not leak the payload back to the user or into a log.
    assert "not json" not in exc.value.message
    assert "not json" not in (exc.value.hint or "")


def test_non_object_profile_is_rejected():
    with pytest.raises(InvalidProfileError):
        _parse_profile('["花生"]')


def test_unknown_enum_value_is_rejected():
    with pytest.raises(InvalidProfileError):
        _parse_profile(json.dumps({"age_band": "30-39 岁"}))


# --------------------------------------------------------------------------
# Prompt boundaries — the reason this feature needed care
# --------------------------------------------------------------------------


def test_profile_block_is_omitted_when_empty():
    assert build_profile_block(UserProfile()) == ""


def test_profile_block_carries_the_values():
    block = build_profile_block(sample_profile())
    assert "花生" in block and "虾" in block
    assert "素食" in block
    assert SAMPLE_NOTES in block


def test_profile_block_forbids_body_metrics():
    block = build_profile_block(sample_profile())
    for term in ("BMI", "体重", "体脂", "基础代谢"):
        assert term in block, f"画像提示词必须点名禁止 {term}"


def test_profile_block_forbids_judging_and_diagnosing():
    block = build_profile_block(sample_profile())
    assert "体型" in block
    assert "诊断" in block
    assert "治疗性" in block


def test_profile_block_forbids_restating_health_information():
    assert "复述" in build_profile_block(sample_profile())


def test_profile_block_prioritises_allergens_in_risk_notes():
    block = build_profile_block(sample_profile())
    assert "过敏原" in block
    assert "risk_notes" in block


def test_system_prompt_includes_the_profile_block():
    prompt = build_system_prompt("detailed", sample_profile())
    assert SAMPLE_NOTES in prompt
    # And the safety rules travel with it.
    assert "BMI" in prompt


def test_system_prompt_unchanged_without_a_profile():
    assert "BMI" not in build_system_prompt("detailed")
    assert build_system_prompt("quick") == build_system_prompt("quick", None)


# --------------------------------------------------------------------------
# The profile must never be persisted
# --------------------------------------------------------------------------


def test_stored_record_has_no_profile_columns():
    columns = {column.name for column in AnalysisRecord.__table__.columns}
    forbidden = {
        "profile",
        "user_profile",
        "allergies",
        "avoidances",
        "preferences",
        "dietary_pattern",
        "health_notes",
        "age_band",
        "sex",
    }
    assert not (columns & forbidden)


def test_serialised_result_contains_no_profile_contents():
    """The result records only that a profile was used, never what was in it."""
    meal = MealAnalysis(dish_name="番茄炒蛋", confidence=0.8, advice="搭配青菜更均衡。")
    profile = sample_profile()

    result = _from_meal(
        meal,
        mode="quick",
        prepared=[PreparedImage(data=b"x", mime="image/jpeg", width=10, height=10)],
        provider_name="mock",
        degraded=False,
        profile_used=profile_in_use(profile),
    )

    payload = result.model_dump_json()
    assert result.profile_used is True
    for secret in [*profile.allergies, *profile.avoidances, SAMPLE_NOTES, "素食"]:
        assert secret not in payload, f"画像内容 {secret!r} 不应出现在结果里"


def test_profile_used_is_false_for_an_empty_profile():
    assert profile_in_use(None) is False
    assert profile_in_use(UserProfile()) is False
    assert profile_in_use(sample_profile()) is True


def test_result_defaults_to_profile_not_used():
    result = AnalysisResult(id="a", dish_name="x", confidence=0.5)
    assert result.profile_used is False


# --------------------------------------------------------------------------
# Log redaction backstop
# --------------------------------------------------------------------------


def test_log_redaction_covers_profile_fields():
    line = json.dumps(
        {"allergies": ["花生"], "health_notes": SAMPLE_NOTES}, ensure_ascii=False
    )
    cleaned = redact(line)
    assert "花生" not in cleaned
    assert SAMPLE_NOTES not in cleaned
    assert "<REDACTED>" in cleaned


def test_log_redaction_covers_a_bare_assignment():
    cleaned = redact("health_notes=血脂偏高")
    assert "血脂偏高" not in cleaned
