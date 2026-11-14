from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.browser import (
    BrowserActionName,
    BrowserBatchResult,
    BrowserCreate,
    BrowserDetail,
    BrowserMutationResult,
    BrowserOptions,
    BrowserUpdate,
)
from app.schemas.domain import BrowserPoolPayload
from app.services import browser_pool, cluster
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["browsers"])


class ActionPayload(BaseModel):
    """单个实例的生命周期动作。"""

    action: BrowserActionName


class BatchPayload(BaseModel):
    """批量动作：ids 上限 200，避免一次请求锁太多行。"""

    ids: list[str] = Field(min_length=1, max_length=200)
    action: BrowserActionName


@router.get("/browsers", response_model=BrowserPoolPayload, summary="浏览器池列表")
async def get_browsers(snapshot: Annotated[Snapshot, Depends(get_snapshot)]) -> BrowserPoolPayload:
    return cluster.browsers(snapshot)


# 顺序很重要：/browsers/options 必须排在 /browsers/{browser_id} 前面，
# 否则 "options" 会被当成实例名去吃详情接口
@router.get("/browsers/options", response_model=BrowserOptions, summary="新建/绑定的候选资源")
async def get_browser_options(
    session: SessionDep,
    browser_id: Annotated[
        str | None,
        Query(description="编辑场景传实例 id：把它已绑定的内核 / 代理保回来，避免保存时被清空"),
    ] = None,
) -> BrowserOptions:
    return await browser_pool.options(session, browser_id)


@router.get("/browsers/{browser_id}", response_model=BrowserDetail, summary="实例详情")
async def get_browser(browser_id: str, session: SessionDep) -> BrowserDetail:
    return await browser_pool.detail(session, browser_id)


@router.post(
    "/browsers",
    response_model=BrowserDetail,
    status_code=status.HTTP_201_CREATED,
    summary="新建实例",
    dependencies=[Depends(require_permission("browser:create"))],
)
async def create_browser(
    payload: BrowserCreate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserDetail:
    return await browser_pool.create(session, payload, operator=user.username, request=request)


@router.patch(
    "/browsers/{browser_id}",
    response_model=BrowserDetail,
    summary="编辑实例 / 绑定资源",
    dependencies=[Depends(require_permission("browser:update"))],
)
async def update_browser(
    browser_id: str,
    payload: BrowserUpdate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserDetail:
    return await browser_pool.update(
        session, browser_id, payload, operator=user.username, request=request
    )


@router.post(
    "/browsers/{browser_id}/duplicate",
    response_model=BrowserDetail,
    status_code=status.HTTP_201_CREATED,
    summary="复制实例（沿用内核与备注，不复制账号 / 出口 / 指纹）",
    dependencies=[Depends(require_permission("browser:create"))],
)
async def duplicate_browser(
    browser_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserDetail:
    return await browser_pool.duplicate(
        session, browser_id, operator=user.username, request=request
    )


@router.delete(
    "/browsers/{browser_id}",
    response_model=BrowserMutationResult,
    summary="删除实例",
    dependencies=[Depends(require_permission("browser:delete"))],
)
async def delete_browser(
    browser_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserMutationResult:
    await browser_pool.remove(session, browser_id, operator=user.username, request=request)
    return BrowserMutationResult(ok=True, message="实例已删除")


@router.post(
    "/browsers/{browser_id}/actions",
    response_model=BrowserMutationResult,
    summary="启动 / 停止 / 重启",
    dependencies=[Depends(require_permission("browser:execute"))],
)
async def run_browser_action(
    browser_id: str,
    payload: ActionPayload,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserMutationResult:
    item = await browser_pool.act(
        session, browser_id, payload.action, operator=user.username, request=request
    )
    return BrowserMutationResult(ok=item.ok, message=item.message)


@router.post(
    "/browsers/batch",
    response_model=BrowserBatchResult,
    summary="批量启动 / 停止 / 重启",
    dependencies=[Depends(require_permission("browser:execute"))],
)
async def run_browser_batch(
    payload: BatchPayload,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> BrowserBatchResult:
    return await browser_pool.batch(
        session, payload.ids, payload.action, operator=user.username, request=request
    )
