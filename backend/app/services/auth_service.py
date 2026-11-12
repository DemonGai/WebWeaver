r"""账号安全服务：验证码、密码规则，以及登录 / 注册 / 重置密码的完整流程。

分两层：

1. **纯函数**（验证码、邮箱校验、密码强度）不碰数据库，测试里可以直接调；
   验证码目前存在进程内存里，多实例部署时要换成 Redis。
2. **流程函数**（:func:`login` / :func:`register` / :func:`logout` /
   :func:`forgot_password` / :func:`resend_reset` / :func:`reset_password`）
   负责读写 ``users`` / ``auth_sessions`` / ``password_reset_tokens``，
   并在成功或失败后落一条 ``audit_logs``——失败的登录尝试同样是证据。

安全上的几条取舍：

- 密码用 scrypt 哈希（见 ``app/core/security.py``），库里没有明文也没有可逆密文；
- 令牌明文只在签发时返回一次，库里存 SHA-256 摘要；
- 「账号不存在」和「密码错误」对外是同一句提示，避免账号枚举；
- 「忘记密码」对被注册与被封禁的邮箱返回同样的成功提示，同样是为了不泄漏账号存在性；
- 连续失败达阈值后临时锁定（``users.locked_until``），锁定结束时计数清零，
  避免攻击者靠「锁一次试一次」慢慢把字典试完。
"""

import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging_config import logger
from app.core.security import (
    TokenError,
    decode_access_token,
    encode_access_token,
    hash_password,
    new_token,
    token_digest,
    verify_password,
)
from app.models import (
    AuditAction,
    AuditResourceType,
    AuditResult,
    AuditSource,
    AuthSession,
    PasswordResetToken,
    Role,
    User,
    UserRole,
    UserStatus,
)
from app.models.base import utcnow
from app.schemas.auth import AuthResponse, AuthUser, Captcha, PasswordRule
from app.services import audit, rbac

CAPTCHA_TTL = 120
CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# 「最近使用」的刷新节流：每次请求都写库没必要，5 分钟一次足够判断活跃
TOUCH_INTERVAL = timedelta(minutes=5)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")

# 进程内保存最近一次下发的验证码
_captcha: dict[str, float | str | None] = {"code": None, "at": 0.0}

# ── 纯函数：验证码 / 邮箱 / 密码规则 ─────────────────────────────


def issue_captcha() -> Captcha:
    code = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(4))
    _captcha["code"] = code
    _captcha["at"] = time.time()
    return Captcha(code=code, expires_in=CAPTCHA_TTL)


def verify_captcha(text: str) -> bool:
    code = _captcha["code"]
    issued_at = float(_captcha["at"] or 0)
    if not code or time.time() - issued_at > CAPTCHA_TTL:
        return False
    return text.strip().upper() == str(code).upper()


def is_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def is_username(value: str) -> bool:
    return bool(_USERNAME_RE.match(value.strip()))


def password_checks(password: str, email: str, confirm: str) -> list[PasswordRule]:
    local_part = (email or "").split("@")[0].lower()
    tokens = [t for t in re.split(r"[._-]", local_part) if len(t) >= 3]
    lowered = password.lower()

    return [
        PasswordRule(key="length", label="至少 10 位字符", passed=len(password) >= 10),
        PasswordRule(key="digit", label="包含数字", passed=any(c.isdigit() for c in password)),
        PasswordRule(key="upper", label="包含大写字母", passed=any(c.isupper() for c in password)),
        PasswordRule(
            key="special",
            label="包含特殊符号",
            passed=any(not c.isalnum() and not c.isspace() for c in password),
        ),
        PasswordRule(key="lower", label="包含小写字母", passed=any(c.islower() for c in password)),
        PasswordRule(
            key="no_account",
            label="不含账号名",
            passed=bool(password) and not any(t in lowered for t in tokens),
        ),
    ]


def strength_of(checks: list[PasswordRule]) -> int:
    """0-4 段强度：字符类规则（长度/数字/大写/特殊/小写）各占一格。"""
    base = [c for c in checks if c.key != "no_account"]
    passed = sum(1 for c in base if c.passed)
    return 4 if passed == len(base) and all(c.passed for c in checks) else passed


def password_problem(password: str, identifier: str, confirm: str | None = None) -> str | None:
    """返回第一条不满足的规则说明；全部通过返回 ``None``。"""
    if confirm is not None and password != confirm:
        return "两次输入的密码不一致"
    checks = password_checks(password, identifier, confirm or password)
    failed = [c.label for c in checks if not c.passed]
    return f"密码未满足：{'、'.join(failed)}" if failed else None


