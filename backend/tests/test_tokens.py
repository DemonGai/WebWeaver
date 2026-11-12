"""双令牌：签发、续期、轮转、重放检测、到期踢出、改密与全局下线。

这些用例绝大多数会真的读写 ``auth_sessions``，所以每个用例结束后
把 ``user_agent='testclient'`` 的会话清掉——测试不该在开发库里堆垃圾。
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.db import SessionLocal, dispose
from app.core.security import encode_access_token, token_digest
from app.main import app
from app.models import AuthSession, User
from app.services.seed import DEMO_PASSWORD

client = TestClient(app)
TEST_UA = "testclient"
ADMIN = "admin_chen"

# 本文件里所有「改完要还原」的清理都以这个时刻为界：
# 只删本轮跑出来的审计行，开发库里更早的手工记录一概不碰
RUN_STARTED = datetime.now(UTC)


# ── 工具 ─────────────────────────────────────────────────────


def _run(coro_fn) -> None:
    try:
        asyncio.run(coro_fn())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture(autouse=True)
def clean_sessions():
    """每个用例前后都清掉测试留下的会话，避免相互干扰。"""
    _purge()

    def run() -> None:
        _purge()

    yield
    run()


def _purge() -> None:
    async def go() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(AuthSession).where(AuthSession.user_agent == TEST_UA))
            await session.commit()

    _run(go)


def _login(account: str = ADMIN, password: str = DEMO_PASSWORD, remember: bool = False) -> dict:
    client.cookies.clear()
    body = client.post(
        "/api/auth",
        json={"action": "login", "account": account, "password": password, "remember": remember},
    ).json()
    assert body["ok"] is True, body
    return body


def _access() -> str:
    token = client.cookies.get("wv_at")
    assert token
    return token


def _refresh() -> str:
    token = client.cookies.get("wv_rt")
    assert token
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session_of(refresh: str) -> AuthSession:
    """按刷新令牌摘要取会话行。"""

    async def go() -> AuthSession:
        async with SessionLocal() as session:
            row = await session.scalar(
                select(AuthSession).where(AuthSession.refresh_hash == token_digest(refresh))
            )
            assert row is not None, "会话行应当存在"
            return row

    return _run_result(go)


def _run_result(coro_fn):
    try:
        return asyncio.run(coro_fn())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


def _patch_session(refresh: str, **values) -> None:
    """直接改库，模拟时间流逝导致的过期。"""

    async def go() -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.refresh_hash == token_digest(refresh))
                .values(**values)
            )
            await session.commit()

    _run(go)


# ── 登录态检测 ───────────────────────────────────────────────


def test_session_reports_anonymous_without_token() -> None:
    client.cookies.clear()
    body = client.get("/api/auth/session").json()

    # 未登录是 200 而不是 401：这是启动时的常规探测，不该触发前端的续期逻辑
    assert body["ok"] is True
    assert body["authenticated"] is False
    assert body["user"] is None


def test_session_reports_remaining_time() -> None:
    _login(remember=True)
    body = client.get("/api/auth/session").json()

    assert body["authenticated"] is True
    assert body["user"]["username"] == ADMIN
    assert body["remember"] is True
    # 访问令牌 30 分钟、刷新令牌 30 天，各自的剩余时间都要给出来
    assert 1700 <= body["access_ttl"] <= settings.auth_access_ttl_minutes * 60
    assert body["refresh_ttl"] > 29 * 24 * 3600
    assert body["absolute_ttl"] > 0
    assert body["session_id"] and body["signed_in_at"]


def test_session_counts_other_devices() -> None:
    _login()
    client.cookies.clear()
    _login()

    # 刚才那场会话仍在库里，所以第二场应当看到「另有 1 台」
    body = client.get("/api/auth/session").json()
    assert body["other_sessions"] == 1


# ── 续期与轮转 ───────────────────────────────────────────────


def test_refresh_rotates_both_tokens() -> None:
    _login()
    old_access, old_refresh = _access(), _refresh()

    body = client.post("/api/auth/refresh").json()
    assert body["ok"] is True and body["action"] == "refresh"

    new_access, new_refresh = _access(), _refresh()
    assert new_access != old_access
    assert new_refresh != old_refresh
    # 令牌换了，但仍属于同一场会话（轮转不是新登录）
    assert body["user"]["username"] == ADMIN

    # 旧访问令牌已经带不动请求了？不——它没被吊销，只是不再被下发。
    # 会话还在，所以它仍然可用，直到自己过期。真正的失效手段是吊销整场会话。
    assert client.get("/api/auth/me", headers=_auth(old_access)).status_code == 200


def test_expired_access_token_is_renewable() -> None:
    _login()
    refresh = _refresh()
    row = _session_of(refresh)

    # 手工造一个「刚过期」的访问令牌，模拟用户离开了 40 分钟
    expired, _, _ = encode_access_token(
        subject=str(row.user_id),
        session_id=str(row.id),
        ttl=timedelta(seconds=-60),
        secret=settings.auth_jwt_secret,
    )
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=_auth(expired)).status_code == 401

    # 刷新令牌还有效，所以续期之后又能用了
    client.cookies.set("wv_rt", refresh, path="/api/auth")
    renewed = client.post("/api/auth/refresh")
    assert renewed.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_tampered_access_token_rejected() -> None:
    _login()
    token = _access()
    header, body, signature = token.split(".")
    forged = f"{header}.{body}.{'A' * len(signature)}"

    client.cookies.clear()
    assert client.get("/api/auth/me", headers=_auth(forged)).status_code == 401


def test_refresh_rejects_expired_refresh_token() -> None:
    _login()
    refresh = _refresh()

    past = datetime.now(UTC) - timedelta(minutes=1)
    _patch_session(refresh, expires_at=past)

    client.cookies.clear()
    client.cookies.set("wv_rt", refresh, path="/api/auth")
    res = client.post("/api/auth/refresh")
    assert res.status_code == 401
    # 401 要顺带把 Cookie 清掉，否则浏览器会一直带着一个死令牌
    expired_cookie = [
        value for value in res.headers.get_list("set-cookie") if value.startswith("wv_rt=")
    ]
    assert expired_cookie and 'Max-Age=0' in expired_cookie[0]


def test_absolute_deadline_ends_session_even_with_valid_refresh() -> None:
    _login()
    refresh = _refresh()

    past = datetime.now(UTC) - timedelta(seconds=1)
    _patch_session(refresh, absolute_expires_at=past)

    client.cookies.clear()
    client.cookies.set("wv_rt", refresh, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_token_replay_kills_whole_session() -> None:
    _login()
    first = _refresh()

    assert client.post("/api/auth/refresh").status_code == 200
    second = _refresh()
    assert second != first

    # 有人拿着上一代来换令牌：说明它被复制过
    client.cookies.clear()
    client.cookies.set("wv_rt", first, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401

    # 整场会话都作废，最新那代也用不了了
    client.cookies.clear()
    client.cookies.set("wv_rt", second, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401

    row = _session_of(second)
    assert row.revoked_reason == "reuse_detected"


# ── 修改密码 ─────────────────────────────────────────────────


def test_change_password_requires_current_password() -> None:
    _login()
    body = client.post(
        "/api/auth",
        json={
            "action": "change_password",
            "current_password": "definitely-wrong",
            "password": "Nw#Cluster2026",
            "confirm": "Nw#Cluster2026",
        },
    ).json()

    assert body["ok"] is False
    assert "原密码" in body["message"]


def test_change_password_rejects_weak_and_identical() -> None:
    _login()
    same = client.post(
        "/api/auth",
        json={
            "action": "change_password",
            "current_password": DEMO_PASSWORD,
            "password": DEMO_PASSWORD,
            "confirm": DEMO_PASSWORD,
        },
    ).json()
    assert same["ok"] is False
    assert "不能与原密码相同" in same["message"]

    weak = client.post(
        "/api/auth",
        json={
            "action": "change_password",
            "current_password": DEMO_PASSWORD,
            "password": "abcdefghij",
            "confirm": "abcdefghij",
        },
    ).json()
    assert weak["ok"] is False
    assert weak["checks"] and any(not c["passed"] for c in weak["checks"])


def test_change_password_kicks_other_devices_but_keeps_current() -> None:
    # 设备 A
    _login()
    token_a = _access()

    # 设备 B
    client.cookies.clear()
    _login()
    token_b = _access()
    refresh_b = _refresh()

    new_password = "Nw#Cluster2026"
    done = client.post(
        "/api/auth",
        json={
            "action": "change_password",
            "current_password": DEMO_PASSWORD,
            "password": new_password,
            "confirm": new_password,
        },
    ).json()

    try:
        assert done["ok"] is True, done["message"]
        assert done["revoked_sessions"] >= 1
        # 当前设备换了新的刷新令牌，旧的那份立刻作废
        assert _refresh() != refresh_b

        # A 被踢；B 还活着
        client.cookies.clear()
        assert client.get("/api/auth/me", headers=_auth(token_a)).status_code == 401
        assert client.get("/api/auth/me", headers=_auth(token_b)).status_code == 200

        # 旧密码不能登录，新密码可以
        client.cookies.clear()
        old = client.post(
            "/api/auth", json={"action": "login", "account": ADMIN, "password": DEMO_PASSWORD}
        ).json()
        assert old["ok"] is False
        fresh = client.post(
            "/api/auth", json={"action": "login", "account": ADMIN, "password": new_password}
        ).json()
        assert fresh["ok"] is True
    finally:
        _restore_password()


def _restore_password() -> None:
    """把演示账号的密码、锁定状态与改密痕迹改回去，别影响其他用例。

    只恢复 ``password_hash`` 是不够的：``/api/user/profile`` 的
    ``password_updated_at`` 是**从审计日志里算出来的**（取该用户最近一条
    ``reset_password`` 成功记录的 ``occurred_at``）。不删那条记录，
    别的用例就会看到一个「刚刚改过密码」的账号。
    """

    async def go() -> None:
        from app.core.security import hash_password
        from app.models import AuditLog, AuditResult
        from app.models.audit import AuditAction

        async with SessionLocal() as session:
            user = await session.scalar(select(User).where(User.username == ADMIN))
            assert user is not None
            user.password_hash = hash_password(DEMO_PASSWORD)
            user.failed_login_count = 0
            user.locked_until = None
            session.add(user)
            # 只删本轮跑出来的那几条，别动开发库里更早的手工记录
            await session.execute(
                delete(AuditLog).where(
                    AuditLog.action == AuditAction.reset_password,
                    AuditLog.operator == ADMIN,
                    AuditLog.result == AuditResult.success,
                    AuditLog.occurred_at >= RUN_STARTED,
                )
            )
            await session.commit()

    _run(go)


def test_change_password_requires_login() -> None:
    client.cookies.clear()
    res = client.post(
        "/api/auth",
        json={
            "action": "change_password",
            "current_password": DEMO_PASSWORD,
            "password": "Nw#Cluster2026",
            "confirm": "Nw#Cluster2026",
        },
    )
    assert res.status_code == 401


# ── 下线所有设备 ─────────────────────────────────────────────


def test_logout_all_keeps_current_device_by_default() -> None:
    _login()
    token_a = _access()

    client.cookies.clear()
    _login()
    token_b = _access()

    body = client.post("/api/auth", json={"action": "logout_all", "keep_current": True}).json()
    assert body["ok"] is True
    assert body["revoked_sessions"] >= 1

    client.cookies.clear()
    assert client.get("/api/auth/me", headers=_auth(token_a)).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(token_b)).status_code == 200


def test_logout_all_can_drop_everything() -> None:
    _login()
    assert client.get("/api/auth/me").status_code == 200

    body = client.post("/api/auth", json={"action": "logout_all", "keep_current": False}).json()
    assert body["ok"] is True
    # 连自己这台也下线了，Cookie 一并清掉
    assert client.cookies.get("wv_at") is None
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
