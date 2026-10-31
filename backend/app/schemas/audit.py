"""审计日志接口的出入参。

字段与 ``audit_logs`` 表一一对应；``occurred_at`` 用 datetime 原样返回，
前端自行按本地时区格式化，不在后端拼「3 分钟前」这类相对文案——
审计时间要能被复制到工单里，相对时间反而不便。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AuditAction, AuditResourceType, AuditResult, AuditSource


class AuditLogItem(BaseModel):
    id: UUID
    occurred_at: datetime
    operator: str
    source: AuditSource
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: UUID | None = None
    resource_name: str | None = None
    result: AuditResult
    detail: str | None = None
    changes: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditLogList(BaseModel):
    items: list[AuditLogItem]
    total: int = Field(description="符合条件的总条数（不受分页限制）")
    limit: int
    offset: int
