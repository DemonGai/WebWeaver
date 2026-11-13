"""账号新建 / 编辑 / 批量导入接口测试。

平台名统一用 ``TestShop``：清理时按平台前缀一把删掉，不碰种子里的 8 个账号。
Cookie 走明文 JSONB，测试要覆盖三件事——能写进去、能在详情里原样读出来、
清空后账号状态会跟着从「已登录」退回「未绑定」。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.deps import get_current_user
from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import Account, User

client = TestClient(app)

TEST_PLATFORM = "TestShop"

STORAGE_STATE = {
    "cookies": [
        {
            "name": "session-id",
            "value": "abc-123",
            "domain": ".testshop.com",
            "path": "/",
            "expires": 1893456000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "ubid",
            "value": "999",
            "domain": ".testshop.com",
            "path": "/",
        },
    ],
    "origins": [],
}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _first_user() -> User:
    async with SessionLocal() as session:
        user = (await session.scalars(select(User))).first()
        if user is None:
            pytest.skip("库里没有成员，跳过需要鉴权的用例")
        user.is_superuser = True
        session.expunge(user)
        return user


@pytest.fixture
def api(seeded_database: None) -> Iterator[TestClient]:
    user = _run(_first_user())
    app.dependency_overrides[get_current_user] = lambda: user

    async def cleanup() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Account).where(Account.platform.like(f"{TEST_PLATFORM}%")))
            await session.commit()

    _run(cleanup())
    yield client

    _run(cleanup())
    app.dependency_overrides.clear()
    _run(dispose())


def _create(api: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "platform": TEST_PLATFORM,
        "username": "shop_a",
        "email": "a@example.com",
        "region": "测试区",
        "health": 90,
        **overrides,
    }
    res = api.post("/api/accounts", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _import(api: TestClient, text: str, **overrides: Any) -> dict[str, Any]:
    body = {"text": text, "default_platform": TEST_PLATFORM, "overwrite": False, **overrides}
    res = api.post("/api/accounts/import", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_template_has_bom_and_headers(api: TestClient) -> None:
    res = api.get("/api/accounts/template")
    assert res.status_code == 200
    # Excel 打开中文列名要靠 BOM
    assert res.text.startswith("\ufeff")
    header = res.text.lstrip("\ufeff").splitlines()[0]
    assert header.startswith("platform,username,email,region,health,note")


def test_create_with_storage_state(api: TestClient) -> None:
    created = _create(api, cookies=STORAGE_STATE)

    # 粘了 storage_state 又没指定状态 → 记为已登录
    assert created["status"] == "logged_in"
    assert created["cookies"] is not None and len(created["cookies"]) == 2
    assert created["cookies"][0]["name"] == "session-id"

    detail = api.get(f"/api/accounts/{created['id']}").json()
    assert detail["cookies"][0]["value"] == "abc-123"

    # 列表只回条数，不回 Cookie 内容
    listing = api.get("/api/accounts").json()["accounts"]
    row = next(item for item in listing if item["id"] == created["id"])
    assert row["cookie_count"] == 2
    assert "cookies" not in row


def test_create_without_cookies_is_unbound(api: TestClient) -> None:
    created = _create(api, username="shop_b")
    assert created["status"] == "unbound"
    assert created["cookies"] is None


def test_create_duplicate_conflict(api: TestClient) -> None:
    _create(api, username="shop_dup")
    res = api.post(
        "/api/accounts",
        json={"platform": TEST_PLATFORM, "username": "shop_dup", "region": "", "health": 100},
    )
    assert res.status_code == 409
    assert "已存在" in res.json()["detail"]


def test_create_rejects_broken_cookie_json(api: TestClient) -> None:
    res = api.post(
        "/api/accounts",
        json={
            "platform": TEST_PLATFORM,
            "username": "shop_bad",
            "region": "",
            "health": 100,
            "cookies": "[{oops",
        },
    )
    assert res.status_code == 422
    assert "JSON" in res.json()["detail"]


def test_update_cookies_then_clear(api: TestClient) -> None:
    created = _create(api, username="shop_c", cookies=[{"name": "token", "value": "v1"}])
    assert created["status"] == "logged_in"

    # 换成一条新 Cookie
    res = api.patch(
        f"/api/accounts/{created['id']}",
        json={"cookies": [{"name": "token", "value": "v2"}, {"name": "x", "value": "y"}]},
    )
    assert res.status_code == 204, res.text
    detail = api.get(f"/api/accounts/{created['id']}").json()
    assert [c["name"] for c in detail["cookies"]] == ["token", "x"]

    # 只改备注，Cookie 不动
    api.patch(f"/api/accounts/{created['id']}", json={"note": "改个备注"})
    detail = api.get(f"/api/accounts/{created['id']}").json()
    assert detail["note"] == "改个备注"
    assert len(detail["cookies"]) == 2

    # 清空 Cookie：状态要跟着退回未绑定，不能还挂着「已登录」
    api.patch(f"/api/accounts/{created['id']}", json={"cookies": None})
    detail = api.get(f"/api/accounts/{created['id']}").json()
    assert detail["cookies"] is None
    assert detail["status"] == "unbound"


def test_update_unknown_account(api: TestClient) -> None:
    res = api.patch("/api/accounts/00000000-0000-0000-0000-000000000000", json={"note": "x"})
    assert res.status_code == 404


def test_import_positional(api: TestClient) -> None:
    text = "\n".join(
        [
            "# 注释行会被跳过",
            f"{TEST_PLATFORM},imp_1,imp1@example.com,美国区,88,主店",
            f"{TEST_PLATFORM}\timp_2\timp2@example.com\t日本区\t100",
            "bad_line_only_username",  # 只有账号名 → 用默认平台补齐
        ]
    )
    result = _import(api, text)
    assert result["created"] == 3
    assert result["failed"] == 0

    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["imp_1"]["region"] == "美国区"
    assert rows["imp_2"]["region"] == "日本区"
    assert rows["bad_line_only_username"]["platform"] == TEST_PLATFORM
    assert rows["imp_1"]["health"] == 88
    # 导入的账号没有 Cookie，状态是未绑定
    assert rows["imp_1"]["status"] == "unbound"
    assert rows["imp_1"]["cookie_count"] == 0


def test_import_header_mapping(api: TestClient) -> None:
    text = "\n".join(
        [
            "账号,平台,邮箱,地区,健康度,备注",
            f"hdr_1,{TEST_PLATFORM},hdr1@example.com,英国区,70,来自表头",
        ]
    )
    result = _import(api, text)
    assert result["created"] == 1
    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["hdr_1"]["region"] == "英国区"
    assert rows["hdr_1"]["note"] == "来自表头"


def test_import_skips_duplicates_and_can_overwrite(api: TestClient) -> None:
    _create(api, username="dup_1", region="旧地区", health=50)

    text = f"{TEST_PLATFORM},dup_1,new@example.com,新地区,95,新备注"
    first = _import(api, text)
    assert first["created"] == 0
    assert first["skipped"] == 1

    # 覆盖只更新资料，本来就没有 Cookie，这里主要验证字段被改写
    second = _import(api, text, overwrite=True)
    assert second["updated"] == 1
    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["dup_1"]["region"] == "新地区"
    assert rows["dup_1"]["health"] == 95


def test_import_rejects_bad_health(api: TestClient) -> None:
    result = _import(api, f"{TEST_PLATFORM},bad_health,x@example.com,德国区,不是数字")
    assert result["failed"] == 1
    assert "健康度" in result["rows"][0]["message"]


def test_import_same_batch_duplicate(api: TestClient) -> None:
    text = "\n".join([f"{TEST_PLATFORM},same_1,,,", f"{TEST_PLATFORM},same_1,,,"])
    result = _import(api, text)
    assert result["created"] == 1
    assert result["skipped"] == 1


def test_import_requires_platform(api: TestClient) -> None:
    # 只有账号名又没选默认平台：这一行认不出来
    result = _import(api, "lonely_account", default_platform="")
    assert result["failed"] == 1
    assert "缺少平台" in result["rows"][0]["message"]


def test_import_audit_never_contains_cookie_value(api: TestClient) -> None:
    _create(api, username="audit_1", cookies=[{"name": "s", "value": "SECRET-VALUE"}])

    async def latest() -> str:
        from app.models import AuditLog

        async with SessionLocal() as session:
            log = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.resource_name == f"{TEST_PLATFORM}/audit_1")
                )
            ).first()
            assert log is not None
            return json.dumps(log.changes or {}, ensure_ascii=False)

    # 审计里只留条数与域名，绝不能把 Cookie 值抄进去
    assert "SECRET-VALUE" not in _run(latest())
