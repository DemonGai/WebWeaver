"""登录流程：单入口分发、会话令牌、锁定策略、注册、找回密码。

这些用例会真实改库（登录计数、密码、会话），所以每个用例末尾都恢复现场：
演示成员的密码与锁状态复位，测试写下的会话 / 重置令牌删除，
临时注册的成员整条清掉。这样反复跑测试不会把开发库越改越乱。
"""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.db import SessionLocal, dispose
from app.core.security import hash_password, token_digest, verify_password
from app.main import app
from app.models import AuthSession, PasswordResetToken, User, UserRole
from app.services import auth_service
from app.services.seed import DEMO_PASSWORD

client = TestClient(app)
DEMO_USERNAMES = ["admin_chen", "ops_lee", "viewer_lin"]
STRONG_PASSWORD = "Ww#Cluster2026!"


# ── 工具 ─────────────────────────────────────────────────────


def _post(**body):
    return client.post("/api/auth", json=body)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _run(coro_fn) -> None:
    """在同步测试里跑一段异步数据库操作（NullPool，安全）。"""
    try:
        asyncio.run(coro_fn())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


async def _purge_user(username: str) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == username))
        if user is None:
            return
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        await session.delete(user)
        await session.commit()


@pytest.fixture
def restored_demo_users(seeded_database: None):
    """演示成员的现场恢复：密码回默认口令、锁计数清零、测试会话删除。"""
    yield

    async def run() -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(User)
                .where(User.username.in_(DEMO_USERNAMES))
                .values(
                    password_hash=hash_password(DEMO_PASSWORD),
                    failed_login_count=0,
                    locked_until=None,
                )
            )
            await session.execute(delete(AuthSession).where(AuthSession.ip_address == "testclient"))
            await session.execute(
                delete(PasswordResetToken).where(PasswordResetToken.ip_address == "testclient")
            )
            await session.commit()

    _run(run)


# ── 密码哈希本身 ──────────────────────────────────────────────


def test_password_hash_roundtrip() -> None:
    digest = hash_password("Ww#Cluster2026!")
    assert digest.startswith("scrypt$n=16384,r=8,p=1$")
    assert "Ww#Cluster2026!" not in digest
    assert verify_password("Ww#Cluster2026!", digest)
    assert not verify_password("Ww#Cluster2026", digest)
    # 空值与损坏的哈希串一律判失败，不抛异常
    assert not verify_password("x", None)
    assert not verify_password("x", "bcrypt$broken")


# ── 登录 ─────────────────────────────────────────────────────


