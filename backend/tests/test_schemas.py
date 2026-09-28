from app.schemas import (
    DISCLAIMER_TEXT,
    AnalysisResult,
    DishAnalysis,
    Nutrition,
)


def test_confidence_is_normalised_from_percentage_scale():
    assert DishAnalysis(dish_name="x", confidence=87).confidence == 0.87
    assert DishAnalysis(dish_name="x", confidence=100).confidence == 1.0
    assert DishAnalysis(dish_name="x", confidence=0.87).confidence == 0.87


def test_out_of_range_confidence_is_handled_without_raising():
    assert DishAnalysis(dish_name="x", confidence=-3).confidence == 0.0
    assert DishAnalysis(dish_name="x", confidence=9999).confidence == 1.0
    # Ambiguous in-between values intentionally under-claim rather than
    # over-claim: better to nudge the user to double-check the dish than to
    # assert a confidence the model never earned.
    assert DishAnalysis(dish_name="x", confidence=1.5).confidence == 0.015


def test_percentage_string_confidence_is_normalised():
    assert DishAnalysis(dish_name="x", confidence="82%").confidence == 0.82
    assert DishAnalysis(dish_name="x", confidence="0.4").confidence == 0.4


def test_non_numeric_confidence_falls_back_instead_of_raising():
    assert DishAnalysis(dish_name="x", confidence="很高").confidence == 0.5


def test_nutrition_defaults_are_all_unknown_not_zero():
    """Unknown must be null. Zero would read as a factual claim of 'no calories'."""
    n = Nutrition()
    assert n.calories_kcal is None
    assert n.protein_g is None
    assert n.basis  # a basis string is always present


def test_analysis_result_defaults_to_disclaimer_and_not_degraded():
    result = AnalysisResult(id="a1", dish_name="番茄炒蛋", confidence=0.8)
    assert result.disclaimer == DISCLAIMER_TEXT
    assert result.degraded is False
    assert result.nutrition.calories_kcal is None


def test_result_has_no_health_score_field():
    """Guard rail: a fake-authority score must never become serialisable."""
    fields = set(AnalysisResult.model_fields) | set(Nutrition.model_fields)
    forbidden = {"health_score", "score", "grade", "rating", "health_grade", "stars"}
    assert not (fields & forbidden)
