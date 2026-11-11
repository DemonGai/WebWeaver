"""接口测试。

认证接口用内存数据，直接跑；内核见 ``test_kernels_api.py``。
总览 / 浏览器池 / 账号 / IP / 指纹 / noVNC 走数据库，
依赖 ``seeded_database`` 夹具写入种子数据（共 8 个实例）。
"""

from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"]


def test_overview_shape(seeded_database: None) -> None:
    res = client.get("/api/overview")
    assert res.status_code == 200
    body = res.json()
    # 种子数据：8 个实例，4 运行 + 1 空闲 = 5 在线
    assert body["cluster"]["total"] == 8
    assert body["cluster"]["online"] == 5
    assert body["cluster"]["accounts_total"] == 8
    assert body["cluster"]["ip_total"] == 12
    assert len(body["instances"]) == 8
    # 只有三张基础设施卡：账号 / 出口 IP / 指纹。平台不做自动化调度，
    # 所以没有「运行中任务」也没有「待处理事项」这类卡片。
    assert len(body["cards"]) == 3
    assert [c["key"] for c in body["cards"]] == ["accounts", "ip", "fingerprints"]
    assert "todos" not in body

    # 健康分由四个分项加权得出，权重必须合计 100，否则总分没有意义
    parts = body["health_parts"]
    assert [p["key"] for p in parts] == ["instances", "exit", "accounts", "fingerprints"]
    assert sum(p["weight"] for p in parts) == 100
    assert 0 <= body["cluster"]["health"] <= 100

    # 事件流来自审计表：有记录时字段齐全
    for event in body["events"]:
        assert event["title"] and event["tag"] and event["time"]

    assert body["range"] == "7d"
    assert len(body["trend"]["series"]) == len(body["trend"]["companion"]) == 7
    assert len(body["trend"]["labels"]) <= 7
    assert "novnc_preview" not in body


def test_overview_ranges(seeded_database: None) -> None:
    """三种时间窗分桶数量各不相同，且统计条永远三项。"""
    for range_key, buckets in (("24h", 24), ("7d", 7), ("30d", 30)):
        body = client.get(f"/api/overview?range={range_key}").json()
        assert body["range"] == range_key
        assert len(body["trend"]["series"]) == buckets
        assert len(body["trend_stats"]) == 3

    # 非法时间窗由 FastAPI 的枚举校验挡下
    assert client.get("/api/overview?range=1y").status_code == 422


def test_browsers_and_filters(seeded_database: None) -> None:
    body = client.get("/api/browsers").json()
    assert body["totals"] == {"running": 4, "total": 8, "delta": 0}
    assert len(body["instances"]) == 8
    keys = [f["key"] for f in body["filters"]]
    assert keys == ["all", "running", "idle", "error"]
    assert [f["count"] for f in body["filters"]] == [8, 4, 1, 1]

    # 运行中的排在前面，且主键是 UUID 而不是实例名
    assert body["instances"][0]["status"] == "running"
    assert UUID(body["instances"][0]["id"])

    by_name = {item["name"]: item for item in body["instances"]}
    assert by_name["brw-sg-sin-031"]["note"] == "代理不可达，尝试重连 3 次"
    assert by_name["brw-au-syd-011"]["note"] == "等待调度"
    assert by_name["brw-us-west-042"]["group"] == "北美店铺"
    assert by_name["brw-us-west-042"]["fingerprint"] == "Win11 / C128"


def test_accounts(seeded_database: None) -> None:
    body = client.get("/api/accounts").json()
    assert body["totals"]["total"] == 8
    rows = {a["name"]: a for a in body["accounts"]}
    assert rows["store_sg_031"]["status"] == "restricted"
    assert rows["store_sg_031"]["action"] == "修复会话"
    assert rows["store_sg_031"]["bound_instance"] == "brw-sg-sin-031"
    assert rows["media_hk_025"]["status"] == "in_session"
    assert rows["media_hk_025"]["exit_ip"] == "61.8.212.44"
    assert rows["shop_ca_003"]["registered_days"] >= 39
    assert body["filters"][0]["key"] == "all-platform"


