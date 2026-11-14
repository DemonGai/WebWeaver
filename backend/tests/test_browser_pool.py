"""浏览器池写接口：新建、编辑绑定、启停、批量、删除，以及权限与审计。

这些用例会真实落库，所以统一用 ``brw-test-`` 前缀命名，跑完清干净；
不依赖种子里具体实例的状态，避免种子调整后用例跟着碎。
"""

import asyncio
from collections.abc import Iterator
from subprocess import CompletedProcess
from uuid import UUID

import pytest
from demo_cluster import DEMO_PASSWORD
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
    Kernel,
    KernelStatus,
)
from app.services import browser_novnc, browser_runtime, kernel_image, kernel_scan
from app.services.kernel_image import ImageInfo

client = TestClient(app)

TEST_PREFIX = "brw-test-"

# 伪造的本地镜像清单：用例不能依赖「这台机器拉过哪些镜像」。
# ungoogled-chromium 故意不给镜像，用来验证「没拉过镜像的内核不进下拉」。
FAKE_IMAGES: dict[str, list[str]] = {
    "cloakbrowser": ["128.0.6613.5", "128.0.6613.2"],
    "fingerprint-chromium": ["126.0.6478.1"],
    "camoufox": ["128.0.3"],
}


def _fake_images(*, without: str | None = None) -> list[ImageInfo]:
    """按 ``FAKE_IMAGES`` 造镜像清单，``without`` 指定某个内核当作没拉过镜像。"""
    items: list[ImageInfo] = []
    for slug, versions in FAKE_IMAGES.items():
        if slug == without:
            continue
        for version in versions:
            tag = f"{slug}-{version}"
            items.append(
                ImageInfo(
                    ref=f"demo/browser_engine:{tag}",
                    repository="demo/browser_engine",
                    tag=tag,
                    image_id=f"sha256:{tag}",
                    size_bytes=400 * 1024 * 1024,
                    created_at="2026-11-10T13:50:54Z",
                    digest=f"sha256:{tag}",
                    arch="amd64",
                    os_name="linux",
                    labels={"org.opencontainers.image.version": version},
                )
            )
    return items


@pytest.fixture(autouse=True)
def fake_local_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kernel_image, "list_images", lambda *_a, **_k: _fake_images())


# 容器调用流水：(动作, 实例 id, 关键字参数)。用例用它核对「容器名就是实例 ID」
CONTAINER_CALLS: list[tuple[str, str, dict]] = []
# 解析 docker 输出这类用例要绕过下面的 fixture，先留一份真实现
_REAL_PUBLISHED_PORTS = browser_runtime.published_ports
_REAL_RESOLVE_IMAGE = browser_runtime.resolve_image


@pytest.fixture(autouse=True)
def fake_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    """把容器生命周期换成一个内存集合。

    启停现在是真打 docker 的，测试里不能因此真起一堆浏览器容器：慢、占端口，
    还会在开发机 ``docker ps`` 里留下一堆垃圾。这里只保留「起没起」这个事实，
    足以覆盖状态流转与错误分支。
    """
    live: set[str] = set()
    # 与 docker 一致：停止后容器仍保留端口映射，只有删掉才没有
    ports: dict[str, tuple[int, int]] = {}
    CONTAINER_CALLS.clear()

    async def start_container(browser_id, **kwargs) -> None:
        CONTAINER_CALLS.append(("start", str(browser_id), kwargs))
        live.add(str(browser_id))
        ports[str(browser_id)] = (kwargs["cdp_port"], kwargs["vnc_port"])

    async def stop_container(browser_id) -> None:
        CONTAINER_CALLS.append(("stop", str(browser_id), {}))
        live.discard(str(browser_id))

    async def restart_container(browser_id) -> None:
        CONTAINER_CALLS.append(("restart", str(browser_id), {}))
        if str(browser_id) not in live:
            raise browser_runtime.ContainerError("容器不存在")
        # 原地重启：容器前后都在跑，端口与配置不变

    async def remove_container(browser_id) -> None:
        CONTAINER_CALLS.append(("remove", str(browser_id), {}))
        live.discard(str(browser_id))
        ports.pop(str(browser_id), None)

    async def state(browser_id) -> str:
        return "running" if str(browser_id) in live else "absent"

    async def published_ports(browser_id) -> tuple[int, int] | None:
        return ports.get(str(browser_id))

    monkeypatch.setattr(browser_runtime, "start_container", start_container)
    monkeypatch.setattr(browser_runtime, "stop_container", stop_container)
    monkeypatch.setattr(browser_runtime, "restart_container", restart_container)
    monkeypatch.setattr(browser_runtime, "remove_container", remove_container)
    monkeypatch.setattr(browser_runtime, "state", state)
    monkeypatch.setattr(browser_runtime, "published_ports", published_ports)
    # 镜像解析也不查 docker：真实 ref 长什么样与状态流转无关
    monkeypatch.setattr(
        browser_runtime, "resolve_image", lambda *_a, **_k: "demo/browser_engine:test"
    )


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
    """建实例。没显式给内核时默认绑 CloakBrowser —— 启动要镜像，不绑内核起不来。"""
    payload: dict = {"name": name}
    if "kernel_id" not in extra:
        payload["kernel_id"] = _kernel_id("CloakBrowser")
    payload.update(extra)
    res = client.post("/api/browsers", json=payload, headers=_auth(token))
    assert res.status_code == 201, res.text
    return res.json()


