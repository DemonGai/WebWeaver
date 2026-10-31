"""RBAC 只读接口：角色、权限目录、成员。

目前只开读：登录流程还没做，写接口（改角色、给成员授权）需要先有「当前操作人」，
否则无法回答「谁把 owner 权限给了谁」。等认证接上后再补写接口，
并在写操作里落一条 ``audit_logs``（``resource_type=role`` / ``user``）。
"""

from collections import defaultdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Permission, Role, RolePermission, User, UserRole
from app.schemas.rbac import (
    PermissionItem,
    PermissionList,
    RoleItem,
    RoleList,
    UserItem,
    UserList,
)

router = APIRouter(prefix="/rbac", tags=["rbac"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/permissions", response_model=PermissionList, summary="权限点目录")
async def get_permissions(session: SessionDep) -> PermissionList:
    rows = await session.scalars(select(Permission).order_by(Permission.code))
    return PermissionList(
        items=[PermissionItem.model_validate(row, from_attributes=True) for row in rows]
    )


@router.get("/roles", response_model=RoleList, summary="角色列表（含权限点）")
async def get_roles(session: SessionDep) -> RoleList:
    roles = list(await session.scalars(select(Role).order_by(Role.sort_order, Role.code)))

    # 两次批量查询把权限点与成员数一次取齐，避免按角色逐个查（N+1）
    permission_map: dict[UUID, list[str]] = defaultdict(list)
    for role_id, code in await session.execute(
        select(RolePermission.role_id, Permission.code)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .order_by(Permission.code)
    ):
        permission_map[role_id].append(code)

    user_counts = dict(
        (
            await session.execute(select(UserRole.role_id, func.count()).group_by(UserRole.role_id))
        ).all()
    )

    return RoleList(
        items=[
            RoleItem(
                id=role.id,
                code=role.code,
                name=role.name,
                description=role.description,
                is_system=role.is_system,
                sort_order=role.sort_order,
                permission_codes=permission_map.get(role.id, []),
                user_count=int(user_counts.get(role.id, 0)),
            )
            for role in roles
        ]
    )


@router.get("/users", response_model=UserList, summary="成员列表（含角色）")
async def get_users(session: SessionDep) -> UserList:
    users = list(await session.scalars(select(User).order_by(User.username)))

    role_map: dict[UUID, list[str]] = defaultdict(list)
    for user_id, code in await session.execute(
        select(UserRole.user_id, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .order_by(Role.sort_order, Role.code)
    ):
        role_map[user_id].append(code)

    return UserList(
        items=[
            UserItem(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                status=user.status,
                is_superuser=user.is_superuser,
                role_codes=role_map.get(user.id, []),
                last_login_at=user.last_login_at,
            )
            for user in users
        ]
    )
