from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.domain import (
    FingerprintApplyRequest,
    FingerprintApplyResult,
    FingerprintCreate,
    FingerprintDetailPayload,
    FingerprintInstanceRef,
    FingerprintPayload,
    FingerprintUpdate,
    KernelFingerprintCaps,
)
from app.services import fingerprint_pool
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["fingerprints"])


@router.get("/fingerprints", response_model=FingerprintPayload, summary="指纹池列表")
async def get_fingerprints(
    snapshot: Annotated[Snapshot, Depends(get_snapshot)],
) -> FingerprintPayload:
    return fingerprint_pool.fingerprints(snapshot)


# 和 /browsers/options 同理：/fingerprints/options 必须排在 /{fingerprint_id} 前面，
# 否则 "options" 会被当成指纹 ID 去查详情
@router.get(
    "/fingerprints/capabilities",
    response_model=list[KernelFingerprintCaps],
    summary="各内核的指纹能力",
)
async def get_fingerprint_capabilities(session: SessionDep) -> list[KernelFingerprintCaps]:
    """哪些内核能做指纹、各自的种子范围和认哪些参数。"""
    return await fingerprint_pool.capabilities(session)


@router.get(
    "/fingerprints/options",
    response_model=list[FingerprintInstanceRef],
    summary="下发时可选的实例",
)
async def get_fingerprint_options(session: SessionDep) -> list[FingerprintInstanceRef]:
    return await fingerprint_pool.apply_options(session)


@router.get(
    "/fingerprints/{fingerprint_id}",
    response_model=FingerprintDetailPayload,
    summary="指纹详情",
)
async def get_fingerprint(fingerprint_id: str, session: SessionDep) -> FingerprintDetailPayload:
    return await fingerprint_pool.detail(session, fingerprint_id)


@router.post(
    "/fingerprints",
    response_model=FingerprintDetailPayload,
    status_code=status.HTTP_201_CREATED,
    summary="新建指纹",
    dependencies=[Depends(require_permission("fingerprint:create"))],
)
async def create_fingerprint(
    payload: FingerprintCreate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> FingerprintDetailPayload:
    return await fingerprint_pool.create(session, payload, operator=user.username, request=request)


@router.patch(
    "/fingerprints/{fingerprint_id}",
    response_model=FingerprintDetailPayload,
    summary="编辑指纹",
    dependencies=[Depends(require_permission("fingerprint:update"))],
)
async def update_fingerprint(
    fingerprint_id: str,
    payload: FingerprintUpdate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> FingerprintDetailPayload:
    return await fingerprint_pool.update(
        session, fingerprint_id, payload, operator=user.username, request=request
    )


@router.delete(
    "/fingerprints/{fingerprint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除指纹",
    dependencies=[Depends(require_permission("fingerprint:delete"))],
)
async def delete_fingerprint(
    fingerprint_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    await fingerprint_pool.remove(
        session, fingerprint_id, operator=user.username, request=request
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/fingerprints/{fingerprint_id}/probe",
    response_model=FingerprintDetailPayload,
    summary="采集真实指纹",
    dependencies=[Depends(require_permission("fingerprint:update"))],
)
async def probe_fingerprint(
    fingerprint_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> FingerprintDetailPayload:
    """起一个临时容器按当前参数装配一次人格，把 UA / GPU / 分辨率这些读回来。"""
    return await fingerprint_pool.probe(
        session, fingerprint_id, operator=user.username, request=request
    )


@router.post(
    "/fingerprints/{fingerprint_id}/apply",
    response_model=FingerprintApplyResult,
    summary="下发到实例容器",
    dependencies=[Depends(require_permission("fingerprint:update"))],
)
async def apply_fingerprint(
    fingerprint_id: str,
    payload: FingerprintApplyRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> FingerprintApplyResult:
    """把指纹写成 fingerprint.json 塞进实例容器，再重启容器让它重新装配。"""
    return await fingerprint_pool.apply_to(
        session, fingerprint_id, payload.instance_ids, operator=user.username, request=request
    )
