"""指纹池接口测试：列表的内核适配、新建校验、采集回填、下发落库。

真实 docker 一律不打桩也不行：采集要起容器、下发要重启容器，跑一次几十秒还会
污染本机。所以 `fingerprint_probe.collect` 和 `fingerprint_apply.apply` 在两个
用例里被替换成固定结果，其余用例完全不碰它们 —— 这样「接口逻辑」和「docker
真的能跑」两件事各自独立验证，前者快、后者在本机手动跑过一遍（见 CLAUDE 记录）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.deps import get_current_user
from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import Browser, Fingerprint, Kernel, User
from app.models.enums import FingerprintMode, PlatformFamily
from app.services import fingerprint_apply, fingerprint_probe

client = TestClient(app)

# 测试造的指纹都带这个前缀，清理时按前缀删，不碰种子数据
PREFIX = "__t_fp"


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


async def _kernel_id(name: str) -> str:
    async with SessionLocal() as session:
        kernel = await session.scalar(select(Kernel).where(Kernel.name == name))
        if kernel is None:
            pytest.skip(f"库里没有 {name} 内核")
        return str(kernel.id)


@pytest.fixture
def api(seeded_database: None) -> Iterator[TestClient]:
    """把鉴权短路成超管，并在用例结束后清掉自己造的指纹。

    演示账号在早前的需求里被删掉了，所以不能走真实登录；内核接口的测试也是
    同样的做法（`dependency_overrides[get_current_user]`）。
    """
    user = _run(_first_user())
    app.dependency_overrides[get_current_user] = lambda: user
    yield client

    async def cleanup() -> None:
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(Fingerprint).where(Fingerprint.code.like(f"{PREFIX}%"))
                )
            ).all()
            for row in rows:
                await session.delete(row)
            await session.commit()
        await dispose()

    _run(cleanup())
    app.dependency_overrides.clear()


@pytest.fixture
def legacy_on_unsupported_kernel(api: TestClient) -> str:
    """直接写库造一条绑在 ungoogled-chromium 上的指纹。

    接口现在会 422 拦掉这种组合，但历史数据里确实可能存在（种子里就有一条绑
    Camoufox 的）。页面对这类记录必须能正确显示「不支持」而不是崩掉。
    """

    async def run() -> str:
        async with SessionLocal() as session:
            kernel = await session.scalar(
                select(Kernel).where(Kernel.name == "ungoogled-chromium")
            )
            if kernel is None:
                pytest.skip("库里没有 ungoogled-chromium 内核")
            fp = Fingerprint(
                code=f"{PREFIX}-legacy",
                name=f"{PREFIX} 历史指纹",
                platform_family=PlatformFamily.windows,
                platform="Windows",
                user_agent="",
                timezone="Asia/Shanghai",
                language="zh-CN",
                resolution="",
                dpr="1",
                seed=42817,
                kernel_id=kernel.id,
            )
            session.add(fp)
            await session.commit()
            return str(fp.id)

    return _run(run())


def _payload(**overrides: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": f"{PREFIX} 测试指纹",
        "platform_family": "windows",
        "timezone": "Asia/Shanghai",
        "language": "zh-CN",
    }
    body.update(overrides)
    return body


def _create(body: dict[str, Any]) -> dict[str, Any]:
    res = client.post("/api/fingerprints", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _row_of(body: dict[str, Any], fingerprint_id: str) -> dict[str, Any]:
    return next(item for item in body["templates"] if item["id"] == fingerprint_id)


# ── 列表 ─────────────────────────────────────────────────


def test_list_marks_kernels_that_cannot_spoof(api: TestClient) -> None:
    body = api.get("/api/fingerprints").json()

    assert body["total"] == len(body["templates"])
    # 四个内核里只有 CloakBrowser 与 fingerprint-chromium 能做指纹
    assert body["supported_kernels"] == 2
    assert body["kernels"] == 4

    # 种子里有绑到 Camoufox 的模板，必须被标成不支持且给出原因
    camo = [item for item in body["templates"] if item["kernel_slug"] == "camoufox"]
    assert camo, "种子里应该有绑到 Camoufox 的指纹"
    assert all(item["supported"] is False for item in camo)
    assert all(item["unsupported_reason"] for item in camo)


def test_list_reports_probe_state(api: TestClient) -> None:
    body = api.get("/api/fingerprints").json()
    states = {item["probe_state"] for item in body["templates"]}
    # 种子数据从来没采集过，不能假装有实测值
    assert states <= {"never", "fresh", "stale", "failed"}
    assert all(item["seed"] is not None for item in body["templates"])


# ── 新建校验 ─────────────────────────────────────────────


def test_create_rejects_kernel_without_spoofing(api: TestClient) -> None:
    res = api.post(
        "/api/fingerprints",
        json=_payload(kernel_id=_run(_kernel_id("ungoogled-chromium")), code=f"{PREFIX}-un"),
    )
    assert res.status_code == 422
    assert "纯净 Chromium" in res.json()["detail"]


def test_create_rejects_mobile_family_on_desktop_kernel(api: TestClient) -> None:
    res = api.post(
        "/api/fingerprints",
        json=_payload(
            kernel_id=_run(_kernel_id("CloakBrowser")),
            platform_family="android",
            code=f"{PREFIX}-android",
        ),
    )
    assert res.status_code == 422
    # 桌面内核装不成手机，这件事必须在保存前就说清楚
    assert "桌面内核" in res.json()["detail"]


def test_create_rejects_seed_out_of_kernel_range(api: TestClient) -> None:
    res = api.post(
        "/api/fingerprints",
        json=_payload(kernel_id=_run(_kernel_id("CloakBrowser")), seed=999, code=f"{PREFIX}-seed"),
    )
    assert res.status_code == 422
    assert "10000" in res.json()["detail"]


def test_create_fills_seed_and_code(api: TestClient) -> None:
    body = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-auto"))
    low, high = body["seed_range"]
    assert low <= body["seed"] <= high
    assert body["probe_state"] == "never"
    assert body["supported"] is True
    # 没采集过就不能有实测值，否则页面会拿假数据骗人
    assert body["ua"] == ""
    assert body["gpu"] is None


def test_create_keeps_duplicate_code_unique(api: TestClient) -> None:
    kernel_id = _run(_kernel_id("CloakBrowser"))
    first = _create(_payload(kernel_id=kernel_id, code=f"{PREFIX}-dup"))
    second = _create(_payload(kernel_id=kernel_id, code=f"{PREFIX}-dup", name=f"{PREFIX} 第二条"))
    assert first["fp_id"] != second["fp_id"]


# ── 详情与下发物料 ──────────────────────────────────────


def test_detail_renders_per_kernel_material(api: TestClient) -> None:
    cloak = _create(
        _payload(
            kernel_id=_run(_kernel_id("CloakBrowser")),
            code=f"{PREFIX}-cloak",
            seed=42817,
            platform_version="10.0.0",
            hardware_concurrency=8,
        )
    )
    chromium = _create(
        _payload(
            kernel_id=_run(_kernel_id("fingerprint-chromium")),
            code=f"{PREFIX}-chromium",
            seed=42817,
            platform_version="10.0.0",
            hardware_concurrency=8,
            webrtc_ip="203.0.113.10",
        )
    )

    cloak_render = cloak["render"]
    assert cloak_render["payload"]["seed"] == 42817
    # CloakBrowser 不认平台版本，写进去也无效，必须列在 ignored 里
    assert "platform_version" not in cloak_render["payload"]
    assert "平台版本" in cloak_render["ignored"]
    assert not cloak_render["ignored"].count("WebRTC 出口 IP")

    chromium_render = chromium["render"]
    assert chromium_render["payload"]["platform_version"] == "10.0.0"
    assert chromium_render["payload"]["hardware_concurrency"] == 8
    # 反过来，fingerprint-chromium 没有 webrtc 参数
    assert "webrtc_ip" not in chromium_render["payload"]
    assert "WebRTC 出口 IP" in chromium_render["ignored"]


def test_detail_explains_why_unsupported(
    api: TestClient, legacy_on_unsupported_kernel: str
) -> None:
    detail = api.get(f"/api/fingerprints/{legacy_on_unsupported_kernel}").json()
    assert detail["supported"] is False
    # 不支持就不该给下发物料：给了等于暗示「照着发就行」
    assert detail["render"] is None
    assert "纯净 Chromium" in detail["unsupported_reason"]


# ── 采集回填 ─────────────────────────────────────────────


def _fake_probe(monkeypatch: pytest.MonkeyPatch, **raw: Any) -> None:
    payload: dict[str, Any] = {
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "hardwareConcurrency": 8,
        "language": "zh-CN",
        "languages": ["zh-CN", "zh"],
        "timezone": "Asia/Shanghai",
        "screen": {"width": 1920, "height": 1080},
        "devicePixelRatio": 1,
        "webgl": {
            "vendor": "Google Inc. (NVIDIA)",
            "renderer": (
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Laptop GPU (0x00002520) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
        },
        "canvasHash": "a1b3f6d7",
        "webdriver": False,
    }
    payload.update(raw)

    async def fake(caps: Any, spec: Any, **_kwargs: Any) -> fingerprint_probe.ProbeResult:
        return fingerprint_probe.ProbeResult(
            raw=payload, seed=spec.seed, duration=1.5, image_ref="demo/browser_engine:cloakbrowser"
        )

    monkeypatch.setattr(fingerprint_probe, "collect", fake)


def test_probe_backfills_real_persona(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-probe"))
    assert created["probe_state"] == "never"

    _fake_probe(monkeypatch)
    body = api.post(f"/api/fingerprints/{created['id']}/probe")
    assert body.status_code == 200, body.text
    data = body.json()

    assert data["probe_state"] == "fresh"
    assert "Chrome/146" in data["ua"]
    assert data["resolution"] == "1920x1080"
    # GPU 要去掉 ANGLE 那圈前缀，只留型号
    assert data["gpu"] == "NVIDIA GeForce RTX 3060 Laptop GPU"
    assert data["canvas_hash"] == "a1b3f6d7"
    assert data["languages"] == ["zh-CN", "zh"]
    assert data["webdriver"] is False
    assert data["warnings"] == []


def test_probe_flags_webdriver_leak(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-leak"))
    _fake_probe(monkeypatch, webdriver=True)

    data = api.post(f"/api/fingerprints/{created['id']}/probe").json()
    assert data["probe_state"] == "fresh"
    assert any("webdriver" in warning for warning in data["warnings"])


def test_probe_flags_tiny_screen(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """虚拟屏没铺开时 screen 是 800x600 的兜底值，不能当真实人格照抄。

    这个值一旦落库，页面上就会显示一个现实中不存在的分辨率，
    比「没采集」更误导 —— 所以要显式告警。
    """
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-tiny"))
    _fake_probe(monkeypatch, screen={"width": 800, "height": 600})

    data = api.post(f"/api/fingerprints/{created['id']}/probe").json()
    assert data["resolution"] == "800x600"
    assert any("800x600" in warning for warning in data["warnings"])


def test_probe_failure_is_recorded_not_swallowed(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-fail"))

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise fingerprint_probe.ProbeError("本地没有 cloakbrowser 的镜像")

    monkeypatch.setattr(fingerprint_probe, "collect", boom)
    res = api.post(f"/api/fingerprints/{created['id']}/probe")
    assert res.status_code == 502
    assert "镜像" in res.json()["detail"]

    detail = api.get(f"/api/fingerprints/{created['id']}").json()
    assert detail["probe_state"] == "failed"
    assert "镜像" in detail["probe_error"]


def test_changing_seed_makes_measurement_stale(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-stale"))
    _fake_probe(monkeypatch)
    api.post(f"/api/fingerprints/{created['id']}/probe")

    # 换种子等于换个人，旧的 UA / GPU 立刻失效，页面必须看得出来
    res = api.patch(f"/api/fingerprints/{created['id']}", json={"seed": 55555})
    assert res.status_code == 200, res.text
    assert res.json()["probe_state"] == "stale"


def test_editing_other_fields_also_invalidates_measurement(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不换种子、只改时区，人格也变了，同样算过期。"""
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-tz"))
    _fake_probe(monkeypatch)
    api.post(f"/api/fingerprints/{created['id']}/probe")
    assert api.get(f"/api/fingerprints/{created['id']}").json()["probe_state"] == "fresh"

    api.patch(f"/api/fingerprints/{created['id']}", json={"timezone": "Europe/London"})
    assert api.get(f"/api/fingerprints/{created['id']}").json()["probe_state"] == "stale"


