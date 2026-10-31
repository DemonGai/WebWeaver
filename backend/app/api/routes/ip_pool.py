from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.domain import IpPoolPayload
from app.services import cluster
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["ip-pool"])


@router.get("/ip-pool", response_model=IpPoolPayload, summary="IP 池资源与健康度")
async def get_ip_pool(snapshot: Annotated[Snapshot, Depends(get_snapshot)]) -> IpPoolPayload:
    return cluster.ip_pool(snapshot)
