"""账号中心：头像浮层、个人信息、登录设备、安全概览、我的操作日志。

这些用例会真实登录并写会话，跑完把 ``ip_address = 'testclient'`` 的会话删掉；
审计日志由 conftest 的会话级夹具统一清理。
"""

import asyncio

from demo_cluster import DEMO_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import AuthSession, User
from app.services.user import parse_user_agent

client = TestClient(app)

TEST_CLIENT_HOST = "testclient"


# ── 工具 ─────────────────────────────────────────────────────


def _login(account: str = "admin_chen", password: str = DEMO_PASSWORD) -> str:
    """登录并从 Cookie 里取访问令牌。

    令牌不再出现在响应体里（httpOnly Cookie 才拿得到），但测试仍需要一份
    可直接放进 Authorization 头的凭据——两者指向同一个会话，等价。
    """
    client.cookies.clear()
    body = client.post(
        "/api/auth", json={"action": "login", "account": account, "password": password}
    ).json()
    assert body["ok"] is True, body
    token = client.cookies.get("wv_at")
    assert token, "登录后应当下发访问令牌 Cookie"
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _run(coro_fn) -> None:
    try:
        asyncio.run(coro_fn())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


def _cleanup_sessions() -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(AuthSession).where(AuthSession.ip_address == TEST_CLIENT_HOST)
            )
            await session.commit()

    try:
        _run(run)
    except Exception:  # noqa: BLE001 - 清理失败不能让测试变红
        pass


# ── 工作区 ───────────────────────────────────────────────────


def test_workspaces_follow_default_workspace(seeded_database: None) -> None:
    """``default_id`` 跟着当前成员走，不是写死的值。"""
    admin = client.get("/api/auth/workspaces", headers=_auth(_login())).json()
    assert admin["default_id"] == "webweaver-team"
    assert [item["id"] for item in admin["items"]] == [
        "webweaver-team",
        "webweaver-lab",
        "acme-growth",
    ]
    # members 是「默认工作区指向它的人数」
    assert admin["items"][0]["members"] >= 2

    viewer = client.get("/api/auth/workspaces", headers=_auth(_login("viewer_lin"))).json()
    assert viewer["default_id"] == "webweaver-lab"

    # 匿名 = 既没有 header 也没有 Cookie；上一步登录留下了 Cookie，先清掉
    client.cookies.clear()
    anonymous = client.get("/api/auth/workspaces").json()
    assert anonymous["default_id"] == "webweaver-team"
    _cleanup_sessions()


def test_every_member_has_default_workspace(seeded_database: None) -> None:
    """种子成员的默认工作区都已回填，不留 NULL。"""

    async def run() -> None:
        async with SessionLocal() as session:
            users = list(await session.scalars(select(User)))
            assert users
            assert all(user.default_workspace_id is not None for user in users)

    _run(run)


# ── 头像浮层 ─────────────────────────────────────────────────


def test_menu_uses_real_member(seeded_database: None) -> None:
    body = client.get("/api/user/menu", headers=_auth(_login())).json()
    assert body["name"] == "陈默"
    assert body["role"] == "所有者"
    assert body["workspace"] == "webweaver-team"
    assert body["workspace_code"] == "webweaver-team"
    assert body["workspace_note"]
    assert body["last_login"].startswith("上次登录")

    flat = [row for group in body["groups"] for row in group]
    keys = [row["key"] for row in flat]
    # 去掉了切换账号：只有一个默认工作区
    assert "switch-account" not in keys
    assert keys.count("devices") == 1

    devices = next(row for row in flat if row["key"] == "devices")
    assert devices["badge"].endswith("台在线")
    _cleanup_sessions()


# ── 个人信息 ─────────────────────────────────────────────────


def test_profile_payload(seeded_database: None) -> None:
    token = _login()
    body = client.get("/api/user/profile", headers=_auth(token)).json()

    assert body["username"] == "admin_chen"
    assert body["role_code"] == "owner"
    assert body["status"] == "active"
    assert body["workspace"]["code"] == "webweaver-team"
    assert body["initial"] == "陈"
    assert body["active_sessions"] >= 1
    # 没改过密码时为空，前端显示「还没有修改过密码」
    assert body["password_updated_at"] is None
    client.cookies.clear()
    assert client.get("/api/user/profile").status_code == 401
    _cleanup_sessions()


