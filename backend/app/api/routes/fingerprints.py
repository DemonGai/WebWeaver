from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.domain import FingerprintPayload
from app.services import cluster
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["fingerprints"])


@router.get("/fingerprints", response_model=FingerprintPayload, summary="指纹模板列表")
async def get_fingerprints(
    snapshot: Annotated[Snapshot, Depends(get_snapshot)],
) -> FingerprintPayload:
    return cluster.fingerprints(snapshot)
