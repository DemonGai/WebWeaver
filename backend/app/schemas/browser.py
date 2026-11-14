"""浏览器池的写接口模型：新建、编辑、绑定、启停与批量操作。

与 ``schemas/domain.py`` 里的只读展示模型分开：那边是「列表页要渲染成什么样」，
这里是「前端能提交什么」。两者刻意不共用，展示模型加个字段不该顺带让写接口
多接受一个参数。
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.domain import InstanceStatus

# 生命周期动作：启动 / 停止 / 重启。重启用一条动作表示，
# 而不是让前端自己拼 stop+start——那样两次请求之间状态会短暂不一致。
BrowserActionName = Literal["start", "stop", "restart"]

# 实例名：中文、字母、数字，可夹点 / 下划线 / 短横线 / 空格，但不能以它们开头。
# 这里不用 `\w` 是因为它把全角标点、各种 Unicode 字母都算进来，名字会越写越野，
# 而实例名是要当唯一键用的。空格允许「上海 01」这类习惯写法，首尾由服务层 strip。
INSTANCE_NAME_PATTERN = r"^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._\- ]*$"

# 名字长度上限。复制实例时会拼「 副本N」后缀，也要按这条截，别让副本名超长
INSTANCE_NAME_MAX = 64


class BrowserOption(BaseModel):
    """下拉选项：id + 展示文案 + 补充说明，够前端直接渲染。"""

    id: str
    label: str
    hint: str = ""
    # 已被别的实例占用时为 True：仍展示但不让选，用户能看懂「为什么没有它」
    disabled: bool = False


class KernelOption(BrowserOption):
    """内核候选。

    只有内核自己知道它带不带指纹补丁：不带的内核（ungoogled-chromium、Firefox 系）
    收到 ``--fingerprint`` 只会静默忽略，看上去正常、实际没生效。所以把能力
    直接挂在选项上，前端据此决定要不要显示指纹与出口两栏。
    """

    supports_fingerprint: bool = True
    # 不支持时的理由，直接给用户看
    fingerprint_note: str = ""
    # 当前部署版本，版本下拉的「跟随内核当前版本」要显示它
    version: str = ""


class BrowserOptions(BaseModel):
    """新建 / 绑定弹窗需要的全部候选资源。"""

    groups: list[BrowserOption]
    kernels: list[KernelOption]
    # 内核 → 磁盘上已下载的版本（新到旧）。新建实例时可以让用户挑版本，
    # 老实例留在旧版本上，新实例直接用新版本。
    kernel_versions: dict[str, list[str]] = Field(default_factory=dict)
    accounts: list[BrowserOption]
    ips: list[BrowserOption]
    fingerprints: list[BrowserOption]


class BrowserCreate(BaseModel):
    """新建实例。

    资源字段全部可空：允许先建空壳再逐个绑定，这在实际运维里很常见
    （先把机器占下来，账号 IP 后面再分配）。``ip_id`` / ``fingerprint_id``
    传空表示直连与默认指纹，与表上的模式约束一致。
    """

    name: str = Field(
        min_length=2,
        max_length=INSTANCE_NAME_MAX,
        pattern=INSTANCE_NAME_PATTERN,
        description="实例名，作为业务唯一标识；支持中文",
    )
    group_id: UUID | None = None
    kernel_id: UUID | None = None
    # 留空 = 跟随该内核当前版本
    kernel_version: str | None = Field(default=None, max_length=64)
    account_id: UUID | None = None
    ip_id: UUID | None = None
    fingerprint_id: UUID | None = None
    note: str | None = Field(default=None, max_length=255)


class BrowserUpdate(BaseModel):
    """编辑实例。只处理「请求里出现过的字段」，没传的保持原值。

    这一点对 ``ip_id`` / ``fingerprint_id`` 尤其重要：显式传 ``null`` 是
    「切回直连 / 默认指纹」，不传才是「别动」。所以服务层用
    ``model_fields_set`` 判断，不能用 ``is not None``。
    """

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=INSTANCE_NAME_MAX,
        pattern=INSTANCE_NAME_PATTERN,
    )
    group_id: UUID | None = None
    kernel_id: UUID | None = None
    kernel_version: str | None = Field(default=None, max_length=64)
    account_id: UUID | None = None
    ip_id: UUID | None = None
    fingerprint_id: UUID | None = None
    note: str | None = Field(default=None, max_length=255)


class BrowserDetail(BaseModel):
    """单个实例的完整信息，编辑弹窗回填用。"""

    id: str
    name: str
    status: InstanceStatus
    group_id: str | None = None
    group: str
    kernel_id: str | None = None
    kernel: str
    kernel_version: str | None = None
    account_id: str | None = None
    account: str
    ip_id: str | None = None
    ip: str
    ip_mode: str
    region: str
    fingerprint_id: str | None = None
    fingerprint: str
    fingerprint_mode: str
    cdp_url: str | None = None
    vnc_url: str | None = None
    vnc_port: int | None = None
    fps: int | None = None
    latency_ms: int | None = None
    started_at: str | None = None
    last_active_at: str | None = None
    created_at: str
    updated_at: str
    note: str | None = None


class BrowserActionItem(BaseModel):
    """单个实例的动作结果。批量里失败的那几条也要说清原因。"""

    id: str
    name: str
    ok: bool
    status: str
    message: str


class BrowserBatchResult(BaseModel):
    ok: bool
    action: str
    succeeded: int
    failed: int
    items: list[BrowserActionItem]


class BrowserMutationResult(BaseModel):
    ok: bool
    message: str

class NoVncTarget(BaseModel):
    """一台实例的 noVNC 可接管情况。

    ``supports_novnc`` 是镜像能力（这个镜像里到底有没有 noVNC），``ready`` 是
    当下能不能点进去看（还要实例在跑）。两者分开，界面才能把「镜像不支持」
    和「先启动一下」区分开。
    """

    id: str
    name: str
    status: InstanceStatus
    group: str
    account: str
    ip: str
    kernel: str | None = None
    kernel_version: str | None = None
    image: str | None = None
    port: int | None = None
    url: str | None = None
    supports_novnc: bool
    ready: bool
    # 一句话结论的机器可读版本：ready / stopped / unsupported / blocked。
    # 界面据此选文案与按钮，不用去解析 reason 字符串
    availability: Literal["ready", "stopped", "unsupported", "blocked"]
    # 不可用时的一句话：告诉用户下一步做什么，而不是只报「不可用」
    reason: str | None = None


class NoVncTotals(BaseModel):
    total: int
    ready: int
    # 镜像层面就不带 noVNC 的台数：这部分无论怎么启动都看不了画面
    unsupported: int
    # 支持 noVNC 但当前没在跑的台数：启动后就能接管
    offline: int
    # 连镜像都还没有的台数：既不是「不支持」，也不是「启动一下就好」
    blocked: int


class NoVncOverview(BaseModel):
    totals: NoVncTotals
    instances: list[NoVncTarget]
