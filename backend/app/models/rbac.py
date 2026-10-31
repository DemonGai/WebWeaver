"""RBAC：成员、角色、权限点，以及两张映射表。

**为什么不用数据库扩展**：官方 ``postgres`` 镜像自带的扩展里没有任何 RBAC 实现
（``pg_available_extensions`` 只有 pgcrypto / ltree / pg_trgm 这类通用件）；
社区那个 ``pg-rbac`` 管的是 schema 级对象权限，需要自编译进镜像，且不覆盖
「控制台成员 → 角色 → 权限点」这层，所以这里按业务表自己建模。

**模型**（标准 RBAC，用户 - 角色 - 权限 三张主表 + 两张映射表）::

    users ──< user_roles >── roles ──< role_permissions >── permissions

- 权限点用「模块:动作」编码（``browser:read``），角色是权限点的集合，
  成员通过角色间接拿到权限；不给成员直接挂权限，避免出现无法审计的例外。
- 两张映射表各自有独立 UUID 主键，另加唯一约束防止重复授权
  （主键不用复合键是项目约定：所有表都是单列 UUID 主键）。
- ``User`` 是**控制台成员**，与平台账号 ``Account``（Amazon / TikTok 账号）无关。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type, utcnow
from app.models.enums import RbacAction, RbacModule, UserStatus


class Role(IdMixin, TimestampMixin, table=True):
    __tablename__ = "roles"
    __table_args__ = ({"comment": "角色表：权限点的集合，成员通过角色获得权限"},)

    code: str = Field(
        max_length=32,
        unique=True,
        index=True,
        description="角色编码",
        sa_column_kwargs={"comment": "角色编码（唯一）：owner / admin / operator / viewer"},
    )
    name: str = Field(
        max_length=64,
        description="角色名称",
        sa_column_kwargs={"comment": "角色名称（展示用中文名）"},
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "角色说明：这个角色能做什么"},
    )
    # 内置角色不允许删除/改编码，避免把 owner 删掉后无人能管系统
    is_system: bool = Field(
        default=False,
        description="是否内置角色",
        sa_column_kwargs={"comment": "是否内置角色：内置角色不可删除、不可改编码"},
    )
    sort_order: int = Field(
        default=0,
        description="排序值",
        sa_column_kwargs={"comment": "排序值，越小越靠前"},
    )


class Permission(IdMixin, table=True):
    """权限点目录：由代码定义、随迁移初始化，不在界面上随意增删。"""

    __tablename__ = "permissions"
    __table_args__ = ({"comment": "权限点表：模块与动作的组合，如 browser:read"},)

    code: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="权限编码",
        sa_column_kwargs={"comment": "权限编码（唯一），格式「模块:动作」，如 browser:read"},
    )
    name: str = Field(
        max_length=64,
        description="权限名称",
        sa_column_kwargs={"comment": "权限名称（展示用中文名，如「查看浏览器」）"},
    )
    module: RbacModule = Field(
        sa_type=enum_type(RbacModule, 16),
        index=True,
        description="所属模块",
        sa_column_kwargs={
            "comment": "所属模块：browser / account / ip / fingerprint / kernel / "
            "group / audit / user / role"
        },
    )
    action: RbacAction = Field(
        sa_type=enum_type(RbacAction, 16),
        index=True,
        description="动作",
        sa_column_kwargs={
            "comment": "动作：read 查看 / create 新建 / update 修改 / "
            "delete 删除 / execute 执行 / export 导出"
        },
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "权限说明"},
    )


class User(IdMixin, TimestampMixin, table=True):
    """控制台成员，不是平台账号（那是 ``accounts``）。"""

    __tablename__ = "users"
    __table_args__ = (
        {"comment": "成员表：控制台登录用户，通过角色获得权限（与平台账号 accounts 无关）"},
    )

    username: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="登录名",
        sa_column_kwargs={"comment": "登录名（唯一）"},
    )
    email: str = Field(
        max_length=255,
        unique=True,
        index=True,
        description="邮箱",
        sa_column_kwargs={"comment": "邮箱（唯一），用于登录与通知"},
    )
    display_name: str = Field(
        max_length=64,
        description="显示名",
        sa_column_kwargs={"comment": "显示名（界面上展示的名字）"},
    )
    # 只存哈希；演示账号留空，因为还没有登录流程
    password_hash: str | None = Field(
        default=None,
        max_length=255,
        description="密码哈希",
        sa_column_kwargs={"comment": "密码哈希（Argon2/bcrypt），不落明文；为空表示尚未设置密码"},
    )
    status: UserStatus = Field(
        default=UserStatus.active,
        sa_type=enum_type(UserStatus, 16),
        index=True,
        description="状态：active / disabled / locked",
        sa_column_kwargs={"comment": "状态：active 正常 / disabled 已停用 / locked 已锁定"},
    )
    # 超级管理员跳过权限校验，只留给初始化用；日常授权应当走角色
    is_superuser: bool = Field(
        default=False,
        description="是否超级管理员",
        sa_column_kwargs={"comment": "是否超级管理员：为真时跳过权限校验，仅用于初始化"},
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "最近登录时间"},
    )
    # 登录失败计数 + 临时锁定时间：暴力破解防护，不依赖外部缓存
    failed_login_count: int = Field(
        default=0,
        description="连续登录失败次数",
        sa_column_kwargs={
            "server_default": "0",
            "comment": "连续登录失败次数，登录成功后清零，达到阈值触发临时锁定",
        },
    )
    locked_until: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "comment": "临时锁定截止时间（UTC），非空且未到期时拒绝登录；"
            "与 status=locked（管理员手动锁定）不是一回事"
        },
    )
    # 每人一个默认工作区：登录后头像浮层、审计记录都用它；
    # 为空表示尚未分配（老数据），登录不受影响，只是浮层显示「未分配」
    default_workspace_id: UUID | None = Field(
        default=None,
        foreign_key="workspaces.id",
        index=True,
        description="默认工作区 ID",
        sa_column_kwargs={"comment": "默认工作区 ID，指向 workspaces.id；为空表示尚未分配"},
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        sa_column_kwargs={"comment": "备注"},
    )


class UserRole(IdMixin, table=True):
    """成员 - 角色 授权记录。

    与绑定日志不同，这是**当前有效**的关系表：撤销授权就删除对应行，
    历史由 ``audit_logs`` 负责留痕。
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        {"comment": "成员角色表：成员与角色的对应关系，撤销授权即删除记录"},
    )

    user_id: UUID = Field(
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "成员 ID，指向 users.id"},
    )
    role_id: UUID = Field(
        foreign_key="roles.id",
        index=True,
        sa_column_kwargs={"comment": "角色 ID，指向 roles.id"},
    )
    granted_by: str = Field(
        default="system",
        max_length=64,
        description="授权人",
        sa_column_kwargs={"comment": "授权人（用户名或服务名），初始化数据为 system"},
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "comment": "授权时间（UTC）"},
    )


class RolePermission(IdMixin, table=True):
    """角色 - 权限点 授权记录，同样是当前有效的关系表。"""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        {"comment": "角色权限表：角色与权限点的对应关系，决定该角色能做什么"},
    )

    role_id: UUID = Field(
        foreign_key="roles.id",
        index=True,
        sa_column_kwargs={"comment": "角色 ID，指向 roles.id"},
    )
    permission_id: UUID = Field(
        foreign_key="permissions.id",
        index=True,
        sa_column_kwargs={"comment": "权限点 ID，指向 permissions.id"},
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "comment": "授权时间（UTC）"},
    )
