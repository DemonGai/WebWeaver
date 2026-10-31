"""审计日志：差异计算、查询接口、写入往返。

接口用例依赖种子数据（11 条审计样例）；写入用例自建一条再删掉，
不给后面的用例留下行数变化。
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import AuditAction, AuditLog, AuditResourceType, AuditResult
from app.services import audit

client = TestClient(app)


def test_snapshot_diff_keeps_only_changed_fields() -> None:
    diff = audit.snapshot_diff(
        {"status": "idle", "fps": 30, "note": "旧备注"},
        {"status": "running", "fps": 30, "note": "旧备注"},
    )
    assert diff == {"status": {"before": "idle", "after": "running"}}


def test_snapshot_diff_handles_new_and_removed_fields() -> None:
    diff = audit.snapshot_diff({"a": 1}, {"b": 2})
    assert diff == {
        "a": {"before": 1, "after": None},
        "b": {"before": None, "after": 2},
    }


def test_snapshot_diff_is_none_without_changes() -> None:
    assert audit.snapshot_diff({"a": 1}, {"a": 1}) is None
    assert audit.snapshot_diff(None, None) is None


def test_snapshot_diff_truncates_long_text() -> None:
    long_text = "x" * 500
    diff = audit.snapshot_diff(None, {"note": long_text})
    assert diff is not None
    kept = diff["note"]["after"]
    assert len(kept) < len(long_text)
    assert kept.endswith("…")


def test_audit_logs_endpoint(seeded_database: None) -> None:
    body = client.get("/api/audit-logs").json()
    # 认证接口的用例也会顺手写审计，所以这里只断言种子数据的下界
    assert body["total"] >= 11
    assert len(body["items"]) == min(50, body["total"])
    # 时间倒序：最新的一条在前面
    times = [item["occurred_at"] for item in body["items"]]
    assert times == sorted(times, reverse=True)

    first = body["items"][0]
    assert first["id"] and first["operator"] and first["action"] and first["resource_type"]
    assert set(first) >= {"result", "changes", "request_id", "ip_address"}


def test_audit_logs_filters(seeded_database: None) -> None:
    browsers = client.get("/api/audit-logs", params={"resource_type": "browser"}).json()
    # 只断言「至少有种子里那 5 条」：浏览器池的增删改与启停现在都会写审计，
    # 开发库里人工操作过几台实例，总数就不该被钉死
    assert browsers["total"] >= 5
    assert {item["resource_type"] for item in browsers["items"]} == {"browser"}

    failures = client.get("/api/audit-logs", params={"result": "failure"}).json()
    assert failures["total"] >= 2
    assert failures["items"][0]["error_message"]

    reset = client.get("/api/audit-logs", params={"action": "reset_password"}).json()
    assert reset["total"] >= 1
    assert reset["items"][0]["resource_type"] == "auth"


def test_audit_logs_pagination(seeded_database: None) -> None:
    page = client.get("/api/audit-logs", params={"limit": 3, "offset": 3}).json()
    assert page["total"] >= 11
    assert len(page["items"]) == 3
    assert page["limit"] == 3 and page["offset"] == 3


def test_audit_logs_are_read_only(seeded_database: None) -> None:
    """审计表对外只有读接口：不允许删记录，否则等于销毁证据。"""
    assert client.delete("/api/audit-logs").status_code == 405
    assert client.post("/api/audit-logs", json={}).status_code == 405


def test_record_writes_full_row(seeded_database: None) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            log = await audit.record(
                session,
                action=AuditAction.update,
                resource_type=AuditResourceType.system,
                resource_name="pytest",
                operator="pytest",
                detail="写入往返测试",
                changes=audit.snapshot_diff({"status": "idle"}, {"status": "running"}),
            )
            assert log is not None and log.id

            row = await session.scalar(select(AuditLog).where(AuditLog.id == log.id))
            assert row is not None
            assert row.result is AuditResult.success
            assert row.changes == {"status": {"before": "idle", "after": "running"}}

            # 用例自己清理，避免影响其它用例的行数断言
            await session.delete(row)
            await session.commit()

    try:
        asyncio.run(run())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001 - 清理失败不影响断言结果
            pass
