"""内核管理接口测试：镜像识别、版本切换、实例批量迁移。

不碰真实 docker：``kernel_image.available`` 和 ``list_images`` 都被替换成固定数据，
这样用例在任何机器上跑结果都一样。切版本/迁移会改库，夹具在用例结束后把
``kernels.version`` 与 ``browsers.kernel_version`` 还原，避免污染同一个测试库。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import Browser, Kernel, User
from app.services import kernel_image, kernel_pool
from app.services.kernel_image import ImageInfo

client = TestClient(app)

# 每个引擎在"本地"有哪些镜像：(tag, image_id, 版本号)。ungoogled-chromium 故意
# 留空，用来验证「未获取」；Camoufox 有镜像但还没被支持，验证它照样显示「暂未支持」。
IMAGE_LAYOUT: dict[str, list[tuple[str, str, str]]] = {
    "cloakbrowser": [
        ("cloakbrowser", "sha256:cb5", "128.0.6613.5"),  # 滚动 tag，指向最新
        ("cloakbrowser-128.0.6613.5", "sha256:cb5", "128.0.6613.5"),
        ("cloakbrowser-128.0.6613.2", "sha256:cb2", "128.0.6613.2"),
    ],
    "fingerprint-chromium": [
        ("fingerprint-chromium-126.0.6478.1", "sha256:fp1", "126.0.6478.1"),
        ("fingerprint-chromium", "sha256:fp1", "126.0.6478.1"),
    ],
    "camoufox": [("camoufox-128.0.3", "sha256:cf1", "128.0.3")],
}


def _images() -> list[ImageInfo]:
    items: list[ImageInfo] = []
    for tags in IMAGE_LAYOUT.values():
        for tag, image_id, version in tags:
            items.append(
                ImageInfo(
                    ref=f"demo/browser_engine:{tag}",
                    repository="demo/browser_engine",
                    tag=tag,
                    image_id=image_id,
                    size_bytes=400 * 1024 * 1024,
                    created_at="2026-11-10T13:50:54.693761427Z",
                    digest=f"sha256:{image_id}",
                    arch="amd64",
                    os_name="linux",
                    labels={"org.opencontainers.image.version": version},
                )
            )
    return items


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
    """把库里「当前生效版本」钉到测试自己造的镜像版本上。

    不能依赖种子里的版本号：真机上拉过镜像之后指针就会被切到新版本，这时
    「本地最新 vs 当前版本」的比较结果全变了，用例会假失败。
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


def _version_of(name: str) -> str | None:
    async def run() -> str | None:
        async with SessionLocal() as session:
            row = await session.scalar(select(Kernel).where(Kernel.name == name))
            version = row.version if row is not None else None
        await dispose()
        return version

    return _run(run())


def _make_browsers(kernel_name: str, version: str, count: int = 2) -> list[str]:
    """造几台固定在内核某版本上的实例，返回 id 列表。"""

    async def run() -> list[str]:
        async with SessionLocal() as session:
            kernel = await session.scalar(select(Kernel).where(Kernel.name == kernel_name))
            assert kernel is not None
            made = []
            for index in range(count):
                browser = Browser(
                    name=f"__test_kernel_{index}",
                    kernel_id=kernel.id,
                    kernel_version=version,
                )
                session.add(browser)
                made.append(browser)
            await session.commit()
            ids = [str(item.id) for item in made]
        await dispose()
        return ids

    return _run(run())


def _drop_browsers(ids: list[str]) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            for raw_id in ids:
                row = await session.get(Browser, raw_id)
                if row is not None:
                    await session.delete(row)
            await session.commit()
        await dispose()

    if ids:
        _run(run())


