"""个人中心：头像浮层、个人信息、登录设备、安全概览、我的操作日志。

针对的是控制台成员（``users``），不是浏览器账号池（``accounts``）。

这些数据都在「当前成员自己」身上，所以路由层只需要登录态，不需要权限点——
能改别人资料的接口才需要 ``user:update``。

几个刻意的做法：

- 浮层里的 badge（设备数、两步验证状态）全部现算，不写死。写死的话
  「3 台在线」会一直显示 3，哪怕实际只剩 1 台。
- 「上次改密」不在 ``users`` 上加列，改为查审计里最近一条成功的
  ``reset_password``：改密本来就留痕，再存一列等于有两份真相。
- 设备描述从 User-Agent 解析，解析不出来就显示「未知设备」，不猜。
"""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AuditAction, AuditLog, AuditResourceType, AuditResult, AuthSession, User
from app.models import Workspace as WorkspaceModel
from app.models.base import utcnow
from app.schemas.auth import Workspace, WorkspaceList
from app.schemas.user import (
    MenuRow,
    ProfilePayload,
    SecurityEvent,
    SecurityPayload,
    SessionItem,
    SessionList,
    UserMenuPayload,
    WorkspaceBrief,
)
from app.services import audit, rbac

ROLE_LABELS = {
    "owner": "所有者",
    "admin": "管理员",
    "operator": "运营",
    "viewer": "只读",
}

# 安全页展示的事件类型：只挑认证相关，业务操作去「操作日志」页看
SECURITY_ACTIONS = (
    AuditAction.login,
    AuditAction.logout,
    AuditAction.reset_password,
)


# ── User-Agent 解析 ─────────────────────────────────────
def parse_user_agent(ua: str | None) -> tuple[str, str]:
    """粗解析 User-Agent → (浏览器, 系统)。

    只做展示用途，不追求完备：顺序很重要，Edge 的 UA 里也带 "Chrome"、
    Chrome 的 UA 里也带 "Safari"，所以先判更具体的那个。
    """
    if not ua:
        return "未知浏览器", "未知系统"

    text = ua.lower()
    if "edg/" in text:
        browser = "Edge"
    elif "opr/" in text or "opera" in text:
        browser = "Opera"
    elif "firefox" in text:
        browser = "Firefox"
    elif "chrome" in text or "chromium" in text:
        browser = "Chrome"
    elif "safari" in text:
        browser = "Safari"
    elif "python" in text or "httpx" in text or "curl" in text:
        browser = "命令行"
    else:
        browser = "未知浏览器"

    if "windows" in text:
        system = "Windows"
    elif "iphone" in text or "ipad" in text:
        system = "iOS"
    elif "android" in text:
        system = "Android"
    elif "mac os x" in text or "macintosh" in text:
        system = "macOS"
    elif "linux" in text:
        system = "Linux"
    else:
        system = "未知系统"

    return browser, system


def _device_label(ua: str | None) -> str:
    browser, system = parse_user_agent(ua)
    if browser == "未知浏览器" and system == "未知系统":
        return "未知设备"
    return f"{browser} · {system}"


# ── 通用查询 ────────────────────────────────────────────
async def _workspace_of(session: AsyncSession, user: User) -> WorkspaceModel | None:
    if user.default_workspace_id is None:
        return None
    return await session.get(WorkspaceModel, user.default_workspace_id)


async def _role_labels(session: AsyncSession, user: User) -> tuple[str, str]:
    """返回 (中文标签, 角色编码)；没有角色时给「未授权」。"""
    roles = [role.code for role in await rbac.roles_of_user(session, user.id)]
    if not roles:
        return "未授权", ""
    return ROLE_LABELS.get(roles[0], roles[0]), roles[0]


async def _active_sessions(session: AsyncSession, user_id: UUID) -> int:
    """当前仍然有效的会话数（未吊销且未过期）。"""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > utcnow(),
            )
        )
        or 0
    )


async def _last_password_change(session: AsyncSession, username: str) -> datetime | None:
    return await session.scalar(
        select(func.max(AuditLog.occurred_at)).where(
            AuditLog.action == AuditAction.reset_password,
            AuditLog.result == AuditResult.success,
            AuditLog.operator == username,
        )
    )


def _relative(moment: datetime | None) -> str:
    """「今天 14:02」「3 天前」这种短描述，浮层页脚只有一行位置。"""
    if moment is None:
        return "首次登录"
    now = utcnow()
    delta = now - moment
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    if minutes < 60 * 24 and moment.date() == now.date():
        return f"今天 {moment.astimezone().strftime('%H:%M')}"
    days = minutes // (60 * 24)
    if days < 7:
        return f"{days} 天前"
    return moment.astimezone().strftime("%Y-%m-%d")


