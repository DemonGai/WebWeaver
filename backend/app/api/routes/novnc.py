from fastapi import APIRouter

from app.schemas.domain import NoVncPayload
from app.services import mock_data

router = APIRouter(tags=["novnc"])


@router.get("/novnc/{instance_id}", response_model=NoVncPayload, summary="noVNC 会话详情")
async def get_novnc(instance_id: str) -> NoVncPayload:
    return mock_data.novnc(instance_id)
