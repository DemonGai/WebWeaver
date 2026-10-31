"""分组表：浏览器实例、账号、IP 都按分组管理（如「北美店铺」「日本社媒」）。"""

from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import GroupKind


class Group(IdMixin, TimestampMixin, table=True):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_groups_kind_name"),
        {"comment": "分组表：按业务线或店铺划分浏览器、账号与 IP 资源，支持二级分组"},
    )

    # 稳定的业务标识（slug），用于配置、导入导出时引用，改名不影响
    code: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="分组业务标识",
        sa_column_kwargs={"comment": "分组业务标识（唯一 slug，配置与导入导出引用）"},
    )
    name: str = Field(
        max_length=64,
        index=True,
        description="分组名称",
        sa_column_kwargs={"comment": "分组名称（同一类型下唯一）"},
    )
    kind: GroupKind = Field(
        default=GroupKind.browser,
        sa_type=enum_type(GroupKind, 16),
        index=True,
        description="分组类型：browser / account / ip",
        sa_column_kwargs={"comment": "分组类型：browser 浏览器 / account 账号 / ip 代理 IP"},
    )
    # 支持二级分组（如「北美店铺 / 美国站」），顶层为 None
    parent_id: UUID | None = Field(
        default=None,
        foreign_key="groups.id",
        index=True,
        description="上级分组 ID",
        sa_column_kwargs={"comment": "上级分组 ID，为空表示顶级分组"},
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "分组说明"},
    )
    # 前端标签色，形如 #4171f1
    color: str | None = Field(
        default=None,
        max_length=16,
        sa_column_kwargs={"comment": "前端标签颜色，形如 #4171f1"},
    )
    sort_order: int = Field(
        default=0,
        description="列表排序，越小越前",
        sa_column_kwargs={"comment": "排序值，越小越靠前"},
    )
    is_default: bool = Field(
        default=False,
        description="新建资源的默认落点分组",
        sa_column_kwargs={"comment": "是否为默认分组，新建资源默认落入"},
    )
