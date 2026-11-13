"""领域模型，与前端 src/types/domain.ts 一一对应。"""

from enum import StrEnum
from typing import Any

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
    email: str | None = None
    # 列表只回 Cookie 条数，不回整份内容：几十条 Cookie 逐行下发会把列表撑大，
    # 真要编辑时再走 GET /accounts/{id} 拿完整 JSON
    cookie_count: int = 0


class AccountDetail(BaseModel):
    """编辑弹窗用：含明文 Cookie，只在单条详情里给。"""

    id: str
    platform: str
    username: str
    email: str | None = None
    region: str
    health: int
    status: AccountStatus
    note: str | None = None
    cookies: list[dict[str, Any]] | None = None


class AccountCreateRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=64, description="平台，如 Amazon")
    username: str = Field(min_length=1, max_length=128, description="平台登录名")
    email: str | None = Field(default=None, max_length=255)
    region: str = Field(default="", max_length=64)
    health: int = Field(default=100, ge=0, le=100)
    note: str | None = Field(default=None, max_length=255)
    # 不传就按「有没有 Cookie」推断：有 Cookie 视为已登录，否则未绑定
    status: AccountStatus | None = None
    # 接受 cookies 数组，或 Playwright storage_state 整个对象 {"cookies": [...]}
    cookies: Any | None = None


class AccountUpdateRequest(BaseModel):
    """编辑：字段都是可选的，只改真正传上来的那些。"""

    platform: str | None = Field(default=None, min_length=1, max_length=64)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    health: int | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=255)
    status: AccountStatus | None = None
    # 传 null 表示清空登录态；字段不出现表示不动
    cookies: Any | None = None


class AccountImportRequest(BaseModel):
    text: str = Field(min_length=1, description="粘贴的账号清单，每行一条")
    default_platform: str = Field(default="", max_length=64)
    overwrite: bool = False


class AccountImportRow(BaseModel):
    line: int
    ok: bool
    label: str
    message: str


class AccountImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    failed: int
    rows: list[AccountImportRow]


class IpResource(BaseModel):
    id: str
    ip: str
    # 代理只写地址没法用，端口和协议是「怎么连」的另一半
    port: int
    protocol: str
    supplier: str
    region: str
    city: str
    type: str
    # 代理认证：前端要拼 socks5://user:pass@host:port，所以原样下发
    username: str | None = None
    password: str | None = None
    latency_ms: int
    health: int
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


# ── 账号管理 ──────────────────────────────────────────────
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


# ── 代理导入 / 检测 ────────────────────────────────────
class IpImportRequest(BaseModel):
    text: str = Field(min_length=1, description="粘贴的代理清单，每行一条")
    # 清单里没写类型 / 供应商时用这两个兜底，省得对着模板逐行补齐
    default_kind: str = "residential"
    default_supplier: str = "未标注"
    overwrite: bool = False


class IpImportRow(BaseModel):
    """一行导入结果，只回失败的：成功的条数看汇总就够，逐行回传没意义。"""

    line: int
    ok: bool
    label: str
    message: str


class IpImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    failed: int
    rows: list[IpImportRow]


class IpCheckItem(BaseModel):
    id: str
    ip: str
    port: int
    ok: bool
    latency_ms: int
    message: str


class IpCheckResult(BaseModel):
    checked: int
    ok: int
    failed: int
    items: list[IpCheckItem]


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
    """列表里的一行。

    `seed` 是下发的输入，`ua` / `resolution` / `gpu` 是采集回来的结果 —— 前者
    我们说了算，后者只能观察。`probe_state` 把「结果还能不能信」这件事显式化：
    改过种子却没重采，UA 就还是上一个人的，页面上必须看得出来。
    """

    id: str
    name: str
    fp_id: str
    # 用于前端挑平台图标：windows / macos / linux / android / ios
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

    # ── 下发与采集 ────────────────────────────────────────────────
    seed: int | None = None
    # 适配的内核。指纹参数按内核变化，所以「绑定哪个内核」是这一行的核心属性
    kernel: str | None = None
    kernel_slug: str | None = None
    # 该内核能不能做指纹（ungoogled-chromium / Camoufox 为 False）
    supported: bool = False
    unsupported_reason: str | None = None
    # 伪移动：内核人格仍是桌面，只有 UA / 视口 / DPR 换成了移动端
    pseudo_mobile: bool = False
    # 采集结果摘要
    gpu: str | None = None
    canvas_hash: str | None = None
    probed_at: str | None = None
    # never 未采集 / fresh 与当前 seed 一致 / stale 改过参数没重采 / failed 上次失败
    probe_state: str = "never"


class FingerprintPayload(BaseModel):
    total: int
    kernels: int
    # 支持指纹的内核数 / 已采集数 / 实测值过期数
    supported_kernels: int = 0
    probed: int = 0
    stale: int = 0
    filters: list[FilterItem]
    templates: list[FingerprintTemplate]
    shown: int
    selected: int
    page: int
    pages: int


