"""Health and public runtime configuration.

The frontend reads /api/config at boot so upload limits and allowed formats
live in exactly one place (backend/.env) instead of being duplicated in TS.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.schemas import (
    DISCLAIMER_TEXT,
    PRIVACY_NOTE,
    HealthResponse,
    ModeOption,
    PublicConfig,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["meta"])

ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]

MODE_OPTIONS = [
    ModeOption(
        value="quick",
        label="快速识别",
        description="只识别菜品与主要营养，响应更快，适合先看一眼。",
    ),
    ModeOption(
        value="detailed",
        label="详细分析",
        description="识别主要食材与份量，补充膳食纤维、糖、钠与过敏原提示，耗时更长。",
    ),
]


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        logger.exception("Database health check failed")
        database = "error"

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        provider=settings.resolved_provider,
        llm_configured=settings.llm_configured,
        demo_mode=settings.demo_mode,
        llm_model=settings.llm_model,
        database=database,
    )


@router.get("/config", response_model=PublicConfig)
def public_config(settings: Settings = Depends(get_settings)) -> PublicConfig:
    return PublicConfig(
        app_name=settings.app_name,
        version=settings.version,
        demo_mode=settings.demo_mode,
        max_upload_mb=settings.max_upload_mb,
        max_image_edge=settings.max_image_edge,
        max_images=settings.max_images,
        multi_image_max_edge=settings.multi_image_max_edge,
        max_total_upload_mb=settings.max_total_upload_mb,
        allowed_mime_types=ALLOWED_MIME_TYPES,
        modes=MODE_OPTIONS,
        low_confidence_threshold=settings.low_confidence_threshold,
        disclaimer=DISCLAIMER_TEXT,
        privacy_note=PRIVACY_NOTE,
    )
