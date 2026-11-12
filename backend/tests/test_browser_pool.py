"""浏览器池写接口：新建、编辑绑定、启停、批量、删除，以及权限与审计。

这些用例会真实落库，所以统一用 ``brw-test-`` 前缀命名，跑完清干净；
不依赖种子里具体实例的状态，避免种子调整后用例跟着碎。
"""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import (
    AuditLog,
    Browser,
    BrowserAccountBinding,
    BrowserFingerprintBinding,
    BrowserIpBinding,
)
from app.services.seed import DEMO_PASSWORD

client = TestClient(app)

TEST_PREFIX = "brw-test-"


@pytest.fixture(scope="module", autouse=True)
def clean_test_browsers() -> Iterator[None]:
    """跑完删掉本文件造出来的实例与流水，别把开发库塞满。"""
    yield

    async def run() -> None:
        async with SessionLocal() as session:
            rows = list(
                await session.scalars(select(Browser).where(Browser.name.like(f"{TEST_PREFIX}%")))
            )
            for browser in rows:
                for model in (
                    BrowserAccountBinding,
                    BrowserIpBinding,
                    BrowserFingerprintBinding,
                ):
                    for log in await session.scalars(
                        select(model).where(model.browser_id == browser.id)
                    ):
                        await session.delete(log)
                await session.delete(browser)
            await session.execute(
                delete(AuditLog).where(AuditLog.resource_name.like(f"{TEST_PREFIX}%"))
            )
            await session.commit()

    try:
        asyncio.run(run())
    except Exception:  # noqa: BLE001 - 清理失败不该让测试变红
        pass
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


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


def _create(name: str, token: str, **extra) -> dict:
    res = client.post("/api/browsers", json={"name": name, **extra}, headers=_auth(token))
    assert res.status_code == 201, res.text
    return res.json()


def _actions(browser_id: str, action: str, token: str):
    return client.post(
        f"/api/browsers/{browser_id}/actions",
        json={"action": action},
        headers=_auth(token),
    )


# ── 读取 ─────────────────────────────────────────────────────


def test_options_lists_candidates(seeded_database: None) -> None:
    res = client.get("/api/browsers/options")
    assert res.status_code == 200
    body = res.json()
    for key in ("groups", "kernels", "accounts", "ips", "fingerprints"):
        assert body[key], f"{key} 不应为空"
        assert {"id", "label"} <= set(body[key][0])

    # 已被占用的账号 / IP 要标记出来：前端据此置灰，而不是让用户提交后才报错
    assert any(item["disabled"] for item in body["accounts"])


def test_detail_unknown_returns_404(seeded_database: None) -> None:
    assert client.get("/api/browsers/not-a-real-instance").status_code == 404


# ── 生命周期 ────────────────────────────────────────────────


def test_lifecycle_start_stop_restart(seeded_database: None) -> None:
    token = _login()
    created = _create(f"{TEST_PREFIX}life", token)
    assert created["status"] == "stopped"

    started = _actions(created["id"], "start", token)
    assert started.status_code == 200 and started.json()["ok"] is True

    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "running"
    # 启动后必须拿到一组可用的接管地址，否则前端「打开 noVNC」没地方去
    assert detail["cdp_url"].startswith("http://127.0.0.1:")
    assert detail["vnc_port"] and detail["vnc_url"]

    # 重复启动是明确的冲突，不是静默成功
    assert _actions(created["id"], "start", token).status_code == 409

    restarted = _actions(created["id"], "restart", token)
    assert restarted.status_code == 200

    stopped = _actions(created["id"], "stop", token)
    assert stopped.status_code == 200
    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "stopped"
    assert detail["cdp_url"] is None and detail["vnc_url"] is None

    assert _actions(created["id"], "stop", token).status_code == 409


def test_restart_from_stopped_starts_it(seeded_database: None) -> None:
    token = _login()
    created = _create(f"{TEST_PREFIX}restart", token)
    res = _actions(created["id"], "restart", token)
    assert res.status_code == 200
    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "running"


# ── 新建与绑定 ─────────────────────────────────────────────


