"""Manual-correction tests.

The point of the feature is that a user can fix what the model got wrong. Two
properties matter beyond the happy path: the correction must be *labelled* as
one, and it must not quietly invalidate the parts it doesn't touch.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.repository import AnalysisRepository
from app.db.session import Base
from app.schemas import (
    EDIT_MAX_INGREDIENTS,
    AnalysisEditRequest,
    AnalysisResult,
    Ingredient,
    MealAspect,
    MealOverall,
    Nutrition,
)


def make_result(dish: str = "番茄炒蛋") -> AnalysisResult:
    return AnalysisResult(
        id="a1",
        dish_name=dish,
        confidence=0.8,
        confidence_reason="形态符合",
        ingredients=[
            Ingredient(name="鸡蛋", estimated_amount="约 2 个"),
            Ingredient(name="番茄", estimated_amount="约 200g"),
        ],
        portion_estimate="约 300g",
        nutrition=Nutrition(calories_kcal=285, protein_g=14.2, basis="按约 300g 折算"),
        overall=MealOverall(
            summary="以蛋白质为主。", aspects=[MealAspect(label="蔬菜", level="偏少", note="少量")]
        ),
        advice="搭配青菜更均衡。",
        risk_notes=["含鸡蛋"],
        uncertainty_notes=["用油量无法判断"],
        profile_used=True,
    )


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = AnalysisRepository(session)
    repository.save(make_result())
    try:
        yield repository
    finally:
        session.close()


# --------------------------------------------------------------------------
# Applying a correction
# --------------------------------------------------------------------------


def test_correction_updates_the_editable_fields(repo):
    updated = repo.update(
        "a1",
        AnalysisEditRequest(
            dish_name="西红柿炒鸡蛋",
            ingredients=[Ingredient(name="鸡蛋", estimated_amount="3 个")],
            portion_estimate="约 400g",
        ),
    )
    assert updated is not None
    assert updated.dish_name == "西红柿炒鸡蛋"
    assert [i.name for i in updated.ingredients] == ["鸡蛋"]
    assert updated.portion_estimate == "约 400g"


def test_correction_is_flagged_as_edited(repo):
    updated = repo.update("a1", AnalysisEditRequest(dish_name="炒蛋"))
    assert updated is not None
    assert updated.edited is True


def test_correction_leaves_untouched_fields_alone(repo):
    """Nutrition and advice are derived from the ingredients; a correction to
    the ingredients must not silently rewrite them."""
    updated = repo.update("a1", AnalysisEditRequest(dish_name="炒蛋"))
    assert updated is not None
    assert updated.nutrition.calories_kcal == 285
    assert updated.nutrition.basis == "按约 300g 折算"
    assert updated.advice == "搭配青菜更均衡。"
    assert updated.risk_notes == ["含鸡蛋"]
    assert updated.uncertainty_notes == ["用油量无法判断"]
    assert updated.confidence == 0.8
    assert updated.overall is not None
    assert updated.overall.aspects[0].label == "蔬菜"


def test_correction_survives_a_reload(repo):
    repo.update("a1", AnalysisEditRequest(dish_name="西红柿炒鸡蛋"))
    reloaded = repo.get("a1")
    assert reloaded is not None
    assert reloaded.dish_name == "西红柿炒鸡蛋"
    assert reloaded.edited is True


def test_denormalised_dish_name_column_is_kept_in_sync(repo):
    """The history list reads a copy of the name from its own column."""
    repo.update("a1", AnalysisEditRequest(dish_name="西红柿炒鸡蛋"))
    page = repo.list_page()
    assert page.items[0].dish_name == "西红柿炒鸡蛋"


def test_correcting_twice_keeps_the_latest(repo):
    repo.update("a1", AnalysisEditRequest(dish_name="第一版"))
    repo.update("a1", AnalysisEditRequest(dish_name="第二版"))
    assert repo.get("a1").dish_name == "第二版"


# --------------------------------------------------------------------------
# Missing / malformed input
# --------------------------------------------------------------------------


def test_updating_a_missing_record_returns_none(repo):
    assert repo.update("nope", AnalysisEditRequest(dish_name="x")) is None


def test_blank_dish_name_is_rejected():
    with pytest.raises(Exception):
        AnalysisEditRequest(dish_name="   ")


def test_blank_ingredient_rows_are_dropped():
    """An empty row in the edit form means "removed", not an error."""
    patch = AnalysisEditRequest(
        dish_name="番茄炒蛋",
        ingredients=[
            Ingredient(name="鸡蛋"),
            Ingredient(name="   "),
            Ingredient(name="番茄"),
        ],
    )
    assert [i.name for i in patch.ingredients] == ["鸡蛋", "番茄"]


def test_ingredient_count_is_capped():
    patch = AnalysisEditRequest(
        dish_name="番茄炒蛋",
        ingredients=[Ingredient(name=f"料{i}") for i in range(50)],
    )
    assert len(patch.ingredients) == EDIT_MAX_INGREDIENTS


def test_ingredient_fields_are_trimmed():
    patch = AnalysisEditRequest(
        dish_name=" 番茄炒蛋 ",
        ingredients=[Ingredient(name=" 鸡蛋 ", estimated_amount=" 约2个 ")],
    )
    assert patch.dish_name == "番茄炒蛋"
    assert patch.ingredients[0].name == "鸡蛋"
    assert patch.ingredients[0].estimated_amount == "约2个"


def test_blank_portion_becomes_none():
    assert AnalysisEditRequest(dish_name="x", portion_estimate="  ").portion_estimate is None


def test_clearing_all_ingredients_is_allowed(repo):
    """Someone may genuinely want to say "no ingredients listed"."""
    updated = repo.update("a1", AnalysisEditRequest(dish_name="番茄炒蛋", ingredients=[]))
    assert updated is not None
    assert updated.ingredients == []


# --------------------------------------------------------------------------
# Compatibility
# --------------------------------------------------------------------------


def test_a_result_without_overall_can_still_be_edited():
    legacy = AnalysisResult(id="a2", dish_name="旧记录", confidence=0.5, advice="x")
    assert legacy.overall is None
    edited = legacy.model_copy(update={"dish_name": "改过了", "edited": True})
    assert edited.dish_name == "改过了"
    assert edited.overall is None
