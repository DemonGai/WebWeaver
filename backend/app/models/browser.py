"""浏览器表：一个浏览器实例（profile + 内核 + 指纹 + 出口 IP + 账号）的组合。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import BrowserStatus, FingerprintMode, IpBindingMode


class Browser(IdMixin, TimestampMixin, table=True):
    __tablename__ = "browsers"
    __table_args__ = (
        # 模式与 id 必须成对出现：直连不指向具体 IP，默认指纹不指向模板
        CheckConstraint(
            "(ip_mode = 'proxy' AND ip_id IS NOT NULL) OR (ip_mode = 'direct' AND ip_id IS NULL)",
            name="ck_browsers_ip_mode_target",
        ),
        CheckConstraint(
            "(fingerprint_mode = 'template' AND fingerprint_id IS NOT NULL) OR "
            "(fingerprint_mode = 'default' AND fingerprint_id IS NULL)",
            name="ck_browsers_fingerprint_mode_target",
        ),
        {"comment": "浏览器表：一个浏览器实例，组合 profile、内核、指纹、出口 IP 与账号"},
    )

    # 实例名即业务标识，如 brw-us-west-042，前端列表直接展示
    name: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="实例名称",
        sa_column_kwargs={"comment": "实例名称（唯一，如 brw-us-west-042）"},
    )
    status: BrowserStatus = Field(
        default=BrowserStatus.stopped,
        sa_type=enum_type(BrowserStatus, 16),
        index=True,
        description="状态：queued / running / idle / error / stopped",
        sa_column_kwargs={
            "comment": "状态：queued 排队 / running 运行中 / idle 空闲 / "
            "error 异常 / stopped 已停止"
        },
    )

    # 关联资源，全部可为空：实例可以先建好再逐个绑定
    group_id: UUID | None = Field(
        default=None,
        foreign_key="groups.id",
        index=True,
        sa_column_kwargs={"comment": "所属分组 ID，为空表示未分组"},
    )
    kernel_id: UUID | None = Field(
        default=None,
        foreign_key="kernels.id",
        index=True,
        sa_column_kwargs={"comment": "使用的内核 ID"},
    )
    # 内核版本与内核分开存：同一个引擎升级后，老实例要能继续留在旧版本上，
    # 直到被批量迁移。为空表示跟随 kernels.version（历史数据的兼容口径）。
    kernel_version: str | None = Field(
        default=None,
        max_length=64,
        description="实例实际使用的内核版本，为空表示跟随内核当前版本",
        sa_column_kwargs={"comment": "实例使用的内核版本，为空表示跟随内核当前版本"},
    )
    fingerprint_mode: FingerprintMode = Field(
        default=FingerprintMode.default,
        sa_type=enum_type(FingerprintMode, 16),
        index=True,
        description="指纹模式：template 套用模板 / default 默认（原生指纹）",
        sa_column_kwargs={
            "comment": "指纹模式：template 套用模板 / default 默认模式（浏览器原生指纹，"
            "不绑定模板）"
        },
    )
    fingerprint_id: UUID | None = Field(
        default=None,
        foreign_key="fingerprints.id",
        index=True,
        sa_column_kwargs={"comment": "绑定的指纹 ID，默认模式下为空"},
    )
    ip_mode: IpBindingMode = Field(
        default=IpBindingMode.direct,
        sa_type=enum_type(IpBindingMode, 16),
        index=True,
        description="出口 IP 模式：proxy 代理 / direct 直连（本机 IP）",
        sa_column_kwargs={
            "comment": "出口 IP 模式：proxy 使用代理 IP / direct 直连（直接使用本机公网 IP）"
        },
    )
    ip_id: UUID | None = Field(
        default=None,
        foreign_key="ips.id",
        index=True,
        sa_column_kwargs={"comment": "绑定的出口 IP 的 ID，直连模式下为空"},
    )
    account_id: UUID | None = Field(
        default=None,
        foreign_key="accounts.id",
        index=True,
        sa_column_kwargs={"comment": "绑定的账号 ID"},
    )

    # 运行时信息
    cdp_url: str | None = Field(
        default=None,
        max_length=255,
        description="Chrome DevTools Protocol 地址",
        sa_column_kwargs={"comment": "Chrome DevTools Protocol 调试地址"},
    )
    vnc_url: str | None = Field(
        default=None,
        max_length=255,
        description="noVNC 会话地址",
        sa_column_kwargs={"comment": "noVNC 远程会话地址"},
    )
    vnc_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="noVNC 端口",
        sa_column_kwargs={"comment": "noVNC 监听端口"},
    )
    fps: int | None = Field(
        default=None,
        ge=0,
        description="当前画面帧率",
        sa_column_kwargs={"comment": "当前画面帧率"},
    )
    latency_ms: int | None = Field(
        default=None,
        ge=0,
        description="操作链路延迟 ms",
        sa_column_kwargs={"comment": "操作链路延迟（毫秒）"},
    )
    started_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="本次启动时间",
        sa_column_kwargs={"comment": "本次启动时间"},
    )
    last_active_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="最近活跃时间",
        sa_column_kwargs={"comment": "最近活跃时间"},
    )

    note: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "备注"},
    )
