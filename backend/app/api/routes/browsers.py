from fastapi import APIRouter

from app.schemas.domain import BrowserPoolPayload
from app.services import mock_data

router = APIRouter(tags=["browsers"])


@router.get("/browsers", response_model=BrowserPoolPayload, summary="浏览器池列表")
async def get_browsers() -> BrowserPoolPayload:
    return mock_data.browsers()
