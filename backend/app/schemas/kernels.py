"""内核管理模型：4 套引擎、磁盘版本扫描结果与实例迁移。

页面上的数据全部来自三处，没有假的演示数字：

1. ``kernels`` 表 —— 引擎台账（名称、当前生效版本、是否主力）；
2. 引擎档案 ``<kernel_root>/<slug>/engine.json`` —— 人工维护的介绍、优劣势、
   下载源与「可下载版本清单」；每个引擎的获取方式不同，靠 ``kind`` 区分；
3. 磁盘版本目录 —— `<kernel_root>/<slug>/<version>/meta.json`，装了哪些版本由扫描决定。

``kind`` 只有三种，一个安装器覆盖四个引擎：

- ``pip``：装官方 Python 包，再调它自己的 CLI 把二进制拉进缓存，最后搬进版本目录；
- ``archive``：官方直链下载压缩包，校验 sha256 后解压；
- ``manual``：只给链接（第三方构建、需要登录的源），用户自己下完交给导入器。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KernelVersion(BaseModel):
    """磁盘上的一个版本目录"""

    version: str
    base: str | None = None  # 上游基线，如 Chromium 128.0.6613.120
    arch: str | None = None
    channel: str | None = None
    size: str | None = None  # 人类可读，如 412 MB
    released_at: str | None = None  # 上游发布日期
    packaged_at: str | None = None  # 落盘时间
    source: str | None = None  # 该版本的上游发布页
    path: str  # 绝对路径，排障时直接复制
    ready: bool = True  # 目录里有 meta.json 等标记文件
    current: bool = False  # 是否是当前生效版本
    instances: int = 0  # 有多少台实例固定在这个版本上
    warning: str | None = None  # ready=False 时的原因


class KernelCard(BaseModel):
    """页面上的一张内核卡片"""

    id: str
    slug: str  # 目录名
    name: str
    engine: str  # Chromium / Firefox
    channel: str
    arch: str
    tone: str
    tagline: str
    detection_level: str | None = None
    repo_url: str | None = None
    mirror_url: str | None = None
    is_primary: bool = False

    current_version: str | None = None
    latest_version: str | None = None  # 磁盘上最新的可用版本
    update_available: bool = False  # latest > current
    downloaded: bool = False  # 至少有一个可用版本目录
    version_count: int = 0
    instance_count: int = 0
    stale_count: int = 0  # 还留在旧版本上的实例数

    disk_path: str
    scanned_at: str
    versions: list[KernelVersion] = Field(default_factory=list)
    note: str | None = None


class KernelStat(BaseModel):
    """顶部一条小统计"""

    key: str
    label: str
    value: str
    hint: str
    tone: str
    icon: str


class KernelPayload(BaseModel):
    stats: list[KernelStat]
    cards: list[KernelCard]
    root: str  # 内核根目录的绝对路径
    scanned_at: str
    total_instances: int
    total_versions: int


class KernelInstance(BaseModel):
    """批量迁移弹窗里的一行实例"""

    id: str
    name: str
    version: str | None = None
    group: str
    status: str


class VersionSwitchRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)


class MigrationRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    # 留空表示该内核下所有不在目标版本上的实例
    browser_ids: list[str] = Field(default_factory=list, max_length=200)


class MigrationResult(BaseModel):
    ok: bool
    version: str
    migrated: int
    message: str


class PrimaryResponse(BaseModel):
    ok: bool
    primary_id: str
    message: str


# ── 引擎档案（engine.json） ────────────────────────────────────────────


class EngineLink(BaseModel):
    """档案里的一个外链：官方发布页 / 文档 / 构建索引 / 镜像。"""

    label: str
    url: str
    kind: Literal["release", "docs", "bucket", "mirror"] = "release"


class EnginePackage(BaseModel):
    """某个版本在某个平台上的一种获取方式。"""

    kind: Literal["pip", "archive", "manual"] = "archive"
    os: str = "any"
    arch: str = "any"
    size: str | None = None  # 人类可读，如 "1.22 GB"
    url: str | None = None  # archive / manual 用
    sha256: str | None = None  # 留空表示上游没提供，页面标「未校验」
    installer: str | None = None  # pip 包名
    pin: str | None = None  # pip 版本
    note: str | None = None


class EngineVersionSpec(BaseModel):
    """档案里声明的一个可下载版本（有没有装由扫描决定，不在这里）。"""

    version: str
    base: str | None = None
    channel: str | None = None
    released_at: str | None = None
    notes: str | None = None
    packages: list[EnginePackage] = Field(default_factory=list)


class AcquireSpec(BaseModel):
    """引擎级默认获取方式，供没有逐版本声明时兜底。"""

    kind: Literal["pip", "archive", "manual"] = "manual"
    installer: str | None = None
    pin: str | None = None
    # 装完包之后要跑的取二进制命令，如 ["-m", "cloakbrowser", "install"]
    fetch: list[str] = Field(default_factory=list)
    # 二进制的直链模板（含 {version}）。填了就直接下载这个 zip 并解压，
    # 跳过官方 CLI 的下载步骤：CLI 是单连接，500MB 的包只能跑到 ~30 KB/s
    binary_url: str | None = None
    # 二进制会落在哪些缓存目录（支持 ~ 与环境变量），找不到时在这些目录里搜
    cache_dirs: list[str] = Field(default_factory=list)
    executable: str | None = None
    note: str | None = None


class EngineProfile(BaseModel):
    """``browser_engine/<slug>/engine.json`` —— 人工维护的引擎档案。"""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema")
    name: str
    engine: str = "Chromium"
    tone: str | None = None
    tagline: str | None = None
    best_for: str | None = None
    detection_level: str | None = None
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    install_notes: list[str] = Field(default_factory=list)
    links: list[EngineLink] = Field(default_factory=list)
    acquire: AcquireSpec | None = None
    versions: list[EngineVersionSpec] = Field(default_factory=list)


class EngineVersionView(EngineVersionSpec):
    """档案版本 + 磁盘状态，详情页直接渲染这个。"""

    installed: bool = False
    installed_size: str | None = None
    is_current: bool = False
    on_disk_only: bool = False  # 磁盘有、档案没登记（手工放的旧版本）


class KernelDetailPayload(BaseModel):
    """引擎详情页数据：台账卡片 + 档案 + 磁盘状态 + 正文。"""

    slug: str
    card: KernelCard
    profile: EngineProfile | None = None
    profile_ok: bool = False
    profile_error: str | None = None
    versions: list[EngineVersionView] = Field(default_factory=list)
    docs: str | None = None
    docs_path: str
    install_hint: str | None = None


# ── 安装任务 ──────────────────────────────────────────────────────────


class InstallRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    os: str = "windows"
    arch: str = "x64"


class InstallJob(BaseModel):
    """一次内核获取任务。进程内内存态，重启即丢，页面会提示「任务中断」。"""

    id: str
    slug: str
    version: str
    kind: str
    status: Literal["running", "success", "failed"] = "running"
    progress: float = 0.0  # 0~1
    message: str = ""
    error: str | None = None
    started_at: str
    finished_at: str | None = None
