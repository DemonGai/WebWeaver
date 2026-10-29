"""内核管理（引擎维度）与账号菜单模型"""

from pydantic import BaseModel, Field


# ── 通用小块 ────────────────────────────────────────────
class KernelMetric(BaseModel):
    label: str
    value: str


class GrayStage(BaseModel):
    label: str
    active: bool = False


class GrayRelease(BaseModel):
    eyebrow: str
    title: str
    done: int
    total: int
    percent: int
    stages: list[GrayStage]


class Changelog(BaseModel):
    version: str
    items: list[str]
    published_at: str


# ── 内核引擎 ────────────────────────────────────────────
class KernelCheck(BaseModel):
    """单个反检测 / 指纹检测项的实测结果"""

    label: str
    status: str
    tone: str


class KernelRelease(BaseModel):
    """某内核下已安装或可获取的版本镜像"""

    version: str
    base: str
    arch: str
    size: str
    instances: int
    status: str
    status_tone: str
    installed: bool = True
    released_at: str


class KernelEngine(BaseModel):
    id: str
    name: str
    engine: str  # Chromium / Firefox
    base: str  # 上游基线版本
    level: str  # 反检测实现层级
    tone: str
    tagline: str  # 定位
    usage: str  # 建议用途
    origin: str  # 来源说明
    version: str  # 当前部署版本
    latest: str  # 最新可用版本
    update: bool
    channel: str
    size: str
    arch: str
    instances: int
    share: int  # 实例占比
    status: str
    status_tone: str
    primary: bool
    pass_rate: int
    checks: list[KernelCheck]
    releases: list[KernelRelease]
    note: str


class KernelSummaryTile(BaseModel):
    key: str
    label: str
    value: str
    hint: str
    icon: str
    tone: str


class KernelTab(BaseModel):
    key: str
    label: str
    count: int


class FallbackStep(BaseModel):
    """检测兜底链路中的一个环节"""

    id: str
    name: str
    engine: str
    role: str
    detail: str
    tone: str


class KernelEnginePayload(BaseModel):
    tiles: list[KernelSummaryTile]
    tabs: list[KernelTab]
    engines: list[KernelEngine]
    fallback: list[FallbackStep]
    fallback_triggers: list[str]
    release_note: Changelog
    gray: GrayRelease
    total_instances: int
    check_labels: list[str]


class PrimaryResponse(BaseModel):
    ok: bool
    primary_id: str
    message: str


# ── 升级任务弹窗 ────────────────────────────────────────
class KernelOption(BaseModel):
    id: str
    name: str
    channel: str
    size: str
    note: str
    recommended: bool = False
    disabled: bool = False


class GroupOption(BaseModel):
    id: str
    name: str
    count: int


class StrategyToggle(BaseModel):
    key: str
    label: str
    description: str
    default: bool = True


class UpgradeOptions(BaseModel):
    kernels: list[KernelOption]
    groups: list[GroupOption]
    scope_tabs: list[str]
    batches: list[str]
    intervals: list[str]
    toggles: list[StrategyToggle]
    notice: str
    eta: str


class UpgradeRequest(BaseModel):
    kernel_id: str
    scope: str = "group"
    groups: list[str] = Field(default_factory=list)
    batch: str = "3 批 (8/8/8)"
    interval: str = "10 分钟"
    auto_rollback: bool = True
    pause_queue: bool = True
    refresh_ua: bool = True


class UpgradeResponse(BaseModel):
    ok: bool
    task_id: str
    kernel: str
    targets: int
    batch: str
    interval: str
    eta: str
    message: str


# ── 账号菜单浮层 ────────────────────────────────────────
class MenuRow(BaseModel):
    key: str
    label: str
    icon: str
    badge: str | None = None
    badge_tone: str | None = None
    danger: bool = False


class AccountMenu(BaseModel):
    name: str
    initial: str
    email: str
    role: str
    workspace: str
    workspace_note: str
    groups: list[list[MenuRow]]
    last_login: str
    version: str
