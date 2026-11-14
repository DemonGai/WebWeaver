"""noVNC 能力检测与「可接管清单」。

**能不能看画面由镜像决定，不是由实例状态决定。** 三个引擎的 Dockerfile 都有
``ARG WITH_VNC``：``=1`` 装 Xvfb + x11vnc + noVNC，``=0`` 只留无头内核，6080
端口上根本没有服务。所以先问镜像，再看实例在不在跑——顺序反了就会给出一个
点进去必然白屏的入口。

判定按「先准后宽」排：

1. 镜像标签 ``com.webweaver.novnc``（新构建的镜像会写 ``1`` / ``0``）——
   最可靠，重建镜像也不会误判；
2. 镜像层历史里出现 ``novnc`` / ``websockify`` —— 老镜像没有这个标签，但装包
   那一层还在，这是不需要启动容器就能用的判据；
3. 都不满足就当作不支持，并把原因直接给用户看。

结果按镜像引用缓存在进程内：一次清单请求要给十几台实例判定，每台都跑两条
docker 命令太慢。镜像是低频变化的东西，缓存不做 TTL，重新拉取镜像时由
:func:`forget` 主动清掉。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.browser import NoVncOverview, NoVncTarget, NoVncTotals
from app.schemas.domain import InstanceStatus
from app.services import kernel_image, kernel_scan
from app.services.cluster import Snapshot

# 镜像自带的 noVNC 能力标记，与 browser_engine/*/Dockerfile 里的 LABEL 对应
NOVNC_LABEL = "com.webweaver.novnc"
# 容器内 noVNC 的端口，与 browser_runtime.CONTAINER_NOVNC_PORT 一致
CONTAINER_NOVNC_PORT = 6080
# noVNC 自带的网页路径；autoconnect 省一次点击，resize=scale 让画面跟着窗口缩放
NOVNC_PATH = "/vnc.html?autoconnect=1&resize=scale"


@dataclass(frozen=True)
class Capability:
    """一个镜像的 noVNC 能力。``reason`` 只在不可用时给用户看。"""

    supported: bool
    reason: str
    source: str  # label / history / unknown

    @property
    def ok(self) -> bool:
        return self.supported


_CACHE: dict[str, Capability] = {}


def forget(image_ref: str | None = None) -> None:
    """清缓存。镜像重新拉取 / 重建后调用，避免继续用旧的判定。"""
    if image_ref is None:
        _CACHE.clear()
    else:
        _CACHE.pop(image_ref, None)


def detect(image_ref: str | None) -> Capability:
    """判断镜像是否带 noVNC。找不到镜像时返回不支持 + 原因，不抛异常。"""
    if not image_ref:
        return Capability(False, "还没有可用的内核镜像", "unknown")

    cached = _CACHE.get(image_ref)
    if cached is not None:
        return cached

    try:
        info = kernel_image.inspect(image_ref)
    except kernel_image.DockerError as exc:
        # Docker 不可用属于环境问题，不是镜像的结论，不能缓存
        return Capability(False, f"读不到镜像信息：{exc}", "unknown")
    if info is None:
        return Capability(False, f"镜像 {image_ref} 不在本地了，重新拉取后再试", "unknown")

    flag = ((info.labels or {}).get(NOVNC_LABEL) or "").strip()
    if flag == "1":
        cap = Capability(True, "", "label")
    elif flag == "0":
        cap = Capability(
            False,
            "这个镜像构建时用了 WITH_VNC=0，只装了无头内核，没有 noVNC",
            "label",
        )
    else:
        # 老镜像没有能力标签，退回看构建历史里有没有装包那一层
        cap = (
            Capability(True, "", "history")
            if _mentions_novnc(image_ref)
            else Capability(
                False,
                "这个镜像里没有 noVNC（构建时没装 Xvfb / x11vnc / websockify）",
                "history",
            )
        )

    _CACHE[image_ref] = cap
    return cap


def _mentions_novnc(image_ref: str) -> bool:
    """镜像层历史里是否出现过 noVNC 组件。历史拿不到就按不支持处理。"""
    try:
        proc = kernel_image.run(
            ["history", "--no-trunc", "--format", "{{.CreatedBy}}", image_ref], timeout=30
        )
    except kernel_image.DockerError:
        return False
    if proc.returncode != 0:
        return False
    text = (proc.stdout or "").lower()
    return "novnc" in text or "websockify" in text


def base_url(host: str, port: int) -> str:
    """拼接某台实例的 noVNC 地址。IPv6 字面量要加方括号，否则解析不出端口。"""
    address = host if ":" not in host or host.startswith("[") else f"[{host}]"
    return f"http://{address}:{port}{NOVNC_PATH}"


def overview(snapshot: Snapshot, host: str) -> NoVncOverview:
    """所有实例的 noVNC 可接管情况。"""
    images = _local_images()
    targets = [_target(snapshot, browser, host, images) for browser in _sorted(snapshot.browsers)]

    def count(kind: str) -> int:
        return sum(1 for item in targets if item.availability == kind)

    return NoVncOverview(
        totals=NoVncTotals(
            total=len(targets),
            ready=count("ready"),
            offline=count("stopped"),
            unsupported=count("unsupported"),
            blocked=count("blocked"),
        ),
        instances=targets,
    )


def target(snapshot: Snapshot, key: str, host: str) -> NoVncTarget:
    """单个实例的可接管信息；实例不存在时抛 404 由路由处理。"""
    browser = snapshot.find_browser(key)
    if browser is None:
        raise LookupError(key)
    return _target(snapshot, browser, host, _local_images())


def _target(
    snapshot: Snapshot,
    browser,
    host: str,
    images: list[kernel_image.ImageInfo],
) -> NoVncTarget:
    kernel = snapshot.kernels.get(browser.kernel_id) if browser.kernel_id else None
    account = snapshot.accounts.get(browser.account_id) if browser.account_id else None
    ip = snapshot.ips.get(browser.ip_id) if browser.ip_id else None
    image_ref = _image_for(kernel, browser.kernel_version, images)
    cap = detect(image_ref)

    # 不可用原因按「用户下一步该做什么」排：先修配置，再修镜像，最后才是启动
    if kernel is None:
        availability = "blocked"
        reason = "还没绑定内核，先到浏览器池编辑配置选一个"
    elif image_ref is None:
        availability = "blocked"
        reason = f"本地没有 {kernel.name} 这个版本的镜像，先到内核管理拉取"
    elif not cap.ok:
        availability = "unsupported"
        reason = cap.reason
    elif browser.vnc_port is None:
        # 端口只在容器真的起来后才分配，停止时清空——比状态字段更接近事实
        availability = "stopped"
        reason = "实例未启动，先启动实例再接管画面"
    else:
        availability = "ready"
        reason = None

    url = base_url(host, browser.vnc_port) if availability == "ready" and browser.vnc_port else None

    return NoVncTarget(
        id=str(browser.id),
        name=browser.name,
        status=InstanceStatus(browser.status.value),
        group=snapshot.groups[browser.group_id].name
        if browser.group_id in snapshot.groups
        else "未分组",
        account=account.username if account else "未绑定",
        ip=ip.address if ip else "直连",
        kernel=kernel.name if kernel else None,
        kernel_version=(browser.kernel_version or (kernel.version if kernel else None)),
        image=image_ref,
        port=browser.vnc_port,
        url=url,
        supports_novnc=cap.ok,
        ready=url is not None,
        availability=availability,
        reason=reason,
    )


def _local_images() -> list[kernel_image.ImageInfo]:
    """本地镜像清单。Docker 不可用时给空表，让每台实例各自说明缺失原因。"""
    try:
        return kernel_image.list_images(kernel_scan.registry())
    except kernel_image.DockerError:
        return []


def _image_for(kernel, version: str | None, images: list[kernel_image.ImageInfo]) -> str | None:
    """实例要跑的镜像引用：钉了版本就找那个版本，否则用最新可用版本。"""
    if kernel is None:
        return None
    versions = kernel_scan.scan_versions(kernel.name, images=images)
    if not versions:
        return None
    wanted = version or kernel.version
    if not wanted:
        return versions[0].image_ref
    for item in versions:
        if item.version == wanted:
            return item.image_ref
    return None


# 运行中的排前面，其余按状态收敛；同一状态内按名字，和浏览器池列表一致
_RANK = {
    InstanceStatus.running: 0,
    InstanceStatus.idle: 1,
    InstanceStatus.queued: 2,
    InstanceStatus.error: 3,
    InstanceStatus.stopped: 4,
}


def _sorted(browsers) -> list:
    return sorted(
        browsers,
        key=lambda b: (_RANK.get(InstanceStatus(b.status.value), 9), b.name),
    )
