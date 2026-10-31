"""RBAC 接口的出入参。

成员列表里**没有** ``password_hash``：接口永远不回传凭证，哪怕只是哈希。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import RbacAction, RbacModule, UserStatus


class PermissionItem(BaseModel):
    code: str
    name: str
    module: RbacModule
    action: RbacAction
    description: str | None = None


class PermissionList(BaseModel):
    items: list[PermissionItem]


class RoleItem(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    is_system: bool
    sort_order: int
    permission_codes: list[str]
    user_count: int


class RoleList(BaseModel):
    items: list[RoleItem]


class UserItem(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str
    status: UserStatus
    is_superuser: bool
    role_codes: list[str]
    last_login_at: datetime | None = None


class UserList(BaseModel):
    items: list[UserItem]
