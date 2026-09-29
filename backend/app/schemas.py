"""API contract. Frontend mirrors these types in ``src/types/api.ts``.

Design rule that drives this file: fields the product must never emit have no
home here at all. There is deliberately no ``health_score`` / ``grade`` /
``rating``, so nobody can reintroduce a fake-authority number by accident.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AnalysisMode = Literal["quick", "detailed"]

DISCLAIMER_TEXT = (
    "本结果由 AI 根据单张图片估算，可能存在偏差，仅供日常饮食参考，"
    "不构成医疗、营养或食品安全诊断。如有食物过敏、慢性疾病或特殊饮食需求，"
    "请咨询医生或注册营养师。"
)

PRIVACY_NOTE = (
    "图片仅用于本次分析。服务端在处理结束后即删除原图，不会长期保存，"
    "也不会记录图片内容或定位信息。若你保存分析结果，结果中不含原图。"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Model-facing schema: what we ask the LLM to produce and what we validate.
# Everything is optional-by-default so a partially-filled answer still renders
# instead of blowing up the request.
# --------------------------------------------------------------------------


class Nutrition(BaseModel):
    calories_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    # Which portion the numbers refer to. Without it the numbers are
    # unanchored and read as more authoritative than they are.
    basis: str = Field(
        default="未提供估算口径",
        description="估算口径，例如「按图中约 250g 份量折算」",
    )


class Ingredient(BaseModel):
    name: str
    estimated_amount: str | None = None
    note: str | None = None


# --------------------------------------------------------------------------
# Meal overall
#
# A dimension-by-dimension description of the meal as a whole. This is the part
# of the product closest to becoming a judgement, so the shape itself keeps it
# descriptive: there is no score, grade or rank anywhere, and `level` is only
# ever a quantity word (偏少 / 适中 / 偏多) — never a quality word. The UI must
# not colour it green-or-red either, or "偏少" becomes a grade in disguise.
# --------------------------------------------------------------------------

ASPECT_MAX = 6
ASPECT_LABEL_CHARS = 12
ASPECT_LEVEL_CHARS = 6
ASPECT_NOTE_CHARS = 80
OVERALL_SUMMARY_CHARS = 240


class MealAspect(BaseModel):
    """One dimension, e.g. 蔬菜「偏少 —— 只有少量葱花点缀」."""

    label: str = ""
    #: Quantity only. None for dimensions where a quantity word makes no sense
    #: (such as 烹调方式).
    level: str | None = None
    note: str = ""

    @field_validator("label", mode="before")
    @classmethod
    def _clean_label(cls, v: object) -> str:
        return str(v or "").strip()[:ASPECT_LABEL_CHARS]

    @field_validator("level", mode="before")
    @classmethod
    def _clean_level(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()[:ASPECT_LEVEL_CHARS]
        return text or None

    @field_validator("note", mode="before")
    @classmethod
    def _clean_note(cls, v: object) -> str:
        return str(v or "").strip()[:ASPECT_NOTE_CHARS]


class MealOverall(BaseModel):
    summary: str = ""
    aspects: list[MealAspect] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, v: object) -> str:
        return str(v or "").strip()[:OVERALL_SUMMARY_CHARS]

    @field_validator("aspects", mode="before")
    @classmethod
    def _clean_aspects(cls, v: object) -> list[MealAspect]:
        if not isinstance(v, list):
            return []
        out: list[MealAspect] = []
        for raw in v[:ASPECT_MAX]:
            if isinstance(raw, MealAspect):
                out.append(raw)
            elif isinstance(raw, dict):
                out.append(MealAspect.model_validate(raw))
            # Anything else is dropped rather than failing the whole result.
        return out

    @property
    def is_empty(self) -> bool:
        return not self.aspects and not self.summary


class DishAnalysis(BaseModel):
    """One dish's analysis.

    Used both as the shape of each dish in a multi-dish meal and, via
    :class:`MealAnalysis`, as the base of the payload we ask the model for — so
    the frontend can reuse one set of rendering components per dish.
    """

    dish_name: str
    dish_name_alternatives: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    confidence_reason: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    portion_estimate: str | None = None
    nutrition: Nutrition = Field(default_factory=Nutrition)
    advice: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, v: object) -> float:
        """Accept whatever scale the model felt like using, always land in 0..1.

        Models variously return ``0.87``, ``87`` or ``"87%"``. A value above 1
        is read as a percentage. Anything past 100, or non-numeric, is treated
        as unusable — and we err toward *under*-claiming confidence, because a
        wrongly low number nudges the user to double-check while a wrongly high
        one reads as false authority.
        """
        if isinstance(v, str):
            v = v.strip().rstrip("%")
        try:
            num = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.5
        if num != num:  # NaN
            return 0.5
        if num < 0:
            return 0.0
        if num <= 1:
            return num
        if num <= 100:
            return num / 100
        return 1.0


class MealAnalysis(DishAnalysis):
    """The model's top-level payload: a primary dish plus any others seen.

    A separate class rather than a field on DishAnalysis, so an additional dish
    can't itself contain additional dishes.
    """

    #: Describes the meal as a whole, which is where a multi-dish spread is
    #: actually useful to summarise.
    overall: MealOverall = Field(default_factory=MealOverall)
    additional_dishes: list[DishAnalysis] = Field(default_factory=list)


class ProcessedImage(BaseModel):
    """What the server actually fed to the model, shown back to the user."""

    #: Position in the uploaded set, so the UI can pair a thumbnail with its
    #: processing record.
    index: int = 0
    width: int
    height: int
    bytes: int
    mime: str
    operations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Client-facing schema
# --------------------------------------------------------------------------


class AnalysisResult(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=_utcnow)
    mode: AnalysisMode = "quick"

    dish_name: str
    dish_name_alternatives: list[str] = Field(default_factory=list)
    confidence: float
    confidence_reason: str | None = None

    ingredients: list[Ingredient] = Field(default_factory=list)
    portion_estimate: str | None = None
    nutrition: Nutrition = Field(default_factory=Nutrition)
    #: Dimension-by-dimension view of the meal. None for results recorded before
    #: this existed, and for replies that didn't include one.
    overall: MealOverall | None = None
    # Other dishes identified in the same photos. Empty when the meal is a
    # single dish, which is the common case.
    additional_dishes: list[DishAnalysis] = Field(default_factory=list)

    advice: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)

    disclaimer: str = DISCLAIMER_TEXT
    # True when the model's output could not be parsed as JSON and we fell
    # back to showing raw text.
    degraded: bool = False
    provider: str = "mock"
    # Metadata only — never image bytes. Empty for follow-up turns in a
    # conversation, where the photos were already discarded.
    images: list[ProcessedImage] = Field(default_factory=list)
    # True when a user profile informed this result. The profile's contents are
    # never stored, here or anywhere else.
    profile_used: bool = False
    #: True once the user has corrected the recognition by hand. Surfaced on the
    #: card, in history and in exports — without it, presenting edited values
    #: under an "AI estimate" disclaimer would be misleading.
    edited: bool = False


class AnalysisSummary(BaseModel):
    """Lightweight row for the history list (no image, ever)."""

    id: str
    created_at: datetime
    mode: AnalysisMode
    dish_name: str
    confidence: float
    calories_kcal: float | None = None


class HistoryPage(BaseModel):
    items: list[AnalysisSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


#: Limits for a hand-corrected result.
EDIT_MAX_INGREDIENTS = 20
EDIT_MAX_NAME_CHARS = 60
EDIT_MAX_AMOUNT_CHARS = 40
EDIT_MAX_NOTE_CHARS = 60
EDIT_MAX_PORTION_CHARS = 80


class AnalysisEditRequest(BaseModel):
    """The fields a user may correct by hand.

    Deliberately excludes the nutrition numbers and the advice text: those are
    derived from the ingredients, and letting them be edited independently would
    leave a card whose parts contradict each other under an "AI estimate"
    disclaimer. Editing the ingredients is the meaningful correction.
    """

    dish_name: str
    ingredients: list[Ingredient] = Field(default_factory=list)
    portion_estimate: str | None = None

    @field_validator("dish_name", mode="before")
    @classmethod
    def _clean_dish_name(cls, v: object) -> str:
        text = str(v or "").strip()[:EDIT_MAX_NAME_CHARS]
        if not text:
            raise ValueError("dish_name must not be empty")
        return text

    @field_validator("portion_estimate", mode="before")
    @classmethod
    def _clean_portion(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()[:EDIT_MAX_PORTION_CHARS]
        return text or None

    @field_validator("ingredients", mode="before")
    @classmethod
    def _clean_ingredients(cls, v: object) -> list[Ingredient]:
        if not isinstance(v, list):
            return []

        out: list[Ingredient] = []
        for raw in v:
            if isinstance(raw, Ingredient):
                item = raw
            elif isinstance(raw, dict):
                item = Ingredient.model_validate(raw)
            else:
                continue

            name = (item.name or "").strip()[:EDIT_MAX_NAME_CHARS]
            if not name:
                # A blank row in the edit form means "removed", not an error.
                continue
            amount = (item.estimated_amount or "").strip()[:EDIT_MAX_AMOUNT_CHARS]
            out.append(
                Ingredient(
                    name=name,
                    estimated_amount=amount or None,
                    note=(item.note or "").strip()[:EDIT_MAX_NOTE_CHARS] or None,
                )
            )
            if len(out) >= EDIT_MAX_INGREDIENTS:
                break
        return out


# --------------------------------------------------------------------------
# Conversations
#
# A conversation is a sequence of turns. A turn that carried images produced an
# analysis; a turn without them is a chat reply. Only the *current* turn's
# images are ever sent to the model — earlier photos were discarded, which the
# prompt states outright so the model doesn't invent visual details about them.
# --------------------------------------------------------------------------

MessageRole = Literal["user", "assistant"]


class ConversationMessage(BaseModel):
    id: str
    seq: int
    role: MessageRole
    text: str = ""
    #: Metadata only, never bytes.
    images: list[ProcessedImage] = Field(default_factory=list)
    #: Present when this turn produced a structured analysis.
    analysis: AnalysisResult | None = None
    #: Whether a profile informed this turn. Contents are never stored.
    profile_used: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Conversation(BaseModel):
    id: str
    title: str
    mode: AnalysisMode = "quick"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    """List row — no messages, so the list stays cheap."""

    id: str
    title: str
    mode: AnalysisMode
    created_at: datetime
    updated_at: datetime
    turn_count: int = 0


class ConversationPage(BaseModel):
    items: list[ConversationSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class ModeOption(BaseModel):
    value: AnalysisMode
    label: str
    description: str


# --------------------------------------------------------------------------
# User profile
#
# Scope is a product decision with safety consequences: the fields here are
# limited to things that let the model *filter and adjust* (allergies,
# avoidances, preferences, dietary pattern) plus optional context. Body metrics
# and diagnosed conditions are deliberately absent — the app promises not to
# grade, judge or diagnose, and structured height/weight would invite exactly
# that. `health_notes` is the one free-text opening, constrained by prompt
# rules and a length cap.
#
# The profile is never persisted: the frontend keeps it in localStorage and
# sends it per request. See `AnalysisResult.profile_used`.
# --------------------------------------------------------------------------

PROFILE_MAX_ITEMS = 20
PROFILE_MAX_ITEM_CHARS = 30
PROFILE_MAX_HEALTH_NOTES = 200


class AgeBand(str, Enum):
    """Bands rather than a precise age — precision buys nothing here."""

    UNDER_18 = "<18"
    B18_29 = "18-29"
    B30_39 = "30-39"
    B40_49 = "40-49"
    B50_59 = "50-59"
    B60_PLUS = "60+"


class Sex(str, Enum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNSET = "unset"


def _clean_list(values: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate, and bound the result."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        text = str(raw).strip()[:PROFILE_MAX_ITEM_CHARS]
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= PROFILE_MAX_ITEMS:
            break
    return cleaned


class UserProfile(BaseModel):
    """What a user voluntarily tells us, to make advice fit them better."""

    allergies: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    dietary_pattern: str | None = None
    age_band: AgeBand | None = None
    sex: Sex | None = None
    #: Free text the user wrote about what they want to keep an eye on. Treated
    #: as context for filtering ingredients — never as a basis for a diagnosis.
    health_notes: str | None = None

    @field_validator("allergies", "avoidances", "preferences", mode="before")
    @classmethod
    def _normalise_lists(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            # Tolerate a comma-separated string from a simple form.
            v = [part for part in v.replace("，", ",").split(",")]
        if not isinstance(v, list):
            return []
        return _clean_list([str(item) for item in v])

    @field_validator("dietary_pattern", mode="before")
    @classmethod
    def _normalise_pattern(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()[:PROFILE_MAX_ITEM_CHARS]
        return text or None

    @field_validator("health_notes", mode="before")
    @classmethod
    def _normalise_notes(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()[:PROFILE_MAX_HEALTH_NOTES]
        return text or None

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.allergies,
                self.avoidances,
                self.preferences,
                self.dietary_pattern,
                self.age_band,
                self.sex,
                self.health_notes,
            ]
        )


class PublicConfig(BaseModel):
    """Handed to the frontend so limits aren't hardcoded in two places."""

    app_name: str
    version: str
    demo_mode: bool
    max_upload_mb: float
    max_image_edge: int
    max_images: int
    multi_image_max_edge: int
    max_total_upload_mb: float
    allowed_mime_types: list[str]
    modes: list[ModeOption]
    low_confidence_threshold: float
    disclaimer: str
    privacy_note: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    provider: str
    llm_configured: bool
    demo_mode: bool
    llm_model: str
    database: str


# --------------------------------------------------------------------------
# Errors — every failure the user can hit has a human-readable shape.
# --------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    hint: str | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SSEEventName:
    """The four event types on /api/analyze/stream."""

    STATUS = "status"
    PARTIAL = "partial"
    RESULT = "result"
    ERROR = "error"


class StatusEvent(BaseModel):
    stage: Literal[
        "received", "validating", "preprocessing", "calling_model", "parsing", "done"
    ]
    message: str


class PartialEvent(BaseModel):
    text: str