def test_duplicate_name_rejected(seeded_database: None) -> None:
    token = _login()
    _create(f"{TEST_PREFIX}dup", token)
    res = client.post("/api/browsers", json={"name": f"{TEST_PREFIX}dup"}, headers=_auth(token))
    assert res.status_code == 409


def test_bind_and_unbind_switches_modes(seeded_database: None) -> None:
    token = _login()
    options = client.get("/api/browsers/options").json()
    account = next(a for a in options["accounts"] if not a["disabled"])
    ip = next(i for i in options["ips"] if not i["disabled"])
    fingerprint = options["fingerprints"][0]

    created = _create(f"{TEST_PREFIX}bind", token)
    res = client.patch(
        f"/api/browsers/{created['id']}",
        json={
            "account_id": account["id"],
            "ip_id": ip["id"],
            "fingerprint_id": fingerprint["id"],
        },
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["account"] == account["label"]
    assert body["ip_mode"] == "proxy"
    assert body["fingerprint_mode"] == "template"

    # 传 null 是「切回直连 / 默认指纹」，模式必须同步改，否则 CHECK 约束会拒绝
    res = client.patch(
        f"/api/browsers/{created['id']}",
        json={"ip_id": None, "fingerprint_id": None},
        headers=_auth(token),
    )
    body = res.json()
    assert body["ip_id"] is None and body["ip_mode"] == "direct"
    assert body["fingerprint_id"] is None and body["fingerprint_mode"] == "default"


def test_account_already_bound_rejected(seeded_database: None) -> None:
    token = _login()
    options = client.get("/api/browsers/options").json()
    taken = next(a for a in options["accounts"] if a["disabled"])
    created = _create(f"{TEST_PREFIX}conflict", token)

    res = client.patch(
        f"/api/browsers/{created['id']}",
        json={"account_id": taken["id"]},
        headers=_auth(token),
    )
    assert res.status_code == 409
    assert "已绑定实例" in res.json()["detail"]


# ── 批量与删除 ─────────────────────────────────────────────


def test_batch_reports_partial_failure(seeded_database: None) -> None:
    token = _login()
    first = _create(f"{TEST_PREFIX}batch1", token)
    second = _create(f"{TEST_PREFIX}batch2", token)
    _actions(first["id"], "start", token)

    res = client.post(
        "/api/browsers/batch",
        json={"ids": [first["id"], second["id"], "no-such-instance"], "action": "start"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    # 第一条已在运行、第三条不存在 → 只有第二条成功，且失败项要带实例名或原始 ID
    assert body["succeeded"] == 1
    assert body["failed"] == 2
    assert body["ok"] is False
    assert all(item["message"] for item in body["items"])


def test_delete_requires_stopped(seeded_database: None) -> None:
    token = _login()
    created = _create(f"{TEST_PREFIX}del", token)
    _actions(created["id"], "start", token)

    assert client.delete(f"/api/browsers/{created['id']}", headers=_auth(token)).status_code == 409

    _actions(created["id"], "stop", token)
    res = client.delete(f"/api/browsers/{created['id']}", headers=_auth(token))
    assert res.status_code == 200
    assert client.get(f"/api/browsers/{created['id']}").status_code == 404


# ── 权限与审计 ─────────────────────────────────────────────


def test_viewer_cannot_create(seeded_database: None) -> None:
    token = _login("viewer_lin")
    res = client.post("/api/browsers", json={"name": f"{TEST_PREFIX}viewer"}, headers=_auth(token))
    assert res.status_code == 403
    assert "browser:create" in res.json()["detail"]


def test_actions_are_audited(seeded_database: None) -> None:
    token = _login()
    created = _create(f"{TEST_PREFIX}audit", token)
    _actions(created["id"], "start", token)

    logs = client.get("/api/audit-logs", params={"resource_type": "browser", "limit": 50}).json()
    items = logs.get("items", logs.get("logs", []))
    mine = [row for row in items if row.get("resource_name") == f"{TEST_PREFIX}audit"]
    actions = {row["action"] for row in mine}
    assert {"create", "start"} <= actions
    assert all(row["operator"] == "admin_chen" for row in mine)
    # 启停要记录状态变化，否则「几点停的、从什么状态停的」查不回来
    start_row = next(row for row in mine if row["action"] == "start")
    assert start_row["changes"]["status"]["after"] == "running"
