from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.domain import (
    AccountCreateRequest,
    AccountDetail,
    AccountImportRequest,
    AccountImportResult,
    AccountPoolPayload,
    AccountUpdateRequest,
    PlatformDetection,
)
from app.services import account_pool, cluster
from app.services.cluster import Snapshot, get_snapshot
from app.services.platforms import InvalidLoginUrl, detect_platform, normalize_login_url

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=AccountPoolPayload, summary="账号管理列表")
async def get_accounts(snapshot: Annotated[Snapshot, Depends(get_snapshot)]) -> AccountPoolPayload:
    return cluster.accounts(snapshot)


# 静态路径要排在 /accounts/{account_id} 前面，否则 template 会被当成 ID
@router.get("/accounts/template", summary="下载账号导入模板")
async def download_template() -> Response:
    return Response(
        content=account_pool.account_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="account-import-template.csv"'},
    )


@router.get("/accounts/detect", response_model=PlatformDetection, summary="从登录地址识别平台")
async def detect(login_url: str) -> PlatformDetection:
    """填地址时即时回显「这是哪家平台」，前端不用再抄一份域名映射。"""
    try:
        platform, known = detect_platform(login_url)
        normalized = normalize_login_url(login_url)
    except InvalidLoginUrl as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PlatformDetection(login_url=normalized, platform=platform, known=known)


@router.post(
    "/accounts/import",
    response_model=AccountImportResult,
    summary="批量导入账号",
    dependencies=[Depends(require_permission("account:create"))],
)
async def import_accounts(
    payload: AccountImportRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> AccountImportResult:
    return await account_pool.import_accounts(
        session, payload, operator=user.username, request=request
    )


@router.get("/accounts/{account_id}", response_model=AccountDetail, summary="账号详情（含 Cookie）")
async def get_account(account_id: UUID, session: SessionDep) -> AccountDetail:
    return await account_pool.get_detail(session, account_id)


@router.post(
    "/accounts",
    response_model=AccountDetail,
    status_code=201,
    summary="新建账号",
    dependencies=[Depends(require_permission("account:create"))],
)
async def create_account(
    payload: AccountCreateRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> AccountDetail:
    account_id = await account_pool.create_account(
        session, payload, operator=user.username, request=request
    )
    return await account_pool.get_detail(session, UUID(account_id))


@router.patch(
    "/accounts/{account_id}",
    status_code=204,
    summary="编辑账号",
    dependencies=[Depends(require_permission("account:update"))],
)
async def update_account(
    account_id: UUID,
    payload: AccountUpdateRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    await account_pool.update_account(
        session, account_id, payload, operator=user.username, request=request
    )
    return Response(status_code=204)
