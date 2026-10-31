from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.domain import AccountPoolPayload
from app.services import cluster
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=AccountPoolPayload, summary="账号池列表")
async def get_accounts(snapshot: Annotated[Snapshot, Depends(get_snapshot)]) -> AccountPoolPayload:
    return cluster.accounts(snapshot)