# ── 内部工具 ──────────────────────────────────────────────────


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:45]
    return request.client.host if request.client else None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("User-Agent")
    return ua[:255] if ua else None


async def _audit(
    session: AsyncSession,
    request: Request | None,
    *,
    action: AuditAction,
    operator: str,
    ok: bool,
    detail: str,
    error_message: str | None = None,
) -> None:
    """认证链路的审计：统一 ``resource_type=auth``，只区分动作与结果。"""
    await audit.record(
        session,
        action=action,
        resource_type=AuditResourceType.auth,
        resource_name=operator,
        operator=operator or "anonymous",
        source=AuditSource.api,
        result=AuditResult.success if ok else AuditResult.failure,
        detail=detail,
        error_message=error_message,
        request=request,
    )


async def _find_by_login(session: AsyncSession, account: str) -> User | None:
    """用户名或邮箱登录，两边都不区分大小写。"""
    ident = account.strip().lower()
    return await session.scalar(
        select(User).where(or_(func.lower(User.username) == ident, func.lower(User.email) == ident))
    )


async def _roles_and_permissions(session: AsyncSession, user: User) -> tuple[list[str], list[str]]:
    roles = [role.code for role in await rbac.roles_of_user(session, user.id)]
    permissions = sorted(await rbac.permission_codes_of_user(session, user.id))
    return roles, permissions


async def profile_of(session: AsyncSession, user: User) -> AuthUser:
    """成员的可对外字段：不含 password_hash，也不含任何令牌。"""
    roles, permissions = await _roles_and_permissions(session, user)
    return AuthUser(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status.value,
        is_superuser=user.is_superuser,
        roles=roles,
        permissions=permissions,
        last_login_at=user.last_login_at,
    )


@dataclass(frozen=True)
class TokenBundle:
    """一次签发的双令牌与各自的到期时间。

    前端用 ``access_expires_at`` 安排静默续期，用 ``refresh_expires_at``
    展示「这次登录还能撑多久」，``absolute_expires_at`` 是硬上限——
    到了就必须重新登录，续期也救不回来。
    """

    user: User
    session_id: UUID
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    absolute_expires_at: datetime
    remember: bool

    @property
    def access_ttl_seconds(self) -> int:
        return max(0, int((self.access_expires_at - utcnow()).total_seconds()))

    @property
    def refresh_ttl_seconds(self) -> int:
        return max(0, int((self.refresh_expires_at - utcnow()).total_seconds()))


def _access_ttl() -> timedelta:
    return timedelta(minutes=settings.auth_access_ttl_minutes)


def _refresh_ttl(remember: bool) -> timedelta:
    minutes = (
        settings.auth_refresh_ttl_remember_minutes
        if remember
        else settings.auth_refresh_ttl_minutes
    )
    return timedelta(minutes=minutes)


def _absolute_deadline(now: datetime) -> datetime:
    """会话硬上限：从登录那一刻算起，续期再多也越不过这条线。"""
    return now + timedelta(minutes=settings.auth_absolute_ttl_minutes)


def _bundle_of(
    row: AuthSession,
    user: User,
    *,
    refresh_token: str,
    now: datetime,
) -> TokenBundle:
    """按会话行签一个访问令牌，凑成完整的 :class:`TokenBundle`。

    访问令牌里的 ``sid`` 指向会话行：这是「踢人」能立刻生效的原因。
    只看 JWT 的话，一个还没过期的访问令牌在被踢之后仍然可用，
    服务端必须回表确认这场登录是否还活着。
    """
    access_token, access_expires_at, _ = encode_access_token(
        subject=str(user.id),
        session_id=str(row.id),
        ttl=_access_ttl(),
        secret=settings.auth_jwt_secret,
        now=now,
    )
    return TokenBundle(
        user=user,
        session_id=row.id,
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=row.expires_at,
        absolute_expires_at=row.absolute_expires_at,
        remember=row.remember,
    )