# ── 工作区 ──────────────────────────────────────────────
async def list_workspaces(session: AsyncSession, user: User | None) -> WorkspaceList:
    """工作区列表 + 当前成员的默认工作区。

    ``members`` 按「默认工作区指向它的人数」统计——现在一人只挂一个工作区，
    所以这个数就是真实成员数。以后加多工作区关联表时改这里的聚合即可。
    """
    rows = list(
        await session.scalars(
            select(WorkspaceModel).order_by(WorkspaceModel.sort_order, WorkspaceModel.code)
        )
    )
    counter = dict(
        (
            await session.execute(
                select(User.default_workspace_id, func.count())
                .where(User.default_workspace_id.is_not(None))
                .group_by(User.default_workspace_id)
            )
        ).all()
    )

    items = [
        Workspace(id=row.code, name=row.name, members=int(counter.get(row.id, 0))) for row in rows
    ]

    default_code = ""
    if user is not None and user.default_workspace_id is not None:
        matched = next((row for row in rows if row.id == user.default_workspace_id), None)
        default_code = matched.code if matched else ""
    if not default_code and rows:
        default_code = rows[0].code

    return WorkspaceList(items=items, default_id=default_code)


# ── 头像浮层 ────────────────────────────────────────────
async def build_menu(session: AsyncSession, user: User | None) -> UserMenuPayload:
    """浮层数据。未登录时返回演示占位，保证组件永远有东西可渲染。

    菜单项去掉了「切换账号」：成员只有一个默认工作区，切换没有意义；
    也没有右上角设置图标，改资料统一走「个人信息」页。
    """
    version = f"v{settings.app_version}"

    if user is None:
        return UserMenuPayload(
            name="未登录",
            initial="?",
            email="",
            role="访客",
            workspace="未分配工作区",
            workspace_code="",
            workspace_note="登录后显示默认工作区",
            groups=[
                [
                    MenuRow(key="profile", label="个人信息", icon="user"),
                    MenuRow(key="reset-password", label="重置密码", icon="lock"),
                    MenuRow(key="mfa", label="安全与二次验证", icon="shield", badge="未开启"),
                ],
                [
                    MenuRow(key="devices", label="登录设备管理", icon="devices"),
                    MenuRow(key="audit", label="账号操作日志", icon="list"),
                ],
                [MenuRow(key="logout", label="退出登录", icon="logout", danger=True)],
            ],
            last_login="未登录",
            version=version,
        )

    role_label, _ = await _role_labels(session, user)
    workspace = await _workspace_of(session, user)
    active = await _active_sessions(session, user.id)

    return UserMenuPayload(
        name=user.display_name,
        initial=user.display_name[:1] or user.username[:1].upper(),
        email=user.email,
        role=role_label,
        workspace=workspace.name if workspace else "未分配工作区",
        workspace_code=workspace.code if workspace else "",
        workspace_note=workspace.note if workspace and workspace.note else "默认工作区",
        groups=[
            [
                MenuRow(key="profile", label="个人信息", icon="user"),
                MenuRow(key="reset-password", label="重置密码", icon="lock"),
                MenuRow(
                    key="mfa",
                    label="安全与二次验证",
                    icon="shield",
                    badge="未开启",
                    badge_tone="zinc",
                ),
            ],
            [
                MenuRow(
                    key="devices",
                    label="登录设备管理",
                    icon="devices",
                    badge=f"{active} 台在线" if active else "无在线设备",
                    badge_tone="zinc",
                ),
                MenuRow(key="audit", label="账号操作日志", icon="list"),
            ],
            [MenuRow(key="logout", label="退出登录", icon="logout", danger=True)],
        ],
        last_login=f"上次登录 {_relative(user.last_login_at)}",
        version=version,
    )


# ── 个人信息 ────────────────────────────────────────────
async def build_profile(session: AsyncSession, user: User) -> ProfilePayload:
    role_label, role_code = await _role_labels(session, user)
    workspace = await _workspace_of(session, user)

    return ProfilePayload(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        initial=user.display_name[:1] or user.username[:1].upper(),
        role=role_label,
        role_code=role_code,
        status=user.status.value,
        is_superuser=user.is_superuser,
        workspace=WorkspaceBrief.model_validate(workspace, from_attributes=True)
        if workspace
        else None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        password_updated_at=await _last_password_change(session, user.username),
        active_sessions=await _active_sessions(session, user.id),
        mfa_enabled=False,
    )