def test_restoring_original_params_makes_measurement_fresh_again(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """改完又改回原值，人格回到同一个，不该逼着用户重采一次。"""
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-undo"))
    _fake_probe(monkeypatch)
    api.post(f"/api/fingerprints/{created['id']}/probe")

    api.patch(f"/api/fingerprints/{created['id']}", json={"timezone": "Europe/London"})
    assert api.get(f"/api/fingerprints/{created['id']}").json()["probe_state"] == "stale"

    api.patch(f"/api/fingerprints/{created['id']}", json={"timezone": "Asia/Shanghai"})
    assert api.get(f"/api/fingerprints/{created['id']}").json()["probe_state"] == "fresh"


# ── 下发 ─────────────────────────────────────────────────


def _make_instance(name: str, fingerprint_id: str | None) -> str:
    """造一台挂在这条指纹上的实例，用于验证下发与删除保护。"""

    async def run() -> str:
        async with SessionLocal() as session:
            browser = Browser(
                name=name,
                fingerprint_id=fingerprint_id,
                fingerprint_mode=(
                    FingerprintMode.template if fingerprint_id else FingerprintMode.default
                ),
            )
            session.add(browser)
            await session.commit()
            return str(browser.id)

    return _run(run())


def _drop_instances(ids: list[str]) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Browser).where(Browser.id.in_(ids)))
            await session.commit()
        await dispose()

    _run(run())


