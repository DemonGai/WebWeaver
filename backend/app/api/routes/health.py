from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import db
from app.core.config import settings

router = APIRouter(tags=["health"])


class DatabaseStatus(BaseModel):
    status: str
    version: str | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    database: DatabaseStatus | None = None


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health() -> HealthResponse:
    ok, info = await db.ping()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(UTC).isoformat(),
        database=DatabaseStatus(
            status="up" if ok else "down",
            version=info if ok else None,
            detail=None if ok else info,
        ),
    )
