from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.domain import NoVncPayload
from app.services import cluster
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["novnc"])


@router.get("/novnc/{instance_id}", response_model=NoVncPayload, summary="noVNC 会话详情")
async def get_novnc(
    instance_id: str,
    snapshot: Annotated[Snapshot, Depends(get_snapshot)],
) -> NoVncPayload:
    # instance_id 既接受 UUID，也接受实例名（老链接里是 brw-us-west-042 这种）
    return cluster.novnc(snapshot, instance_id)