def _kernel_id(name: str) -> str:
    """按内核名查库拿 id：用来构造「下拉里没有，但接口仍要挡住」的场景。"""

    async def run() -> str:
        async with SessionLocal() as session:
            kernel = await session.scalar(select(Kernel).where(Kernel.name == name))
            assert kernel is not None, f"种子里没有内核 {name}"
            return str(kernel.id)

    return asyncio.run(run())


def _set_kernel_status(kernel_id: str, status: str) -> None:
    """直接改库里的内核状态，用来模拟「这个内核后来被标成弃用」。"""

    async def run() -> None:
        async with SessionLocal() as session:
            kernel = await session.get(Kernel, UUID(kernel_id))
            assert kernel is not None
            kernel.status = KernelStatus(status)
            await session.commit()

    asyncio.run(run())


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


def test_options_only_kernels_with_images(seeded_database: None) -> None:
    """下拉只列「镜像就绪」的内核，口径与内核管理页的绿标一致。

    状态不是门槛：fingerprint-chromium 是 testing，但镜像在本地，照样能起；
    反过来 ungoogled-chromium 是 active，没拉过镜像选了也只会在启动时炸。
    Camoufox 就算本地有镜像也不算——它还没做成受支持的内核。
    """
    body = client.get("/api/browsers/options").json()
    names = [k["label"] for k in body["kernels"]]
    assert "CloakBrowser" in names
    assert "fingerprint-chromium" in names, "测试中但镜像就绪，应该可选"
    assert "ungoogled-chromium" not in names, "没有本地镜像的不该出现"
    assert "Camoufox" not in names, "还没做成镜像的引擎不算就绪"

    # 指纹能力挂在选项上：前端据此决定要不要显示「出口 IP / 指纹模板」
    cloak = next(k for k in body["kernels"] if k["label"] == "CloakBrowser")
    assert cloak["supports_fingerprint"] is True
    assert body["kernel_versions"][cloak["id"]] == ["128.0.6613.5", "128.0.6613.2"]


def test_fingerprint_rejected_on_kernel_without_patch(seeded_database: None) -> None:
    """不带指纹补丁的内核绑指纹 → 422。

    这种组合不会报错，只会静默忽略参数，界面上写着「已套模板」实际什么都没变；
    宁可在写入时挡住，也别让人以为在伪装。
    """
    token = _login()
    options = client.get("/api/browsers/options").json()
    # 下拉里已经没有不带指纹补丁的内核了，按名字取 id 直接打接口
    kernel_id = _kernel_id("Camoufox")
    fingerprint = options["fingerprints"][0]

    res = client.post(
        "/api/browsers",
        json={
            "name": f"{TEST_PREFIX}fp",
            "kernel_id": kernel_id,
            "fingerprint_id": fingerprint["id"],
        },
        headers=_auth(token),
    )
    assert res.status_code == 422
    assert "不支持指纹" in res.json()["detail"]


def test_chinese_instance_name(seeded_database: None) -> None:
    """实例名允许中文：它是要给人看的业务标识，不是容器名。"""
    token = _login()
    name = f"{TEST_PREFIX}上海-01 店铺"
    created = _create(name, token)
    assert created["name"] == name
    # 中文名同样能按名字查详情（前端路由里可能传名字）
    assert client.get(f"/api/browsers/{name}", headers=_auth(token)).json()["id"] == created["id"]


