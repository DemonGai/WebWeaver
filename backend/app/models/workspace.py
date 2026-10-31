"""工作区表：一套资源（实例 / 账号 / IP）的隔离边界。

为什么单独建表而不是在 ``users`` 上放一个字符串：工作区要有稳定编码、
展示名、备注和成员数，字符串一改历史数据就对不上。成员与工作区的关系
目前按需求做成「每人一个默认工作区」（``users.default_workspace_id``），
以后要支持一人多工作区时再加 ``user_workspaces`` 关联表，
把 ``default_workspace_id`` 当作其中一个标记即可，不需要改这张表。
"""

from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin


class Workspace(IdMixin, TimestampMixin, table=True):
    __tablename__ = "workspaces"
    __table_args__ = ({"comment": "工作区表：资源隔离边界，每个成员有一个默认工作区"},)

    # 稳定标识，登录 / 找回密码 / 审计里都引用它，改名不影响
    code: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="工作区业务标识",
        sa_column_kwargs={"comment": "工作区业务标识（唯一 slug，配置与审计引用）"},
    )
    name: str = Field(
        max_length=64,
        index=True,
        description="工作区展示名",
        sa_column_kwargs={"comment": "工作区展示名"},
    )
    note: str | None = Field(
        default=None,
        max_length=128,
        sa_column_kwargs={"comment": "工作区备注，浮层里作为副标题展示"},
    )
    sort_order: int = Field(
        default=0,
        description="列表排序，越小越前",
        sa_column_kwargs={"comment": "排序值，越小越靠前"},
    )
