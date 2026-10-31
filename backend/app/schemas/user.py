"""个人中心（头像浮层 + 个人信息 / 安全 / 设备）的接口模型。

这里的 "user" 指控制台成员（``users`` 表），不是浏览器账号池（``accounts`` 表）——
后者的模型在 ``schemas/domain.py`` 的 ``AccountCard`` / ``AccountPoolPayload``。

从 ``schemas/kernels.py`` 把 ``MenuRow`` / ``UserMenuPayload`` 搬过来：它们描述的
是成员自己的账号，跟内核管理没有关系，之前只是顺手放在一起。

工作区只出现在浮层和个人信息里，因此这里给一个精简的 ``WorkspaceBrief``，
不复用 ``auth.Workspace``（那个带成员数，是找回密码页用的）。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── 头像浮层 ────────────────────────────────────────────
class MenuRow(BaseModel):
    key: str
    label: str
    icon: str
    badge: str | None = None
    badge_tone: str | None = None
    danger: bool = False


class UserMenuPayload(BaseModel):
    """头像浮层：一个成员的全部展示信息。"""

    name: str
    initial: str
    email: str
    role: str
    # 显示名与业务标识分开：浮层上给人看 name，跳转/审计用 code
    workspace: str
    workspace_code: str
    workspace_note: str
    groups: list[list[MenuRow]]
    last_login: str
    version: str


# ── 个人信息 ────────────────────────────────────────────
class WorkspaceBrief(BaseModel):
    id: UUID
    code: str
    name: str
    note: str | None = None


class ProfilePayload(BaseModel):
    id: UUID
    username: str
    display_name: str
    email: str
    initial: str
    role: str
    role_code: str
    status: str
    is_superuser: bool
    workspace: WorkspaceBrief | None = None
    created_at: datetime
    last_login_at: datetime | None = None
    # 改成「上次改密」而不是 users 加一列：改密本来就落审计，不再存第二份真相
    password_updated_at: datetime | None = None
    active_sessions: int = 0
    mfa_enabled: bool = False


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64, description="新的显示名")


class ProfileUpdateResponse(BaseModel):
    ok: bool
    message: str
    profile: ProfilePayload


# ── 登录设备 ────────────────────────────────────────────
class SessionItem(BaseModel):
    id: UUID
    current: bool
    ip_address: str | None = None
    browser: str
    os: str
    # 「Chrome · Windows」这种一行描述，前端直接展示，不用再拼
    device: str
    issued_at: datetime
    last_seen_at: datetime | None = None
    expires_at: datetime
    revoked: bool
    revoked_reason: str | None = None


class SessionList(BaseModel):
    items: list[SessionItem]
    total: int
    active_total: int


class SessionRevokeResponse(BaseModel):
    ok: bool
    message: str
    revoked: int
    # 吊销的是当前会话时前端要跳登录页，否则只是列表里少一行
    signed_out: bool = False


# ── 安全概览 ────────────────────────────────────────────
class SecurityEvent(BaseModel):
    id: UUID
    action: str
    action_label: str
    result: str
    detail: str | None = None
    ip_address: str | None = None
    occurred_at: datetime


class SecurityPayload(BaseModel):
    password_updated_at: datetime | None = None
    failed_login_count: int = 0
    locked_until: datetime | None = None
    lock_remaining_minutes: int = 0
    active_sessions: int = 0
    mfa_enabled: bool = False
    # 两步验证还没接 TOTP，这里如实说明，不给一个点不动的假开关
    mfa_note: str
    last_login_at: datetime | None = None
    recent_events: list[SecurityEvent] = []
