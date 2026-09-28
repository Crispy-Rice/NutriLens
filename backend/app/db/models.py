"""Persistence model.

Privacy note: there is intentionally **no column for the image** — not the
bytes, not a path, not a hash. Only the structured result the user already
sees on screen is stored, so the database never becomes a photo archive.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    dish_name: Mapped[str] = mapped_column(String(200), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    degraded: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Full AnalysisResult JSON — the same payload the API returned.
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_analysis_records_created_at", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AnalysisRecord {self.id} {self.dish_name!r} conf={self.confidence:.2f}>"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    #: Derived from the first identified dish, so the list is readable.
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新的对话")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="quick")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (Index("ix_conversations_updated_at", "updated_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Conversation {self.id} {self.title!r}>"


class ConversationMessage(Base):
    """One turn.

    Privacy note, again by construction: there is no column for image bytes.
    ``images`` holds metadata only, and ``profile_used`` records that a profile
    informed the turn without recording a single field of it.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: JSON list of image metadata.
    images: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    #: JSON AnalysisResult for analysis turns; NULL for chat turns.
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_conversation_messages_conversation", "conversation_id", "seq"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ConversationMessage {self.conversation_id}#{self.seq} {self.role}>"
