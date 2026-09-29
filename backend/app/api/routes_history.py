"""History of past analyses.

These endpoints only ever return the structured result the user already saw.
There is no endpoint that serves an image, because none is stored.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.repository import AnalysisRepository
from app.db.session import get_db
from app.schemas import AnalysisEditRequest, AnalysisResult, HistoryPage

router = APIRouter(tags=["history"])


def _repo(db: Session = Depends(get_db)) -> AnalysisRepository:
    return AnalysisRepository(db)


@router.get("/history", response_model=HistoryPage)
def list_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: AnalysisRepository = Depends(_repo),
) -> HistoryPage:
    return repo.list_page(limit=limit, offset=offset)


@router.get("/history/{analysis_id}", response_model=AnalysisResult)
def get_history_item(
    analysis_id: str, repo: AnalysisRepository = Depends(_repo)
) -> AnalysisResult:
    result = repo.get(analysis_id)
    if result is None:
        raise NotFoundError("未找到这条分析记录。", hint="它可能已被删除。")
    return result


@router.patch("/history/{analysis_id}", response_model=AnalysisResult)
def update_history_item(
    analysis_id: str,
    patch: AnalysisEditRequest,
    repo: AnalysisRepository = Depends(_repo),
) -> AnalysisResult:
    """Apply a user's correction to a stored recognition.

    Only the fields a user can meaningfully judge are editable. The nutrition
    figures are left as estimated — see AnalysisEditRequest for why.
    """
    updated = repo.update(analysis_id, patch)
    if updated is None:
        raise NotFoundError("未找到这条分析记录。", hint="它可能已被删除。")
    return updated


@router.delete("/history/{analysis_id}", status_code=204)
def delete_history_item(analysis_id: str, repo: AnalysisRepository = Depends(_repo)) -> None:
    if not repo.delete(analysis_id):
        raise NotFoundError("未找到这条分析记录。", hint="它可能已被删除。")