def test_duplicate_copies_kernel_only(seeded_database: None) -> None:
    """复制实例：内核、分组、备注跟着走，账号 / 出口 / 指纹故意不复制。

    这三样是排他资源，原实例正占着；照抄只会撞「已被占用」。复制出来的是
    「同款空壳」，用户按需再绑。
    """
    token = _login()
    created: list[dict] = []
    try:
        options = client.get("/api/browsers/options").json()
        kernel = next(k for k in options["kernels"] if k["supports_fingerprint"])
        account = next(a for a in options["accounts"] if not a["disabled"])
        ip = next(i for i in options["ips"] if not i["disabled"])

        source = _create(
            f"{TEST_PREFIX}copy",
            token,
            kernel_id=kernel["id"],
            account_id=account["id"],
            ip_id=ip["id"],
            fingerprint_id=options["fingerprints"][0]["id"],
            note="仓库一号",
        )
        created.append(source)
        assert source["account_id"] and source["ip_id"]

        res = client.post(f"/api/browsers/{source['id']}/duplicate", headers=_auth(token))
        assert res.status_code == 201, res.text
        copied = res.json()
        created.append(copied)
        assert copied["name"] == f"{TEST_PREFIX}copy 副本"
        assert copied["kernel_id"] == kernel["id"]
        assert copied["note"] == "仓库一号"
        assert copied["status"] == "stopped"
        assert copied["account_id"] is None
        assert copied["ip_id"] is None
        assert copied["fingerprint_id"] is None
        assert copied["ip_mode"] == "direct"

        # 连着复制：名字往后排，不会撞唯一键
        again = client.post(f"/api/browsers/{source['id']}/duplicate", headers=_auth(token)).json()
        created.append(again)
        assert again["name"] == f"{TEST_PREFIX}copy 副本2"
    finally:
        # 这个用例占着种子里唯一可用的账号与 IP，不释放会把后面的用例饿死
        for item in created:
            client.delete(f"/api/browsers/{item['id']}", headers=_auth(token))


