"""内核管理接口（引擎维度）。

四个引擎固定，不支持"接入新内核"；能变的只有版本——
版本由磁盘目录决定，接口只负责扫描、切当前版本、把实例批量迁到新版本。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.models import AuditAction, AuditResourceType
from app.schemas.kernels import (
    InstallJob,
    InstallRequest,
    KernelDetailPayload,
    KernelInstance,
    KernelPayload,
    MigrationRequest,
    MigrationResult,
    PrimaryResponse,
    VersionSwitchRequest,
)
from app.services import audit, kernel_install, kernel_pool

router = APIRouter(tags=["kernels"])


@router.get("/kernels", response_model=KernelPayload, summary="内核引擎与磁盘版本")
async def get_kernels(session: SessionDep) -> KernelPayload:
    return await kernel_pool.payload(session)


@router.post(
    "/kernels/rescan",
    response_model=KernelPayload,
    summary="重新扫描内核目录",
)
async def rescan_kernels(session: SessionDep) -> KernelPayload:
    # 扫描是只读操作：不写审计，避免刷新页面把审计刷满
    return await kernel_pool.payload(session)


# tips: 这两条必须排在 /kernels/{slug} 之前，否则 "jobs" 会被当成 slug 匹配掉
@router.get(
    "/kernels/jobs",
    response_model=list[InstallJob],
    summary="内核获取任务列表",
)
async def list_install_jobs() -> list[InstallJob]:
    return kernel_install.jobs()


@router.get(
    "/kernels/jobs/{job_id}",
    response_model=InstallJob,
    summary="单个获取任务进度",
)
async def get_install_job(job_id: str) -> InstallJob:
    item = kernel_install.job(job_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在，可能是服务重启后丢了",
        )
    return item


@router.get(
    "/kernels/{slug}",
    response_model=KernelDetailPayload,
    summary="引擎详情：档案 + 磁盘状态 + 正文",
)
async def kernel_detail(slug: str, session: SessionDep) -> KernelDetailPayload:
    return await kernel_pool.detail(session, slug)


@router.post(
    "/kernels/{slug}/install",
    response_model=InstallJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="按档案里的下载源获取一个版本（pip / archive）",
    dependencies=[Depends(require_permission("kernel:update"))],
)
async def install_kernel_version(
    slug: str,
    payload: InstallRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> InstallJob:
    # 先写审计再开工：审计失败就直接返回，不留一个悄悄在跑的后台任务
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.kernel,
        resource_id=slug,
        operator=user.username,
        detail=f"获取内核 {slug} {payload.version}",
        request=request,
    )

    try:
        return await kernel_install.start(slug, payload.version, payload.os, payload.arch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/kernels/{kernel_id}/instances",
    response_model=list[KernelInstance],
    summary="内核下的实例清单（批量迁移候选）",
)
async def kernel_instances(
    kernel_id: str,
    session: SessionDep,
    stale: Annotated[bool, Query(description="只看不在当前版本上的实例")] = False,
    version: Annotated[str | None, Query(description="只看指定版本")] = None,
) -> list[KernelInstance]:
    return await kernel_pool.instances(session, kernel_id, stale=stale, version=version)


@router.post(
    "/kernels/{kernel_id}/version",
    response_model=KernelPayload,
    summary="切换当前版本（旧版本目录保留）",
    dependencies=[Depends(require_permission("kernel:update"))],
)
async def switch_kernel_version(
    kernel_id: str,
    payload: VersionSwitchRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> KernelPayload:
    return await kernel_pool.switch_version(
        session,
        kernel_id,
        payload.version,
        operator=user.username,
        request=request,
    )


@router.post(
    "/kernels/{kernel_id}/migrate",
    response_model=MigrationResult,
    summary="把实例批量迁移到指定版本",
    dependencies=[Depends(require_permission("kernel:update"))],
)
async def migrate_kernel_version(
    kernel_id: str,
    payload: MigrationRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> MigrationResult:
    return await kernel_pool.migrate(
        session,
        kernel_id,
        payload.version,
        payload.browser_ids,
        operator=user.username,
        request=request,
    )


@router.post(
    "/kernels/{kernel_id}/primary",
    response_model=PrimaryResponse,
    summary="设为主力内核",
    dependencies=[Depends(require_permission("kernel:update"))],
)
async def set_primary(
    kernel_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> PrimaryResponse:
    return await kernel_pool.set_primary(
        session,
        kernel_id,
        operator=user.username,
        request=request,
    )