async def update_display_name(
    session: AsyncSession,
    user: User,
    display_name: str,
    *,
    request: Request | None = None,
) -> ProfilePayload:
    """改显示名。邮箱不在这里改：换邮箱要走验证流程，不是一次 PATCH 能了结的。"""
    new_name = display_name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="显示名不能为空")
    if len(new_name) > 64:
        raise HTTPException(status_code=422, detail="显示名最长 64 个字符")
    if new_name == user.display_name:
        return await build_profile(session, user)

    before = user.display_name
    user.display_name = new_name
    session.add(user)
    await session.commit()
    await session.refresh(user)

    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.user,
        resource_id=user.id,
        resource_name=user.username,
        operator=user.username,
        detail=f"修改显示名：{before} → {new_name}",
        changes=audit.snapshot_diff({"display_name": before}, {"display_name": new_name}),
        request=request,
    )
    return await build_profile(session, user)


# ── 登录设备 ────────────────────────────────────────────
def session_item(row: AuthSession, *, current_id: UUID | None) -> SessionItem:
    browser, system = parse_user_agent(row.user_agent)
    return SessionItem(
        id=row.id,
        current=row.id == current_id,
        ip_address=row.ip_address,
        browser=browser,
        os=system,
        device=_device_label(row.user_agent),
        issued_at=row.issued_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        revoked=row.revoked_at is not None,
        revoked_reason=row.revoked_reason,
    )


async def list_sessions(
    session: AsyncSession,
    user: User,
    *,
    current_id: UUID | None,
) -> SessionList:
    """列出该成员的全部会话，有效的在前。

    已注销的也返回（默认只看最近 20 条）：排查「这个设备是什么时候被踢的」
    需要历史，只给在线设备等于把审计的一半藏起来。
    """
    rows = list(
        await session.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id)
            .order_by(AuthSession.revoked_at.is_(None).desc(), AuthSession.issued_at.desc())
            .limit(20)
        )
    )
    items = [session_item(row, current_id=current_id) for row in rows]
    return SessionList(
        items=items,
        total=len(items),
        active_total=sum(1 for row in rows if row.revoked_at is None and row.expires_at > utcnow()),
    )


async def revoke_session(
    session: AsyncSession,
    user: User,
    target_id: UUID,
    *,
    current_id: UUID | None,
    request: Request | None = None,
) -> int:
    """吊销一个会话；返回吊销条数（已失效的返回 0，不报错）。

    只能吊销自己的：``user_id`` 条件写进 where，别人的 ID 查不到也就改不动。
    """
    row = await session.get(AuthSession, target_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")
    if row.revoked_at is not None:
        return 0

    row.revoked_at = utcnow()
    row.revoked_reason = "logout" if target_id == current_id else "admin"
    session.add(row)
    await session.commit()

    signed_out = target_id == current_id
    await audit.record(
        session,
        action=AuditAction.logout,
        resource_type=AuditResourceType.auth,
        resource_id=user.id,
        resource_name=user.username,
        operator=user.username,
        detail=(
            f"退出当前设备（{_device_label(row.user_agent)}）"
            if signed_out
            else f"踢出设备：{_device_label(row.user_agent)}（{row.ip_address or '未知 IP'}）"
        ),
        request=request,
    )
    return 1


# ── 我的操作日志 ────────────────────────────────────────
async def list_my_logs(
    session: AsyncSession,
    user: User,
    *,
    action: AuditAction | None = None,
    result: AuditResult | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """只查当前成员自己的记录。

    ``operator`` 强行钉成登录名而不是由前端传：自己看自己的日志是「个人信息」，
    想看全部得走带权限校验的审计接口。
    """
    return await audit.list_logs(
        session,
        action=action,
        result=result,
        operator=user.username,
        limit=limit,
        offset=offset,
    )


# ── 安全概览 ────────────────────────────────────────────
async def build_security(session: AsyncSession, user: User) -> SecurityPayload:
    locked_until = user.locked_until
    remaining = 0
    if locked_until is not None:
        remain = (locked_until - utcnow()).total_seconds()
        remaining = max(0, int(remain // 60) + (1 if remain % 60 else 0)) if remain > 0 else 0

    rows = list(
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.operator == user.username,
                AuditLog.action.in_(SECURITY_ACTIONS),
            )
            .order_by(AuditLog.occurred_at.desc())
            .limit(8)
        )
    )

    return SecurityPayload(
        password_updated_at=await _last_password_change(session, user.username),
        failed_login_count=user.failed_login_count,
        locked_until=locked_until,
        lock_remaining_minutes=remaining,
        active_sessions=await _active_sessions(session, user.id),
        mfa_enabled=False,
        mfa_note="两步验证尚未接入 TOTP，接入后可在本页开通；当前登录仅校验密码",
        last_login_at=user.last_login_at,
        recent_events=[
            SecurityEvent(
                id=row.id,
                action=row.action.value,
                action_label=ACTION_LABELS.get(row.action, row.action.value),
                result=row.result.value,
                detail=row.detail,
                ip_address=row.ip_address,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ],
    )


ACTION_LABELS = {
    AuditAction.login: "登录",
    AuditAction.logout: "退出登录",
    AuditAction.reset_password: "重置密码",
}
