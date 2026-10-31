"""领域模型，与前端 src/types/domain.ts 一一对应。"""

from enum import StrEnum

from pydantic import BaseModel, Field


class InstanceStatus(StrEnum):
    running = "running"
    idle = "idle"
    error = "error"
    stopped = "stopped"
    queued = "queued"


class AccountStatus(StrEnum):
    logged_in = "logged_in"
    in_session = "in_session"
    restricted = "restricted"
    unbound = "unbound"


class IpStatus(StrEnum):
    available = "available"
    in_use = "in_use"
    failed = "failed"


class InstanceSummary(BaseModel):
    id: str
    name: str
    status: InstanceStatus
    group: str
    account: str
    ip: str
    region: str
    fingerprint: str
    fps: int | None = None
    latency_ms: int | None = None
    started_at: str | None = None
    note: str | None = None


class AccountCard(BaseModel):
    id: str
    name: str
    platform: str
    status: AccountStatus
    region: str
    registered_days: int
    bound_instance: str | None = None
    exit_ip: str | None = None
    health: int
    action: str
    note: str | None = None


class IpResource(BaseModel):
    id: str
    ip: str
    supplier: str
    region: str
    city: str
    type: str
    latency_ms: int
    status: IpStatus
    bound_instance: str | None = None


class ClusterEvent(BaseModel):
    id: str
    tone: str
    title: str
    detail: str | None = None
    time: str
    tag: str


class TrendPoint(BaseModel):
    labels: list[str]
    series: list[float]
    companion: list[float]


class MiniCard(BaseModel):
    title: str
    value: int
    unit: str = ""
    hint: str
    progress: int = 0
    tone: str
    tag: str = ""
    key: str = ""


class FilterItem(BaseModel):
    key: str
    label: str
    count: int


# ── 总览 ────────────────────────────────────────────────
class ClusterInfo(BaseModel):
    total: int
    online: int
    health: float
    updated_seconds: int
    accounts_used: int
    accounts_total: int
    ip_used: int
    ip_total: int
    avg_latency_ms: int
    novnc_fps: int


class HealthPart(BaseModel):
    """健康分的构成项：主指标（总分）+ 四个可解释的分项。"""

    key: str
    label: str
    score: float
    weight: int
    detail: str
    tone: str


class PoolStatusItem(BaseModel):
    label: str
    value: int
    status: InstanceStatus


class TrendStat(BaseModel):
    label: str
    value: str
    unit: str


class OverviewPayload(BaseModel):
    range: str
    cluster: ClusterInfo
    health_parts: list[HealthPart]
    pool_status: list[PoolStatusItem]
    cards: list[MiniCard]
    instances: list[InstanceSummary]
    events: list[ClusterEvent]
    trend: TrendPoint
    trend_stats: list[TrendStat]


# ── 浏览器池 ────────────────────────────────────────────
class BrowserTotals(BaseModel):
    running: int
    total: int
    delta: int


class BrowserPoolPayload(BaseModel):
    totals: BrowserTotals
    cards: list[MiniCard]
    instances: list[InstanceSummary]
    filters: list[FilterItem]


# ── 账号池 ──────────────────────────────────────────────
class AccountTotals(BaseModel):
    total: int
    health: float


class AccountPoolPayload(BaseModel):
    totals: AccountTotals
    cards: list[MiniCard]
    accounts: list[AccountCard]
    filters: list[FilterItem]


# ── IP 池 ──────────────────────────────────────────────
class IpTotals(BaseModel):
    available: int
    total: int
    online_rate: float


class RegionSlice(BaseModel):
    label: str
    value: int
    unit: str = "个"
    tone: str


class SupplierHealth(BaseModel):
    name: str
    count: int
    health: float


class RotationPolicy(BaseModel):
    enabled: bool
    items: list[dict[str, str]]


class IpPoolPayload(BaseModel):
    totals: IpTotals
    cards: list[MiniCard]
    resources: list[IpResource]
    region_distribution: list[RegionSlice]
    suppliers: list[SupplierHealth]
    trend: TrendPoint
    rotation: RotationPolicy
    filters: list[FilterItem]


# ── noVNC ─────────────────────────────────────────────
class NoVncInstance(BaseModel):
    id: str
    name: str
    status: InstanceStatus
    group: str
    connection: str
    url: str
    fps: int
    latency_ms: int
    session_time: str
    quality: str


class NoVncState(BaseModel):
    started_at: str
    kernel: str
    memory: str


class NoVncAccount(BaseModel):
    name: str
    platform: str
    region: str
    tags: list[str]


class NoVncExitIp(BaseModel):
    ip: str
    location: str
    type: str
    latency_ms: int


class NoVncFingerprint(BaseModel):
    user_agent: str
    timezone: str
    resolution: str
    canvas_noise: bool
    score: int


class NoVncLog(BaseModel):
    time: str
    action: str
    kind: str
    detail: str
    result: str


class NoVncPayload(BaseModel):
    instance: NoVncInstance
    state: NoVncState
    account: NoVncAccount
    exit_ip: NoVncExitIp
    fingerprint: NoVncFingerprint
    logs: list[NoVncLog] = Field(default_factory=list)


# ── 指纹库 ─────────────────────────────────────────────
class FingerprintTemplate(BaseModel):
    """一条指纹模板；列表视图逐行比对 UA / 时区 / 分辨率 / 伪装项。"""

    id: str
    name: str
    fp_id: str
    # 用于前端挑平台图标：windows / macos / mobile
    platform_family: str
    platform: str
    ua: str
    timezone: str
    language: str
    resolution: str
    dpr: str
    disguises: list[str] = Field(default_factory=list)
    # 唯一性得分；为 None 时前端显示 "—"（例如插件过期无法评估）
    uniqueness: int | None = None
    # 异常提示，如 "需升级 Canvas 插件"
    warning: str | None = None
    instances: int = 0
    # 非空时操作列替换为修复按钮，如 "一键更新 UA"
    action: str | None = None


class FingerprintPayload(BaseModel):
    total: int
    kernels: int
    filters: list[FilterItem]
    templates: list[FingerprintTemplate]
    shown: int
    selected: int
    page: int
    pages: int
