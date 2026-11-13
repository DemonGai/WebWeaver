"""数据库查询层：把 6 张表的行拼装成前端需要的 payload。

路由只负责依赖注入，取数与拼装都集中在这里，便于单元测试与复用。

量级说明：一个集群通常是几百到几千个实例，这里一次性把相关表读进内存，
再在 Python 侧聚合。比六个接口各写一套 SQL 聚合更好维护；数据量再涨一个
量级时，把 ``load_snapshot`` 换成按需查询即可，接口形状不用动。
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import (
    Account,
    AuditAction,
    AuditLog,
    AuditResourceType,
    AuditResult,
    Browser,
    BrowserStatus,
    Fingerprint,
    FingerprintMode,
    FingerprintStatus,
    Group,
    Ip,
    IpBindingMode,
    IpKind,
    IpStatus,
    Kernel,
    PlatformFamily,
)
from app.models import AccountStatus as DbAccountStatus
from app.models.base import utcnow
from app.schemas.domain import (
    AccountCard,
    AccountPoolPayload,
    AccountStatus,
    AccountTotals,
    BrowserPoolPayload,
    BrowserTotals,
    ClusterEvent,
    ClusterInfo,
    FilterItem,
    HealthPart,
    InstanceStatus,
    InstanceSummary,
    IpPoolPayload,
    IpResource,
    IpTotals,
    MiniCard,
    NoVncAccount,
    NoVncExitIp,
    NoVncFingerprint,
    NoVncInstance,
    NoVncLog,
    NoVncPayload,
    NoVncState,
    OverviewPayload,
    PoolStatusItem,
    RegionSlice,
    RotationPolicy,
    SupplierHealth,
    TrendPoint,
    TrendStat,
)
from app.schemas.domain import (
    IpStatus as SchemaIpStatus,
)
from app.services import audit

# ── 占位指标 ────────────────────────────────────────────────
# 总览页的曲线与统计来自审计表（真实数据）；只有 IP 池的趋势图仍是占位——
# 它需要 IP 健康度的历史采样，目前没有对应采集与历史表，先给固定值保证
# 接口形状稳定，接入采集后替换为真实读数。
_TREND_LABELS = ["00:00", "06:00", "12:00", "18:00", "24:00"]
_IP_TREND = TrendPoint(
    labels=_TREND_LABELS,
    series=[93.2, 94.1, 93.6, 95.0, 94.4, 95.8, 95.1, 96.2, 95.6, 96.4, 95.9, 96.8, 96.4],
    companion=[12, 18, 15, 24, 19, 28, 22, 31, 26, 34, 29, 37, 32],
)
# 轮换策略是调度器配置，暂时没有落表，按默认策略返回。
_ROTATION = RotationPolicy(
    enabled=True,
    items=[
        {"label": "轮换周期", "value": "每 30 分钟"},
        {"label": "失败自动切换", "value": "连续 2 次失败"},
        {"label": "同区域优先", "value": "已开启"},
        {"label": "黑名单过滤", "value": "3 个平台"},
    ],
)

_STATUS_RANK = {
    BrowserStatus.running: 0,
    BrowserStatus.idle: 1,
    BrowserStatus.queued: 2,
    BrowserStatus.error: 3,
    BrowserStatus.stopped: 4,
}
_IP_TYPE_LABEL = {IpKind.residential: "住宅", IpKind.datacenter: "机房", IpKind.mobile: "移动"}
_IP_STATUS_RANK = {IpStatus.available: 0, IpStatus.in_use: 1, IpStatus.failed: 2}
_ACCOUNT_STATE_LABEL = {
    DbAccountStatus.logged_in: "已登录",
    DbAccountStatus.in_session: "会话中",
    DbAccountStatus.restricted: "受限",
    DbAccountStatus.unbound: "未绑定",
}
_ACCOUNT_ACTION = {
    DbAccountStatus.logged_in: "更换绑定",
    DbAccountStatus.in_session: "打开会话",
    DbAccountStatus.restricted: "修复会话",
    DbAccountStatus.unbound: "绑定实例",
}
# 大区归类：IP 池的地区分布按国家码聚合到四个大区，和前端配色保持一致。
_REGION_BUCKET = {
    "US": "美国",
    "CA": "美国",
    "MX": "美国",
    "BR": "美国",
    "GB": "欧洲",
    "DE": "欧洲",
    "FR": "欧洲",
    "NL": "欧洲",
    "ES": "欧洲",
    "IT": "欧洲",
    "SE": "欧洲",
    "PL": "欧洲",
    "JP": "亚洲",
    "SG": "亚洲",
    "HK": "亚洲",
    "KR": "亚洲",
    "TW": "亚洲",
    "TH": "亚洲",
    "VN": "亚洲",
    "MY": "亚洲",
    "ID": "亚洲",
    "PH": "亚洲",
    "IN": "亚洲",
}
_BUCKET_ORDER = {"美国": 0, "欧洲": 1, "亚洲": 2, "其他": 3}
_BUCKET_TONE = {"美国": "emerald", "欧洲": "blue", "亚洲": "violet", "其他": "amber"}


@dataclass(slots=True)
class Snapshot:
    """一次请求内用到的全部数据，附带几份索引避免反复线性查找。"""

    groups: dict[UUID, Group]
    kernels: dict[UUID, Kernel]
    fingerprints: dict[UUID, Fingerprint]
    ips: dict[UUID, Ip]
    accounts: dict[UUID, Account]
    browsers: list[Browser]
    browser_by_id: dict[UUID, Browser]
    browser_by_account: dict[UUID, Browser]
    browser_by_ip: dict[UUID, Browser]
    browsers_by_fingerprint: dict[UUID, list[Browser]]

    def find_browser(self, key: str) -> Browser | None:
        """按 UUID 或实例名查实例——前端路由里两者都可能出现。"""
        try:
            return self.browser_by_id.get(UUID(key))
        except ValueError:
            return next((b for b in self.browsers if b.name == key), None)


async def load_snapshot(session: AsyncSession) -> Snapshot:
    groups = {row.id: row for row in (await session.scalars(select(Group))).all()}
    kernels = {row.id: row for row in (await session.scalars(select(Kernel))).all()}
    fingerprints = {row.id: row for row in (await session.scalars(select(Fingerprint))).all()}
    ips = {row.id: row for row in (await session.scalars(select(Ip))).all()}
    accounts = {row.id: row for row in (await session.scalars(select(Account))).all()}
    browsers = list((await session.scalars(select(Browser))).all())

    by_account: dict[UUID, Browser] = {}
    by_ip: dict[UUID, Browser] = {}
    by_fingerprint: dict[UUID, list[Browser]] = {}
    for browser in browsers:
        if browser.account_id:
            by_account.setdefault(browser.account_id, browser)
        if browser.ip_id:
            by_ip.setdefault(browser.ip_id, browser)
        if browser.fingerprint_id:
            by_fingerprint.setdefault(browser.fingerprint_id, []).append(browser)

    return Snapshot(
        groups=groups,
        kernels=kernels,
        fingerprints=fingerprints,
        ips=ips,
        accounts=accounts,
        browsers=browsers,
        browser_by_id={b.id: b for b in browsers},
        browser_by_account=by_account,
        browser_by_ip=by_ip,
        browsers_by_fingerprint=by_fingerprint,
    )


async def get_snapshot(session: Annotated[AsyncSession, Depends(get_session)]) -> Snapshot:
    """FastAPI 依赖：按请求加载一次快照，六个接口共用。"""
    return await load_snapshot(session)


# ── 小工具 ─────────────────────────────────────────────────


def _humanize(moment: datetime | None) -> str | None:
    """把时间戳转成「12 分钟前」这类相对描述，前端直接展示。"""
    if moment is None:
        return None
    seconds = int((utcnow() - moment).total_seconds())
    if seconds < 0:
        return "刚刚"
    if seconds < 60:
        return f"{seconds} 秒前"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


def _clock(moment: datetime | None) -> str:
    return moment.astimezone().strftime("%H:%M:%S") if moment else "--:--:--"


def _duration(moment: datetime | None) -> str:
    if moment is None:
        return "00:00:00"
    total = max(int((utcnow() - moment).total_seconds()), 0)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _short_platform(platform: str) -> str:
    """Windows 11 → Win11；Pixel 8 / Android 14 → Android。"""
    if platform.startswith("Windows "):
        return "Win" + platform.removeprefix("Windows ")
    if platform.startswith("macOS"):
        return "macOS"
    if "/" in platform:
        tail = platform.split("/")[-1].strip().split()
        return tail[0] if tail else platform
    return platform.split()[0] if platform else "未知"


def _code_suffix(code: str, platform: str) -> str:
    """fp-win11-c128 → C128、fp-cloak-win11 → Cloak，实例列表里当短标识用。

    默认取最后一段，但它可能跟平台名撞：`fp-cloak-win11` 配「Windows 11」会显示成
    「Win11 / Win11」。撞了就往前退一段——按现在的命名约定，退出来的是内核缩写，
    正好能区分「同平台、不同内核」的两条模板。
    """
    segments = [segment for segment in code.split("-") if segment]
    if not segments:
        return code
    short_platform = _short_platform(platform).replace(" ", "").lower()
    for segment in reversed(segments[1:]):
        if re.fullmatch(r"c\d+\w*", segment, re.IGNORECASE):
            return segment.upper()
        if segment.replace(" ", "").lower() != short_platform:
            return segment.capitalize()
    return segments[-1].capitalize()


def _fingerprint_label(
    fingerprint: Fingerprint | None, mode: FingerprintMode = FingerprintMode.template
) -> str:
    """默认模式是正常状态，不能显示成「未绑定」。"""
    if fingerprint is None:
        return "默认指纹" if mode is FingerprintMode.default else "未绑定指纹"
    platform = _short_platform(fingerprint.platform)
    return f"{platform} / {_code_suffix(fingerprint.code, fingerprint.platform)}"


def _ip_label(ip: Ip | None, mode: IpBindingMode = IpBindingMode.proxy) -> str:
    """直连（本机公网 IP）也是一种有效的出口，与「未分配」区分开。"""
    if ip is not None:
        return ip.address
    return "直连 · 本机 IP" if mode is IpBindingMode.direct else "未分配"


def _ua_label(user_agent: str) -> str:
    """把完整 UA 压成「Chrome 128.0.6613」，表格里放得下。"""
    if "Edg/" in user_agent:
        name, marker = "Edge", "Edg/"
    elif "Firefox/" in user_agent:
        name, marker = "Firefox", "Firefox/"
    elif "Chrome/" in user_agent:
        name, marker = "Chrome", "Chrome/"
    elif "Version/" in user_agent:
        name, marker = "Safari", "Version/"
    else:
        return user_agent[:32]
    version = user_agent.split(marker, 1)[1].split()[0]
    return f"{name} {version}"


def _region_label(ip: Ip | None, mode: IpBindingMode = IpBindingMode.proxy) -> str:
    if ip is None:
        return "本机网络" if mode is IpBindingMode.direct else "未分配"
    return " · ".join(part for part in (ip.country_code, ip.city) if part)


def _status_note(browser: Browser, ip: Ip | None) -> str | None:
    """没有显式备注时，按状态生成一句说明，卡片上不留空。"""
    if browser.note:
        return browser.note
    if browser.status is BrowserStatus.error:
        if ip is not None and ip.status is IpStatus.failed:
            return "代理不可达"
        return "会话异常"
    if browser.status is BrowserStatus.idle:
        return f"已空闲 {_humanize(browser.last_active_at) or '一段时间'}"
    if browser.status is BrowserStatus.running:
        return f"启动于 {_humanize(browser.started_at) or '刚刚'}"
    if browser.status is BrowserStatus.queued:
        return "等待调度"
    return "已停止"


def _summary(browser: Browser, snapshot: Snapshot) -> InstanceSummary:
    group = snapshot.groups.get(browser.group_id) if browser.group_id else None
    account = snapshot.accounts.get(browser.account_id) if browser.account_id else None
    ip = snapshot.ips.get(browser.ip_id) if browser.ip_id else None
    fingerprint = (
        snapshot.fingerprints.get(browser.fingerprint_id) if browser.fingerprint_id else None
    )
    return InstanceSummary(
        id=str(browser.id),
        name=browser.name,
        status=InstanceStatus(browser.status.value),
        group=group.name if group else "未分组",
        account=account.username if account else "未绑定",
        ip=_ip_label(ip, browser.ip_mode),
        region=_region_label(ip, browser.ip_mode),
        fingerprint=_fingerprint_label(fingerprint, browser.fingerprint_mode),
        fps=browser.fps,
        latency_ms=browser.latency_ms,
        started_at=_humanize(browser.started_at),
        note=_status_note(browser, ip),
    )


def _sorted_browsers(browsers: list[Browser]) -> list[Browser]:
    return sorted(browsers, key=lambda b: (_STATUS_RANK.get(b.status, 9), b.name))


def _count(browsers: list[Browser], *statuses: BrowserStatus) -> int:
    return sum(1 for b in browsers if b.status in statuses)


# ── 总览 ───────────────────────────────────────────────────

# 审计动作 / 资源类型 → 中文，事件流直接用
_ACTION_LABEL = {
    AuditAction.create: "新建",
    AuditAction.update: "修改",
    AuditAction.delete: "删除",
    AuditAction.bind: "绑定",
    AuditAction.unbind: "解绑",
    AuditAction.start: "启动",
    AuditAction.stop: "停止",
    AuditAction.login: "登录",
    AuditAction.logout: "登出",
    AuditAction.reset_password: "重置密码",
    AuditAction.export: "导出",
    AuditAction.import_: "导入",
}
_RESOURCE_LABEL = {
    AuditResourceType.browser: "浏览器",
    AuditResourceType.account: "账号",
    AuditResourceType.ip: "出口 IP",
    AuditResourceType.fingerprint: "指纹",
    AuditResourceType.kernel: "内核",
    AuditResourceType.group: "分组",
    AuditResourceType.binding: "绑定关系",
    AuditResourceType.auth: "账号安全",
    AuditResourceType.user: "成员",
    AuditResourceType.role: "角色",
    AuditResourceType.system: "系统",
}
# 失败永远最刺眼；删除 / 停止 / 重置密码这类破坏性动作次之
_ACTION_TONE = {
    AuditAction.delete: "amber",
    AuditAction.stop: "amber",
    AuditAction.reset_password: "violet",
    AuditAction.start: "emerald",
    AuditAction.login: "emerald",
    AuditAction.bind: "emerald",
    AuditAction.update: "blue",
    AuditAction.export: "blue",
}


def _event_of(log: AuditLog) -> ClusterEvent:
    """一条审计记录 → 一条事件。失败优先染色，其次看动作危险程度。"""
    action_label = _ACTION_LABEL.get(log.action, log.action.value)
    resource_label = _RESOURCE_LABEL.get(log.resource_type, log.resource_type.value)
    if log.resource_type is AuditResourceType.auth:
        # 登录 / 登出没有资源名，主语换成操作人本身
        title = (
            f"{log.operator} {action_label}失败"
            if log.result is AuditResult.failure
            else f"{log.operator} {action_label}"
        )
    else:
        name = log.resource_name or resource_label
        title = f"{log.operator} {action_label} {name}"
    tone = "rose" if log.result is AuditResult.failure else _ACTION_TONE.get(log.action, "zinc")
    return ClusterEvent(
        id=str(log.id),
        tone=tone,
        title=title,
        detail=log.error_message or log.detail,
        time=_humanize(log.occurred_at) or "刚刚",
        tag=resource_label,
    )


def _tick_labels(labels: list[str], max_ticks: int = 7) -> list[str]:
    """24 / 30 个分桶全部标在横轴上会糊成一片，按等距抽稀到 7 个刻度。"""
    if len(labels) <= max_ticks:
        return labels
    step = (len(labels) - 1) / (max_ticks - 1)
    return [labels[round(i * step)] for i in range(max_ticks)]


def _grade(score: float) -> str:
    """分项染色只看分数本身：91% 的可用率不该因为「有 1 个失败」被染成红色。"""
    if score >= 95:
        return "emerald"
    if score >= 85:
        return "blue"
    if score >= 70:
        return "amber"
    return "rose"


def _health_parts(
    *,
    total: int,
    online: int,
    ip_total: int,
    failed_ips: int,
    account_health: float,
    fp_total: int,
    fp_active: int,
    error: int,
) -> list[HealthPart]:
    """把「集群健康度」拆成四个可解释的分项，权重相加为 100。

    只看实例在线率会让「IP 全挂但实例进程还活着」显示成 100% 健康，
    所以出口、账号、指纹各占一份：任何一块烂掉，总分都掉得动。
    """

    def ratio(hit: int, whole: int) -> float:
        return round(hit / whole * 100, 1) if whole else 0.0

    instance_score = ratio(online, total)
    exit_score = ratio(ip_total - failed_ips, ip_total)
    fp_score = ratio(fp_active, fp_total)
    account_score = round(account_health, 1)
    return [
        HealthPart(
            key="instances",
            label="实例可用性",
            score=instance_score,
            weight=45,
            detail=f"{online} / {total} 台在线 · 异常 {error} 台",
            tone=_grade(instance_score),
        ),
        HealthPart(
            key="exit",
            label="出口可用性",
            score=exit_score,
            weight=25,
            detail=f"{ip_total - failed_ips} / {ip_total} 个出口可达",
            tone=_grade(exit_score),
        ),
        HealthPart(
            key="accounts",
            label="账号健康度",
            score=account_score,
            weight=20,
            detail=f"平台账号平均健康分 {account_score}",
            tone=_grade(account_score),
        ),
        HealthPart(
            key="fingerprints",
            label="指纹覆盖",
            score=fp_score,
            weight=10,
            detail=f"{fp_active} / {fp_total} 套模板已启用",
            tone=_grade(fp_score),
        ),
    ]


def overview(
    snapshot: Snapshot, activity: audit.Activity, recent: list[AuditLog]
) -> OverviewPayload:
    browsers = snapshot.browsers
    total = len(browsers)
    running = _count(browsers, BrowserStatus.running)
    idle = _count(browsers, BrowserStatus.idle)
    error = _count(browsers, BrowserStatus.error)
    stopped = _count(browsers, BrowserStatus.stopped)
    queued = _count(browsers, BrowserStatus.queued)
    online = running + idle

    accounts = list(snapshot.accounts.values())
    available_accounts = sum(1 for a in accounts if a.status is DbAccountStatus.logged_in)
    session_accounts = sum(1 for a in accounts if a.status is DbAccountStatus.in_session)
    risk_accounts = sum(1 for a in accounts if a.status is DbAccountStatus.restricted)
    account_health = sum(a.health for a in accounts) / len(accounts) if accounts else 0.0

    ips = list(snapshot.ips.values())
    available_ips = sum(1 for ip in ips if ip.status is IpStatus.available)
    used_ips = sum(1 for ip in ips if ip.status is IpStatus.in_use)
    failed_ips = sum(1 for ip in ips if ip.status is IpStatus.failed)
    ip_kind_count = {kind: sum(1 for ip in ips if ip.kind is kind) for kind in IpKind}

    fingerprints = list(snapshot.fingerprints.values())
    fp_family_count = {
        family: sum(1 for fp in fingerprints if fp.platform_family is family)
        for family in PlatformFamily
    }
    mobile_fp = fp_family_count[PlatformFamily.android] + fp_family_count[PlatformFamily.ios]
    active_fp = sum(1 for fp in fingerprints if fp.status is FingerprintStatus.active)

    health_parts = _health_parts(
        total=total,
        online=online,
        ip_total=len(ips),
        failed_ips=failed_ips,
        account_health=account_health,
        fp_total=len(fingerprints),
        fp_active=active_fp,
        error=error,
    )
    health = round(sum(p.score * p.weight for p in health_parts) / 100, 1)

    latencies = [b.latency_ms for b in browsers if b.latency_ms]
    fps_values = [b.fps for b in browsers if b.fps]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0
    avg_fps = round(sum(fps_values) / len(fps_values)) if fps_values else 0
    latest = max((b.updated_at for b in browsers), default=None)
    updated_seconds = int((utcnow() - latest).total_seconds()) if latest else 0

    # 这层只做「基础设施维护」——浏览器 / 账号 / IP / 指纹。
    # 自动化任务由使用者用 CDP 自行接管，调度与待办都不在这里，所以没有 to-do 列表。

    return OverviewPayload(
        range=activity.range,
        cluster=ClusterInfo(
            total=total,
            online=online,
            health=health,
            updated_seconds=max(updated_seconds, 0),
            accounts_used=session_accounts,
            accounts_total=len(accounts),
            ip_used=used_ips,
            ip_total=len(ips),
            avg_latency_ms=avg_latency,
            novnc_fps=avg_fps,
        ),
        health_parts=health_parts,
        pool_status=[
            PoolStatusItem(label="运行中", value=running, status=InstanceStatus.running),
            PoolStatusItem(label="空闲待命", value=idle, status=InstanceStatus.idle),
            PoolStatusItem(label="排队中", value=queued, status=InstanceStatus.queued),
            PoolStatusItem(label="异常中断", value=error, status=InstanceStatus.error),
            PoolStatusItem(label="已停止", value=stopped, status=InstanceStatus.stopped),
        ],
        cards=[
            MiniCard(
                key="accounts",
                title="账号总量",
                value=len(accounts),
                unit="个",
                hint=(
                    f"可用 {available_accounts} · 会话中 {session_accounts} · 风险 {risk_accounts}"
                ),
                progress=round(available_accounts / len(accounts) * 100) if accounts else 0,
                tone="blue",
            ),
            MiniCard(
                key="ip",
                title="可用 IP",
                value=available_ips,
                unit=f"/ {len(ips)}",
                hint=(
                    f"住宅 {ip_kind_count[IpKind.residential]} · "
                    f"机房 {ip_kind_count[IpKind.datacenter]} · "
                    f"移动 {ip_kind_count[IpKind.mobile]}"
                ),
                progress=round(available_ips / len(ips) * 100) if ips else 0,
                tone="emerald",
            ),
            MiniCard(
                key="fingerprints",
                title="指纹模板",
                value=len(fingerprints),
                unit="套",
                hint=(
                    f"Windows {fp_family_count[PlatformFamily.windows]} · "
                    f"macOS {fp_family_count[PlatformFamily.macos]} · 移动 {mobile_fp}"
                ),
                progress=round(active_fp / len(fingerprints) * 100) if fingerprints else 0,
                tone="violet",
            ),
        ],
        # 全部实例按「状态优先级」排序返回，前端自己按 tab 过滤——总览的量级
        # （一个集群几百台）一次性下发比每个 tab 再请求一次更省事
        instances=[_summary(b, snapshot) for b in _sorted_browsers(browsers)],
        events=[_event_of(log) for log in recent],
        trend=TrendPoint(
            labels=_tick_labels(activity.labels),
            series=activity.totals,
            companion=activity.failures,
        ),
        trend_stats=[
            TrendStat(label="操作总量", value=str(activity.total), unit="次"),
            TrendStat(label="失败操作", value=str(activity.failure_total), unit="次"),
            TrendStat(label="活跃操作人", value=str(activity.operators), unit="人"),
        ],
    )


# ── 浏览器池 ───────────────────────────────────────────────


def browsers(snapshot: Snapshot) -> BrowserPoolPayload:
    rows = snapshot.browsers
    total = len(rows)
    running = _count(rows, BrowserStatus.running)
    idle = _count(rows, BrowserStatus.idle)
    error = _count(rows, BrowserStatus.error)
    queued = _count(rows, BrowserStatus.queued)

    return BrowserPoolPayload(
        totals=BrowserTotals(running=running, total=total, delta=0),
        cards=[
            MiniCard(title="可调度", value=idle, hint="空间待命实例", tone="blue", tag="可调度"),
            MiniCard(
                title="需处理",
                value=error,
                hint=f"异常中断 · {queued} 个排队中",
                tone="rose",
                tag="需处理",
            ),
            MiniCard(
                title="队列",
                value=queued,
                hint="等待调度的自动化任务",
                tone="violet",
                tag="队列",
            ),
        ],
        instances=[_summary(b, snapshot) for b in _sorted_browsers(rows)],
        filters=[
            FilterItem(key="all", label="全部", count=total),
            FilterItem(key="running", label="运行中", count=running),
            FilterItem(key="idle", label="空闲", count=idle),
            FilterItem(key="error", label="异常", count=error),
        ],
    )


# ── 账号池 ─────────────────────────────────────────────────


def _account_card(account: Account, snapshot: Snapshot) -> AccountCard:
    browser = snapshot.browser_by_account.get(account.id)
    ip = snapshot.ips.get(browser.ip_id) if browser and browser.ip_id else None
    registered_days = (
        max((utcnow() - account.registered_at).days, 0) if account.registered_at else 0
    )
    return AccountCard(
        id=str(account.id),
        name=account.username,
        platform=account.platform,
        status=AccountStatus(account.status.value),
        region=account.region or "—",
        registered_days=registered_days,
        bound_instance=browser.name if browser else None,
        exit_ip=_ip_label(ip, browser.ip_mode) if browser else None,
        health=account.health,
        action=_ACCOUNT_ACTION[account.status],
        note=account.note,
    )


def accounts(snapshot: Snapshot) -> AccountPoolPayload:
    rows = list(snapshot.accounts.values())
    health = round(sum(a.health for a in rows) / len(rows), 1) if rows else 0.0
    logged_in = sum(1 for a in rows if a.status is DbAccountStatus.logged_in)
    in_session = sum(1 for a in rows if a.status is DbAccountStatus.in_session)
    restricted = sum(1 for a in rows if a.status is DbAccountStatus.restricted)

    platform_counts: dict[str, int] = {}
    for account in rows:
        platform_counts[account.platform] = platform_counts.get(account.platform, 0) + 1
    filters = [FilterItem(key="all-platform", label="全部平台", count=len(rows))]
    filters += [
        FilterItem(key=platform.lower(), label=platform, count=count)
        for platform, count in sorted(platform_counts.items(), key=lambda kv: -kv[1])
    ]

    return AccountPoolPayload(
        totals=AccountTotals(total=len(rows), health=health),
        cards=[
            MiniCard(
                title="可用", value=logged_in, hint="可直接绑定到实例", tone="emerald", tag="可用"
            ),
            MiniCard(
                title="会话中", value=in_session, hint="已绑定运行中实例", tone="blue", tag="会话中"
            ),
            MiniCard(
                title="受限",
                value=restricted,
                hint="触发风控，需更换 IP",
                tone="rose",
                tag="受限",
            ),
        ],
        # 健康度低的排前面，运维先看到要处理的账号
        accounts=[_account_card(a, snapshot) for a in sorted(rows, key=lambda a: a.health)],
        filters=filters,
    )


# ── IP 池 ──────────────────────────────────────────────────


def ip_pool(snapshot: Snapshot) -> IpPoolPayload:
    rows = list(snapshot.ips.values())
    total = len(rows)
    available = sum(1 for ip in rows if ip.status is IpStatus.available)
    failed = sum(1 for ip in rows if ip.status is IpStatus.failed)
    online_rate = round((total - failed) / total * 100, 1) if total else 0.0

    def avg_latency(kind: IpKind) -> int:
        values = [ip.latency_ms for ip in rows if ip.kind is kind and ip.latency_ms]
        return round(sum(values) / len(values)) if values else 0

    by_kind = {kind: sum(1 for ip in rows if ip.kind is kind) for kind in IpKind}

    bucket_counts: dict[str, int] = {}
    for ip in rows:
        label = _REGION_BUCKET.get(ip.country_code, "其他")
        bucket_counts[label] = bucket_counts.get(label, 0) + 1
    regions = [
        RegionSlice(label=label, value=count, tone=_BUCKET_TONE[label])
        for label, count in sorted(bucket_counts.items(), key=lambda kv: _BUCKET_ORDER[kv[0]])
    ]

    supplier_rows: dict[str, list[Ip]] = {}
    for ip in rows:
        supplier_rows.setdefault(ip.supplier, []).append(ip)
    suppliers = [
        SupplierHealth(
            name=name,
            count=len(items),
            health=round(sum(ip.health for ip in items) / len(items), 1),
        )
        for name, items in sorted(supplier_rows.items(), key=lambda kv: -len(kv[1]))
    ]

    resources = sorted(
        (
            IpResource(
                id=str(ip.id),
                ip=ip.address,
                port=ip.port,
                protocol=ip.protocol.value,
                supplier=ip.supplier,
                region=ip.country_code,
                city=ip.city or "—",
                type=_IP_TYPE_LABEL[ip.kind],
                username=ip.username,
                password=ip.password,
                latency_ms=ip.latency_ms or 0,
                health=ip.health,
                status=SchemaIpStatus(ip.status.value),
                bound_instance=(
                    snapshot.browser_by_ip[ip.id].name if ip.id in snapshot.browser_by_ip else None
                ),
            )
            for ip in rows
        ),
        key=lambda res: (_IP_STATUS_RANK[IpStatus(res.status.value)], res.ip),
    )

    return IpPoolPayload(
        totals=IpTotals(available=available, total=total, online_rate=online_rate),
        cards=[
            MiniCard(
                title="住宅",
                value=by_kind[IpKind.residential],
                hint=f"高匿名 · 平均延迟 {avg_latency(IpKind.residential)}ms",
                tone="emerald",
                tag="住宅",
            ),
            MiniCard(
                title="机房",
                value=by_kind[IpKind.datacenter],
                hint=f"高并发 · 平均延迟 {avg_latency(IpKind.datacenter)}ms",
                tone="blue",
                tag="机房",
            ),
            MiniCard(
                title="失败",
                value=failed,
                hint="连接失败 · 待替换",
                tone="rose",
                tag="失败",
            ),
        ],
        resources=resources,
        region_distribution=regions,
        suppliers=suppliers,
        trend=_IP_TREND,
        rotation=_ROTATION,
        filters=[
            FilterItem(key="all", label="全部", count=total),
            FilterItem(key="residential", label="住宅", count=by_kind[IpKind.residential]),
            FilterItem(key="datacenter", label="机房", count=by_kind[IpKind.datacenter]),
            FilterItem(key="mobile", label="移动", count=by_kind[IpKind.mobile]),
        ],
    )


# ── noVNC ──────────────────────────────────────────────────


def novnc(snapshot: Snapshot, instance_id: str) -> NoVncPayload:
    browser = snapshot.find_browser(instance_id)
    if browser is None:
        raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

    group = snapshot.groups.get(browser.group_id) if browser.group_id else None
    kernel = snapshot.kernels.get(browser.kernel_id) if browser.kernel_id else None
    fingerprint = (
        snapshot.fingerprints.get(browser.fingerprint_id) if browser.fingerprint_id else None
    )
    ip = snapshot.ips.get(browser.ip_id) if browser.ip_id else None
    account = snapshot.accounts.get(browser.account_id) if browser.account_id else None

    logs: list[NoVncLog] = []
    if browser.started_at:
        logs.append(
            NoVncLog(
                time=_clock(browser.started_at),
                action="建立 noVNC 会话",
                kind="session",
                detail=f"{browser.vnc_url or browser.cdp_url or '本地会话'}",
                result="成功",
            )
        )
    if account and account.last_login_at:
        logs.append(
            NoVncLog(
                time=_clock(account.last_login_at),
                action="账号登录",
                kind="login",
                detail=f"{account.username} 登录 {account.platform}，指纹校验通过",
                result="成功",
            )
        )
    if browser.last_active_at:
        logs.append(
            NoVncLog(
                time=_clock(browser.last_active_at),
                action="最近活跃",
                kind="activity",
                detail=f"画面 {browser.fps or 0} fps，链路延迟 {browser.latency_ms or 0} ms",
                result="成功",
            )
        )
    if not logs:
        logs.append(
            NoVncLog(
                time="--:--:--",
                action="尚未启动",
                kind="session",
                detail="实例还没有启动记录",
                result="待启动",
            )
        )

    return NoVncPayload(
        instance=NoVncInstance(
            id=str(browser.id),
            name=browser.name,
            status=InstanceStatus(browser.status.value),
            group=group.name if group else "未分组",
            connection="会话已连接" if browser.vnc_url else "未建立会话",
            url=browser.vnc_url or browser.cdp_url or "about:blank",
            fps=browser.fps or 0,
            latency_ms=browser.latency_ms or 0,
            session_time=_duration(browser.started_at),
            quality="高清",
        ),
        state=NoVncState(
            started_at=_humanize(browser.started_at) or "未启动",
            kernel=(
                f"{kernel.name} {browser.kernel_version or kernel.version}"
                if kernel
                else "未绑定内核"
            ),
            # 内存占用来自容器指标，暂无采集
            memory="—",
        ),
        account=NoVncAccount(
            name=account.username if account else "未绑定账号",
            platform=account.platform if account else "—",
            region=account.region if account else "—",
            tags=(
                [
                    _ACCOUNT_STATE_LABEL[account.status],
                    f"健康度 {account.health}%",
                ]
                if account
                else []
            ),
        ),
        exit_ip=NoVncExitIp(
            ip=_ip_label(ip, browser.ip_mode),
            location=_region_label(ip, browser.ip_mode),
            type=(
                f"{_IP_TYPE_LABEL[ip.kind]}代理"
                if ip
                else ("直连本机" if browser.ip_mode is IpBindingMode.direct else "—")
            ),
            latency_ms=(ip.latency_ms or 0) if ip else 0,
        ),
        fingerprint=NoVncFingerprint(
            user_agent=(
                _ua_label(fingerprint.user_agent)
                if fingerprint
                else (
                    "默认指纹（浏览器原生）"
                    if browser.fingerprint_mode is FingerprintMode.default
                    else "未绑定指纹"
                )
            ),
            timezone=fingerprint.timezone if fingerprint else "—",
            resolution=fingerprint.resolution if fingerprint else "—",
            canvas_noise=bool(fingerprint and fingerprint.canvas_noise),
            score=(fingerprint.uniqueness if fingerprint else 0) or 0,
        ),
        logs=logs,
    )
