"""审计日志表：横向记录「谁、什么时候、对哪个资源、做了什么、结果如何」。

**与三张绑定日志的区别**：绑定表是业务流水，只回答「账号 / IP / 指纹 什么时候
挂到了哪个浏览器」；审计表是全局账本，覆盖创建、修改、删除、绑定、启停、登录、
导出等所有敏感动作，既能回答「这个实例是谁改的」，也能回答「谁重置了管理员密码」。

**两条设计取舍**：

1. ``resource_id`` 故意**不建外键**。审计记录必须在资源被删除之后依然可读，
   外键会把历史绑死在当前数据上；资源的名字以快照形式存进 ``resource_name``，
   所以即便 ``browsers`` 里已经没有这一行，也能看出当时操作的是哪个实例。
2. **只追加不修改**。没有 ``updated_at``，写错了应当是再记一条更正记录，
   而不是覆盖原记录——否则审计本身就不再有证明力。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import IdMixin, enum_type, utcnow
from app.models.enums import AuditAction, AuditResourceType, AuditResult, AuditSource


class AuditLog(IdMixin, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # 「某资源的历史」是最常见的查询路径：先按类型再按 ID 过滤
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        # 「某个人最近做了什么」：按操作人 + 时间倒序翻页
        Index("ix_audit_logs_operator_time", "operator", "occurred_at"),
        {
            "comment": "审计日志：全量写操作留痕，记录操作人、动作、对象、结果与变更内容，"
            "只追加不修改"
        },
    )

    occurred_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        index=True,
        description="操作发生时间",
        sa_column_kwargs={"server_default": func.now(), "comment": "操作发生时间（UTC）"},
    )

    # ── 谁 ────────────────────────────────────────────────
    operator: str = Field(
        default="system",
        max_length=64,
        description="操作人",
        sa_column_kwargs={"comment": "操作人（用户名或服务名），内部任务为 system"},
    )
    source: AuditSource = Field(
        default=AuditSource.api,
        sa_type=enum_type(AuditSource, 16),
        description="发起渠道：manual / api / scheduler / bulk / system",
        sa_column_kwargs={
            "comment": "发起渠道：manual 人工 / api 接口 / scheduler 调度器 / "
            "bulk 批量导入 / system 内部任务"
        },
    )

    # ── 做了什么 ──────────────────────────────────────────
    action: AuditAction = Field(
        sa_type=enum_type(AuditAction, 16),
        index=True,
        description="动作：create / update / delete / bind / start / login …",
        sa_column_kwargs={
            "comment": "动作：create 新建 / update 修改 / delete 删除 / bind 绑定 / "
            "unbind 解绑 / start 启动 / stop 停止 / login 登录 / logout 登出 / "
            "reset_password 重置密码 / export 导出 / import 导入"
        },
    )
    resource_type: AuditResourceType = Field(
        sa_type=enum_type(AuditResourceType, 16),
        index=True,
        description="资源类型：browser / account / ip / fingerprint / …",
        sa_column_kwargs={
            "comment": "资源类型：browser 浏览器 / account 账号 / ip 代理 IP / "
            "fingerprint 指纹 / kernel 内核 / group 分组 / binding 绑定关系 / "
            "auth 认证 / system 系统"
        },
    )
    # 不建外键：资源删除后审计仍要能查（见模块说明）
    resource_id: UUID | None = Field(
        default=None,
        index=True,
        sa_column_kwargs={
            "comment": "被操作资源的 ID（逻辑引用，不建外键：资源删除后审计仍可追溯）"
        },
    )
    resource_name: str | None = Field(
        default=None,
        max_length=128,
        description="资源名称快照",
        sa_column_kwargs={"comment": "操作时的资源名称快照，避免资源改名或删除后无法辨认"},
    )

    # ── 结果 ──────────────────────────────────────────────
    result: AuditResult = Field(
        default=AuditResult.success,
        sa_type=enum_type(AuditResult, 16),
        index=True,
        description="结果：success / failure",
        sa_column_kwargs={"comment": "操作结果：success 成功 / failure 失败"},
    )
    detail: str | None = Field(
        default=None,
        max_length=500,
        sa_column_kwargs={"comment": "操作摘要（人可读，一句话说明做了什么）"},
    )
    # 变更前后快照：{"field": {"before": ..., "after": ...}}，只存变化过的字段
    changes: dict[str, Any] | None = Field(
        default=None,
        sa_type=JSONB,
        description="变更前后快照",
        sa_column_kwargs={
            "comment": ('变更快照 JSONB：{"字段": {"before": 旧值, "after": 新值}}，只存变化的字段')
        },
    )
    error_message: str | None = Field(
        default=None,
        max_length=500,
        sa_column_kwargs={"comment": "失败原因，result 为 failure 时填写"},
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        sa_column_kwargs={"comment": "操作耗时（毫秒），用于排查慢操作"},
    )

    # ── 来源链路 ──────────────────────────────────────────
    request_id: str | None = Field(
        default=None,
        max_length=64,
        index=True,
        sa_column_kwargs={"comment": "请求 ID，与请求日志（X-Request-ID）对应"},
    )
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        sa_column_kwargs={"comment": "发起操作的客户端 IP（IPv6 最长 45 字符）"},
    )
    user_agent: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "客户端 User-Agent"},
    )
