from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.domain import (
    AccountCreateRequest,
    AccountDetail,
    AccountImportRequest,
    AccountImportResult,
    AccountPoolPayload,
    AccountUpdateRequest,
)
from app.services import account_pool, cluster
from app.services.cluster import Snapshot, get_snapshot

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