def test_apply_writes_and_binds(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-apply"))
    instance_id = _make_instance(f"{PREFIX}-inst", None)
    installed: list[str] = []

    async def fake_apply(caps: Any, spec: Any, *, instance_name: str, **_: Any) -> Any:
        installed.append(instance_name)
        return fingerprint_apply.ApplyResult(
            container=f"wv-{instance_name}",
            payload={"seed": spec.seed},
            restarted=True,
        )

    monkeypatch.setattr(fingerprint_apply, "apply", fake_apply)
    try:
        res = api.post(
            f"/api/fingerprints/{created['id']}/apply", json={"instance_ids": [instance_id]}
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ok"] is True
        assert body["succeeded"] == 1
        assert installed == [f"{PREFIX}-inst"]

        # 下发成功就该把这台机器归到这条指纹名下
        detail = api.get(f"/api/fingerprints/{created['id']}").json()
        assert [item["id"] for item in detail["instances"]] == [instance_id]
    finally:
        _drop_instances([instance_id])


def test_apply_reports_container_errors_per_instance(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-noctr"))
    instance_id = _make_instance(f"{PREFIX}-nobox", None)

    async def fake_apply(*_args: Any, **_kwargs: Any) -> Any:
        raise fingerprint_apply.ApplyError(
            "找不到容器 wv-x", detail=["先在实例上点启动"]
        )

    monkeypatch.setattr(fingerprint_apply, "apply", fake_apply)
    try:
        body = api.post(
            f"/api/fingerprints/{created['id']}/apply", json={"instance_ids": [instance_id]}
        ).json()
        assert body["ok"] is False
        assert body["failed"] == 1
        assert "找不到容器" in body["items"][0]["message"]
    finally:
        _drop_instances([instance_id])


def test_apply_is_refused_for_unsupported_kernel(
    api: TestClient, legacy_on_unsupported_kernel: str
) -> None:
    res = api.post(
        f"/api/fingerprints/{legacy_on_unsupported_kernel}/apply",
        json={"instance_ids": [str(uuid4())]},
    )
    assert res.status_code == 409
    assert res.json()["detail"]


# ── 删除 ─────────────────────────────────────────────────


def test_delete_is_blocked_while_instances_use_it(api: TestClient) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-busy"))
    instance_id = _make_instance(f"{PREFIX}-user", created["id"])
    try:
        res = api.delete(f"/api/fingerprints/{created['id']}")
        assert res.status_code == 409
        assert f"{PREFIX}-user" in res.json()["detail"]
    finally:
        _drop_instances([instance_id])


def test_delete_removes_unused_fingerprint(api: TestClient) -> None:
    created = _create(_payload(kernel_id=_run(_kernel_id("CloakBrowser")), code=f"{PREFIX}-gone"))
    assert api.delete(f"/api/fingerprints/{created['id']}").status_code == 204
    assert api.get(f"/api/fingerprints/{created['id']}").status_code == 404
