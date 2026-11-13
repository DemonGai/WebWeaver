"""账号新建 / 编辑 / 批量导入接口测试。

账号不绑平台、绑登录页：平台从 URL 推导，所以测试数据全部落在
``*.verifyshop.com``（未收录的域名 → 按注册域兜底成 ``Verifyshop``），
清理时按这个域名前缀一把删掉，不会碰种子里那 8 个账号。

Cookie 走明文 JSONB，要覆盖三件事——能写进去、能在详情里原样读出来、
清空后状态会跟着从「已登录」退回「未绑定」。
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

TEST_DOMAIN = "verifyshop.com"
URL_A = f"https://a.{TEST_DOMAIN}/login"
URL_B = f"https://b.{TEST_DOMAIN}/login"

STORAGE_STATE = {
    "cookies": [
        {
            "name": "session-id",
            "value": "abc-123",
            "domain": ".verifyshop.com",
            "path": "/",
            "expires": 1893456000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "ubid",
            "value": "999",
            "domain": ".verifyshop.com",
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
            await session.execute(
                delete(Account).where(Account.login_url.like(f"%{TEST_DOMAIN}%"))
            )
            await session.commit()

    _run(cleanup())
    yield client

    _run(cleanup())
    app.dependency_overrides.clear()
    _run(dispose())


def _create(api: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "login_url": URL_A,
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
    body = {"text": text, "overwrite": False, **overrides}
    res = api.post("/api/accounts/import", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_template_starts_with_login_url(api: TestClient) -> None:
    res = api.get("/api/accounts/template")
    assert res.status_code == 200
    # Excel 打开中文列名要靠 BOM
    assert res.text.startswith("\ufeff")
    header = res.text.lstrip("\ufeff").splitlines()[0]
    assert header.startswith("login_url,username,email,region,health,note")
    # 模板里不该再出现 platform 列：平台是推导值
    assert "platform" not in header


def test_create_derives_platform_from_url(api: TestClient) -> None:
    created = _create(api, cookies=STORAGE_STATE)

    # 未收录的域名按注册域兜底：verifyshop → Verifyshop
    assert created["platform"] == "Verifyshop"
    assert created["login_url"] == URL_A
    # 粘了 storage_state 又没指定状态 → 记为已登录
    assert created["status"] == "logged_in"
    assert created["cookies"] is not None and len(created["cookies"]) == 2

    detail = api.get(f"/api/accounts/{created['id']}").json()
    assert detail["cookies"][0]["value"] == "abc-123"

    # 列表只回条数，不回 Cookie 内容
    listing = api.get("/api/accounts").json()["accounts"]
    row = next(item for item in listing if item["id"] == created["id"])
    assert row["cookie_count"] == 2
    assert row["login_url"] == URL_A
    assert "cookies" not in row


def test_create_normalizes_url(api: TestClient) -> None:
    # 不带协议、末尾带斜杠，都要归一到同一形态
    created = _create(api, login_url=f"a.{TEST_DOMAIN}/login/")
    assert created["login_url"] == URL_A

    # 归一后与上一条完全相同 → 同 URL 同账号冲突
    res = api.post(
        "/api/accounts",
        json={"login_url": "https://a.verifyshop.com/login", "username": "shop_a"},
    )
    assert res.status_code == 409


def test_create_without_cookies_is_unbound(api: TestClient) -> None:
    created = _create(api, username="shop_b")
    assert created["status"] == "unbound"
    assert created["cookies"] is None


def test_same_platform_different_login_page_is_allowed(api: TestClient) -> None:
    first = _create(api, login_url=URL_A, username="same_name")
    second = _create(api, login_url=URL_B, username="same_name")
    # 同一家平台（推导结果一致）的两个站点可以有同名账号
    assert first["platform"] == second["platform"] == "Verifyshop"
    assert first["id"] != second["id"]


def test_create_rejects_bad_url(api: TestClient) -> None:
    res = api.post(
        "/api/accounts",
        json={"login_url": "Amazon", "username": "shop_bad"},
    )
    # 平台名会被当成域名 → 没有点号，主机名解析不出来
    assert res.status_code == 422
    assert "登录地址" in res.json()["detail"]


def test_create_rejects_broken_cookie_json(api: TestClient) -> None:
    res = api.post(
        "/api/accounts",
        json={"login_url": URL_A, "username": "shop_bad_cookie", "cookies": "[{oops"},
    )
    assert res.status_code == 422
    assert "JSON" in res.json()["detail"]


def test_update_login_url_recalculates_platform(api: TestClient) -> None:
    created = _create(api, username="shop_move")
    assert created["platform"] == "Verifyshop"

    try:
        # 换成亚马逊的登录页：平台要跟着变，不能还留旧值
        res = api.patch(
            f"/api/accounts/{created['id']}",
            json={"login_url": "https://sellercentral.amazon.com/ap/signin"},
        )
        assert res.status_code == 204, res.text
        detail = api.get(f"/api/accounts/{created['id']}").json()
        assert detail["platform"] == "Amazon"
        assert detail["login_url"] == "https://sellercentral.amazon.com/ap/signin"
        assert detail["username"] == "shop_move"
    finally:
        # 址改回测试域名，否则 fixture 按域名清理时删不到这条，
        # 会残留在库里把后续用例的账号总数算多
        api.patch(f"/api/accounts/{created['id']}", json={"login_url": URL_A})


def test_update_cookies_then_clear(api: TestClient) -> None:
    created = _create(api, username="shop_c", cookies=[{"name": "token", "value": "v1"}])
    assert created["status"] == "logged_in"

    # 换成两条新 Cookie
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


def test_detect_platform(api: TestClient) -> None:
    known = api.get(
        "/api/accounts/detect",
        params={"login_url": "sellercentral.amazon.co.jp/ap/signin"},
    )
    assert known.status_code == 200
    body = known.json()
    assert body["platform"] == "Amazon"
    assert body["known"] is True
    # 回显的是规范化之后的地址
    assert body["login_url"] == "https://sellercentral.amazon.co.jp/ap/signin"

    unknown = api.get("/api/accounts/detect", params={"login_url": "mysite.example"})
    # 没收录的域名按注册名兜底：mysite.example 的注册名是 mysite
    assert unknown.json() == {
        "login_url": "https://mysite.example",
        "platform": "Mysite",
        "known": False,
    }

    bad = api.get("/api/accounts/detect", params={"login_url": ""})
    assert bad.status_code == 422


def test_import_positional(api: TestClient) -> None:
    text = "\n".join(
        [
            "# 注释行会被跳过",
            f"{URL_A},imp_1,imp1@example.com,美国区,88,主店",
            f"{URL_B}\timp_2\timp2@example.com\t日本区\t100",
        ]
    )
    result = _import(api, text)
    assert result["created"] == 2
    assert result["failed"] == 0

    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["imp_1"]["region"] == "美国区"
    assert rows["imp_2"]["region"] == "日本区"
    # 平台全部由地址推导，不需要用户填
    assert rows["imp_1"]["platform"] == "Verifyshop"
    assert rows["imp_1"]["health"] == 88
    # 导入的账号没有 Cookie，状态是未绑定
    assert rows["imp_1"]["status"] == "unbound"
    assert rows["imp_1"]["cookie_count"] == 0


def test_import_header_mapping(api: TestClient) -> None:
    text = "\n".join(
        [
            "账号,登录地址,邮箱,地区,健康度,备注",
            f"hdr_1,{URL_A},hdr1@example.com,英国区,70,来自表头",
        ]
    )
    result = _import(api, text)
    assert result["created"] == 1
    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["hdr_1"]["region"] == "英国区"
    assert rows["hdr_1"]["note"] == "来自表头"
    assert rows["hdr_1"]["login_url"] == URL_A


def test_import_skips_duplicates_and_can_overwrite(api: TestClient) -> None:
    _create(api, login_url=URL_A, username="dup_1", region="旧地区", health=50)

    text = f"{URL_A},dup_1,new@example.com,新地区,95,新备注"
    first = _import(api, text)
    assert first["created"] == 0
    assert first["skipped"] == 1

    second = _import(api, text, overwrite=True)
    assert second["updated"] == 1
    rows = {item["name"]: item for item in api.get("/api/accounts").json()["accounts"]}
    assert rows["dup_1"]["region"] == "新地区"
    assert rows["dup_1"]["health"] == 95


def test_import_rejects_bad_health(api: TestClient) -> None:
    result = _import(api, f"{URL_A},bad_health,x@example.com,德国区,不是数字")
    assert result["failed"] == 1
    assert "健康度" in result["rows"][0]["message"]


def test_import_same_batch_duplicate(api: TestClient) -> None:
    text = "\n".join([f"{URL_A},same_1,,,", f"{URL_A},same_1,,,"])
    result = _import(api, text)
    assert result["created"] == 1
    assert result["skipped"] == 1


def test_import_requires_login_url(api: TestClient) -> None:
    # 只有账号名 / 第一列写平台名：都认不出来，得提示该填地址
    names_only = _import(api, "lonely_account")
    assert names_only["failed"] == 1
    assert "两列" in names_only["rows"][0]["message"]

    platform_col = _import(api, "Amazon,shop_x,,")
    assert platform_col["failed"] == 1
    assert "登录地址" in platform_col["rows"][0]["message"]


def test_import_audit_never_contains_cookie_value(api: TestClient) -> None:
    created = _create(api, username="audit_1", cookies=[{"name": "s", "value": "SECRET-VALUE"}])

    async def changes() -> str:
        from app.models import AuditLog

        async with SessionLocal() as session:
            log = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.resource_name == "Verifyshop/audit_1")
                )
            ).first()
            assert log is not None
            assert created["id"]  # 确保账号确实建出来了
            return json.dumps(log.changes or {}, ensure_ascii=False)

    # 审计里只留条数与域名，绝不能把 Cookie 值抄进去
    assert "SECRET-VALUE" not in _run(changes())