@pytest.fixture
def kernel_images(monkeypatch: pytest.MonkeyPatch, seeded_database: None) -> Iterator[None]:
    payload = _images()
    # docker 换成固定数据，用例在任何机器上结果都一样
    monkeypatch.setattr(kernel_image, "available", lambda: (True, None))
    monkeypatch.setattr(kernel_image, "list_images", lambda repository: payload)

    # 登录直接绕过：内核接口跟认证无关，走真实登录会让用例依赖演示账号还在不在。
    # 拿库里任意一个成员当超级管理员，写接口就不会被权限挡。
    async def load() -> User | None:
        async with SessionLocal() as session:
            user = await session.scalar(select(User).order_by(User.username))
        await dispose()
        return user

    user = _run(load())
    assert user is not None, "测试库没有成员，seed 没写进去"
    user.is_superuser = True  # 只改内存对象，不落库
    app.dependency_overrides[get_current_user] = lambda: user

    kernels_before, browsers_before = _snapshot()
    # CloakBrowser 钉在旧版本上，才能验证「本地有更新镜像 → 可切换」
    _pin_versions({"CloakBrowser": "128.0.6613.2"})
    # 切版本/迁移需要真的挂几台实例，库里可能一台都没有，测试自己造
    created = _make_browsers("CloakBrowser", "128.0.6613.2", count=2)
    yield
    _drop_browsers(created)
    _restore(kernels_before, browsers_before)
    app.dependency_overrides.clear()


def _card(body: dict, slug: str) -> dict:
    return next(card for card in body["cards"] if card["slug"] == slug)


def test_payload_reflects_local_images(kernel_images: None) -> None:
    body = client.get("/api/kernels").json()

    assert body["docker_ok"] is True
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
    assert cloak["installed"] is True
    assert cloak["version_count"] == 2
    # 本地有比当前版本更新的镜像，才算「可切换」
    assert cloak["latest_version"] == "128.0.6613.5"
    assert cloak["update_available"] is True
    # 版本按版本号倒序，最新的在最前面
    assert [v["version"] for v in cloak["versions"]] == ["128.0.6613.5", "128.0.6613.2"]
    assert [v["current"] for v in cloak["versions"]] == [False, True]
    # 当前版本用固定 tag 当引用；滚动 tag 指向的是最新那个镜像，不在这条里
    assert cloak["current_ref"].endswith("cloakbrowser-128.0.6613.2")
    assert cloak["versions"][1]["tags"] == ["cloakbrowser-128.0.6613.2"]

    # Camoufox 还没做镜像：即使本地有同名镜像也不列版本
    camoufox = _card(body, "camoufox")
    assert camoufox["supported"] is False
    assert camoufox["installed"] is False
    assert camoufox["versions"] == []
    assert "敬请期待" in camoufox["unsupported_reason"]

    # 没有任何镜像 → 未获取
    ungoogled = _card(body, "ungoogled-chromium")
    assert ungoogled["installed"] is False
    assert ungoogled["latest_version"] is None
    assert ungoogled["version_count"] == 0
    assert ungoogled["versions"] == []

    stats = {s["key"]: s["value"] for s in body["stats"]}
    assert stats["engines"] == "4"
    # 支持 3 套，其中 2 套本地有镜像
    assert stats["installed"] == "2/3"
    assert stats["update"] == "1"


def test_detail_lists_images_and_run_command(kernel_images: None) -> None:
    body = client.get("/api/kernels/cloakbrowser").json()
    assert body["card"]["slug"] == "cloakbrowser"
    assert len(body["versions"]) == 2
    assert body["run_command"].startswith("docker run")
    assert "9232:9222" in body["run_command"]
    assert body["docs"] is None or isinstance(body["docs"], str)

    camoufox = client.get("/api/kernels/camoufox").json()
    assert camoufox["card"]["supported"] is False
    assert camoufox["run_command"] is None

    assert client.get("/api/kernels/not-exist").status_code == 404


def test_switch_version_keeps_instances_on_old_version(kernel_images: None) -> None:
    body = client.get("/api/kernels").json()
    cloak = _card(body, "cloakbrowser")
    old_version = cloak["current_version"]
    new_version = "128.0.6613.5"
    assert cloak["stale_count"] == 0

    res = client.post(
        f"/api/kernels/{cloak['id']}/version",
        json={"version": new_version},
    )
    assert res.status_code == 200
    after = _card(res.json(), "cloakbrowser")
    assert after["current_version"] == new_version
    # 切版本不迁移实例：老实例原样留在旧版本上，等着被批量迁移
    assert after["instance_count"] > 0
    assert after["stale_count"] == after["instance_count"]
    assert after["update_available"] is False

    stale = client.get(f"/api/kernels/{cloak['id']}/instances?stale=true").json()
    assert len(stale) == after["stale_count"]
    assert all(item["version"] == old_version for item in stale)


