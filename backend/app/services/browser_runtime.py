"""实例容器的生命周期：启动 / 停止 / 重启。

**容器名就是实例 ID**（``browsers.id``，UUID）。不用实例名有两个硬理由：

1. Docker 只接受 ``[a-zA-Z0-9][a-zA-Z0-9_.-]*``，而实例名允许中文（``上海-01``
   这种名字直接 ``docker run`` 会被拒）；
2. 实例可以改名，容器名跟着改名就得迁移容器；用 ID 则改名不影响运行中的容器。

这样 ``docker ps`` 里看到的名字与列表里 ID 徽标是同一个值，查日志不用再做映射。

**profile 挂在命名卷上**：``wv-data-<id>`` → 容器内 ``/data``。删容器重建不丢
登录态，这也是「换内核不换账号」能成立的前提。

**指纹只能启动时装配**：内核进程只在 entrypoint 里读一次指纹参数，没有热更新。
所以流程是「先起来 → ``docker cp`` 写 /data/fingerprint.json → 重启一次」，
写成 ``fingerprint_apply`` 复用同一套逻辑。
"""

from __future__ import annotations

import asyncio
import shlex
from uuid import UUID

from loguru import logger

from app.models import Ip, Kernel
from app.services import fingerprint_apply, kernel_image, kernel_scan
from app.services.fingerprint_caps import FingerprintSpec, KernelCaps

# 容器内的固定端口，与 browser_engine/*/entrypoint.sh 的默认值一致
CONTAINER_CDP_PORT = 9222
CONTAINER_NOVNC_PORT = 6080
# profile / 指纹都落在这里；entrypoint 的 USER_DATA_DIR 默认是 /data/profile
CONTAINER_DATA_DIR = "/data"
# 命名卷前缀，方便 docker volume ls 认出来
DATA_VOLUME_PREFIX = "wv-data-"
# 容器打标：按标记能筛出「本系统管理的实例容器」，不依赖名字前缀
INSTANCE_LABEL = "webweaver.instance"

# 起容器等它进入 running 的上限。镜像在本地时通常 2~5 秒
START_TIMEOUT = 40.0
# 停止给浏览器留的收尾时间，太短会留下半写的 profile
STOP_GRACE_SECONDS = 10

_PROXY_DEFAULT_PORT = {"http": 80, "https": 443, "socks5": 1080}


class ContainerError(RuntimeError):
    """容器操作失败。文案直接给用户看，要说清下一步做什么。"""


def container_name(browser_id: UUID | str) -> str:
    return str(browser_id)


def data_volume(browser_id: UUID | str) -> str:
    return f"{DATA_VOLUME_PREFIX}{browser_id}"


def proxy_argument(ip: Ip | None) -> str | None:
    """把出口 IP 拼成 ``--proxy-server`` 的值；直连返回 None。

    认证信息内联进 URL：Chromium 对 HTTP 代理认 ``user:pass@``，Socks5 的认证
    在部分版本上会被忽略 —— 这是内核侧的限制，不是这里能绕开的。
    """
    if ip is None:
        return None
    host = ip.address
    # IPv6 必须加方括号，否则 ``::`` 会被当成端口分隔符
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = ip.port or _PROXY_DEFAULT_PORT.get(ip.protocol.value, 0)
    auth = ""
    if ip.username:
        auth = f"{ip.username}:{ip.password or ''}@"
    return f"{ip.protocol.value}://{auth}{host}:{port}"


def resolve_image(kernel: Kernel, version: str | None) -> str:
    """实例要跑的镜像。固定 tag 优先，找不到就报清楚缺哪个版本。

    ``version`` 为空表示「跟随内核当前版本」。这种情况下若台账登记的版本本地
    没有镜像（种子数据里的版本号往往比实际拉取的旧），就退到最新可用镜像 ——
    与内核管理页「当前版本」的判定同口径，否则页面显示 156、启动却报缺 124。
    实例明确钉了某个版本时不退：那是用户的选择，缺了就该说缺。
    """
    try:
        images = kernel_image.list_images(kernel_scan.registry())
    except kernel_image.DockerError as exc:
        raise ContainerError(str(exc)) from exc

    versions = kernel_scan.scan_versions(kernel.name, images=images)
    if not versions:
        raise ContainerError(
            f"本地还没有 {kernel.name} 的镜像，先到内核管理里点「获取内核」拉一个"
        )

    wanted = version or kernel.version
    if not wanted:
        return versions[0].image_ref
    for item in versions:
        if item.version == wanted:
            return item.image_ref
    if version is None:
        logger.warning(
            "{} 登记的当前版本 {} 本地没有镜像，本次按最新镜像 {} 启动",
            kernel.name,
            wanted,
            versions[0].version,
        )
        return versions[0].image_ref
    available = "、".join(item.version for item in versions[:4])
    raise ContainerError(
        f"{kernel.name} 本地没有 {wanted} 版本的镜像（现有：{available}），"
        "换个版本或先拉取该版本"
    )


