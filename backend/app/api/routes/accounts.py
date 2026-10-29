from fastapi import APIRouter

from app.schemas.domain import AccountPoolPayload
from app.services import mock_data

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=AccountPoolPayload, summary="账号池列表")
async def get_accounts() -> AccountPoolPayload:
    return mock_data.accounts()
