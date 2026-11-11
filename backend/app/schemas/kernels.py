"""内核管理模型。

数据只有两处，没有假的演示数字：

1. ``kernels`` 表 —— 台账（名称、当前生效版本、是否主力）；
2. **本地 Docker 镜像** —— 有哪些版本、多大、什么时候拉的，全部来自
   ``docker image ls``。镜像在就算这个内核可用，不在就是没获取。

所以「获取内核」等于 ``docker pull``，页面上不存在「档案登记了但没下载」这种
中间状态：要么本地有镜像，要么没有。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KernelVersion(BaseModel):
    """本地的一个版本（同一个镜像的多个 tag 合并成一条）"""

    version: str  # 146.0.7680.177.5
    tag: str  # 首选引用用的 tag：固定 tag 优先，没有才用滚动 tag
    image_ref: str  # demon1315132284/browser_engine:cloakbrowser
    image_id: str | None = None  # 短 id，12 位
    digest: str | None = None  # sha256:...
    size: str | None = None  # 人类可读，如 532 MB
    size_bytes: int = 0
    created_at: str | None = None  # 镜像构建时间（本地时区）
    rolling: bool = False  # 有滚动 tag 指向这个镜像
    pinned: bool = False  # 有固定版本 tag，可以用来钉住
    tags: list[str] = Field(default_factory=list)
    arch: str | None = None
    current: bool = False  # 是否是该内核当前生效版本
    instances: int = 0  # 有多少台实例固定在这个版本上


class KernelCard(BaseModel):
    """页面上的一张内核卡片"""

    id: str
    slug: str  # 镜像 tag 前缀
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

    # 镜像维度
    registry: str = ""
    supported: bool = True  # Camoufox 这类还没做镜像的，false
    unsupported_reason: str | None = None

    current_version: str | None = None
    current_ref: str | None = None  # 当前版本对应的完整镜像名
    latest_version: str | None = None  # 本地最新的可用版本
    update_available: bool = False  # latest > current
    installed: bool = False  # 本地至少有一个镜像
    version_count: int = 0
    total_size: str | None = None  # 该内核镜像合计占用
    instance_count: int = 0
    stale_count: int = 0  # 还留在旧版本上的实例数

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
    registry: str  # 镜像仓库，如 demon1315132284/browser_engine
    docker_ok: bool = True
    docker_error: str | None = None  # docker 不可用时的原因，页面顶部直接显示
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


class KernelDetailPayload(BaseModel):
    """内核详情页：台账卡片 + 本地镜像清单 + 说明文档。"""

    slug: str
    card: KernelCard
    versions: list[KernelVersion] = Field(default_factory=list)
    docs: str | None = None
    docs_path: str
    hint: str | None = None  # 页面上一句话提示
    run_command: str | None = None  # 可以直接复制去跑的 docker run
    docker_ok: bool = True
    docker_error: str | None = None


# ── 拉取任务 ──────────────────────────────────────────────────────────


class InstallRequest(BaseModel):
    """拉哪个 tag。留空表示拉滚动 tag（= 该内核最近一次构建）。"""

    tag: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=64)


class InstallJob(BaseModel):
    """一次镜像拉取任务。进程内内存态，重启即丢，页面会提示「任务中断」。"""

    id: str
    slug: str
    version: str  # 期望的版本号，未知时用 tag
    tag: str
    image_ref: str
    kind: str = "docker"
    status: Literal["running", "success", "failed"] = "running"
    progress: float = 0.0  # 0~1
    message: str = ""
    error: str | None = None
    started_at: str
    finished_at: str | None = None

    model_config = ConfigDict(populate_by_name=True)
