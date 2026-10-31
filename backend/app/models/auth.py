"""登录会话与密码重置令牌。

两张表都是「短期凭证」，和业务数据放在一起但生命周期不同：

- ``auth_sessions``：一次登录一行，注销/被踢/过期都只改自己的行（``revoked_at``）。
  令牌明文不落库，只存 SHA-256 摘要，见 ``app/core/security.py``。
- ``password_reset_tokens``：一次「忘记密码」一行，用完标记 ``used_at``。
  重置成功时同表顺带把该成员的会话全部吊销——改密码就应该踢掉所有设备。

会话不跟着 ``users`` 走级联删除：成员被删后仍要能查出「谁在什么时候登录过」，
历史留在 ``audit_logs`` 里，这两张表只保留必要的外键约束。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlmodel import Field

from app.models.base import IdMixin, utcnow


class AuthSession(IdMixin, table=True):
    """登录会话：每登录一次生成一行，注销即置 ``revoked_at``。"""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        {"comment": "登录会话表：一次登录一行，令牌只存摘要，注销/过期置 revoked_at"},
    )

    user_id: UUID = Field(
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "成员 ID，指向 users.id"},
    )
    token_hash: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="令牌摘要",
        sa_column_kwargs={"comment": "令牌的 SHA-256 摘要（64 位十六进制，明文不落库）"},
    )
    issued_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "comment": "签发时间（UTC）"},
    )
    expires_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        index=True,
        sa_column_kwargs={"comment": "过期时间（UTC），到期后不再接受该令牌"},
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "吊销时间（UTC），非空表示已失效（注销/改密/被踢）"},
    )
    revoked_reason: str | None = Field(
        default=None,
        max_length=64,
        sa_column_kwargs={
            "comment": "吊销原因：logout 主动注销 / password_reset 改密 / admin 被踢"
        },
    )
    last_seen_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "最近一次使用该令牌的时间（UTC）"},
    )
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        sa_column_kwargs={"comment": "登录时的客户端 IP（IPv4/IPv6）"},
    )
    user_agent: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "登录时的 User-Agent，用于展示登录设备"},
    )


class PasswordResetToken(IdMixin, table=True):
    """密码重置令牌：通过邮件发出的一次性链接，用后即废。"""

    __tablename__ = "password_reset_tokens"
    __table_args__ = ({"comment": "密码重置令牌表：一次性链接，过期或用过即失效"},)

    user_id: UUID = Field(
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "成员 ID，指向 users.id"},
    )
    token_hash: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="令牌摘要",
        sa_column_kwargs={"comment": "令牌的 SHA-256 摘要（64 位十六进制，明文不落库）"},
    )
    expires_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        index=True,
        sa_column_kwargs={"comment": "过期时间（UTC），默认 30 分钟"},
    )
    used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "使用时间（UTC），非空表示该链接已用过"},
    )
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        sa_column_kwargs={"comment": "申请重置时的客户端 IP"},
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "comment": "申请时间（UTC）"},
    )
