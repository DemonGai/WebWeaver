"""审计日志查询接口（只读）。

日志由业务侧通过 ``services.audit.record`` 写入，接口层不提供新增 / 修改 / 删除：
审计表对外是纯账本，允许前端删记录等于允许销毁证据。
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.enums import AuditAction, AuditResourceType, AuditResult
from app.schemas.audit import AuditLogItem, AuditLogList
from app.services import audit

router = APIRouter(tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/audit-logs", response_model=AuditLogList, summary="审计日志列表")
async def get_audit_logs(
    session: SessionDep,
    action: Annotated[AuditAction | None, Query(description="按动作筛选")] = None,
    resource_type: Annotated[AuditResourceType | None, Query(description="按资源类型筛选")] = None,
    resource_id: Annotated[UUID | None, Query(description="按资源 ID 筛选")] = None,
    operator: Annotated[str | None, Query(description="按操作人筛选")] = None,
    result: Annotated[AuditResult | None, Query(description="按结果筛选")] = None,
    since: Annotated[datetime | None, Query(description="起始时间（含）")] = None,
    until: Annotated[datetime | None, Query(description="截止时间（含）")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="每页条数")] = 50,
    offset: Annotated[int, Query(ge=0, description="偏移量")] = 0,
) -> AuditLogList:
    rows, total = await audit.list_logs(
        session,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        operator=operator,
        result=result,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return AuditLogList(
        items=[AuditLogItem.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
