"""账号表：各登录站点上的店铺 / 社媒账号。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import AccountStatus


class Account(IdMixin, TimestampMixin, table=True):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("login_url", "username", name="uq_accounts_login_url_username"),
        {"comment": "账号表：按登录页地址归属，可绑定浏览器实例"},
    )

    # 账号不绑平台，绑的是登录页面。平台由这个地址推导（services/platforms.py），
    # 用户不需要也不应该手选——同一家平台在不同国家站点是不同的登录页
    login_url: str | None = Field(
        default=None,
        max_length=512,
        index=True,
        description="登录页地址，平台由它推导",
        sa_column_kwargs={"comment": "登录页地址；平台由域名推导，不单独指定"},
    )
    # Amazon / TikTok / Facebook ... 由 login_url 推导出来的展示值，用于筛选用
    platform: str = Field(
        max_length=64,
        index=True,
        description="由登录地址推导出的平台",
        sa_column_kwargs={"comment": "由登录地址推导的平台，如 Amazon / TikTok（不手工指定）"},
    )
    username: str = Field(
        max_length=128,
        description="登录名",
        sa_column_kwargs={"comment": "登录名（与登录页地址联合唯一）"},
    )
    email: str | None = Field(
        default=None,
        max_length=255,
        index=True,
        description="绑定邮箱",
        sa_column_kwargs={"comment": "绑定邮箱"},
    )
    # 明文密码不入库，统一存密文（对称加密，密钥走环境变量）
    password_encrypted: str | None = Field(
        default=None,
        max_length=512,
        description="登录密码（加密存储）",
        sa_column_kwargs={"comment": "登录密码（加密存储，不落明文）"},
    )
    # Cookie 是登录态凭证，不同平台字段差异很大（expires 有的是秒级时间戳、
    # 有的是 ISO 串，还有平台带额外字段），建宽表会让大半列长期为空，
    # 因此整份存 JSON，结构对齐 Playwright storage_state 的 cookies 数组。
    # 注意：这份数据等价于「已登录」，接口层默认不返回（当前列表接口不含该字段）。
    cookies: list[dict[str, Any]] | None = Field(
        default=None,
        sa_type=JSONB,
        description="登录态 Cookie 列表（Playwright storage_state.cookies 结构）",
        sa_column_kwargs={
            "comment": (
                "登录态 Cookie（JSONB 数组）：元素含 name/value/domain/path/expires/"
                "httpOnly/secure/sameSite；为空表示尚未采集"
            )
        },
    )
    status: AccountStatus = Field(
        default=AccountStatus.unbound,
        sa_type=enum_type(AccountStatus, 16),
        index=True,
        description="状态：logged_in / in_session / restricted / unbound",
        sa_column_kwargs={
            "comment": "状态：logged_in 已登录 / in_session 会话中 / "
            "restricted 受限 / unbound 未绑定"
        },
    )
    region: str = Field(
        default="",
        max_length=64,
        description="注册地 / 归属区域",
        sa_column_kwargs={"comment": "注册地或归属区域"},
    )
    health: int = Field(
        default=100,
        ge=0,
        le=100,
        description="账号健康度 %",
        sa_column_kwargs={"comment": "账号健康度（百分比）"},
    )
    registered_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="注册时间",
        sa_column_kwargs={"comment": "注册时间"},
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="最近登录时间",
        sa_column_kwargs={"comment": "最近登录时间"},
    )
    # 账号也可以分组（如「日本社媒」），为空表示未分组
    group_id: UUID | None = Field(
        default=None,
        foreign_key="groups.id",
        index=True,
        description="所属分组 ID",
        sa_column_kwargs={"comment": "所属分组 ID，为空表示未分组"},
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "备注"},
    )