def image_of(browser_id: UUID | str) -> str | None:
    """容器当前实际使用的镜像；容器不存在返回 None。"""
    proc = kernel_image.run(
        [
            "inspect",
            "--type",
            "container",
            "--format",
            "{{.Config.Image}}",
            container_name(browser_id),
        ],
        timeout=20,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


async def state(browser_id: UUID | str) -> str:
    """``running`` / ``exited`` / ``created`` / …；容器不存在返回 ``absent``。"""
    return await _state(container_name(browser_id))


async def published_ports(browser_id: UUID | str) -> tuple[int, int] | None:
    """容器实际发布到宿主机的 ``(CDP, noVNC)`` 端口；容器不在或没发布返回 None。

    端口必须问 Docker，不能只信数据库。``docker restart``、手工 ``docker start``、
    进程异常退出后重建都不会经过我们写库，库里记的值随时可能落后于事实；拿旧值
    去拼 noVNC 地址，用户看到的就是一个没人监听的端口。
    """
    proc = await asyncio.to_thread(
        kernel_image.run, ["port", container_name(browser_id)], timeout=20
    )
    if proc.returncode != 0:
        return None

    found: dict[int, int] = {}
    for line in (proc.stdout or "").splitlines():
        # 形如 ``6080/tcp -> 0.0.0.0:6081``；IPv6 会再来一行 ``[::]:6081``，
        # 先出现的那条（通常是 IPv4）就够了
        if "->" not in line:
            continue
        left, right = (part.strip() for part in line.split("->", 1))
        try:
            inner = int(left.split("/", 1)[0])
            outer = int(right.rsplit(":", 1)[-1])
        except ValueError:
            continue
        found.setdefault(inner, outer)

    cdp = found.get(CONTAINER_CDP_PORT)
    vnc = found.get(CONTAINER_NOVNC_PORT)
    if cdp is None or vnc is None:
        return None
    return cdp, vnc


async def start_container(
    browser_id: UUID | str,
    *,
    image_ref: str,
    cdp_port: int,
    vnc_port: int,
    instance_name: str = "",
    proxy: str | None = None,
    fingerprint: tuple[KernelCaps, FingerprintSpec] | None = None,
) -> None:
    """按实例 ID 起容器；容器已存在（停止/异常）则删掉重建，卷保留。"""
    name = container_name(browser_id)
    current = await _state(name)
    if current == "running":
        return
    if current != "absent":
        # 旧容器可能带着上一次的代理 / 端口配置。重建才拿得到当前配置，
        # 而 profile 在命名卷上，重建不等于重来。
        await _force_remove(name)

    args = [
        "run",
        "-d",
        "--name",
        name,
        "--label",
        f"{INSTANCE_LABEL}={browser_id}",
        "-p",
        f"{cdp_port}:{CONTAINER_CDP_PORT}",
        "-p",
        f"{vnc_port}:{CONTAINER_NOVNC_PORT}",
        "-e",
        "MODE=vnc",
        "-e",
        "SCREEN=1920x1080x24",
        "--shm-size=1g",
        "--init",
        "-v",
        f"{data_volume(browser_id)}:{CONTAINER_DATA_DIR}",
    ]
    if proxy:
        # 用 shlex.quote 兜住密码里的空格 / 引号，entrypoint 是按空格切 CHROME_ARGS 的
        args += ["-e", f"CHROME_ARGS=--proxy-server={shlex.quote(proxy)}"]
    args.append(image_ref)

    proc = await asyncio.to_thread(kernel_image.run, args, timeout=180)
    if proc.returncode != 0:
        raise ContainerError(_explain(proc, name))
    await _wait_running(name)

    if fingerprint is not None:
        caps, spec = fingerprint
        try:
            await fingerprint_apply.apply(
                caps,
                spec,
                instance_name=instance_name or name,
                container=name,
            )
        except fingerprint_apply.ApplyError as exc:
            # 指纹没进去就不要留一台「看着在跑、其实没套模板」的容器
            await _force_remove(name)
            raise ContainerError(f"指纹下发失败，已回滚启动：{exc}") from exc


async def stop_container(browser_id: UUID | str) -> None:
    """按实例 ID 停容器；容器本来就不在也算成功（幂等）。"""
    name = container_name(browser_id)
    if await _state(name) == "absent":
        return
    proc = await asyncio.to_thread(
        kernel_image.run, ["stop", "-t", str(STOP_GRACE_SECONDS), name], timeout=60
    )
    if proc.returncode != 0:
        raise ContainerError(_explain(proc, name))


async def restart_container(browser_id: UUID | str) -> None:
    """原地重启容器：不重建，代理 / 端口等启动参数保持不变。"""
    name = container_name(browser_id)
    if await _state(name) == "absent":
        raise ContainerError(f"容器 {name} 不存在，没法重启")
    proc = await asyncio.to_thread(kernel_image.run, ["restart", name], timeout=120)
    if proc.returncode != 0:
        raise ContainerError(_explain(proc, name))
    await _wait_running(name)


async def remove_container(browser_id: UUID | str) -> None:
    """删容器（卷保留）。实例被删时调用，避免留下占着端口的僵尸容器。"""
    name = container_name(browser_id)
    if await _state(name) == "absent":
        return
    proc = await asyncio.to_thread(kernel_image.run, ["rm", "-f", name], timeout=60)
    if proc.returncode != 0:
        raise ContainerError(_explain(proc, name))


async def _state(name: str) -> str:
    proc = await asyncio.to_thread(
        kernel_image.run,
        ["inspect", "--type", "container", "--format", "{{.State.Status}}", name],
        timeout=20,
    )
    if proc.returncode != 0:
        return "absent"
    return (proc.stdout or "").strip() or "absent"


async def _wait_running(name: str, timeout: float = START_TIMEOUT) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        current = await _state(name)
        if current == "running":
            return
        if current in ("exited", "dead"):
            tail = await _logs(name)
            raise ContainerError(
                "容器启动后立刻退出了，多半是镜像或参数有问题"
                + (f"：\n{tail}" if tail else "")
            )
        await asyncio.sleep(0.4)
    tail = await _logs(name)
    raise ContainerError(
        f"容器 {timeout:.0f} 秒内没进入运行状态" + (f"：\n{tail}" if tail else "")
    )


async def _logs(name: str, lines: int = 12) -> str:
    proc = await asyncio.to_thread(
        kernel_image.run, ["logs", "--tail", str(lines), name], timeout=20
    )
    if proc.returncode != 0:
        return ""
    text = "\n".join(filter(None, [(proc.stdout or "").strip(), (proc.stderr or "").strip()]))
    # 日志可能很长，取尾部即可；容器报错的关键行都在最后
    return text[-800:]


async def _force_remove(name: str) -> None:
    await asyncio.to_thread(kernel_image.run, ["rm", "-f", name], timeout=60)


def _explain(proc, name: str) -> str:
    """把 docker 的报错翻译成一句能照着做的中文。"""
    raw = (proc.stderr or proc.stdout or "").strip()
    last = raw.splitlines()[-1] if raw else f"退出码 {proc.returncode}"
    lowered = raw.lower()
    if "port is already allocated" in lowered or "address already in use" in lowered:
        return f"端口被占用了，换一台实例或先停掉占用的进程（{last}）"
    if "no such image" in lowered:
        return f"镜像不在本地了，到内核管理里重新拉取（{last}）"
    if "is already in use" in lowered:
        return f"容器名 {name} 已被别的容器占用，先执行 docker rm -f {name}（{last}）"
    if "cannot connect" in lowered or "pipe" in lowered:
        return f"Docker 守护进程没在运行（{last}）"
    return f"docker 操作失败：{last}"
