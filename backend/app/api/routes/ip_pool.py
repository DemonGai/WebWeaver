from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.domain import (
    IpCheckResult,
    IpImportRequest,
    IpImportResult,
    IpPoolPayload,
)
from app.services import cluster, ip_pool
from app.services.cluster import Snapshot, get_snapshot

router = APIRouter(tags=["ip-pool"])


@router.get("/ip-pool", response_model=IpPoolPayload, summary="代理资源与健康度")
async def get_ip_pool(snapshot: Annotated[Snapshot, Depends(get_snapshot)]) -> IpPoolPayload:
    return cluster.ip_pool(snapshot)


# 放在 /ip-pool 之后但没有路径参数冲突：以后真加了 /ip-pool/{id}，
# 这条必须保持在它前面，否则 "template" 会被当成资源 ID
@router.get("/ip-pool/template", summary="下载导入模板")
async def download_template() -> Response:
    """导入模板：一行一个代理，列序就是解析器认的顺序。"""
    return Response(
        content=ip_pool.template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ip-import-template.csv"'},
    )


@router.post(
    "/ip-pool/import",
    response_model=IpImportResult,
    summary="批量导入代理",
    dependencies=[Depends(require_permission("ip:create"))],
)
async def import_ips(
    payload: IpImportRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> IpImportResult:
    """把供应商给的清单粘进来批量入库，返回逐行的失败原因。"""
    return await ip_pool.import_many(
        session, payload, operator=user.username, request=request
    )


@router.post(
    "/ip-pool/check",
    response_model=IpCheckResult,
    summary="检测代理端口可达性",
    dependencies=[Depends(require_permission("ip:update"))],
)
async def check_ips(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> IpCheckResult:
    """对全部代理跑一轮 TCP 探测，回写延迟与健康度。"""
    return await ip_pool.check_all(session, operator=user.username, request=request)
