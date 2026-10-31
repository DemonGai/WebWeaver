r"""模型公共部分：UUID 主键、时间戳混入。

主键一律使用应用侧生成的 UUID（``uuid4``），不使用数据库自增 ID：
- 分布式/多实例部署时不会撞号，也不暴露数据量；
- 可以在写库前就把 ID 交给前端或其它服务。

注释约定：每个字段都通过 ``sa_column_kwargs={"comment": ...}`` 写入数据库注释，
``psql \d+`` 或 ``information_schema`` 里能直接看到中文说明。
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """带时区的当前时间（统一存 UTC，展示时再转本地时区）。"""
    return datetime.now(UTC)


def enum_type(enum_cls: type[StrEnum], length: int = 16) -> SAEnum:
    """枚举字段统一落成 VARCHAR + CHECK 约束。

    不用 PostgreSQL 原生 enum：原生类型加值必须 ALTER TYPE，改起来麻烦。
    ``values_callable`` 保证存的是枚举值（与前端字符串一致），回读时自动转回枚举成员。
    每次调用都新建实例，避免多个模型共用同一个类型对象。
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        create_constraint=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class IdMixin(SQLModel):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        sa_column_kwargs={"comment": "主键，应用侧生成的 UUID（非自增）"},
    )


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "comment": "创建时间（UTC）"},
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "comment": "最后更新时间（UTC）",
        },
    )
