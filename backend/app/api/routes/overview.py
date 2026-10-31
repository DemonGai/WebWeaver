from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.domain import OverviewPayload
from app.services import audit
from app.services import cluster as cluster_service
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["overview"])

# 总览会用到的三种时间窗：各自的桶粒度与跨度在 audit.RANGE_SPECS 里定义
OverviewRange = Literal["24h", "7d", "30d"]


@router.get("/overview", response_model=OverviewPayload, summary="集群总览数据")
async def get_overview(
    snapshot: Annotated[Snapshot, Depends(get_snapshot)],
    session: Annotated[AsyncSession, Depends(get_session)],
    range_key: Annotated[
        OverviewRange, Query(alias="range", description="趋势时间窗：24h / 7d / 30d")
    ] = "7d",
) -> OverviewPayload:
    """一次取齐总览页需要的全部数据。

    实例 / 账号 / IP / 指纹来自快照，事件流与趋势来自审计表——这两块是同一批
    查询，所以放在路由里先算好再交给 ``cluster.overview`` 拼装。
    """
    activity = await audit.activity(session, range_key)
    recent = await audit.recent(session, limit=5)
    return cluster_service.overview(snapshot, activity, recent)
