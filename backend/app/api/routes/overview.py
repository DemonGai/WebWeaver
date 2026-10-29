from fastapi import APIRouter

from app.schemas.domain import OverviewPayload
from app.services import mock_data

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewPayload, summary="集群总览数据")
async def get_overview() -> OverviewPayload:
    return mock_data.overview()
