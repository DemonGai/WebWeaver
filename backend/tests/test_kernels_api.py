"""内核管理接口测试：目录扫描、版本切换、实例批量迁移。

内核文件目录用 ``tmp_path`` 造，数据库用种子数据。因为切版本/迁移会改库，
夹具在用例结束后把 ``kernels.version`` 与 ``browsers.kernel_version`` 还原，
避免污染同一个测试库里的其他用例。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import Browser, Kernel
from app.services.kernel_scan import engine_slug
from app.services.seed import DEMO_PASSWORD

client = TestClient(app)

# 每个引擎在"磁盘"上放了哪些版本。ungoogled-chromium 故意留空，
# 用来验证"未下载"这条分支。
DISK_LAYOUT = {
    "CloakBrowser": ["128.0.6613.2", "128.0.6613.5"],
    "Camoufox": ["128.0.3"],
    "fingerprint-chromium": ["126.0.6478.1", "128.0.6613.2"],
}


def _login(account: str = "admin_chen") -> dict[str, str]:
    body = client.post(
        "/api/auth", json={"action": "login", "account": account, "password": DEMO_PASSWORD}
    ).json()
    assert body["ok"] is True, body
    return {"Authorization": f"Bearer {body['token']}"}


def _run(coro):
    return asyncio.run(coro)


def _snapshot() -> tuple[dict[str, str], dict[str, str | None]]:
    async def run() -> tuple[dict[str, str], dict[str, str | None]]:
        async with SessionLocal() as session:
            kernels = {
                row.name: row.version for row in (await session.scalars(select(Kernel))).all()
            }
            browsers = {
                str(row.id): row.kernel_version
                for row in (await session.scalars(select(Browser))).all()
            }
        await dispose()
        return kernels, browsers

    return _run(run())


def _restore(kernels: dict[str, str], browsers: dict[str, str | None]) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            for name, version in kernels.items():
                row = await session.scalar(select(Kernel).where(Kernel.name == name))
                if row is not None:
                    row.version = version
            for raw_id, version in browsers.items():
                row = await session.get(Browser, raw_id)
                if row is not None:
                    row.kernel_version = version
            await session.commit()
        await dispose()

    _run(run())


def _pin_versions(mapping: dict[str, str]) -> None:
    """把库里「当前生效版本」钉到测试自己造的磁盘版本上。

    不能依赖种子里的版本号：真机上装过内核之后指针就会被切到新版本，这时
    「磁盘最新 vs 当前版本」的比较结果全变了，用例会假失败。
    """

    async def run() -> None:
        async with SessionLocal() as session:
            for name, version in mapping.items():
                row = await session.scalar(select(Kernel).where(Kernel.name == name))
                if row is not None:
                    row.version = version
            await session.commit()
        await dispose()

    _run(run())


@pytest.fixture
def kernel_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seeded_database: None
) -> Iterator[Path]:
    monkeypatch.setattr(settings, "kernel_root", str(tmp_path))
    for name, versions in DISK_LAYOUT.items():
        for version in versions:
            directory = tmp_path / engine_slug(name) / version
            directory.mkdir(parents=True)
            (directory / "meta.json").write_text(
                json.dumps(
                    {
                        "version": version,
                        "base": "Chromium 128.0.6613.120",
                        "arch": "x64",
                        "channel": "stable",
                        "size_mb": 400,
                        "released_at": "2026-10-18",
                    }
                ),
                encoding="utf-8",
            )

    kernels_before, browsers_before = _snapshot()
    _pin_versions({name: versions[0] for name, versions in DISK_LAYOUT.items()})
    yield tmp_path
    _restore(kernels_before, browsers_before)


def _card(body: dict, slug: str) -> dict:
    return next(card for card in body["cards"] if card["slug"] == slug)


def test_payload_reflects_disk(kernel_dirs: Path) -> None:
    body = client.get("/api/kernels").json()

    assert body["root"] == str(kernel_dirs)
    assert len(body["cards"]) == 4
    assert {c["slug"] for c in body["cards"]} == {
        "cloakbrowser",
        "camoufox",
        "fingerprint-chromium",
        "ungoogled-chromium",
    }
    # 4 套引擎都给了源码仓库
    assert all(c["repo_url"].startswith("https://github.com/") for c in body["cards"])

    cloak = _card(body, "cloakbrowser")
    assert cloak["downloaded"] is True
    assert cloak["version_count"] == 2
    # 磁盘上有比当前版本更新的，才算"可更新"
    assert cloak["latest_version"] == "128.0.6613.5"
    assert cloak["update_available"] is True
    # 版本按版本号倒序，最新的在最前面
    assert [v["version"] for v in cloak["versions"]] == ["128.0.6613.5", "128.0.6613.2"]
    assert [v["current"] for v in cloak["versions"]] == [False, True]
    assert all(v["ready"] for v in cloak["versions"])

    # 只有当前版本，不算可更新
    camoufox = _card(body, "camoufox")
    assert camoufox["update_available"] is False
    assert camoufox["version_count"] == 1

    # 目录不存在 → 未下载，且没有可用版本
    ungoogled = _card(body, "ungoogled-chromium")
    assert ungoogled["downloaded"] is False
    assert ungoogled["latest_version"] is None
    assert ungoogled["version_count"] == 0
    assert ungoogled["versions"] == []

    stats = {s["key"]: s["value"] for s in body["stats"]}
    assert stats["engines"] == "4"
    assert stats["downloaded"] == "3/4"
    assert stats["update"] == "2"


def test_switch_version_keeps_instances_on_old_version(kernel_dirs: Path) -> None:
    body = client.get("/api/kernels").json()
    cloak = _card(body, "cloakbrowser")
    old_version = cloak["current_version"]
    new_version = "128.0.6613.5"
    assert cloak["stale_count"] == 0

    res = client.post(
        f"/api/kernels/{cloak['id']}/version",
        json={"version": new_version},
        headers=_login(),
    )
    assert res.status_code == 200
    after = _card(res.json(), "cloakbrowser")
    assert after["current_version"] == new_version
    # 切版本不迁移实例：老实例原样留在旧版本上，等着被批量迁移
    assert after["instance_count"] > 0
    assert after["stale_count"] == after["instance_count"]
    assert _card(res.json(), "cloakbrowser")["update_available"] is False

    stale = client.get(f"/api/kernels/{cloak['id']}/instances?stale=true").json()
    assert len(stale) == after["stale_count"]
    assert all(item["version"] == old_version for item in stale)


def test_switch_version_rejects_missing_version(kernel_dirs: Path) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    res = client.post(
        f"/api/kernels/{cloak['id']}/version", json={"version": "9.9.9"}, headers=_login()
    )
    assert res.status_code == 400
    assert "没有可用的 9.9.9" in res.json()["detail"]

    assert (
        client.post(
            "/api/kernels/not-a-uuid/version", json={"version": "1"}, headers=_login()
        ).status_code
        == 404
    )


def test_migrate_moves_instances_to_target_version(kernel_dirs: Path) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    target = "128.0.6613.5"
    client.post(f"/api/kernels/{cloak['id']}/version", json={"version": target}, headers=_login())

    stale = client.get(f"/api/kernels/{cloak['id']}/instances?stale=true").json()
    assert stale, "切版本后应该有需要迁移的实例"
    picked = [stale[0]["id"]]

    res = client.post(
        f"/api/kernels/{cloak['id']}/migrate",
        json={"version": target, "browser_ids": picked},
        headers=_login(),
    )
    assert res.status_code == 200
    result = res.json()
    assert result["ok"] is True
    assert result["migrated"] == 1

    detail = client.get(f"/api/browsers/{picked[0]}").json()
    assert detail["kernel_version"] == target

    # 全部迁完（不传 ids 表示所有旧版本实例）后 stale 归零
    rest = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": target}, headers=_login()
    ).json()
    assert rest["migrated"] == len(stale) - 1
    assert _card(client.get("/api/kernels").json(), "cloakbrowser")["stale_count"] == 0

    empty = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": target}, headers=_login()
    ).json()
    assert empty["ok"] is True
    assert empty["migrated"] == 0


def test_migrate_requires_installed_version(kernel_dirs: Path) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    res = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": "1.2.3"}, headers=_login()
    )
    assert res.status_code == 400


def test_set_primary_marks_single_kernel(kernel_dirs: Path) -> None:
    cards = client.get("/api/kernels").json()["cards"]
    target = next(c for c in cards if c["slug"] == "camoufox")

    res = client.post(f"/api/kernels/{target['id']}/primary", headers=_login()).json()
    assert res["ok"] is True
    assert res["primary_id"] == target["id"]

    cards = client.get("/api/kernels").json()["cards"]
    assert sum(1 for c in cards if c["is_primary"]) == 1
    assert next(c for c in cards if c["is_primary"])["slug"] == "camoufox"

    # 还原成 CloakBrowser 为主力，别把库留成测试时的状态
    cloak = next(c for c in cards if c["slug"] == "cloakbrowser")
    client.post(f"/api/kernels/{cloak['id']}/primary", headers=_login())


def test_rescan_is_readonly(kernel_dirs: Path) -> None:
    before = client.get("/api/kernels").json()
    after = client.post("/api/kernels/rescan").json()
    assert [c["current_version"] for c in after["cards"]] == [
        c["current_version"] for c in before["cards"]
    ]
