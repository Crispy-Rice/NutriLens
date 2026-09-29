"""Conversation turn tests.

The important behaviours: a turn with photos produces an analysis and a turn
without produces prose; earlier turns are replayed but their photos are not; and
the prompt tells the model it cannot see those photos, because otherwise it
invents visual details about them on later turns.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Conversation as ConversationRecord
from app.db.repository import ConversationRepository
from app.db.session import Base
from app.schemas import (
    AnalysisResult,
    Conversation,
    ConversationMessage,
    Nutrition,
    ProcessedImage,
)
from app.services.conversation_service import (
    _compact_analysis,
    build_history,
    render_message,
    stream_turn,
)
from app.services.image_service import PreparedImage
from app.services.llm.mock import MockProvider
from app.services.prompt_service import (
    CONVERSATION_BLOCK,
    build_chat_system_prompt,
    build_system_prompt,
)


def make_image(index: int = 0) -> PreparedImage:
    return PreparedImage(
        data=b"fake", mime="image/jpeg", width=10, height=10, index=index
    )


def make_processed(index: int = 0) -> ProcessedImage:
    """The schema type stored on a message. Distinct from PreparedImage, which
    carries bytes and exists only inside the request."""
    return ProcessedImage(
        index=index, width=10, height=10, bytes=4, mime="image/jpeg"
    )


def make_analysis(dish: str = "番茄炒蛋") -> AnalysisResult:
    return AnalysisResult(
        id="a1",
        dish_name=dish,
        confidence=0.8,
        nutrition=Nutrition(calories_kcal=285, basis="按约 300g 折算"),
        advice="搭配青菜更均衡。",
    )


def msg(
    seq: int, role: str, text: str = "", analysis: AnalysisResult | None = None, images=None
) -> ConversationMessage:
    return ConversationMessage(
        id=f"m{seq}",
        seq=seq,
        role=role,  # type: ignore[arg-type]
        text=text,
        analysis=analysis,
        images=images or [],
    )


async def collect(conversation: Conversation, **kwargs) -> dict:
    """Drive one turn and return the events by name."""
    events: dict[str, list] = {}
    images = kwargs.pop("images", [])
    async for event, payload in stream_turn(
        conversation,
        images=images,
        user_text=kwargs.pop("user_text", ""),
        profile=None,
        provider=MockProvider(),
        history_limit=kwargs.pop("history_limit", 8),
    ):
        events.setdefault(event, []).append(payload)
    return events


# --------------------------------------------------------------------------
# Anti-hallucination prompt rule
# --------------------------------------------------------------------------


def test_conversation_block_states_the_photos_are_gone():
    """The single most important line in this feature."""
    assert "看不到用户之前上传的照片" in CONVERSATION_BLOCK
    assert "绝对不要" in CONVERSATION_BLOCK


def test_conversation_block_is_included_in_both_prompts():
    assert CONVERSATION_BLOCK in build_system_prompt("quick", None, in_conversation=True)
    assert CONVERSATION_BLOCK in build_chat_system_prompt(None, in_conversation=True)


def test_conversation_block_absent_for_single_shot():
    assert CONVERSATION_BLOCK not in build_system_prompt("quick")


def test_chat_prompt_forbids_json_output():
    prompt = build_chat_system_prompt()
    assert "不要输出 JSON" in prompt
    # And keeps the shared safety rules.
    assert "BMI" not in prompt  # no profile supplied
    assert "健康评分" in prompt or "评分" in prompt


# --------------------------------------------------------------------------
# History assembly
# --------------------------------------------------------------------------


def test_history_is_empty_for_the_first_turn():
    assert build_history([], 8) == []


def test_history_renders_user_text_and_photo_count():
    rendered = render_message(msg(1, "user", "这是两人份", images=[make_processed()]))
    assert "这是两人份" in rendered
    assert "附了 1 张照片" in rendered


def test_history_renders_a_photo_only_message():
    """A photo with no caption is meaningful on its own — no filler needed."""
    rendered = render_message(msg(1, "user", images=[make_processed()]))
    assert "1 张照片" in rendered
    assert "没有输入文字" not in rendered


def test_history_marks_a_truly_empty_message():
    assert "（用户没有输入文字）" in render_message(msg(1, "user"))


def test_history_embeds_the_analysis_as_json_for_the_model():
    rendered = render_message(msg(2, "assistant", analysis=make_analysis()))
    assert "番茄炒蛋" in rendered
    assert "285" in rendered
    # It must be parseable so the model sees exact numbers.
    payload = json.loads(rendered.split("\n", 1)[1])
    assert payload["dish_name"] == "番茄炒蛋"


def test_compacted_analysis_drops_rendering_only_fields():
    compact = json.loads(_compact_analysis(make_analysis()))
    for field in ("id", "created_at", "disclaimer", "images", "provider", "profile_used"):
        assert field not in compact
    assert compact["dish_name"] == "番茄炒蛋"
    assert compact["nutrition"]["calories_kcal"] == 285


def test_history_keeps_the_first_analysis_even_when_trimming():
    """The opening analysis anchors the conversation; dropping it would leave
    the model answering about a meal it never saw."""
    messages = [msg(1, "user", "第一轮")]
    messages.append(msg(2, "assistant", analysis=make_analysis()))
    for seq in range(3, 20):
        messages.append(msg(seq, "user" if seq % 2 else "assistant", f"turn {seq}"))

    history = build_history(messages, limit=4)

    assert "番茄炒蛋" in history[0].text or any("番茄炒蛋" in t.text for t in history)
    assert any("番茄炒蛋" in turn.text for turn in history)
    # And it stays bounded.
    assert len(history) <= 5


def test_history_is_ordered_oldest_first():
    messages = [msg(i, "user" if i % 2 else "assistant", f"turn {i}") for i in range(1, 6)]
    history = build_history(messages, limit=8)
    assert [turn.text for turn in history] == [f"turn {i}" for i in range(1, 6)]


def test_history_respects_the_limit():
    messages = [msg(i, "user", f"turn {i}") for i in range(1, 21)]
    assert len(build_history(messages, limit=3)) == 3


# --------------------------------------------------------------------------
# Turn branches
# --------------------------------------------------------------------------


async def test_turn_with_images_produces_an_analysis():
    events = await collect(Conversation(id="c1", title="t"), images=[make_image()])
    completed = events["completed"][0]
    assert completed["analysis"] is not None
    assert completed["analysis"]["dish_name"] == "番茄炒蛋"
    assert completed["assistant_text"] == ""


async def test_turn_without_images_produces_prose_not_json():
    events = await collect(Conversation(id="c1", title="t"), user_text="怎么更清淡？")
    completed = events["completed"][0]
    assert completed["analysis"] is None
    assert completed["assistant_text"]
    assert not completed["assistant_text"].lstrip().startswith("{")


async def test_both_turn_types_emit_status_before_completion():
    for kwargs in ({"images": [make_image()]}, {"user_text": "你好"}):
        events = await collect(Conversation(id="c1", title="t"), **kwargs)
        assert events["status"]
        assert events["completed"]


async def test_analysis_turn_streams_advice_partials():
    events = await collect(Conversation(id="c1", title="t"), images=[make_image()])
    advice = "".join(p["text"] for p in events.get("partial", []) if p["field"] == "advice")
    assert advice
    assert advice in events["completed"][0]["analysis"]["advice"]


async def test_analysis_turn_also_streams_the_dish_name():
    """The name is written first, so the progress view can show it early."""
    events = await collect(Conversation(id="c1", title="t"), images=[make_image()])
    names = "".join(p["text"] for p in events.get("partial", []) if p["field"] == "dish_name")
    assert names
    assert names == events["completed"][0]["analysis"]["dish_name"]
    # And it arrives before the advice finishes, by definition of field order.
    fields = [p["field"] for p in events.get("partial", [])]
    assert fields.index("dish_name") <= fields.index("advice")


async def test_chat_turn_partials_use_the_reply_field():
    """A chat turn has no JSON, so its whole reply streams under one field."""
    events = await collect(Conversation(id="c1", title="t"), user_text="怎么更清淡？")
    partials = events.get("partial", [])
    assert partials
    assert {p["field"] for p in partials} == {"reply"}
    assert "".join(p["text"] for p in partials) == events["completed"][0]["assistant_text"]


# --------------------------------------------------------------------------
# Persistence round-trip
# --------------------------------------------------------------------------


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield ConversationRepository(session)
    finally:
        session.close()


def test_create_and_fetch_conversation(repo):
    created = repo.create(mode="detailed")
    fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.mode == "detailed"
    assert fetched.messages == []


def test_append_messages_keeps_order_and_numbers(repo):
    created = repo.create(mode="quick")
    seq = repo.next_seq(created.id)
    repo.append_message(created.id, role="user", text="第一句", seq=seq)
    repo.append_message(
        created.id,
        role="assistant",
        text="",
        seq=seq + 1,
        analysis=make_analysis(),
        profile_used=True,
    )

    fetched = repo.get(created.id)
    assert [m.seq for m in fetched.messages] == [1, 2]
    assert fetched.messages[0].text == "第一句"
    assert fetched.messages[1].analysis is not None
    assert fetched.messages[1].profile_used is True


def test_stored_message_has_no_image_bytes(repo):
    created = repo.create(mode="quick")
    repo.append_message(
        created.id,
        role="user",
        text="看图",
        seq=1,
        images=[make_processed()],
    )
    stored = repo.get(created.id).messages[0]
    assert stored.images[0].width == 10
    # The bytes exist nowhere in the row.
    assert not hasattr(stored.images[0], "data")


def test_list_page_counts_turns(repo):
    created = repo.create(mode="quick")
    repo.append_message(created.id, role="user", text="a", seq=1)
    repo.append_message(created.id, role="assistant", text="b", seq=2)

    page = repo.list_page()
    assert page.total == 1
    assert page.items[0].turn_count == 2


def test_delete_removes_messages_too(repo):
    created = repo.create(mode="quick")
    repo.append_message(created.id, role="user", text="a", seq=1)

    assert repo.delete(created.id) is True
    assert repo.get(created.id) is None
    assert repo.list_page().total == 0


def test_next_seq_starts_at_one_and_increments(repo):
    created = repo.create(mode="quick")
    assert repo.next_seq(created.id) == 1
    repo.append_message(created.id, role="user", text="a", seq=1)
    assert repo.next_seq(created.id) == 2


def test_get_missing_conversation_returns_none(repo):
    assert repo.get("does-not-exist") is None


def test_rename_sets_the_title(repo):
    created = repo.create(mode="quick")
    repo.rename(created.id, "番茄炒蛋")
    assert repo.get(created.id).title == "番茄炒蛋"


def test_conversation_record_has_no_profile_columns():
    columns = {column.name for column in ConversationRecord.__table__.columns}
    assert not (columns & {"profile", "allergies", "health_notes", "user_profile"})
