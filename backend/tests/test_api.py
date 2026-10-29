from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"]


def test_overview_shape() -> None:
    res = client.get("/api/overview")
    assert res.status_code == 200
    body = res.json()
    assert body["cluster"]["total"] == 168
    assert body["cluster"]["online"] == 128
    assert len(body["instances"]) == 5
    assert len(body["cards"]) == 4
    assert len(body["trend"]["labels"]) >= 5
    assert len(body["trend"]["series"]) == len(body["trend"]["companion"])


def test_browsers_and_filters() -> None:
    body = client.get("/api/browsers").json()
    assert body["totals"]["total"] == 168
    assert len(body["instances"]) == 6
    keys = [f["key"] for f in body["filters"]]
    assert keys == ["all", "running", "idle", "error"]


def test_accounts() -> None:
    body = client.get("/api/accounts").json()
    assert body["totals"]["total"] == 512
    assert any(a["status"] == "restricted" for a in body["accounts"])


def test_ip_pool() -> None:
    body = client.get("/api/ip-pool").json()
    assert body["totals"]["total"] == 420
    assert len(body["region_distribution"]) == 4
    assert body["rotation"]["enabled"] is True


def test_novnc_detail() -> None:
    body = client.get("/api/novnc/brw-us-west-042").json()
    assert body["instance"]["id"] == "brw-us-west-042"
    assert body["fingerprint"]["canvas_noise"] is True
    assert len(body["logs"]) == 4


def test_fingerprints_list() -> None:
    body = client.get("/api/fingerprints").json()
    assert body["total"] == 452
    assert body["shown"] == len(body["templates"]) == 8
    assert [f["key"] for f in body["filters"]] == ["all", "windows", "macos", "mobile"]

    broken = next(t for t in body["templates"] if t["warning"])
    assert broken["uniqueness"] is None
    assert broken["action"] == "一键更新 UA"

    healthy = [t for t in body["templates"] if t["uniqueness"] is not None]
    assert all(t["uniqueness"] > 0 for t in healthy)


def test_auth_workspaces_and_captcha() -> None:
    workspaces = client.get("/api/auth/workspaces").json()
    assert workspaces["default_id"] in [w["id"] for w in workspaces["items"]]

    captcha = client.get("/api/auth/captcha").json()
    assert len(captcha["code"]) == 4


def test_forgot_password_validates_captcha() -> None:
    client.get("/api/auth/captcha")
    bad = client.post(
        "/api/auth/forgot-password",
        json={
            "workspace": "webweaver-team",
            "email": "lin.zhiyuan@webweaver.io",
            "captcha": "0000",
        },
    ).json()
    assert bad["ok"] is False
    assert "验证码" in bad["message"]

    bad_mail = client.post(
        "/api/auth/forgot-password",
        json={"workspace": "webweaver-team", "email": "not-an-email", "captcha": "0000"},
    ).json()
    assert bad_mail["ok"] is False


def test_reset_password_checks() -> None:
    strong = client.post(
        "/api/auth/reset-password",
        json={"password": "Ww#2024Cluster!", "confirm": "Ww#2024Cluster!"},
    ).json()
    assert strong["ok"] is True
    assert strong["strength"] == 4
    assert strong["revoked_sessions"] > 0

    weak = client.post(
        "/api/auth/reset-password", json={"password": "abc123", "confirm": "abc123"}
    ).json()
    assert weak["ok"] is False
    assert weak["strength"] < 4
    assert any(c["key"] == "length" and not c["passed"] for c in weak["checks"])

    mismatch = client.post(
        "/api/auth/reset-password",
        json={"password": "Ww#2024Cluster!", "confirm": "Ww#2024Cluster"},
    ).json()
    assert mismatch["ok"] is False
    assert "不一致" in mismatch["message"]


def test_kernels_payload() -> None:
    body = client.get("/api/kernels").json()
    assert len(body["tiles"]) == 4
    engines = body["engines"]
    assert [e["name"] for e in engines] == [
        "CloakBrowser",
        "Camoufox",
        "fingerprint-chromium",
        "ungoogled-chromium",
    ]
    assert sum(e["instances"] for e in engines) == body["total_instances"] == 168
    assert sum(1 for e in engines if e["primary"]) == 1
    assert [e["engine"] for e in engines] == ["Chromium", "Firefox", "Chromium", "Chromium"]
    assert all(len(e["checks"]) == len(body["check_labels"]) for e in engines)
    assert all(len(e["releases"]) >= 2 for e in engines)
    only = next(e for e in engines if e["update"])
    assert only["id"] == "eng-fpchromium"


def test_kernel_tabs_and_fallback() -> None:
    body = client.get("/api/kernels").json()
    tabs = {t["key"]: t["count"] for t in body["tabs"]}
    assert tabs == {"all": 4, "chromium": 3, "firefox": 1, "update": 1}
    assert len(body["fallback"]) == 4
    assert [f["role"] for f in body["fallback"]] == ["首选", "切换", "复现", "兜底"]
    assert len(body["fallback_triggers"]) == 3


def test_set_primary_kernel() -> None:
    bad = client.post("/api/kernels/eng-nope/primary").json()
    assert bad["ok"] is False
    assert "不存在" in bad["message"]

    ok = client.post("/api/kernels/eng-camoufox/primary").json()
    assert ok["ok"] is True
    assert ok["primary_id"] == "eng-camoufox"
    body = client.get("/api/kernels").json()
    main = next(e for e in body["engines"] if e["primary"])
    assert main["id"] == "eng-camoufox"

    client.post("/api/kernels/eng-cloak/primary")


def test_upgrade_options() -> None:
    body = client.get("/api/kernels/upgrade-options").json()
    assert len(body["kernels"]) == 4
    assert body["kernels"][3]["disabled"] is True
    assert len(body["toggles"]) == 3
    assert all(t["default"] for t in body["toggles"])


def test_create_upgrade_ok() -> None:
    body = client.post(
        "/api/kernels/upgrade",
        json={"kernel_id": "eng-cloak", "scope": "group", "groups": ["g-na"]},
    ).json()
    assert body["ok"] is True
    assert body["targets"] == 24
    assert body["task_id"]


def test_create_upgrade_rejects_disabled_kernel() -> None:
    body = client.post(
        "/api/kernels/upgrade",
        json={"kernel_id": "eng-ungoogled", "scope": "group", "groups": ["g-na"]},
    ).json()
    assert body["ok"] is False
    assert "下载中" in body["message"]


def test_create_upgrade_requires_group() -> None:
    body = client.post(
        "/api/kernels/upgrade",
        json={"kernel_id": "eng-cloak", "scope": "group", "groups": []},
    ).json()
    assert body["ok"] is False
    assert "分组" in body["message"]


def test_account_menu() -> None:
    body = client.get("/api/account/menu").json()
    assert body["name"] == "林知远"
    assert body["version"] == "v2.4.1"
    assert len(body["groups"]) == 3
    flat = [row for group in body["groups"] for row in group]
    assert any(row["danger"] for row in flat)
    assert any(row["badge"] == "已开启" for row in flat)
