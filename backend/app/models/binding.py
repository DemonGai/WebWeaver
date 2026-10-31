"""绑定记录表：账号 / IP / 指纹 到浏览器的绑定操作日志。

**定位**：日志而非关系表。浏览器表上的 ``account_id`` / ``ip_id`` / ``fingerprint_id``
保存「当前生效值」，这三张表保存每一次操作的流水——只追加、不修改，
用于审计与追溯（谁、什么时候、从哪发起、把什么绑到了哪个实例）。

**默认模式**：IP 与指纹都允许「不指向具体资源」的默认取值，这两条是产品上的
正常状态，不是「未绑定」：

- IP ``direct`` 直连：不经过代理，直接用本机公网 IP 出网，``ip_id`` 为空；
- 指纹 ``default`` 默认模式：不套模板，用浏览器与系统原生指纹，``fingerprint_id`` 为空。

所以日志里的 ``mode`` 与资源 ID 必须成对：``CHECK`` 约束保证
「``direct`` ⇒ ``ip_id`` 为空」与「``proxy`` ⇒ ``ip_id`` 非空」，指纹同理。
切回代理 / 模板时再落一条 ``action=bind`` 的记录即可，历史不会丢。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, func
from sqlmodel import Field, SQLModel

from app.models.base import IdMixin, enum_type, utcnow
from app.models.enums import BindingAction, BindingSource, FingerprintMode, IpBindingMode


class BrowserBindingLogBase(SQLModel):
    """三张日志表的公共列。

    只有 ``created_at`` 没有 ``updated_at``：日志一旦写入就不可变，
    改一条日志的语义应当是再追加一条，而不是覆盖。
    """

    browser_id: UUID = Field(
        foreign_key="browsers.id",
        description="浏览器实例 ID",
        sa_column_kwargs={"comment": "浏览器实例 ID，指向 browsers.id"},
    )
    action: BindingAction = Field(
        sa_type=enum_type(BindingAction, 16),
        index=True,
        description="动作：bind / unbind",
        sa_column_kwargs={"comment": "操作动作：bind 绑定 / unbind 解绑"},
    )
    operator: str = Field(
        default="system",
        max_length=64,
        description="操作人",
        sa_column_kwargs={"comment": "操作人（用户名或服务名），默认 system"},
    )
    source: BindingSource = Field(
        default=BindingSource.manual,
        sa_type=enum_type(BindingSource, 16),
        description="发起来源：manual / api / scheduler / bulk",
        sa_column_kwargs={
            "comment": "发起来源：manual 人工 / api 接口 / scheduler 调度器 / bulk 批量导入"
        },
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "备注，记录操作原因等"},
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        description="操作时间",
        sa_column_kwargs={"server_default": func.now(), "comment": "操作时间（UTC）"},
    )


class BrowserAccountBinding(BrowserBindingLogBase, IdMixin, table=True):
    __tablename__ = "browser_account_bindings"
    __table_args__ = (
        Index("ix_browser_account_bindings_browser_time", "browser_id", "created_at"),
        {"comment": "账号绑定日志：账号与浏览器之间的绑定、解绑流水，只追加不修改"},
    )

    account_id: UUID = Field(
        foreign_key="accounts.id",
        index=True,
        description="账号 ID",
        sa_column_kwargs={"comment": "账号 ID，指向 accounts.id（解绑记录记被解绑的账号）"},
    )


class BrowserIpBinding(BrowserBindingLogBase, IdMixin, table=True):
    __tablename__ = "browser_ip_bindings"
    __table_args__ = (
        CheckConstraint(
            "(mode = 'proxy' AND ip_id IS NOT NULL) OR (mode = 'direct' AND ip_id IS NULL)",
            name="ck_browser_ip_bindings_mode_target",
        ),
        Index("ix_browser_ip_bindings_browser_time", "browser_id", "created_at"),
        {"comment": "IP 绑定日志：浏览器出口 IP 的代理绑定与直连切换流水，只追加不修改"},
    )

    mode: IpBindingMode = Field(
        default=IpBindingMode.proxy,
        sa_type=enum_type(IpBindingMode, 16),
        index=True,
        description="模式：proxy 代理 IP / direct 直连（本机 IP）",
        sa_column_kwargs={
            "comment": "本次操作的出口模式：proxy 代理 IP / direct 直连（本机公网 IP）"
        },
    )
    ip_id: UUID | None = Field(
        default=None,
        foreign_key="ips.id",
        index=True,
        sa_column_kwargs={"comment": "代理 IP 的 ID，指向 ips.id；直连模式下为空"},
    )
    # 直连时没有 IP 记录，靠这个字段留下当时实际出网地址的快照
    resolved_address: str | None = Field(
        default=None,
        max_length=45,
        description="出口地址快照",
        sa_column_kwargs={"comment": "操作时的出口地址快照：直连为本机公网 IP，代理为代理地址"},
    )


class BrowserFingerprintBinding(BrowserBindingLogBase, IdMixin, table=True):
    __tablename__ = "browser_fingerprint_bindings"
    __table_args__ = (
        CheckConstraint(
            "(mode = 'template' AND fingerprint_id IS NOT NULL) OR "
            "(mode = 'default' AND fingerprint_id IS NULL)",
            name="ck_browser_fingerprint_bindings_mode_target",
        ),
        Index("ix_browser_fingerprint_bindings_browser_time", "browser_id", "created_at"),
        {"comment": "指纹绑定日志：浏览器指纹模板与默认模式的切换流水，只追加不修改"},
    )

    mode: FingerprintMode = Field(
        default=FingerprintMode.template,
        sa_type=enum_type(FingerprintMode, 16),
        index=True,
        description="模式：template 套用模板 / default 默认（原生指纹）",
        sa_column_kwargs={
            "comment": "本次操作的指纹模式：template 套用模板 / default 默认（原生指纹）"
        },
    )
    fingerprint_id: UUID | None = Field(
        default=None,
        foreign_key="fingerprints.id",
        index=True,
        sa_column_kwargs={"comment": "指纹模板的 ID，指向 fingerprints.id；默认模式下为空"},
    )
