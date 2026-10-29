from fastapi import APIRouter

from app.schemas.domain import FingerprintPayload
from app.services import mock_data

router = APIRouter(tags=["fingerprints"])


@router.get("/fingerprints", response_model=FingerprintPayload, summary="指纹模板列表")
async def get_fingerprints() -> FingerprintPayload:
    return mock_data.fingerprints()