def test_login_returns_token_and_profile(restored_demo_users: None) -> None:
    body = _post(action="login", account="admin_chen", password=DEMO_PASSWORD).json()

    assert body["ok"] is True
    assert body["action"] == "login"
    assert body["token"]
    assert body["expires_at"]
    assert body["user"]["username"] == "admin_chen"
    assert body["user"]["roles"] == ["owner"]
    assert body["user"]["is_superuser"] is False
    assert "user:delete" in body["user"]["permissions"]
    # 响应里不能出现密码哈希
    assert "password_hash" not in body["user"]

    me = client.get("/api/auth/me", headers=_auth(body["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin_chen"

    # 库里存的是摘要，不是令牌明文
    async def check() -> None:
        async with SessionLocal() as session:
            row = await session.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(body["token"]))
            )
            assert row is not None
            assert row.token_hash != body["token"]
            assert len(row.token_hash) == 64
            assert row.revoked_at is None

    _run(check)


def test_login_email_is_accepted_case_insensitively(restored_demo_users: None) -> None:
    body = _post(action="login", account="Ops_Lee@WebWeaver.IO", password=DEMO_PASSWORD).json()
    assert body["ok"] is True
    assert body["user"]["username"] == "ops_lee"
    assert body["user"]["roles"] == ["operator"]


def test_login_unknown_account_and_wrong_password_look_identical(
    restored_demo_users: None,
) -> None:
    wrong = _post(action="login", account="admin_chen", password="not-the-password").json()
    ghost = _post(action="login", account="nobody_here", password="not-the-password").json()

    assert wrong["ok"] is False and ghost["ok"] is False
    assert wrong["message"] == ghost["message"] == "账号或密码不正确"


def test_login_locks_after_threshold(restored_demo_users: None) -> None:
    limit = settings.auth_max_failed_logins
    for _ in range(limit - 1):
        body = _post(action="login", account="ops_lee", password="wrong").json()
        assert body["ok"] is False
        assert body["message"] == "账号或密码不正确"

    locked = _post(action="login", account="ops_lee", password="wrong").json()
    assert locked["ok"] is False
    assert "锁定" in locked["message"]

    # 锁定期间即使密码正确也拒绝：否则爆破脚本只要慢一点就能绕过
    blocked = _post(action="login", account="ops_lee", password=DEMO_PASSWORD).json()
    assert blocked["ok"] is False
    assert "分钟后再试" in blocked["message"]


def test_logout_revokes_current_token(restored_demo_users: None) -> None:
    token = _post(action="login", account="viewer_lin", password=DEMO_PASSWORD).json()["token"]

    out = client.post("/api/auth", json={"action": "logout"}, headers=_auth(token)).json()
    assert out["ok"] is True
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401

    # 再注销一次仍然是成功：注销是幂等的
    again = client.post("/api/auth", json={"action": "logout"}, headers=_auth(token)).json()
    assert again["ok"] is True


# ── 注册 ─────────────────────────────────────────────────────


def test_register_creates_viewer(restored_demo_users: None) -> None:
    username = f"tmp_{uuid4().hex[:8]}"
    body = _post(
        action="register",
        username=username,
        email=f"{username}@webweaver.io",
        password=STRONG_PASSWORD,
        display_name="临时成员",
    ).json()

    try:
        assert body["ok"] is True, body["message"]
        assert body["token"]
        assert body["user"]["roles"] == ["viewer"]
        assert "browser:read" in body["user"]["permissions"]
        assert "browser:delete" not in body["user"]["permissions"]

        me = client.get("/api/auth/me", headers=_auth(body["token"])).json()
        assert me["user"]["display_name"] == "临时成员"

        duplicate = _post(
            action="register",
            username=username,
            email=f"other_{username}@webweaver.io",
            password=STRONG_PASSWORD,
        ).json()
        assert duplicate["ok"] is False
        assert "已被使用" in duplicate["message"]
    finally:
        _run(lambda: _purge_user(username))


def test_register_rejects_weak_password_and_bad_username(restored_demo_users: None) -> None:
    weak = _post(
        action="register",
        username=f"tmp_{uuid4().hex[:6]}",
        email="weak@webweaver.io",
        # 8 位以上但全是小写字母：长度够，字符类规则不过，走业务层校验
        password="abcdefghij",
    ).json()
    assert weak["ok"] is False
    assert "密码未满足" in weak["message"]

    bad_name = _post(
        action="register", username="a b", email="bad@webweaver.io", password=STRONG_PASSWORD
    )
    # 用户名格式由 schema 的正则拦住，进不了业务层
    assert bad_name.status_code == 422


# ── 找回 / 重置密码 ───────────────────────────────────────────


def test_forgot_password_does_not_leak_account_existence(
    restored_demo_users: None,
) -> None:
    code = client.get("/api/auth/captcha").json()["code"]

    bad_captcha = _post(
        action="forgot_password", email="viewer_lin@webweaver.io", captcha="0000"
    ).json()
    assert bad_captcha["ok"] is False
    assert "验证码" in bad_captcha["message"]

    unknown = _post(action="forgot_password", email="ghost@webweaver.io", captcha=code).json()
    assert unknown["ok"] is True
    assert unknown["message"].startswith("重置邮件已发送")
    # 未注册的邮箱不该拿到可用令牌
    assert unknown["reset_token"] is None


def test_reset_password_flow(restored_demo_users: None) -> None:
    if not settings.auth_expose_reset_token:
        pytest.skip("AUTH_EXPOSE_RESET_TOKEN 未开启，无法在不发邮件的情况下走通重置")

    # 先登录一次，重置后要能统计出被踢下线的会话
    login = _post(action="login", account="viewer_lin", password=DEMO_PASSWORD).json()
    assert login["ok"] is True

    code = client.get("/api/auth/captcha").json()["code"]
    asked = _post(action="forgot_password", email="viewer_lin@webweaver.io", captcha=code).json()
    token = asked["reset_token"]
    assert token

    weak = _post(action="reset_password", token=token, password="abc123", confirm="abc123").json()
    assert weak["ok"] is False
    assert any(c["key"] == "length" and not c["passed"] for c in weak["checks"])

    mismatch = _post(
        action="reset_password", token=token, password=STRONG_PASSWORD, confirm="Ww#Cluster2026"
    ).json()
    assert mismatch["ok"] is False
    assert "不一致" in mismatch["message"]

    done = _post(
        action="reset_password",
        token=token,
        password=STRONG_PASSWORD,
        confirm=STRONG_PASSWORD,
        email="viewer_lin@webweaver.io",
    ).json()
    assert done["ok"] is True
    assert done["strength"] == 4
    assert done["revoked_sessions"] >= 1

    # 旧令牌一次性：重放直接失效
    replay = _post(
        action="reset_password",
        token=token,
        password=STRONG_PASSWORD,
        confirm=STRONG_PASSWORD,
    ).json()
    assert replay["ok"] is False
    assert "失效" in replay["message"]

    # 旧密码不能用了，新密码可以
    old_password = _post(action="login", account="viewer_lin", password=DEMO_PASSWORD).json()
    assert old_password["ok"] is False
    new_password = _post(action="login", account="viewer_lin", password=STRONG_PASSWORD).json()
    assert new_password["ok"] is True

    # 会话令牌全部被吊销：重置前签发的那个已经不能用了
    assert client.get("/api/auth/me", headers=_auth(login["token"])).status_code == 401


def test_reset_password_rejects_unknown_token() -> None:
    body = _post(
        action="reset_password",
        token="not-a-real-token-value",
        password=STRONG_PASSWORD,
        confirm=STRONG_PASSWORD,
    ).json()
    assert body["ok"] is False
    assert "失效" in body["message"]


# ── 审计 ─────────────────────────────────────────────────────


def test_login_failures_are_audited(restored_demo_users: None) -> None:
    _post(action="login", account="admin_chen", password="wrong")

    logs = client.get("/api/audit-logs", params={"action": "login"}).json()
    assert logs["total"] >= 1
    assert logs["items"][0]["result"] == "failure"
    assert logs["items"][0]["resource_type"] == "auth"


def test_profile_resolves_effective_permissions(restored_demo_users: None) -> None:
    """profile_of 直接给前端可用的「角色 + 权限点」，不用再查两个接口。"""

    async def run() -> None:
        async with SessionLocal() as session:
            user = await session.scalar(select(User).where(User.username == "ops_lee"))
            assert user is not None
            profile = await auth_service.profile_of(session, user)
            assert profile.roles == ["operator"]
            assert len(profile.permissions) == 13
            assert "browser:execute" in profile.permissions
            assert "role:delete" not in profile.permissions

    _run(run)
