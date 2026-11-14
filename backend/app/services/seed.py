"""初始化数据：工作区、权限目录、超级管理员、四个内核登记项。

**只写系统运行必需的东西**，不塞演示用业务数据（实例、账号、代理、指纹、审计
样例这些一律不写）。空库启动后有：一个默认工作区、一套权限点与四个内置角色、
一个能登录的超级管理员，以及 CloakBrowser / Camoufox / fingerprint-chromium /
ungoogled-chromium 四条内核登记。

内核登记项的意义：内核管理页是按台账渲染卡片的，没有登记项就没有卡片，也就
没有「拉取镜像」的入口。登记只占一行名字与元信息，``version`` 留空表示「还没装
过镜像」，拉起镜像后由 ``kernel_pool.adopt_pulled`` 回填真实版本。

写入是幂等的：已存在就跳过，可以反复执行。没有 ``--reset`` —— 这个脚本只补
不删，删数据不该由初始化脚本负责。

用法::

    cd backend
    uv run python -m app.services.seed
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, dispose
from app.core.security import hash_password
from app.models import (
    Kernel,
    KernelChannel,
    KernelStatus,
    Permission,
    RbacAction,
    RbacModule,
    Role,
    RolePermission,
    User,
    UserRole,
    UserStatus,
    Workspace,
)

# 默认工作区：成员落点，也是未登录时 ``/auth/workspaces`` 的默认项
DEFAULT_WORKSPACE = {
    "code": "webweaver-team",
    "name": "webweaver-team",
    "note": "默认工作区",
    "sort_order": 0,
}

# 超级管理员：本地开发直接 admin / admin 进来，正式环境请立刻改密
ADMIN = {
    "username": "admin",
    "email": "admin@webweaver.local",
    "display_name": "管理员",
    "password": "admin",
    "note": "初始化创建的超级管理员",
}

# 四个内核的登记项。只写「这个引擎存在」，版本号留空 —— 本地装了什么版本由
# kernel_scan 扫镜像得出（页面的「当前版本」就是这么来的），拉取成功后会由
# kernel_pool.adopt_pulled 把真实版本回填到台账。
# 不要在这里写死版本号：写死的值本地没有对应镜像时，实例启动会报「缺这个版本」。
ENGINE_REGISTRATIONS: list[dict[str, object]] = [
    {
        "name": "CloakBrowser",
        "engine": "Chromium",
        "channel": KernelChannel.stable,
        "status": KernelStatus.active,
        "version": "",
        "repo_url": "https://github.com/CloakHQ/CloakBrowser",
        "detection_level": "C++ 层注入",
        "pass_rate": 98,
        "share": 46,
        "note": "主力内核，反检测通过率最高",
    },
    {
        "name": "Camoufox",
        "engine": "Firefox",
        "channel": KernelChannel.stable,
        "status": KernelStatus.active,
        "version": "",
        "repo_url": "https://github.com/daijro/camoufox",
        "detection_level": "Juggler 层修改",
        "pass_rate": 94,
        "share": 28,
        "note": "Firefox 系，适合对 Chromium 敏感的平台",
    },
    {
        "name": "fingerprint-chromium",
        "engine": "Chromium",
        "channel": KernelChannel.stable,
        "status": KernelStatus.testing,
        "version": "",
        "repo_url": "https://github.com/adryfish/fingerprint-chromium",
        "detection_level": "前端 JS 注入",
        "pass_rate": 87,
        "share": 18,
        "note": "开源方案，补丁能力有限",
    },
    {
        "name": "ungoogled-chromium",
        "engine": "Chromium",
        "channel": KernelChannel.beta,
        "status": KernelStatus.deprecated,
        "version": "",
        "repo_url": "https://github.com/ungoogled-software/ungoogled-chromium",
        "detection_level": "原生隐私加固",
        "pass_rate": 72,
        "share": 8,
        "note": "版本偏旧，仅用于问题复现",
    },
]

# 权限点按「模块 → 动作」生成，避免手写三十多行重复定义
PERMISSION_MATRIX: dict[RbacModule, tuple[RbacAction, ...]] = {
    RbacModule.browser: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
        RbacAction.execute,
    ),
    RbacModule.account: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.ip: (RbacAction.read, RbacAction.create, RbacAction.update, RbacAction.delete),
    RbacModule.fingerprint: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.kernel: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.group: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.audit: (RbacAction.read, RbacAction.export),
    RbacModule.user: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.role: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
}

MODULE_LABELS = {
    RbacModule.browser: "浏览器",
    RbacModule.account: "平台账号",
    RbacModule.ip: "代理 IP",
    RbacModule.fingerprint: "指纹",
    RbacModule.kernel: "内核",
    RbacModule.group: "分组",
    RbacModule.audit: "审计日志",
    RbacModule.user: "成员",
    RbacModule.role: "角色",
}

ACTION_LABELS = {
    RbacAction.read: "查看",
    RbacAction.create: "新建",
    RbacAction.update: "修改",
    RbacAction.delete: "删除",
    RbacAction.execute: "执行",
    RbacAction.export: "导出",
}

# 内置角色的授权规则：用谓词表达比列几十条编码更好维护
ROLE_RULES = {
    # 所有者：全部权限
    "owner": lambda module, action: True,
    # 管理员：除「删除成员 / 删除角色」外全部，避免管理员能把自己锁死
    "admin": lambda module, action: (
        not (module in (RbacModule.user, RbacModule.role) and action == RbacAction.delete)
    ),
    # 运营：能看所有，能启停实例、改账号资料，不能新建/删除资源、不能管成员
    "operator": lambda module, action: (
        action == RbacAction.read
        or (
            module == RbacModule.browser
            and action in (RbacAction.create, RbacAction.update, RbacAction.execute)
        )
        or (module == RbacModule.account and action == RbacAction.update)
    ),
    # 只读：只给 read
    "viewer": lambda module, action: action == RbacAction.read,
}

ROLES = [
    {
        "code": "owner",
        "name": "所有者",
        "description": "拥有全部权限，通常是工作区创建者",
        "is_system": True,
        "sort_order": 0,
    },
    {
        "code": "admin",
        "name": "管理员",
        "description": "管理全部业务资源，但不能删除成员与角色",
        "is_system": True,
        "sort_order": 1,
    },
    {
        "code": "operator",
        "name": "运营",
        "description": "日常操作实例与账号，不能新建或删除资源、不能管理成员",
        "is_system": False,
        "sort_order": 2,
    },
    {
        "code": "viewer",
        "name": "只读",
        "description": "只能查看，不能做任何写操作",
        "is_system": False,
        "sort_order": 3,
    },
]


async def _ensure_workspace(session: AsyncSession) -> Workspace:
    """取默认工作区，没有就建一个。"""
    workspace = await session.scalar(
        select(Workspace).where(Workspace.code == DEFAULT_WORKSPACE["code"])
    )
    if workspace is not None:
        return workspace
    workspace = Workspace(**DEFAULT_WORKSPACE)
    session.add(workspace)
    await session.flush()
    return workspace


async def _seed_kernels(session: AsyncSession) -> None:
    """登记四个内核引擎；已有同名登记项就跳过（不动版本与状态）。

    只为了「内核管理页有卡片、能点拉取」。版本、镜像清单一律以本地镜像为准，
    这里不写死任何版本号。
    """
    names = [str(item["name"]) for item in ENGINE_REGISTRATIONS]
    existing = set(await session.scalars(select(Kernel.name).where(Kernel.name.in_(names))))
    for item in ENGINE_REGISTRATIONS:
        if item["name"] in existing:
            continue
        session.add(Kernel(**item))
    await session.flush()
    # 必须自己提交：老库里角色与超管都已存在时，后面两个步骤都会提前 return，
    # 没人再 commit，这段插入会被回滚掉（表现为日志说 kernels=4、表里却是空的）。
    await session.commit()


async def _seed_rbac(session: AsyncSession) -> None:
    """初始化权限目录与内置角色；已经有角色就跳过。"""
    if await session.scalar(select(func.count()).select_from(Role)):
        return

    permissions: dict[str, Permission] = {}
    for module, actions in PERMISSION_MATRIX.items():
        for action in actions:
            code = f"{module.value}:{action.value}"
            permission = Permission(
                code=code,
                name=f"{ACTION_LABELS[action]}{MODULE_LABELS[module]}",
                module=module,
                action=action,
                description=f"{code}：{MODULE_LABELS[module]} - {ACTION_LABELS[action]}",
            )
            session.add(permission)
            permissions[code] = permission
    await session.flush()

    roles: dict[str, Role] = {}
    for item in ROLES:
        role = Role(**item)
        session.add(role)
        roles[item["code"]] = role
    await session.flush()

    # 角色 → 权限点：按谓词逐条判定，写入 role_permissions
    for role_code, role in roles.items():
        allow = ROLE_RULES[role_code]
        for permission_code, permission in permissions.items():
            module_code, action_code = permission_code.split(":", 1)
            if allow(RbacModule(module_code), RbacAction(action_code)):
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    await session.commit()


async def _ensure_admin(session: AsyncSession, workspace: Workspace) -> User:
    """建超级管理员；已存在就原样返回，不覆盖已改过的密码。"""
    user = await session.scalar(select(User).where(User.username == ADMIN["username"]))
    if user is not None:
        return user

    owner = await session.scalar(select(Role).where(Role.code == "owner"))
    user = User(
        username=ADMIN["username"],
        email=ADMIN["email"],
        display_name=ADMIN["display_name"],
        note=ADMIN["note"],
        status=UserStatus.active,
        is_superuser=True,
        password_hash=hash_password(ADMIN["password"]),
        default_workspace_id=workspace.id,
    )
    session.add(user)
    await session.flush()
    if owner is not None:
        session.add(UserRole(user_id=user.id, role_id=owner.id, granted_by="system"))
    await session.commit()
    return user


async def seed(session: AsyncSession) -> dict[str, int]:
    """写入初始化数据，返回各表行数。幂等，可反复执行。"""
    workspace = await _ensure_workspace(session)
    await _seed_kernels(session)
    await _seed_rbac(session)
    await _ensure_admin(session, workspace)
    return await counts(session)


async def counts(session: AsyncSession) -> dict[str, int]:
    """各表当前行数，便于在命令行确认。"""
    result: dict[str, int] = {}
    for model in (Workspace, Permission, Role, RolePermission, User, UserRole, Kernel):
        result[model.__tablename__] = int(
            await session.scalar(select(func.count()).select_from(model)) or 0
        )
    return result


async def _main() -> None:
    async with SessionLocal() as session:
        result = await seed(session)
    await dispose()
    print("初始化数据就绪：" + "、".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    asyncio.run(_main())