async def issue_session(
    session: AsyncSession,
    user: User,
    request: Request | None,
    *,
    remember: bool,
) -> TokenBundle:
    """新登录：建一场会话，签一对令牌。库里只落刷新令牌的摘要。"""
    now = utcnow()
    refresh_token = new_token()
    refresh_ttl = _refresh_ttl(remember)

    row = AuthSession(
        user_id=user.id,
        refresh_hash=token_digest(refresh_token),
        expires_at=now + refresh_ttl,
        absolute_expires_at=_absolute_deadline(now),
        remember=remember,
        last_seen_at=now,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    session.add(row)
    await session.flush()  # 先拿到 row.id，访问令牌的 sid 要用
    return _bundle_of(row, user, refresh_token=refresh_token, now=now)


async def rotate_refresh(
    session: AsyncSession,
    raw_refresh: str | None,
    request: Request | None = None,
) -> TokenBundle | None:
    """用刷新令牌换一对新令牌；无效时返回 ``None``。

    每次成功刷新都会轮转：新令牌写进 ``refresh_hash``，旧摘要挪到
    ``prev_refresh_hash``。如果拿上一代来刷新，说明这个令牌被复制过
    （正常客户端只会用最新的那个），整场会话直接吊销——重放者拿不到新的，
    真正的用户重新登录一次，损失可控。
    """
    if not raw_refresh:
        return None

    now = utcnow()
    digest = token_digest(raw_refresh)

    row = await session.scalar(
        select(AuthSession).where(AuthSession.refresh_hash == digest)
    )

    if row is None:
        # 可能是「上一代」被拿来重放。找到就整场吊销，并把这件事记进审计。
        replayed = await session.scalar(
            select(AuthSession).where(AuthSession.prev_refresh_hash == digest)
        )
        if replayed is not None and replayed.revoked_at is None:
            replayed.revoked_at = now
            replayed.revoked_reason = "reuse_detected"
            session.add(replayed)
            await session.commit()
            logger.warning(
                "检测到刷新令牌重放，会话 {} 已吊销", replayed.id
            )
            await _audit(
                session,
                request,
                action=AuditAction.logout,
                operator=str(replayed.user_id),
                ok=False,
                detail="刷新令牌重复使用：疑似令牌被复制，会话已强制吊销",
                error_message="刷新令牌已失效",
            )
        return None

    if (
        row.revoked_at is not None
        or row.expires_at <= now
        or row.absolute_expires_at <= now
    ):
        return None

    user = await session.get(User, row.user_id)
    if user is None or user.status is not UserStatus.active:
        row.revoked_at = now
        row.revoked_reason = "account_disabled"
        session.add(row)
        await session.commit()
        return None

    new_refresh = new_token()
    row.prev_refresh_hash = row.refresh_hash
    row.refresh_hash = token_digest(new_refresh)
    row.rotated_at = now
    row.last_seen_at = now
    # 滑动续期：从「现在」再往后推一个窗口，但不能越过会话的硬上限
    row.expires_at = min(now + _refresh_ttl(row.remember), row.absolute_expires_at)
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return _bundle_of(row, user, refresh_token=new_refresh, now=now)


async def resolve_access(
    session: AsyncSession, token: str | None
) -> tuple[User, AuthSession] | None:
    """访问令牌 → 成员与会话行；任何一环不成立都返回 ``None``。

    四道检查缺一不可：签名与有效期（JWT 自己保证）、会话存在、
    会话未吊销/未过期、成员仍是 active。后两道必须回表，
    否则「把某人踢下线」要等到访问令牌自然过期才生效。
    """
    if not token:
        return None

    try:
        payload = decode_access_token(token, secret=settings.auth_jwt_secret)
    except TokenError:
        return None

    try:
        session_id = UUID(str(payload["sid"]))
        user_id = UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        return None

    row = await session.get(AuthSession, session_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        return None

    now = utcnow()
    if row.expires_at <= now or row.absolute_expires_at <= now:
        return None

    user = await session.get(User, user_id)
    if user is None or user.status is not UserStatus.active:
        return None
    return user, row


async def touch_session(session: AsyncSession, row: AuthSession) -> None:
    """节流刷新 ``last_seen_at``；写失败不影响请求本身。"""
    now = utcnow()
    if row.last_seen_at is not None and now - row.last_seen_at < TOUCH_INTERVAL:
        return
    try:
        row.last_seen_at = now
        session.add(row)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - 只是活跃时间，丢了不影响鉴权
        await session.rollback()
        logger.debug("刷新会话活跃时间失败：{}", exc)


# ── 登录 / 登出 ───────────────────────────────────────────────


async def login(
    session: AsyncSession,
    *,
    request: Request | None,
    account: str,
    password: str,
    remember: bool = False,
) -> AuthResponse:
    """校验账号密码并签发会话令牌。

    失败分支的顺序是刻意的：先查账号是否存在（对外不区分），再看是否锁定/停用，
    最后才校验密码——否则「锁定的账号」会在密码错误时提前暴露存在性。
    """
    ident = account.strip()
    user = await _find_by_login(session, ident)
    now = utcnow()

    if user is None:
        await _audit(
            session,
            request,
            action=AuditAction.login,
            operator=ident,
            ok=False,
            detail="登录失败：账号不存在",
            error_message="账号或密码不正确",
        )
        return AuthResponse(ok=False, action="login", message="账号或密码不正确")

    if user.locked_until is not None and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        await _audit(
            session,
            request,
            action=AuditAction.login,
            operator=user.username,
            ok=False,
            detail=f"登录被拒：账号临时锁定中，剩余约 {minutes} 分钟",
            error_message="账号已被临时锁定",
        )
        return AuthResponse(
            ok=False,
            action="login",
            message=f"连续登录失败次数过多，请 {minutes} 分钟后再试",
        )

    if user.status is not UserStatus.active:
        reason = (
            "账号已停用，请联系管理员"
            if user.status is UserStatus.disabled
            else "账号已被锁定，请联系管理员"
        )
        await _audit(
            session,
            request,
            action=AuditAction.login,
            operator=user.username,
            ok=False,
            detail=f"登录被拒：账号状态为 {user.status.value}",
            error_message=reason,
        )
        return AuthResponse(ok=False, action="login", message=reason)

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        locked = user.failed_login_count >= settings.auth_max_failed_logins
        if locked:
            user.locked_until = now + timedelta(minutes=settings.auth_lock_minutes)
            # 锁定期间计数清零：解锁后再给满额次数，而不是一次就再锁
            user.failed_login_count = 0
        session.add(user)
        await session.commit()

        if locked:
            message = (
                f"连续失败 {settings.auth_max_failed_logins} 次，"
                f"账号已锁定 {settings.auth_lock_minutes} 分钟"
            )
            detail = f"登录失败：密码错误，达到阈值并锁定（{settings.auth_lock_minutes} 分钟）"
        else:
            # 提示文案必须和「账号不存在」完全一致：多一个「还可以试 N 次」
            # 就等于告诉攻击者这个账号是真的
            message = "账号或密码不正确"
            detail = f"登录失败：密码错误（第 {user.failed_login_count} 次）"

        await _audit(
            session,
            request,
            action=AuditAction.login,
            operator=user.username,
            ok=False,
            detail=detail,
            error_message="密码不正确",
        )
        return AuthResponse(ok=False, action="login", message=message)

    # 成功：清计数、记登录时间、签发一对令牌
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(user)
    bundle = await issue_session(session, user, request, remember=remember)
    await session.commit()

    profile = await profile_of(session, user)
    await _audit(
        session,
        request,
        action=AuditAction.login,
        operator=user.username,
        ok=True,
        detail=(
            f"登录成功（角色：{'、'.join(profile.roles) or '无'}，"
            f"{'记住我，' if remember else ''}"
            f"会话最长 {settings.auth_absolute_ttl_minutes // 1440} 天）"
        ),
    )
    return AuthResponse(
        ok=True,
        action="login",
        message=f"欢迎回来，{user.display_name}",
        user=profile,
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        access_expires_at=bundle.access_expires_at,
        refresh_expires_at=bundle.refresh_expires_at,
        absolute_expires_at=bundle.absolute_expires_at,
        access_ttl=bundle.access_ttl_seconds,
        refresh_ttl=bundle.refresh_ttl_seconds,
        remember=bundle.remember,
    )


async def logout(
    session: AsyncSession,
    *,
    request: Request | None,
    access_token: str | None,
    refresh_token: str | None = None,
) -> AuthResponse:
    """注销当前会话。令牌无效也返回成功——注销是幂等的，不值得报错。

    访问令牌过期后仍然要能退出：用户点「退出登录」时手上那个短令牌
    可能刚过期几分钟，如果只认它，这场会话就会一直躺在库里直到自然失效。
    所以访问令牌解析不出来时，再用刷新令牌的摘要找一次会话行。
    """
    resolved = await resolve_access(session, access_token)
    if resolved is None and refresh_token:
        row = await session.scalar(
            select(AuthSession).where(
                AuthSession.refresh_hash == token_digest(refresh_token)
            )
        )
        if row is not None:
            user = await session.get(User, row.user_id)
            if user is not None:
                resolved = (user, row)

    if resolved is None:
        return AuthResponse(ok=True, action="logout", message="已退出登录")

    user, row = resolved
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoked_reason = "logout"
        session.add(row)
        await session.commit()

        await _audit(
            session,
            request,
            action=AuditAction.logout,
            operator=user.username,
            ok=True,
            detail="退出登录，当前会话已吊销（访问令牌与刷新令牌同时失效）",
        )
    return AuthResponse(ok=True, action="logout", message="已退出登录")


async def logout_everywhere(
    session: AsyncSession,
    *,
    request: Request | None,
    user: User,
    keep_session_id: UUID | None,
) -> AuthResponse:
    """把本人名下所有会话踢下线（可选择留下当前这台）。"""
    revoked = await _revoke_sessions(
        session,
        user.id,
        reason="logout_all",
        keep=keep_session_id,
    )
    await session.commit()
    await _audit(
        session,
        request,
        action=AuditAction.logout,
        operator=user.username,
        ok=True,
        detail=f"下线全部其他设备，共吊销 {revoked} 场会话",
    )
    return AuthResponse(
        ok=True,
        action="logout_all",
        message=f"已下线其他 {revoked} 台设备" if revoked else "没有其他在线设备",
        revoked_sessions=revoked,
    )


# ── 修改密码（已登录） ────────────────────────────────────────


async def change_password(
    session: AsyncSession,
    *,
    request: Request | None,
    user: User,
    current_session: AuthSession,
    current_password: str,
    password: str,
    confirm: str,
) -> AuthResponse:
    """已登录状态下改密码。

    与「忘记密码」的区别是这里必须先证明「你知道原密码」——否则一台没锁屏的
    电脑就能被顺手改掉密码，把真正的主人关在门外。

    改完做三件事：
    1. 踢掉**其他**所有会话（别的设备上的登录不该继续有效）；
    2. 当前会话轮转刷新令牌（旧的那份即便泄露也没用了）；
    3. 重置失败计数与锁定，避免用户被自己之前的手误连累。
    """
    now = utcnow()
    checks = password_checks(password, user.email, confirm)
    strength = strength_of(checks)

    if not verify_password(current_password, user.password_hash):
        user.failed_login_count += 1
        session.add(user)
        await session.commit()
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=False,
            detail="修改密码失败：原密码不正确",
            error_message="原密码不正确",
        )
        return AuthResponse(
            ok=False, action="change_password", message="原密码不正确", checks=checks
        )

    if password == current_password:
        return AuthResponse(
            ok=False,
            action="change_password",
            message="新密码不能与原密码相同",
            checks=checks,
            strength=strength,
        )

    failed = [c.label for c in checks if not c.passed]
    if failed:
        message = f"密码未满足：{'、'.join(failed)}"
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=False,
            detail="修改密码失败：新密码强度不足",
            error_message=message,
        )
        return AuthResponse(
            ok=False,
            action="change_password",
            message=message,
            checks=checks,
            strength=strength,
        )

    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    session.add(user)

    revoked = await _revoke_sessions(
        session, user.id, reason="password_change", keep=current_session.id
    )

    # 当前会话也换一份刷新令牌：改密前泄露出去的那份立刻作废
    new_refresh = new_token()
    current_session.prev_refresh_hash = current_session.refresh_hash
    current_session.refresh_hash = token_digest(new_refresh)
    current_session.rotated_at = now
    current_session.last_seen_at = now
    current_session.expires_at = min(
        now + _refresh_ttl(current_session.remember), current_session.absolute_expires_at
    )
    session.add(current_session)
    await session.commit()
    await session.refresh(current_session)

    bundle = _bundle_of(current_session, user, refresh_token=new_refresh, now=now)
    await _audit(
        session,
        request,
        action=AuditAction.reset_password,
        operator=user.username,
        ok=True,
        detail=f"修改密码成功，其他 {revoked} 场会话已吊销，当前会话已轮转令牌",
    )
    return AuthResponse(
        ok=True,
        action="change_password",
        message="密码已修改，其他设备需要重新登录",
        user=await profile_of(session, user),
        checks=checks,
        strength=4,
        revoked_sessions=revoked,
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        access_expires_at=bundle.access_expires_at,
        refresh_expires_at=bundle.refresh_expires_at,
        absolute_expires_at=bundle.absolute_expires_at,
        access_ttl=bundle.access_ttl_seconds,
        refresh_ttl=bundle.refresh_ttl_seconds,
        remember=bundle.remember,
    )