def test_options_keeps_current_kernel_for_edit(
    seeded_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """编辑弹窗要能看到实例当前绑的内核，哪怕本地镜像已经没了。

    否则用户只是改个备注，下拉里找不到当前值，保存时内核就被清空了。
    """
    token = _login()
    options = client.get("/api/browsers/options").json()
    kernel = next(k for k in options["kernels"] if k["supports_fingerprint"])
    created = _create(f"{TEST_PREFIX}keep", token, kernel_id=kernel["id"])

    slug = kernel_scan.engine_slug(kernel["label"])
    monkeypatch.setattr(kernel_image, "list_images", lambda *_a, **_k: _fake_images(without=slug))

    body = client.get(f"/api/browsers/options?browser_id={created['id']}").json()
    kept = [k for k in body["kernels"] if k["id"] == kernel["id"]]
    assert kept, "当前实例绑的内核必须留在候选里"
    # 别的实例照旧看不到它
    other = client.get("/api/browsers/options").json()
    assert all(k["id"] != kernel["id"] for k in other["kernels"])


def test_options_keeps_deprecated_kernel(seeded_database: None) -> None:
    """过滤只看镜像：已弃用但镜像就绪的内核仍在下拉里。

    状态不参与过滤，也不写进下拉文案——要不要用是用户自己的判断，
    卡片上已经写清楚了。
    """
    options = client.get("/api/browsers/options").json()
    kernel = next(k for k in options["kernels"] if k["supports_fingerprint"])
    _set_kernel_status(kernel["id"], "deprecated")
    try:
        body = client.get("/api/browsers/options").json()
        kept = next(k for k in body["kernels"] if k["id"] == kernel["id"])
        assert "已弃用" not in kept["hint"], "状态不进下拉文案"
    finally:
        _set_kernel_status(kernel["id"], "active")


def test_switch_to_kernel_without_patch_drops_fingerprint(seeded_database: None) -> None:
    """换到不带指纹补丁的内核时，旧模板自动解绑。

    留着它会让卡片上一直写着「已套模板」，而实际下发时一个字都不会带上——
    这种假象比没有更危险。
    """
    token = _login()
    options = client.get("/api/browsers/options").json()
    patchy = next(k for k in options["kernels"] if k["supports_fingerprint"])
    plain_id = _kernel_id("Camoufox")  # 下拉里不列，但接口仍要能正确处理换过去

    created = _create(
        f"{TEST_PREFIX}switch",
        token,
        kernel_id=patchy["id"],
        fingerprint_id=options["fingerprints"][0]["id"],
    )
    assert created["fingerprint_mode"] == "template"

    res = client.patch(
        f"/api/browsers/{created['id']}", json={"kernel_id": plain_id}, headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    assert res.json()["fingerprint_id"] is None
    assert res.json()["fingerprint_mode"] == "default"



# ── 生命周期 ────────────────────────────────────────────────


def test_lifecycle_start_stop_restart(seeded_database: None) -> None:
    token = _login()
    created = _create(f"{TEST_PREFIX}life", token)
    assert created["status"] == "stopped"

    started = _actions(created["id"], "start", token)
    assert started.status_code == 200 and started.json()["ok"] is True

    # 容器名必须是实例 ID：中文实例名在 docker 里根本起不来
    assert CONTAINER_CALLS[-1][1] == created["id"]
    assert CONTAINER_CALLS[-1][2]["instance_name"] == f"{TEST_PREFIX}life"

    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "running"
    # 启动后必须拿到一组可用的接管地址，否则前端「打开 noVNC」没地方去
    assert detail["cdp_url"].startswith("http://127.0.0.1:")
    assert detail["vnc_port"] and detail["vnc_url"]

    # 重复启动是明确的冲突，不是静默成功
    assert _actions(created["id"], "start", token).status_code == 409

    restarted = _actions(created["id"], "restart", token)
    assert restarted.status_code == 200
    # 容器还在时走原地重启，不要偷偷删了重建（那样会丢页面状态）
    assert CONTAINER_CALLS[-1][0] == "restart"
    assert CONTAINER_CALLS[-1][1] == created["id"]

    stopped = _actions(created["id"], "stop", token)
    assert stopped.status_code == 200
    assert CONTAINER_CALLS[-1][0] == "stop"
    assert CONTAINER_CALLS[-1][1] == created["id"]
    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "stopped"
    assert detail["cdp_url"] is None and detail["vnc_url"] is None

    assert _actions(created["id"], "stop", token).status_code == 409


def test_start_without_kernel_is_rejected(seeded_database: None) -> None:
    """没绑内核就没有镜像可跑，422 说清楚缺什么。"""
    token = _login()
    created = _create(f"{TEST_PREFIX}nokernel", token, kernel_id=None)
    res = _actions(created["id"], "start", token)
    assert res.status_code == 422
    assert "内核" in res.json()["detail"]
    # 失败不能留下「自称运行中」的实例
    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "stopped"


def test_start_reports_missing_image(seeded_database: None, monkeypatch) -> None:
    """镜像不在本地时，把原因原样给用户，而不是改完状态再让人去猜。"""
    token = _login()
    created = _create(f"{TEST_PREFIX}noimage", token)

    def explode(*_args, **_kwargs):
        raise browser_runtime.ContainerError("本地还没有 CloakBrowser 的镜像")

    monkeypatch.setattr(browser_runtime, "resolve_image", explode)
    res = _actions(created["id"], "start", token)
    assert res.status_code == 409
    assert "镜像" in res.json()["detail"]
    detail = client.get(f"/api/browsers/{created['id']}", headers=_auth(token)).json()
    assert detail["status"] == "stopped"


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


# ── noVNC 能力检测与可接管清单 ────────────────────────────────


def _label_image(label: str | None) -> ImageInfo:
    labels = {"org.opencontainers.image.version": "128.0.6613.2"}
    if label is not None:
        labels[browser_novnc.NOVNC_LABEL] = label
    return ImageInfo(
        ref="demo/browser_engine:cloakbrowser-128.0.6613.2",
        repository="demo/browser_engine",
        tag="cloakbrowser-128.0.6613.2",
        image_id="sha256:label",
        size_bytes=1,
        created_at="2026-11-10T13:50:54Z",
        labels=labels,
    )


def test_novnc_capability_trusts_image_label(monkeypatch: pytest.MonkeyPatch) -> None:
    browser_novnc.forget()
    monkeypatch.setattr(kernel_image, "inspect", lambda _ref: _label_image("0"))

    cap = browser_novnc.detect("demo/browser_engine:cloakbrowser-128.0.6613.2")
    assert cap.supported is False
    assert "WITH_VNC=0" in cap.reason
    assert cap.source == "label"


def test_novnc_capability_falls_back_to_build_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """老镜像没有能力标签，靠构建历史里装 noVNC 那一层判定。"""
    browser_novnc.forget()
    monkeypatch.setattr(kernel_image, "inspect", lambda _ref: _label_image(None))
    monkeypatch.setattr(
        kernel_image,
        "run",
        lambda args, **_k: CompletedProcess(
            args, 0, "RUN apt-get install xvfb x11vnc novnc websockify", ""
        ),
    )

    cap = browser_novnc.detect("demo/browser_engine:cloakbrowser-128.0.6613.2")
    assert cap.supported is True
    assert cap.source == "history"


def test_novnc_capability_rejects_headless_image(monkeypatch: pytest.MonkeyPatch) -> None:
    browser_novnc.forget()
    monkeypatch.setattr(kernel_image, "inspect", lambda _ref: _label_image(None))
    monkeypatch.setattr(
        kernel_image,
        "run",
        lambda args, **_k: CompletedProcess(args, 0, "RUN apt-get install xvfb", ""),
    )

    cap = browser_novnc.detect("demo/browser_engine:cloakbrowser-128.0.6613.2")
    assert cap.supported is False
    assert "没有 noVNC" in cap.reason


def test_novnc_overview_reports_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    """没启动时给「先启动」的理由，启动后才有地址与端口。"""
    token = _login()
    item = _create(f"{TEST_PREFIX}novnc-01", token)
    monkeypatch.setattr(
        browser_novnc, "detect", lambda _ref: browser_novnc.Capability(True, "", "label")
    )

    body = client.get("/api/browsers/novnc").json()
    row = next(x for x in body["instances"] if x["id"] == item["id"])
    assert row["supports_novnc"] is True
    assert row["ready"] is False
    assert row["availability"] == "stopped"
    assert row["url"] is None
    assert "未启动" in row["reason"]
    assert body["totals"]["total"] == len(body["instances"])

    assert _actions(item["id"], "start", token).status_code == 200

    body = client.get("/api/browsers/novnc").json()
    row = next(x for x in body["instances"] if x["id"] == item["id"])
    assert row["ready"] is True
    assert row["availability"] == "ready"
    # TestClient 的 host 是 testserver，地址跟着请求 host 走
    assert row["url"] == f"http://testserver:{row['port']}/vnc.html?autoconnect=1&resize=scale"
    assert body["totals"]["ready"] >= 1


def test_novnc_overview_explains_unsupported_image(monkeypatch: pytest.MonkeyPatch) -> None:
    token = _login()
    item = _create(f"{TEST_PREFIX}novnc-02", token)
    monkeypatch.setattr(
        browser_novnc,
        "detect",
        lambda _ref: browser_novnc.Capability(False, "这个镜像里没有 noVNC", "history"),
    )

    body = client.get("/api/browsers/novnc").json()
    row = next(x for x in body["instances"] if x["id"] == item["id"])
    assert row["supports_novnc"] is False
    assert row["ready"] is False
    assert row["availability"] == "unsupported"
    assert row["reason"] == "这个镜像里没有 noVNC"


def test_novnc_overview_flags_missing_image_as_blocked() -> None:
    """版本对不上本地镜像：既不算「镜像不支持」，也不该让用户去点启动。"""
    token = _login()
    item = _create(f"{TEST_PREFIX}novnc-03", token, kernel_version="0.0.0")

    body = client.get("/api/browsers/novnc").json()
    row = next(x for x in body["instances"] if x["id"] == item["id"])
    assert row["availability"] == "blocked"
    assert row["supports_novnc"] is False
    assert "本地没有" in row["reason"]
    assert body["totals"]["blocked"] >= 1


def test_novnc_target_unknown_instance_returns_404() -> None:
    assert client.get("/api/browsers/not-exist/novnc").status_code == 404


# ── 端口以容器实际发布为准 ────────────────────────────────────


def _always(value: str):
    async def _fn(_browser_id) -> str:
        return value

    return _fn


def _ports(pair: tuple[int, int]):
    async def _fn(_browser_id) -> tuple[int, int]:
        return pair

    return _fn


def test_published_ports_parses_docker_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """``docker port`` 会为 IPv4/IPv6 各打一行，取先出现的那个即可。"""
    monkeypatch.setattr(browser_runtime, "published_ports", _REAL_PUBLISHED_PORTS)
    monkeypatch.setattr(
        kernel_image,
        "run",
        lambda args, **_k: CompletedProcess(
            args,
            0,
            "6080/tcp -> 0.0.0.0:6081\n6080/tcp -> [::]:6081\n"
            "9222/tcp -> 0.0.0.0:9181\n9222/tcp -> [::]:9181\n",
            "",
        ),
    )
    assert asyncio.run(browser_runtime.published_ports("any-id")) == (9181, 6081)


def test_published_ports_returns_none_when_container_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_runtime, "published_ports", _REAL_PUBLISHED_PORTS)
    monkeypatch.setattr(
        kernel_image,
        "run",
        lambda args, **_k: CompletedProcess(args, 1, "", "Error: No such container"),
    )
    assert asyncio.run(browser_runtime.published_ports("any-id")) is None


def test_start_syncs_ports_from_running_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """容器已在跑但库里记成停止：以容器真实端口回写，别另分一个没人监听的端口。"""
    token = _login()
    item = _create(f"{TEST_PREFIX}ports-01", token)

    monkeypatch.setattr(browser_runtime, "state", _always("running"))
    monkeypatch.setattr(browser_runtime, "published_ports", _ports((9199, 6099)))

    resp = _actions(item["id"], "start", token)
    assert resp.status_code == 200
    # 容器在跑就不该重建
    assert [call[0] for call in CONTAINER_CALLS if call[1] == item["id"]] == []

    detail = client.get(f"/api/browsers/{item['id']}").json()
    assert detail["vnc_port"] == 6099
    assert detail["cdp_url"] == "http://127.0.0.1:9199"
    assert "6099" in detail["vnc_url"]


def test_restart_rewrites_ports_from_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """重启不改端口，但库里的值可能早就漂了，按容器的真实端口纠正。"""
    token = _login()
    item = _create(f"{TEST_PREFIX}ports-02", token)
    assert _actions(item["id"], "start", token).status_code == 200

    before = client.get(f"/api/browsers/{item['id']}").json()["vnc_port"]
    monkeypatch.setattr(browser_runtime, "published_ports", _ports((9399, 6299)))

    assert _actions(item["id"], "restart", token).status_code == 200
    after = client.get(f"/api/browsers/{item['id']}").json()
    assert after["vnc_port"] == 6299
    assert after["vnc_port"] != before
    assert after["cdp_url"] == "http://127.0.0.1:9399"


def test_start_reuses_stopped_container_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """容器还在但已停止：沿用原端口，实例地址不会启动一次换一次。"""
    token = _login()
    item = _create(f"{TEST_PREFIX}ports-03", token)
    assert _actions(item["id"], "start", token).status_code == 200
    first = client.get(f"/api/browsers/{item['id']}").json()["vnc_port"]

    assert _actions(item["id"], "stop", token).status_code == 200
    # 停掉后容器仍保留端口映射（docker port 照样有输出），模拟这一状态
    monkeypatch.setattr(browser_runtime, "published_ports", _ports((first + 3100, first)))

    assert _actions(item["id"], "start", token).status_code == 200
    again = client.get(f"/api/browsers/{item['id']}").json()["vnc_port"]
    assert again == first


# ── 镜像解析：台账版本悬空时退到最新 ────────────────────────────


def test_resolve_image_falls_back_when_ledger_dangles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """种子里的旧版本号本地没镜像、实例又没钉版本：按最新镜像启动，别直接失败。"""
    monkeypatch.setattr(browser_runtime, "resolve_image", _REAL_RESOLVE_IMAGE)
    kernel = Kernel(name="CloakBrowser", version="999.0.0")

    ref = browser_runtime.resolve_image(kernel, None)

    assert ref == "demo/browser_engine:cloakbrowser-128.0.6613.5"


def test_resolve_image_rejects_missing_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """实例明确钉了某版本，缺就是缺——不能悄悄换一个版本跑。"""
    monkeypatch.setattr(browser_runtime, "resolve_image", _REAL_RESOLVE_IMAGE)
    kernel = Kernel(name="CloakBrowser", version="128.0.6613.5")

    with pytest.raises(browser_runtime.ContainerError) as excinfo:
        browser_runtime.resolve_image(kernel, "999.0.0")

    assert "999.0.0" in str(excinfo.value)
