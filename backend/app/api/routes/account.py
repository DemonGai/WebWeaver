"""账号菜单浮层接口"""

from fastapi import APIRouter

from app.schemas.kernels import AccountMenu
from app.services import kernel_data

router = APIRouter(tags=["account"])


@router.get("/account/menu", response_model=AccountMenu, summary="头像菜单浮层数据")
def get_account_menu() -> AccountMenu:
    return kernel_data.account_menu()
