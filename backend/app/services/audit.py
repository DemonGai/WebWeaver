"""审计日志的写入与查询。

写入侧只暴露一个 :func:`record`：业务代码不直接构造 ``AuditLog``，
免得每个调用点各自决定要不要带 request_id、要不要吞异常。
查询侧 :func:`list_logs` 供接口层复用，过滤条件都走索引。

审计是「旁路」：写失败不能把正常业务带崩，所以 ``record`` 内部兜住异常，
只打一条 warning。代价是极端情况下会丢审计记录——这在审计与可用性之间
是刻意的取舍，真正强合规的场景应改为写独立的消息队列。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import logger, request_id_ctx
from app.models import AuditAction, AuditLog, AuditResourceType, AuditResult, AuditSource

# 变更快照里单值最长保留的字符数，避免一坨超长文本把整行撑爆
MAX_VALUE_LENGTH = 200
# User-Agent 这类字段数据库里是 VARCHAR(255)，超长先截断再入库
MAX_UA_LENGTH = 255


def snapshot_diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]] | None:
    """算出前后差异，只保留发生变化的字段。

    返回 ``{"status": {"before": "idle", "after": "running"}}`` 这种结构，
    前端可以直接渲染成「字段 / 旧值 / 新值」三列表格。没有差异时返回 ``None``：
    空对象写进 JSONB 只会让「这条到底改了什么」更难判断。
    """
    if before is None and after is None:
        return None

    before = before or {}
    after = after or {}
    diff: dict[str, dict[str, Any]] = {}
    for field in sorted(set(before) | set(after)):
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        diff[field] = {"before": _shrink(old), "after": _shrink(new)}
    return diff or None


def _shrink(value: Any) -> Any:
    """超长字符串按字符截断，其它类型（数字、布尔、UUID、字典）原样保留。"""
    if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
        return value[:MAX_VALUE_LENGTH] + "…"
    if isinstance(value, UUID):
        return str(value)
    return value


async def record(
    session: AsyncSession,
    *,
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: UUID | str | None = None,
    resource_name: str | None = None,
    operator: str = "system",
    source: AuditSource = AuditSource.api,
    result: AuditResult = AuditResult.success,
    detail: str | None = None,
    changes: dict[str, Any] | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    request: Request | None = None,
) -> AuditLog | None:
    """写一条审计记录并提交。

    ``request`` 只用来补 request_id / 客户端 IP / UA 三个链路字段，
    不传也能写（后台任务、命令行脚本就没有请求上下文）。
    返回落库后的对象；写失败返回 ``None``，不抛异常。
    """
    log = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=_as_uuid(resource_id),
        resource_name=_clip(resource_name, 128),
        operator=_clip(operator, 64) or "system",
        source=source,
        result=result,
        detail=_clip(detail, 500),
        changes=changes,
        error_message=_clip(error_message, 500),
        duration_ms=duration_ms,
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=_clip(_user_agent(request), MAX_UA_LENGTH),
    )

    try:
        session.add(log)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - 审计失败不能影响主流程
        # rollback 自己也可能因为连接已断而再抛一次，这里同样不能放出去
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("审计日志写入失败（action={}）：{}", action.value, exc)
        return None

    logger.debug(
        "审计：{} {} {}（{}）",
        log.operator,
        log.action.value,
        log.resource_type.value,
        log.result.value,
    )
    return log


async def list_logs(
    session: AsyncSession,
    *,
    action: AuditAction | None = None,
    resource_type: AuditResourceType | None = None,
    resource_id: UUID | None = None,
    operator: str | None = None,
    result: AuditResult | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """按条件翻页查询，返回 ``(当前页记录, 总数)``。

    排序固定为「时间倒序 + 主键倒序」：同一毫秒写入的多条记录也要有稳定顺序，
    否则翻页会重复或漏行。
    """
    conditions = []
    if action is not None:
        conditions.append(AuditLog.action == action)
    if resource_type is not None:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditLog.resource_id == resource_id)
    if operator:
        conditions.append(AuditLog.operator == operator)
    if result is not None:
        conditions.append(AuditLog.result == result)
    if since is not None:
        conditions.append(AuditLog.occurred_at >= since)
    if until is not None:
        conditions.append(AuditLog.occurred_at <= until)

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    rows = await session.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


# ── 总览用的活动曲线 ────────────────────────────────────────

# 可选时间窗：步长决定分桶粒度，跨度决定桶数量
RANGE_SPECS: dict[str, tuple[str, int]] = {
    "24h": ("hour", 24),
    "7d": ("day", 7),
    "30d": ("day", 30),
}


@dataclass(slots=True)
class Activity:
    """一段时间内的操作活跃度，供总览页趋势图与统计条使用。"""

    range: str
    labels: list[str]
    totals: list[float]
    failures: list[float]
    total: int
    failure_total: int
    operators: int


def _bucket_start(moment: datetime, step: str) -> datetime:
    if step == "hour":
        return moment.replace(minute=0, second=0, microsecond=0)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


async def activity(session: AsyncSession, range_key: str = "7d") -> Activity:
    """按时间窗把审计记录聚合成折线数据。

    分桶在 Python 侧做而不是 ``date_trunc``：``occurred_at`` 是 timestamptz，
    SQL 里按天截断会先落到库的会话时区（UTC），东八区用户看到的「今天」会整体
    偏 8 小时。审计的窗口量级是「一个控制台几天内的操作」，拉两列在内存里聚合
    完全够用；真到百万级再换成带固定偏移的 SQL 聚合。

    没有操作的时间桶补 0——缺口本身也是信息，曲线不能跳过空档。
    """
    step, count = RANGE_SPECS.get(range_key, RANGE_SPECS["7d"])
    now = datetime.now().astimezone()
    this_bucket = _bucket_start(now, step)
    unit = timedelta(hours=1) if step == "hour" else timedelta(days=1)
    starts = [this_bucket - unit * (count - 1 - i) for i in range(count)]

    rows = await session.execute(
        select(AuditLog.occurred_at, AuditLog.result, AuditLog.operator).where(
            AuditLog.occurred_at >= starts[0]
        )
    )

    totals = [0] * count
    failures = [0] * count
    operators: set[str] = set()
    total = 0
    failure_total = 0
    for occurred_at, result, operator in rows:
        moment = occurred_at.astimezone()
        index = int((moment - starts[0]) / unit)
        if not 0 <= index < count:
            continue
        totals[index] += 1
        total += 1
        operators.add(operator)
        if result is AuditResult.failure:
            failures[index] += 1
            failure_total += 1

    fmt = "%H:%M" if step == "hour" else "%m-%d"
    return Activity(
        range=range_key if range_key in RANGE_SPECS else "7d",
        labels=[start.strftime(fmt) for start in starts],
        totals=[float(v) for v in totals],
        failures=[float(v) for v in failures],
        total=total,
        failure_total=failure_total,
        operators=len(operators),
    )


async def recent(session: AsyncSession, limit: int = 5) -> list[AuditLog]:
    """最近几条操作，总览页的「实时事件」直接用它，不再从当前状态臆造事件。"""
    rows = await session.scalars(
        select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit)
    )
    return list(rows)


def _as_uuid(value: UUID | str | None) -> UUID | None:
    """允许传字符串 ID（路由参数常常是 str），非法值当没传。"""
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if len(value) > limit else value


def _request_id(request: Request | None) -> str | None:
    """优先取中间件写进 contextvar 的值（后台任务里请求对象可能是空的）。"""
    current = request_id_ctx.get()
    if current and current != "N/A":
        return current
    if request is not None:
        return request.headers.get("X-Request-ID")
    return None


def _client_ip(request: Request | None) -> str | None:
    """取真实客户端 IP：有反向代理时以 X-Forwarded-For 的第一段为准。"""
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:45]
    return request.client.host if request.client else None


def _user_agent(request: Request | None) -> str | None:
    return request.headers.get("User-Agent") if request is not None else None
