"""Data access for analysis results.

Every query in the app goes through here, which is what keeps a future
PostgreSQL migration (or a future "user profile" feature) from touching
business logic.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRecord,
    Conversation as ConversationRecord,
    ConversationMessage as ConversationMessageRecord,
)
from app.schemas import (
    AnalysisResult,
    AnalysisSummary,
    Conversation,
    ConversationMessage,
    ConversationPage,
    ConversationSummary,
    HistoryPage,
    ProcessedImage,
)

logger = logging.getLogger(__name__)


class AnalysisRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, result: AnalysisResult) -> None:
        record = AnalysisRecord(
            id=result.id,
            created_at=result.created_at,
            mode=result.mode,
            dish_name=result.dish_name,
            confidence=result.confidence,
            provider=result.provider,
            degraded=result.degraded,
            # mode="json" so datetimes and enums serialize predictably.
            payload=result.model_dump_json(),
        )
        self.db.add(record)
        self.db.commit()

    def get(self, analysis_id: str) -> AnalysisResult | None:
        record = self.db.get(AnalysisRecord, analysis_id)
        if record is None:
            return None
        try:
            return AnalysisResult.model_validate(json.loads(record.payload))
        except Exception:
            # A row written by an older schema shouldn't 500 the whole page.
            logger.exception("Stored payload for %s could not be re-validated", analysis_id)
            return None

    def list_page(self, limit: int = 20, offset: int = 0) -> HistoryPage:
        total = self.db.scalar(select(func.count()).select_from(AnalysisRecord)) or 0
        rows = self.db.scalars(
            select(AnalysisRecord)
            .order_by(AnalysisRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        items: list[AnalysisSummary] = []
        for row in rows:
            calories = None
            try:
                payload = json.loads(row.payload)
                calories = (payload.get("nutrition") or {}).get("calories_kcal")
            except Exception:
                pass
            items.append(
                AnalysisSummary(
                    id=row.id,
                    created_at=row.created_at,
                    mode=row.mode,  # type: ignore[arg-type]
                    dish_name=row.dish_name,
                    confidence=row.confidence,
                    calories_kcal=calories,
                )
            )

        return HistoryPage(items=items, total=total, limit=limit, offset=offset)

    def delete(self, analysis_id: str) -> bool:
        record = self.db.get(AnalysisRecord, analysis_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def delete_all(self) -> int:
        deleted = self.db.query(AnalysisRecord).delete()
        self.db.commit()
        return int(deleted)


class ConversationRepository:
    """Storage for multi-turn conversations.

    Every read/write for conversations goes through here, so a future move to
    PostgreSQL (or adding per-user scoping) touches this class only.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- conversations ----

    def create(self, mode: str, title: str = "新的对话") -> Conversation:
        now = datetime.now(timezone.utc)
        record = ConversationRecord(id=str(uuid.uuid4()), title=title, mode=mode)
        record.created_at = now
        record.updated_at = now
        self.db.add(record)
        self.db.commit()
        return record

    def get(self, conversation_id: str) -> Conversation | None:
        record = self.db.get(ConversationRecord, conversation_id)
        if record is None:
            return None
        messages = self.db.scalars(
            select(ConversationMessageRecord)
            .where(ConversationMessageRecord.conversation_id == conversation_id)
            .order_by(ConversationMessageRecord.seq)
        ).all()
        return self._to_model(record, messages)

    def list_page(self, limit: int = 20, offset: int = 0) -> ConversationPage:
        total = (
            self.db.scalar(select(func.count()).select_from(ConversationRecord)) or 0
        )
        rows = self.db.scalars(
            select(ConversationRecord)
            .order_by(ConversationRecord.updated_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        items = [
            ConversationSummary(
                id=row.id,
                title=row.title,
                mode=row.mode,  # type: ignore[arg-type]
                created_at=row.created_at,
                updated_at=row.updated_at,
                turn_count=self.db.scalar(
                    select(func.count())
                    .select_from(ConversationMessageRecord)
                    .where(ConversationMessageRecord.conversation_id == row.id)
                )
                or 0,
            )
            for row in rows
        ]
        return ConversationPage(items=items, total=total, limit=limit, offset=offset)

    def rename(self, conversation_id: str, title: str) -> None:
        record = self.db.get(ConversationRecord, conversation_id)
        if record is None:
            return
        record.title = title[:200]
        self.db.commit()

    def delete(self, conversation_id: str) -> bool:
        record = self.db.get(ConversationRecord, conversation_id)
        if record is None:
            return False
        self.db.query(ConversationMessageRecord).filter(
            ConversationMessageRecord.conversation_id == conversation_id
        ).delete()
        self.db.delete(record)
        self.db.commit()
        return True

    # ---- messages ----

    def next_seq(self, conversation_id: str) -> int:
        highest = self.db.scalar(
            select(func.max(ConversationMessageRecord.seq)).where(
                ConversationMessageRecord.conversation_id == conversation_id
            )
        )
        return int(highest or 0) + 1

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        text: str,
        seq: int,
        images: list[ProcessedImage] | None = None,
        analysis: AnalysisResult | None = None,
        profile_used: bool = False,
    ) -> ConversationMessage:
        message = ConversationMessageRecord(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            seq=seq,
            role=role,
            text=text,
            # Image metadata only — never bytes.
            images=json.dumps(
                [image.model_dump(mode="json") for image in (images or [])],
                ensure_ascii=False,
            ),
            analysis=analysis.model_dump_json() if analysis else None,
            profile_used=profile_used,
        )
        self.db.add(message)

        record = self.db.get(ConversationRecord, conversation_id)
        if record is not None:
            record.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        return self._message_to_model(message)

    # ---- mapping ----

    @staticmethod
    def _message_to_model(row: ConversationMessageRecord) -> ConversationMessage:
        try:
            images = [
                ProcessedImage.model_validate(item) for item in json.loads(row.images or "[]")
            ]
        except Exception:
            images = []

        analysis = None
        if row.analysis:
            try:
                analysis = AnalysisResult.model_validate(json.loads(row.analysis))
            except Exception:
                # A row written by an older schema shouldn't break the thread.
                logger.warning("会话消息 %s 的分析结果无法解析", row.id)

        return ConversationMessage(
            id=row.id,
            seq=row.seq,
            role=row.role,  # type: ignore[arg-type]
            text=row.text,
            images=images,
            analysis=analysis,
            profile_used=row.profile_used,
            created_at=row.created_at,
        )

    def _to_model(
        self, record: ConversationRecord, messages: list[ConversationMessageRecord]
    ) -> Conversation:
        return Conversation(
            id=record.id,
            title=record.title,
            mode=record.mode,  # type: ignore[arg-type]
            created_at=record.created_at,
            updated_at=record.updated_at,
            messages=[self._message_to_model(row) for row in messages],
        )
