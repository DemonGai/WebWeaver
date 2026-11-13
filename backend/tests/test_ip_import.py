"""代理导入 / 检测接口测试：模板、清单解析、重复与覆盖、探测回写。

测试一律用 ``203.0.113.0/24``（TEST-NET-3，RFC 5737 留给文档和测试的地址段），
既不会真的连到别人的机器，清理时也能按前缀一把删掉。

检测接口会遍历**全库**代理，跑完会把种子数据的延迟 / 健康度改写掉；所以这里
先把这些列快照下来，用例结束时原样写回，开发库不会因为跑一次测试就变样。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.deps import get_current_user
from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import Ip, User
from app.models.enums import IpKind
from app.services import ip_pool

client = TestClient(app)

# 测试造的数据都在这个网段，清理按前缀删，不碰种子里的代理
TEST_NET = "203.0.113."


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
    """鉴权短路成超管，前后都清掉自己的测试数据。"""
    user = _run(_first_user())
    app.dependency_overrides[get_current_user] = lambda: user

    async def cleanup() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Ip).where(Ip.address.like(f"{TEST_NET}%")))
            await session.commit()

    _run(cleanup())
    yield client

    _run(cleanup())
    app.dependency_overrides.clear()
    _run(dispose())


@pytest.fixture
def restore_ips(seeded_database: None) -> Iterator[None]:
    """把所有人造代理之外的 IP 状态列存一份，结束后写回。"""

    async def snapshot() -> list[tuple[Any, ...]]:
        async with SessionLocal() as session:
            rows = (await session.scalars(select(Ip))).all()
            return [
                (row.id, row.latency_ms, row.health, row.status, row.last_checked_at)
                for row in rows
            ]

    before = _run(snapshot())
    yield

    async def restore() -> None:
        async with SessionLocal() as session:
            for ip_id, latency, health, status, checked_at in before:
                row = await session.get(Ip, ip_id)
                if row is None:
                    continue
                row.latency_ms = latency
                row.health = health
                row.status = status
                row.last_checked_at = checked_at
            await session.commit()

    _run(restore())
    _run(dispose())


# ── 解析器 ────────────────────────────────────────────────


def test_parse_accepts_url_shape() -> None:
    item = ip_pool.parse_line(
        "socks5://user:p%40ss@203.0.113.10:8000",
        default_kind=IpKind.residential,
        default_supplier="未标注",
    )
    assert (item.address, item.port) == ("203.0.113.10", 8000)
    # URL 里的百分号编码要还原，否则库里存的密码是 p%40ss
    assert (item.username, item.password) == ("user", "p@ss")
    assert item.protocol.value == "socks5"


def test_parse_accepts_colon_shape() -> None:
    item = ip_pool.parse_line(
        "203.0.113.11:1080:acct:secret",
        default_kind=IpKind.datacenter,
        default_supplier="未标注",
    )
    assert (item.address, item.port, item.username, item.password) == (
        "203.0.113.11",
        1080,
        "acct",
        "secret",
    )
    # 清单没写类型就用默认值，不能空着
    assert item.kind is IpKind.datacenter


def test_parse_csv_with_header_keeps_column_order() -> None:
    header = ip_pool._header_map(
        ["country", "ip", "port", "type", "supplier", "region", "city"]
    )
    item = ip_pool.parse_line(
        "JP,203.0.113.12,3128,mobile,Oxylabs,Tokyo,Tokyo",
        default_kind=IpKind.residential,
        default_supplier="未标注",
        header=header,
    )
    # 列序被打乱也要认得出：表头映射错了就会把 JP 当成地址
    assert item.address == "203.0.113.12"
    assert item.country == "JP"
    assert item.kind is IpKind.mobile
    assert item.supplier == "Oxylabs"


def test_parse_rejects_bad_port() -> None:
    with pytest.raises(ValueError):
        ip_pool.parse_line(
            "203.0.113.13:abc:user",
            default_kind=IpKind.residential,
            default_supplier="未标注",
        )


# ── 模板 ──────────────────────────────────────────────────


def test_template_download(seeded_database: None) -> None:
    res = client.get("/api/ip-pool/template")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    text = res.text
    # 带 BOM，Excel 打开中文列名才不乱码
    assert text.startswith("\ufeff")
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0].lstrip("\ufeff") == ",".join(ip_pool.TEMPLATE_COLUMNS)
    assert len(lines) == 1 + len(ip_pool.TEMPLATE_ROWS)


# ── 导入 ──────────────────────────────────────────────────


def _import(api: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "text": "",
        "default_kind": "residential",
        "default_supplier": "测试供应商",
        "overwrite": False,
    }
    body.update(overrides)
    res = api.post("/api/ip-pool/import", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_import_creates_rows(api: TestClient) -> None:
    body = _import(
        api,
        text="\n".join(
            [
                "# 这行是注释，要跳过",
                "203.0.113.20:8000:acct:pwd",
                "socks5://acct2:pwd2@203.0.113.21:9000",
            ]
        ),
    )

    assert (body["created"], body["skipped"], body["failed"]) == (2, 0, 0)

    pool = api.get("/api/ip-pool").json()
    row = next(item for item in pool["resources"] if item["ip"] == "203.0.113.20")
    assert row["port"] == 8000
    assert row["supplier"] == "测试供应商"
    # 地址、端口、账号密码都得原样下发，前端复制时才拼得出完整地址
    assert (row["username"], row["password"]) == ("acct", "pwd")


def test_import_skips_existing_unless_overwrite(api: TestClient) -> None:
    _import(api, text="203.0.113.30:8000:old:pwd")

    again = _import(api, text="203.0.113.30:8000:new:newpwd")
    assert (again["created"], again["skipped"]) == (0, 1)

    forced = _import(api, text="203.0.113.30:8000:new:newpwd", overwrite=True)
    assert (forced["created"], forced["updated"]) == (0, 1)

    pool = api.get("/api/ip-pool").json()
    row = next(item for item in pool["resources"] if item["ip"] == "203.0.113.30")
    assert (row["username"], row["password"]) == ("new", "newpwd")


def test_import_reports_bad_line_without_failing_batch(api: TestClient) -> None:
    body = _import(
        api,
        text="\n".join(
            [
                "203.0.113.40:8000:ok:pwd",
                "203.0.113.41:not-a-port:user",
            ]
        ),
    )

    assert (body["created"], body["failed"]) == (1, 1)
    assert body["rows"][0]["line"] == 2
    assert "端口" in body["rows"][0]["message"]


# ── 检测 ──────────────────────────────────────────────────


def test_check_writes_latency_back(
    api: TestClient, restore_ips: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(api, text="203.0.113.50:8000:acct:pwd")

    async def fake_probe(address: str, port: int, timeout: float = 4.0) -> tuple[bool, int, str]:
        # 只让测试地址可达，种子里的地址保持原样（不可达那支不改状态）
        return (True, 37, "端口可达") if address.startswith(TEST_NET) else (True, 0, "跳过")

    monkeypatch.setattr(ip_pool, "_tcp_probe", fake_probe)

    body = api.post("/api/ip-pool/check").json()
    assert body["checked"] == body["ok"] + body["failed"]
    assert body["checked"] >= 1
    assert body["failed"] == 0

    pool = api.get("/api/ip-pool").json()
    row = next(item for item in pool["resources"] if item["ip"] == "203.0.113.50")
    assert row["latency_ms"] == 37
    assert row["health"] == 100
    assert row["status"] == "available"


def test_check_marks_failed_after_repeated_misses(
    api: TestClient, restore_ips: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(api, text="203.0.113.60:8000:acct:pwd")

    async def dead_probe(address: str, port: int, timeout: float = 4.0) -> tuple[bool, int, str]:
        return False, 0, "连接被拒绝"

    monkeypatch.setattr(ip_pool, "_tcp_probe", dead_probe)

    # 健康度 100 一次掉 25，掉到一半以下才判失败 —— 连跑三轮才该变红
    for _ in range(3):
        api.post("/api/ip-pool/check")

    pool = api.get("/api/ip-pool").json()
    row = next(item for item in pool["resources"] if item["ip"] == "203.0.113.60")
    assert row["status"] == "failed"
    assert row["health"] == 25
    assert row["latency_ms"] == 0


def test_check_skips_portless_proxy(
    api: TestClient, restore_ips: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 端口留空：CSV 里漏填一列比整行格式错更常见，这种行要能导进来再被检测标红
    _import(api, text="203.0.113.70,,socks5,acct,pwd")

    real_probe = ip_pool._tcp_probe

    async def probe(address: str, port: int, timeout: float = 4.0) -> tuple[bool, int, str]:
        # 测试地址走真实逻辑（port=0 会立刻返回「未配置端口」），其余不真连
        if address.startswith(TEST_NET):
            return await real_probe(address, port, timeout)
        return True, 0, "跳过"

    monkeypatch.setattr(ip_pool, "_tcp_probe", probe)

    body = api.post("/api/ip-pool/check").json()
    item = next(row for row in body["items"] if row["ip"] == "203.0.113.70")
    # 没写端口的行不该被判「可达」——协议默认端口是谁也说不准
    assert item["ok"] is False
    assert item["message"] == "未配置端口"