def test_ip_pool(seeded_database: None) -> None:
    body = client.get("/api/ip-pool").json()
    assert body["totals"] == {"available": 7, "total": 12, "online_rate": 91.7}
    assert [r["label"] for r in body["region_distribution"]] == ["美国", "欧洲", "亚洲"]
    assert sum(r["value"] for r in body["region_distribution"]) == 12
    assert sum(s["count"] for s in body["suppliers"]) == 12
    assert body["rotation"]["enabled"] is True

    failed = [r for r in body["resources"] if r["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["ip"] == "27.124.9.140"
    # 可用资源排在前面，失败的沉底
    assert body["resources"][0]["status"] == "available"
    assert body["resources"][-1]["status"] == "failed"


def test_novnc_detail(seeded_database: None) -> None:
    body = client.get("/api/novnc/brw-us-west-042").json()
    assert body["instance"]["name"] == "brw-us-west-042"
    assert UUID(body["instance"]["id"])
    assert body["instance"]["group"] == "北美店铺"
    assert body["fingerprint"]["canvas_noise"] is True
    assert body["fingerprint"]["score"] == 96
    assert body["account"]["name"] == "shop_us_042"
    assert body["exit_ip"]["ip"] == "104.28.16.73"
    assert len(body["logs"]) == 3

    # 前端路由传的是 UUID，也要能查
    other = client.get("/api/browsers").json()["instances"][0]
    by_id = client.get(f"/api/novnc/{other['id']}").json()
    assert by_id["instance"]["id"] == other["id"]

    assert client.get("/api/novnc/not-exist").status_code == 404


def test_fingerprints_list(seeded_database: None) -> None:
    body = client.get("/api/fingerprints").json()
    assert body["total"] == body["shown"] == len(body["templates"]) == 8
    assert body["kernels"] == 4
    # 四个内核对指纹的支持情况：CloakBrowser 与 fingerprint-chromium 认参数，
    # Camoufox 没做镜像，ungoogled 是纯净 Chromium 不带补丁。
    assert body["supported_kernels"] == 2
    assert [f["key"] for f in body["filters"]] == ["all", "windows", "macos", "mobile"]
    assert [f["count"] for f in body["filters"]] == [8, 5, 2, 1]

    # 种子是下发的唯一入口：没有种子就装配不出人格，所以每条都必须有
    assert all(t["seed"] for t in body["templates"])

    # 统计条的数字必须和每条的实测状态自洽，不能各算各的。
    # 不写死「刚灌完种子所以是 0」——开发库可能已经采集过，
    # 那样断言就会因为环境状态而不是代码问题挂掉。
    fresh = [t for t in body["templates"] if t["probe_state"] == "fresh"]
    stale = [t for t in body["templates"] if t["probe_state"] == "stale"]
    assert body["stale"] == len(stale)
    # probed 是「读回过人格」的条数，含参数改过之后变 stale 的那些
    assert body["probed"] == len(fresh) + len(stale)

    # 内核支持不代表这条指纹能下发：桌面内核伪装不成 Android，
    # 要在列表里就标出来，而不是等用户点了才 422
    android = next(t for t in body["templates"] if t["fp_id"] == "fp-android-c128")
    assert android["supported"] is False
    assert "Android" in (android["unsupported_reason"] or "")

    # 8 个实例里 7 个套模板，brw-au-syd-011 走默认指纹（原生指纹），不占模板
    assert sum(t["instances"] for t in body["templates"]) == 7


def test_browser_modes(seeded_database: None) -> None:
    """直连与默认指纹是独立状态，不能显示成「未分配」。"""
    instances = {item["name"]: item for item in client.get("/api/browsers").json()["instances"]}

    direct = instances["brw-au-syd-011"]
    assert direct["ip"] == "直连 · 本机 IP"
    assert direct["region"] == "本机网络"
    assert direct["fingerprint"] == "默认指纹"

    proxied = instances["brw-us-west-042"]
    assert proxied["ip"] == "104.28.16.73"
    assert proxied["fingerprint"] != "默认指纹"


def test_auth_workspaces_and_captcha() -> None:
    workspaces = client.get("/api/auth/workspaces").json()
    assert workspaces["default_id"] in [w["id"] for w in workspaces["items"]]

    captcha = client.get("/api/auth/captcha").json()
    assert len(captcha["code"]) == 4


def test_forgot_password_validates_captcha() -> None:
    client.get("/api/auth/captcha")
    bad = client.post(
        "/api/auth",
        json={
            "action": "forgot_password",
            "workspace": "webweaver-team",
            "email": "lin.zhiyuan@webweaver.io",
            "captcha": "0000",
        },
    ).json()
    assert bad["ok"] is False
    assert bad["action"] == "forgot_password"
    assert "验证码" in bad["message"]

    bad_mail = client.post(
        "/api/auth",
        json={
            "action": "forgot_password",
            "workspace": "webweaver-team",
            "email": "not-an-email",
            "captcha": "0000",
        },
    ).json()
    assert bad_mail["ok"] is False


def test_auth_endpoint_validates_action_and_requires_login() -> None:
    """单入口靠 action 分发：未知动作与缺字段都应该是 422，而不是 404/500。"""
    unknown = client.post("/api/auth", json={"action": "change_email"})
    assert unknown.status_code == 422

    missing = client.post("/api/auth", json={"action": "login", "account": "admin_chen"})
    assert missing.status_code == 422

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_account_menu_anonymous() -> None:
    """未登录时给占位内容，组件不会因为空数据崩掉。"""
    body = client.get("/api/user/menu").json()
    assert body["name"] == "未登录"
    assert body["workspace"] == "未分配工作区"
    assert body["version"].startswith("v")
    assert len(body["groups"]) == 3

    flat = [row for group in body["groups"] for row in group]
    # 切换账号与设置入口都去掉了：只有默认工作区，没有可切换的东西
    assert not any(row["key"] == "switch-account" for row in flat)
    assert any(row["danger"] for row in flat)