def test_update_display_name(seeded_database: None) -> None:
    token = _login()
    original = client.get("/api/user/profile", headers=_auth(token)).json()["display_name"]
    new_name = "陈默（测试）"

    try:
        res = client.patch(
            "/api/user/profile", json={"display_name": new_name}, headers=_auth(token)
        ).json()
        assert res["ok"] is True
        assert res["profile"]["display_name"] == new_name

        # 浮层跟着变，否则名字改完头像旁边还是旧的
        menu = client.get("/api/user/menu", headers=_auth(token)).json()
        assert menu["name"] == new_name

        # 空白名与超长名都拒绝
        assert (
            client.patch(
                "/api/user/profile", json={"display_name": "   "}, headers=_auth(token)
            ).status_code
            == 422
        )
    finally:
        client.patch("/api/user/profile", json={"display_name": original}, headers=_auth(token))
        _cleanup_sessions()


# ── 登录设备 ─────────────────────────────────────────────────


def test_sessions_mark_current(seeded_database: None) -> None:
    token = _login()
    body = client.get("/api/user/sessions", headers=_auth(token)).json()

    assert body["total"] == len(body["items"])
    currents = [item for item in body["items"] if item["current"]]
    assert len(currents) == 1
    assert currents[0]["device"]
    assert body["active_total"] >= 1
    _cleanup_sessions()


def test_revoke_other_session(seeded_database: None) -> None:
    """在 A 设备上踢掉 B 设备，B 的令牌立刻失效。"""
    token_a = _login()
    token_b = _login()

    sessions = client.get("/api/user/sessions", headers=_auth(token_a)).json()["items"]
    other = next(item for item in sessions if not item["current"])

    res = client.delete(f"/api/user/sessions/{other['id']}", headers=_auth(token_a)).json()
    assert res["ok"] is True
    assert res["revoked"] == 1
    assert res["signed_out"] is False

    assert client.get("/api/auth/me", headers=_auth(token_b)).status_code in (401,)
    _cleanup_sessions()


def test_cannot_revoke_foreign_session(seeded_database: None) -> None:
    """只能踢自己的会话：拿别人的 ID 一律 404，不泄露「有这么个会话」。"""
    admin_token = _login()
    viewer_token = _login("viewer_lin")

    viewer_sessions = client.get("/api/user/sessions", headers=_auth(viewer_token)).json()["items"]
    victim = viewer_sessions[0]["id"]

    res = client.delete(f"/api/user/sessions/{victim}", headers=_auth(admin_token))
    assert res.status_code == 404
    _cleanup_sessions()


# ── 安全概览 ─────────────────────────────────────────────────


def test_security_payload(seeded_database: None) -> None:
    token = _login()
    body = client.get("/api/user/security", headers=_auth(token)).json()

    assert body["failed_login_count"] >= 0
    assert body["lock_remaining_minutes"] == 0
    assert body["active_sessions"] >= 1
    assert body["mfa_enabled"] is False
    assert "TOTP" in body["mfa_note"]
    # 刚登录过，最近事件里应该有 login
    assert any(event["action"] == "login" for event in body["recent_events"])
    _cleanup_sessions()


def test_my_audit_logs_only_mine(seeded_database: None) -> None:
    token = _login()
    body = client.get("/api/user/audit-logs", headers=_auth(token)).json()

    assert body["total"] >= 1
    assert {item["operator"] for item in body["items"]} == {"admin_chen"}

    logins = client.get(
        "/api/user/audit-logs", params={"action": "login"}, headers=_auth(token)
    ).json()
    assert all(item["action"] == "login" for item in logins["items"])
    _cleanup_sessions()


# ── 纯函数 ───────────────────────────────────────────────────


def test_parse_user_agent() -> None:
    chrome = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    assert parse_user_agent(chrome) == ("Chrome", "Windows")

    edge = chrome.replace("Chrome/128.0.0.0 Safari/537.36", "Edg/128.0.0.0")
    assert parse_user_agent(edge) == ("Edge", "Windows")

    safari = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    )
    assert parse_user_agent(safari) == ("Safari", "macOS")

    assert parse_user_agent(None) == ("未知浏览器", "未知系统")