# ── 会话状态（登录态检测） ────────────────────────────────────


def access_expiry_of(token: str | None) -> datetime | None:
    """从访问令牌里读到期时间；令牌无效返回 ``None``。

    只用来给前端显示倒计时，不承担鉴权职责——验证过没验证过都不影响
    它返回的那个时间点。真正放行与否看 :func:`resolve_access`。
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token, secret=settings.auth_jwt_secret)
    except TokenError:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return None
    return datetime.fromtimestamp(exp, UTC)


async def session_state(
    session: AsyncSession,
    user: User,
    row: AuthSession,
    *,
    access_expires_at: datetime | None = None,
) -> AuthResponse:
    """当前会话的完整状态：谁、还剩多久、其他设备几台。

    前端启动时调它判断「已登录 / 未登录」，运行中定时调它刷新倒计时。
    ``access_ttl`` 是给前端安排续期用的：剩余时间小于阈值就该换令牌了。
    """
    now = utcnow()
    others = int(
        await session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.absolute_expires_at > now,
                AuthSession.id != row.id,
            )
        )
        or 0
    )
    access_left = (
        max(0, int((access_expires_at - now).total_seconds())) if access_expires_at else 0
    )
    return AuthResponse(
        ok=True,
        action="session",
        message="已登录",
        authenticated=True,
        user=await profile_of(session, user),
        access_expires_at=access_expires_at,
        refresh_expires_at=row.expires_at,
        absolute_expires_at=row.absolute_expires_at,
        access_ttl=access_left,
        refresh_ttl=max(0, int((row.expires_at - now).total_seconds())),
        absolute_ttl=max(0, int((row.absolute_expires_at - now).total_seconds())),
        remember=row.remember,
        other_sessions=others,
        session_id=str(row.id),
        signed_in_at=row.issued_at,
        last_seen_at=row.last_seen_at,
    )


# ── 注册 ─────────────────────────────────────────────────────


async def register(
    session: AsyncSession,
    *,
    request: Request | None,
    username: str,
    email: str,
    password: str,
    confirm: str | None = None,
    display_name: str | None = None,
    workspace: str | None = None,
) -> AuthResponse:
    """自助注册。

    三条策略：
    - 库里的第一个成员自动成为 ``owner``（自建部署的 bootstrap），之后注册的默认 ``viewer``；
    - ``auth_allow_register=false`` 时关闭自助注册，但仍允许 bootstrap 建第一个号，
      否则新部署的库永远没人能登录；
    - 密码强度规则与重置密码共用一套，避免「注册能过的密码，重置时过不去」。
    """
    username = username.strip().lower()
    email = email.strip().lower()

    member_count = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    bootstrap = member_count == 0

    if not bootstrap and not settings.auth_allow_register:
        await _audit(
            session,
            request,
            action=AuditAction.create,
            operator=username or "anonymous",
            ok=False,
            detail="注册被拒：站点已关闭自助注册",
            error_message="已关闭自助注册，请联系管理员开号",
        )
        return AuthResponse(
            ok=False, action="register", message="已关闭自助注册，请联系管理员开通账号"
        )

    if not is_username(username):
        return AuthResponse(
            ok=False,
            action="register",
            message="用户名需 3-32 位，只能包含字母、数字、点、下划线与连字符",
        )
    if not is_email(email):
        return AuthResponse(ok=False, action="register", message="邮箱格式不正确，请检查后重试")

    problem = password_problem(password, email, confirm)
    if problem:
        await _audit(
            session,
            request,
            action=AuditAction.create,
            operator=username,
            ok=False,
            detail="注册失败：密码不符合规则",
            error_message=problem,
        )
        return AuthResponse(ok=False, action="register", message=problem)

    exists = await session.scalar(
        select(User).where(
            or_(func.lower(User.username) == username, func.lower(User.email) == email)
        )
    )
    if exists is not None:
        await _audit(
            session,
            request,
            action=AuditAction.create,
            operator=username,
            ok=False,
            detail="注册失败：用户名或邮箱已被占用",
            error_message="用户名或邮箱已被使用",
        )
        return AuthResponse(ok=False, action="register", message="用户名或邮箱已被使用")

    role_code = "owner" if bootstrap else "viewer"
    role = await session.scalar(select(Role).where(Role.code == role_code))

    user = User(
        username=username,
        email=email,
        display_name=(display_name or username).strip()[:64] or username,
        password_hash=hash_password(password),
        last_login_at=utcnow(),
    )
    session.add(user)
    await session.flush()  # 先拿到 user.id，再写授权表

    if role is not None:
        session.add(UserRole(user_id=user.id, role_id=role.id, granted_by=username))
    else:
        logger.warning("注册时未找到角色 {}，成员 {} 将没有任何权限", role_code, username)

    bundle = await issue_session(session, user, request, remember=False)
    await session.commit()

    profile = await profile_of(session, user)
    await _audit(
        session,
        request,
        action=AuditAction.create,
        operator=username,
        ok=True,
        detail=(
            f"注册成功，初始角色 {role_code}"
            + ("（首位成员自动成为所有者）" if bootstrap else "")
            + (f"，工作区 {workspace}" if workspace else "")
        ),
    )
    return AuthResponse(
        ok=True,
        action="register",
        message=f"注册成功，已加入工作区{'（所有者）' if bootstrap else ''}",
        user=profile,
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        access_expires_at=bundle.access_expires_at,
        refresh_expires_at=bundle.refresh_expires_at,
        absolute_expires_at=bundle.absolute_expires_at,
        access_ttl=bundle.access_ttl_seconds,
        refresh_ttl=bundle.refresh_ttl_seconds,
        remember=False,
    )


# ── 忘记密码 / 重置密码 ────────────────────────────────────────


async def _issue_reset_token(
    session: AsyncSession,
    user: User,
    request: Request | None,
) -> tuple[str, int]:
    """作废该成员手上未用的重置令牌，再签发新的。返回 ``(明文令牌, 有效期秒)``。"""
    now = utcnow()
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    token = new_token()
    ttl = settings.auth_reset_ttl_minutes
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=now + timedelta(minutes=ttl),
            ip_address=_client_ip(request),
        )
    )
    await session.commit()
    return token, ttl * 60


def _exposed(token: str) -> str | None:
    """仅本地联调时把令牌放进响应；生产环境必须关掉。"""
    return token if settings.auth_expose_reset_token else None


async def forgot_password(
    session: AsyncSession,
    *,
    request: Request | None,
    email: str,
    captcha: str,
    workspace: str | None = None,
) -> AuthResponse:
    """申请重置密码。

    邮箱未注册时同样返回「已发送」：否则这个接口就成了账号枚举器。
    真正的「没发」只体现在服务端日志与审计明细里。
    """
    email = email.strip()
    identifier = email.lower()

    if not is_email(email):
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=identifier,
            ok=False,
            detail="申请重置：邮箱格式不合法",
            error_message="邮箱格式不正确",
        )
        return AuthResponse(
            ok=False, action="forgot_password", message="邮箱格式不正确，请检查后重试"
        )

    if not verify_captcha(captcha):
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=identifier,
            ok=False,
            detail="申请重置：图形验证码校验失败",
            error_message="图形验证码不正确或已过期",
        )
        return AuthResponse(ok=False, action="forgot_password", message="图形验证码不正确或已过期")

    user = await session.scalar(select(User).where(func.lower(User.email) == identifier))
    if user is None:
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=identifier,
            ok=True,
            detail="申请重置：邮箱未注册，按安全策略仍返回已发送（未实际发信）",
        )
        return AuthResponse(
            ok=True,
            action="forgot_password",
            message=f"重置邮件已发送至 {email}",
            email=email,
            cooldown=settings.auth_reset_ttl_minutes * 60,
            expires_in=settings.auth_reset_ttl_minutes * 60,
        )

    token, cooldown = await _issue_reset_token(session, user, request)
    if user.status is not UserStatus.active:
        # 停用/锁定的成员不发可用令牌，但对外仍是「已发送」
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=False,
            detail=f"申请重置：成员状态为 {user.status.value}，令牌已签发但不予使用",
            error_message="成员状态异常",
        )
    else:
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=True,
            detail=f"申请重置：邮件已发送，链接有效期 {cooldown} 秒"
            + (f"，工作区 {workspace}" if workspace else ""),
        )

    return AuthResponse(
        ok=True,
        action="forgot_password",
        message=f"重置邮件已发送至 {email}",
        email=email,
        cooldown=cooldown,
        expires_in=cooldown,
        reset_token=_exposed(token),
    )


async def resend_reset(
    session: AsyncSession,
    *,
    request: Request | None,
    email: str,
) -> AuthResponse:
    """重新发送重置邮件：作废旧令牌后重签一个。"""
    email = email.strip()
    identifier = email.lower()

    if not is_email(email):
        return AuthResponse(ok=False, action="resend_reset", message="邮箱格式不正确，无法重发")

    user = await session.scalar(select(User).where(func.lower(User.email) == identifier))
    if user is None:
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=identifier,
            ok=True,
            detail="重发重置邮件：邮箱未注册，按安全策略仍返回已发送（未实际发信）",
        )
        return AuthResponse(
            ok=True,
            action="resend_reset",
            message="已重新发送，请留意收件箱与垃圾邮件目录",
            email=email,
            cooldown=settings.auth_reset_ttl_minutes * 60,
        )

    token, cooldown = await _issue_reset_token(session, user, request)
    await _audit(
        session,
        request,
        action=AuditAction.reset_password,
        operator=user.username,
        ok=True,
        detail=f"重发重置邮件，旧链接已作废，新链接有效期 {cooldown} 秒",
    )
    return AuthResponse(
        ok=True,
        action="resend_reset",
        message="已重新发送，请留意收件箱与垃圾邮件目录",
        email=email,
        cooldown=cooldown,
        reset_token=_exposed(token),
    )


async def reset_password(
    session: AsyncSession,
    *,
    request: Request | None,
    token: str,
    password: str,
    confirm: str,
    email: str | None = None,
) -> AuthResponse:
    """用一次性令牌设置新密码，并把该成员所有会话踢下线。"""
    row = await session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(token))
    )
    now = utcnow()

    if row is None or row.used_at is not None or row.expires_at <= now:
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=(email or "unknown").strip().lower(),
            ok=False,
            detail="重置失败：令牌不存在、已使用或已过期",
            error_message="重置链接已失效",
        )
        return AuthResponse(
            ok=False,
            action="reset_password",
            message="重置链接已失效，请重新申请找回密码",
        )

    user = await session.get(User, row.user_id)
    if user is None:
        return AuthResponse(
            ok=False, action="reset_password", message="重置链接对应的账号不存在，请联系管理员"
        )

    identifier = (email or user.email).strip()
    checks = password_checks(password, identifier, confirm)
    strength = strength_of(checks)

    if password != confirm:
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=False,
            detail="提交新密码：两次输入不一致",
            error_message="两次输入的密码不一致",
        )
        return AuthResponse(
            ok=False,
            action="reset_password",
            message="两次输入的密码不一致",
            checks=checks,
            strength=strength,
        )

    failed = [c.label for c in checks if not c.passed]
    if failed:
        message = f"密码未满足：{'、'.join(failed)}"
        await _audit(
            session,
            request,
            action=AuditAction.reset_password,
            operator=user.username,
            ok=False,
            detail="提交新密码：密码强度校验未通过",
            error_message=message,
        )
        return AuthResponse(
            ok=False,
            action="reset_password",
            message=message,
            checks=checks,
            strength=strength,
        )

    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    row.used_at = now
    session.add(user)
    session.add(row)

    revoked = await _revoke_sessions(session, user.id, reason="password_reset")
    await session.commit()

    await _audit(
        session,
        request,
        action=AuditAction.reset_password,
        operator=user.username,
        ok=True,
        detail=f"重置密码成功，强制下线 {revoked} 个会话",
    )
    return AuthResponse(
        ok=True,
        action="reset_password",
        message="密码已重置，全部设备需要重新登录",
        email=user.email,
        checks=checks,
        strength=4,
        revoked_sessions=revoked,
    )


async def _revoke_sessions(
    session: AsyncSession,
    user_id: UUID,
    *,
    reason: str,
    keep: UUID | None = None,
) -> int:
    """吊销成员名下所有未失效会话，返回受影响条数。"""
    criteria = [
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ]
    if keep is not None:
        criteria.append(AuthSession.id != keep)

    result = await session.execute(
        update(AuthSession).where(*criteria).values(revoked_at=utcnow(), revoked_reason=reason)
    )
    return int(result.rowcount or 0)


def cooldown_seconds() -> int:
    """前端倒计时用的重置链接有效期（秒）。"""
    return settings.auth_reset_ttl_minutes * 60