class FingerprintRender(BaseModel):
    """按内核渲染出的三种下发物料。"""

    # /data/fingerprint.json 的内容
    payload: dict[str, object] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    args: list[str] = Field(default_factory=list)
    # 填了但该内核不认的字段 —— 不列出来就是静默失效
    ignored: list[str] = Field(default_factory=list)


class KernelFingerprintCaps(BaseModel):
    """一个内核的指纹能力，前端据此决定表单显隐与提示。

    放在接口里而不是前端硬编码：参数名和取值范围只有后端一处定义，
    改内核不用两头改，也不会出现「前端以为支持、后端其实忽略」的偏差。
    """

    # 内核行的 ID：前端新建指纹时直接拿它填 kernel_id，不用再查一遍内核列表
    kernel_id: str
    slug: str
    label: str
    supported: bool
    # seed 合法区间（闭区间），不支持指纹时为 None
    seed_range: list[int] | None = None
    # 该内核认的能力名，与 `fingerprint_caps` 里的常量一致
    features: list[str] = Field(default_factory=list)
    note: str = ""
    reason: str | None = None


class FingerprintInstanceRef(BaseModel):
    """绑定到这条指纹上的实例。"""

    id: str
    name: str
    status: str


class FingerprintDetailPayload(BaseModel):
    """详情：下发参数 + 实测人格 + 当前内核下的下发物料。"""

    id: str
    name: str
    fp_id: str

    kernel: str | None = None
    kernel_slug: str | None = None
    supported: bool = False
    unsupported_reason: str | None = None
    # 伪移动：内核人格仍是桌面，只有 UA / 视口 / DPR 换成了移动端
    pseudo_mobile: bool = False
    # 伪移动的边界说明（给用户看的原话）；真平台时为 None
    pseudo_mobile_note: str | None = None
    # 该内核的指纹机制一句话说明
    note: str | None = None

    # ── 下发参数 ──
    seed: int | None = None
    seed_range: list[int] | None = None
    platform_family: str
    platform_version: str | None = None
    brand: str | None = None
    brand_version: str | None = None
    hardware_concurrency: int | None = None
    timezone: str
    language: str
    accept_lang: str | None = None
    canvas_noise: bool = True
    webgl_noise: bool = True
    audio_noise: bool = True
    webrtc_protected: bool = True

    # ── 实测人格 ──
    ua: str = ""
    resolution: str = ""
    dpr: str = ""
    gpu: str | None = None
    canvas_hash: str | None = None
    languages: list[str] = Field(default_factory=list)
    webdriver: bool | None = None
    probed_at: str | None = None
    probe_state: str = "never"
    probe_error: str | None = None
    # 实测人格里会被识破的矛盾点
    warnings: list[str] = Field(default_factory=list)

    instances: list[FingerprintInstanceRef] = Field(default_factory=list)
    render: FingerprintRender | None = None


# ── 指纹写操作 ─────────────────────────────────────────
class FingerprintCreate(BaseModel):
    """新建一条指纹。种子可以留空，先建后采也行。"""

    name: str = Field(min_length=1, max_length=64)
    kernel_id: str | None = None
    platform_family: str = "windows"
    seed: int | None = Field(default=None, ge=1)
    platform_version: str | None = None
    brand: str | None = None
    brand_version: str | None = None
    hardware_concurrency: int | None = Field(default=None, ge=1, le=256)
    timezone: str = "Asia/Shanghai"
    language: str = "zh-CN"
    accept_lang: str | None = None
    canvas_noise: bool = True
    webgl_noise: bool = True
    audio_noise: bool = True
    webrtc_protected: bool = True
    # 留空按平台族 + 种族自动生成
    code: str | None = None


class FingerprintUpdate(BaseModel):
    """改一条指纹。只传要改的字段；种子一改，实测值立刻作废。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    kernel_id: str | None = None
    platform_family: str | None = None
    seed: int | None = Field(default=None, ge=1)
    platform_version: str | None = None
    brand: str | None = None
    brand_version: str | None = None
    hardware_concurrency: int | None = Field(default=None, ge=1, le=256)
    timezone: str | None = None
    language: str | None = None
    accept_lang: str | None = None
    canvas_noise: bool | None = None
    webgl_noise: bool | None = None
    audio_noise: bool | None = None
    webrtc_protected: bool | None = None


class FingerprintApplyRequest(BaseModel):
    """把指纹写进这些实例的容器并重启。"""

    instance_ids: list[str] = Field(default_factory=list, min_length=1)


class FingerprintApplyItem(BaseModel):
    instance_id: str
    instance_name: str
    container: str
    ok: bool
    message: str
    restarted: bool = False
    ignored: list[str] = Field(default_factory=list)


class FingerprintApplyResult(BaseModel):
    ok: bool
    succeeded: int
    failed: int
    items: list[FingerprintApplyItem]
