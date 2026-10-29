from fastapi import APIRouter

from app.schemas.domain import IpPoolPayload
from app.services import mock_data

router = APIRouter(tags=["ip-pool"])


@router.get("/ip-pool", response_model=IpPoolPayload, summary="IP 池资源与健康度")
async def get_ip_pool() -> IpPoolPayload:
    return mock_data.ip_pool()