def test_switch_version_rejects_missing_image(kernel_images: None) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    res = client.post(
        f"/api/kernels/{cloak['id']}/version", json={"version": "9.9.9"}
    )
    assert res.status_code == 400
    assert "本地没有" in res.json()["detail"]

    assert (
        client.post(
            "/api/kernels/not-a-uuid/version", json={"version": "1"}
        ).status_code
        == 404
    )


def test_migrate_moves_instances_to_target_version(kernel_images: None) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    target = "128.0.6613.5"
    client.post(f"/api/kernels/{cloak['id']}/version", json={"version": target})

    stale = client.get(f"/api/kernels/{cloak['id']}/instances?stale=true").json()
    assert stale, "切版本后应该有需要迁移的实例"
    picked = [stale[0]["id"]]

    res = client.post(
        f"/api/kernels/{cloak['id']}/migrate",
        json={"version": target, "browser_ids": picked},
    )
    assert res.status_code == 200
    result = res.json()
    assert result["ok"] is True
    assert result["migrated"] == 1

    detail = client.get(f"/api/browsers/{picked[0]}").json()
    assert detail["kernel_version"] == target

    # 全部迁完（不传 ids 表示所有旧版本实例）后 stale 归零
    rest = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": target}
    ).json()
    assert rest["migrated"] == len(stale) - 1
    assert _card(client.get("/api/kernels").json(), "cloakbrowser")["stale_count"] == 0

    empty = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": target}
    ).json()
    assert empty["ok"] is True
    assert empty["migrated"] == 0


def test_migrate_requires_local_image(kernel_images: None) -> None:
    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    res = client.post(
        f"/api/kernels/{cloak['id']}/migrate", json={"version": "1.2.3"}
    )
    assert res.status_code == 400


def test_cards_follow_engine_order(kernel_images: None) -> None:
    """卡片按引擎的展示顺序排，而不是按名字（名字序 Camoufox 会排第一）。"""
    cards = client.get("/api/kernels").json()["cards"]
    assert [c["slug"] for c in cards] == [
        "cloakbrowser",
        "camoufox",
        "fingerprint-chromium",
        "ungoogled-chromium",
    ]


def test_rescan_is_readonly(kernel_images: None) -> None:
    before = client.get("/api/kernels").json()
    after = client.post("/api/kernels/rescan").json()
    assert [c["current_version"] for c in after["cards"]] == [
        c["current_version"] for c in before["cards"]
    ]


def test_install_resolves_reference(kernel_images: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """拉取接口把 tag/version 归一成完整镜像名，且不会真的去 pull。"""

    async def fake_start(slug: str, tag: str | None = None, version: str | None = None):
        from app.services.kernel_install import resolve_ref

        ref, display = resolve_ref(slug, tag, version)
        from app.schemas.kernels import InstallJob

        return InstallJob(
            id="job-1",
            slug=slug,
            version=display,
            tag=ref.rsplit(":", 1)[-1],
            image_ref=ref,
            status="running",
            progress=0,
            message="已排队",
            started_at="2026-11-11 10:00:00",
        )

    from app.services import kernel_install as install_module

    monkeypatch.setattr(install_module, "start", fake_start)

    cloak = _card(client.get("/api/kernels").json(), "cloakbrowser")
    res = client.post(
        f"/api/kernels/{cloak['slug']}/install",
        json={"version": "128.0.6613.5"},
    )
    assert res.status_code == 202
    job = res.json()
    assert job["image_ref"].endswith(":cloakbrowser-128.0.6613.5")
    assert job["kind"] == "docker"


# ── 拉取镜像后校正台账 ────────────────────────────────────────


def test_adopt_pulled_repoints_dangling_version(kernel_images: None) -> None:
    """台账指着一个本地不存在的版本时，拉完镜像把它改记成实际的版本。"""
    _pin_versions({"CloakBrowser": "99.0.0"})

    _run(kernel_pool.adopt_pulled("cloakbrowser", "128.0.6613.5"))

    assert _version_of("CloakBrowser") == "128.0.6613.5"


def test_adopt_pulled_keeps_installed_version(kernel_images: None) -> None:
    """台账版本还在本地：那是用户选的，拉个新镜像不许悄悄改掉。"""
    _pin_versions({"CloakBrowser": "128.0.6613.2"})

    _run(kernel_pool.adopt_pulled("cloakbrowser", "128.0.6613.5"))

    assert _version_of("CloakBrowser") == "128.0.6613.2"
