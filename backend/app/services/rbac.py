"""RBAC 解析：算出「某个成员最终能做什么」。

权限是「角色并集」：成员挂多个角色时取并集，不做减法——没有显式拒绝规则，
简单系统里「少给一个角色」比「加一条 deny」更好推理。超级管理员直接短路，
只在初始化/应急时使用。

这里只做纯解析，不碰 HTTP。路由上的用法是
``Depends(require_permission("browser:create"))``，那个依赖在 ``app/api/deps.py``——
放接口层是为了避免 deps 与 service 互相 import 成环。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Permission, Role, RolePermission, User, UserRole
from app.models.enums import UserStatus


async def roles_of_user(session: AsyncSession, user_id: UUID) -> list[Role]:
    """成员当前拥有的角色（按排序值）。"""
    rows = await session.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.sort_order, Role.code)
    )
    return list(rows)


async def permission_codes_of_role(session: AsyncSession, role_id: UUID) -> list[str]:
    """单个角色的权限点编码。"""
    rows = await session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    )
    return list(rows)


async def permission_codes_of_user(session: AsyncSession, user_id: UUID) -> set[str]:
    """成员的**有效权限**：所有角色的权限并集；超级管理员返回全部权限点。

    结果为 ``set``，调用方只关心「有没有」，不需要顺序。
    """
    user = await session.get(User, user_id)
    if user is None or user.status is not UserStatus.active:
        return set()

    if user.is_superuser:
        codes = await session.scalars(select(Permission.code))
        return set(codes)

    codes = await session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return set(codes)


async def has_permission(session: AsyncSession, user_id: UUID, code: str) -> bool:
    """是否拥有某个权限点。"""
    return code in await permission_codes_of_user(session, user_id)
