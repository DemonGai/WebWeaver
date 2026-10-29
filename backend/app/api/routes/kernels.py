"""内核管理接口（引擎维度）"""

from fastapi import APIRouter

from app.schemas.kernels import (
    KernelEnginePayload,
    PrimaryResponse,
    UpgradeOptions,
    UpgradeRequest,
    UpgradeResponse,
)
from app.services import kernel_data

router = APIRouter(tags=["kernels"])


@router.get("/kernels", response_model=KernelEnginePayload, summary="内核引擎列表与统计")
def get_kernels() -> KernelEnginePayload:
    return kernel_data.kernel_payload()


@router.post("/kernels/{kernel_id}/primary", response_model=PrimaryResponse, summary="设为主力内核")
def set_primary(kernel_id: str) -> PrimaryResponse:
    ok = kernel_data.set_primary(kernel_id)
    if not ok:
        return PrimaryResponse(
            ok=False,
            primary_id=kernel_data.PRIMARY_ID,
            message="内核不存在，请刷新页面",
        )

    engine = next(e for e in kernel_data.kernel_payload().engines if e.id == kernel_id)
    return PrimaryResponse(
        ok=True,
        primary_id=kernel_id,
        message=f"{engine.name} 已设为主力内核，新建实例将默认使用该引擎",
    )


@router.get("/kernels/upgrade-options", response_model=UpgradeOptions, summary="内核切换任务选项")
def get_upgrade_options() -> UpgradeOptions:
    return kernel_data.upgrade_options()


@router.post("/kernels/upgrade", response_model=UpgradeResponse, summary="创建内核切换任务")
def create_upgrade(payload: UpgradeRequest) -> UpgradeResponse:
    options = kernel_data.upgrade_options()
    kernel = next((k for k in options.kernels if k.id == payload.kernel_id), None)

    if kernel is None:
        return UpgradeResponse(
            ok=False,
            task_id="",
            kernel="",
            targets=0,
            batch=payload.batch,
            interval=payload.interval,
            eta="",
            message="目标内核不存在，请重新选择",
        )

    if kernel.disabled:
        return UpgradeResponse(
            ok=False,
            task_id="",
            kernel=kernel.name,
            targets=0,
            batch=payload.batch,
            interval=payload.interval,
            eta="",
            message="该内核仍在下载中，暂不可用于切换",
        )

    if payload.scope == "group" and not payload.groups:
        return UpgradeResponse(
            ok=False,
            task_id="",
            kernel=kernel.name,
            targets=0,
            batch=payload.batch,
            interval=payload.interval,
            eta="",
            message="请至少选择一个实例分组",
        )

    chosen = [g for g in options.groups if g.id in payload.groups]
    targets = sum(g.count for g in chosen) if chosen else 24

    return UpgradeResponse(
        ok=True,
        task_id="upg-1280",
        kernel=kernel.name,
        targets=targets,
        batch=payload.batch,
        interval=payload.interval,
        eta=options.eta,
        message=f"已创建切换任务，{targets} 台实例将迁移至 {kernel.name}",
    )
