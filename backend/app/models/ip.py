"""IP 表：出口代理资源（住宅 / 机房 / 移动）。"""

from datetime import datetime

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import IpKind, IpProtocol, IpStatus


class Ip(IdMixin, TimestampMixin, table=True):
    __tablename__ = "ips"
    __table_args__ = (
        UniqueConstraint("address", "port", name="uq_ips_address_port"),
        {"comment": "IP 表：出口代理资源（住宅 / 机房 / 移动），供浏览器实例绑定"},
    )

    # IPv4/IPv6 均支持，最长 45 字符（IPv6 完整写法）
    address: str = Field(
        max_length=45,
        index=True,
        description="IP 地址",
        sa_column_kwargs={"comment": "IP 地址（IPv4 / IPv6）"},
    )
    port: int = Field(
        default=0,
        ge=0,
        le=65535,
        description="端口，0 表示默认端口",
        sa_column_kwargs={"comment": "代理端口，0 表示使用协议默认端口"},
    )
    protocol: IpProtocol = Field(
        default=IpProtocol.socks5,
        sa_type=enum_type(IpProtocol, 16),
        description="协议：http / https / socks5",
        sa_column_kwargs={"comment": "代理协议：http / https / socks5"},
    )
    kind: IpKind = Field(
        default=IpKind.residential,
        sa_type=enum_type(IpKind, 16),
        index=True,
        description="类型：residential / datacenter / mobile",
        sa_column_kwargs={"comment": "IP 类型：residential 住宅 / datacenter 机房 / mobile 移动"},
    )
    supplier: str = Field(
        max_length=64,
        index=True,
        description="供应商",
        sa_column_kwargs={"comment": "IP 供应商"},
    )
    country_code: str = Field(
        max_length=8,
        description="国家/地区代码，如 US / JP",
        sa_column_kwargs={"comment": "国家或地区代码，如 US / JP"},
    )
    region: str = Field(
        max_length=64,
        description="州/省，如 加利福尼亚",
        sa_column_kwargs={"comment": "州或省，如「加利福尼亚」"},
    )
    city: str = Field(
        max_length=64,
        description="城市",
        sa_column_kwargs={"comment": "城市"},
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="出口时区",
        sa_column_kwargs={"comment": "出口时区"},
    )

    # 代理认证信息。密码按使用方要求明文存：代理密码本来就由供应商分发，
    # 而且前端「复制代理地址」要拼成 socks5://user:pass@host:port 直接用。
    username: str | None = Field(
        default=None,
        max_length=64,
        description="代理账号",
        sa_column_kwargs={"comment": "代理认证账号"},
    )
    password: str | None = Field(
        default=None,
        max_length=128,
        description="代理密码（明文）",
        sa_column_kwargs={"comment": "代理认证密码（明文，供前端复制带认证的地址）"},
    )

    latency_ms: int | None = Field(
        default=None,
        ge=0,
        description="最近一次探测延迟 ms",
        sa_column_kwargs={"comment": "最近一次探测的延迟（毫秒）"},
    )
    health: int = Field(
        default=100,
        ge=0,
        le=100,
        description="健康度 %",
        sa_column_kwargs={"comment": "健康度（百分比）"},
    )
    status: IpStatus = Field(
        default=IpStatus.available,
        sa_type=enum_type(IpStatus, 16),
        index=True,
        description="状态：available / in_use / failed",
        sa_column_kwargs={"comment": "状态：available 可用 / in_use 使用中 / failed 失效"},
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="到期时间，None 表示长期",
        sa_column_kwargs={"comment": "到期时间，为空表示长期有效"},
    )
    last_checked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="最近一次可用性探测时间",
        sa_column_kwargs={"comment": "最近一次可用性探测时间"},
    )
