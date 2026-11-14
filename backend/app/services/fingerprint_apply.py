"""把指纹真正写进实例容器：`docker cp` 落盘 + `docker restart` 重新装配。

内核只在**启动时**读一次指纹（entrypoint 里一次性拼好 chrome 参数），所以改
指纹不可能热更新，只能重启容器。重启是安全的：profile 挂在 /data 上，
浏览器历史、Cookie、登录态都不丢，丢的只有内存里的页面。

容器怎么定位：按实例名找 `wv-<实例名>`（和内核管理页生成的 docker run 命令
保持同一个命名），也允许调用方显式指定。

── 一个必须挡住的陷阱 ──────────────────────────────────────────────
entrypoint 的取值顺序是「环境变量 > 指纹文件」::

    SEED="${FINGERPRINT_SEED:-$F_SEED}"

如果容器启动时就带了 `-e FINGERPRINT_SEED=42817`，那么不管我们往
/data/fingerprint.json 里写什么，种子都还是 42817 —— 文件写了等于没写，日志里
一切正常，指纹却没变。这种静默失效比报错难查得多，所以这里先查环境变量，
有冲突就直接拒绝，并告诉用户要么去掉环境变量，要么按新参数重建容器。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services import kernel_image
from app.services.fingerprint_caps import FingerprintSpec, KernelCaps, render

# 容器名就是实例 ID（browser_runtime.container_name），不再拼实例名：
# 实例名允许中文，Docker 会拒绝；改名后也会指到一个不存在的容器。
CONTAINER_PREFIX = "wv-"
# 容器内指纹文件路径，对应 entrypoint 的 FINGERPRINT_FILE 默认值
CONTAINER_FINGERPRINT_PATH = "/data/fingerprint.json"
# entrypoint 会读的环境变量前缀。带了这些就一定优先于文件
SHADOWING_PREFIX = "FINGERPRINT_"
# 重启后等容器重新跑起来的上限
RESTART_TIMEOUT = 60.0


class ApplyError(RuntimeError):
    """下发失败。文案直接给人看，要写清楚下一步做什么。"""

    def __init__(self, message: str, *, detail: list[str] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or []


@dataclass(frozen=True)
class ApplyResult:
    container: str
    payload: dict[str, Any]
    # 字段给了但内核不认，写进去也不会生效
    ignored: list[str] = field(default_factory=list)
    # 重启后容器有没有真的起来
    restarted: bool = False
    # 给用户看的补充说明（比如「重启后历史记录不丢」）
    note: str | None = None


async def apply(
    caps: KernelCaps,
    spec: FingerprintSpec,
    *,
    instance_name: str,
    container: str | None = None,
) -> ApplyResult:
    """把指纹写进容器并重启。失败抛 ApplyError。"""
    if not caps.supported:
        raise ApplyError(caps.reason or f"{caps.engine_label} 不支持指纹，下发没有意义")

    rendered = render(spec, caps)
    if not rendered.payload:
        raise ApplyError(
            f"没有可以写给 {caps.engine_label} 的指纹参数，先至少填一个种子或平台"
        )

    # 容器名必须由调用方给：它就是实例 ID（见 browser_runtime.container_name）。
    # 以前按「wv-<实例名>」推算，实例名允许中文后 docker 直接拒绝，改名后也会指错。
    if not container:
        raise ApplyError("没给容器名，无法定位要下发指纹的实例容器")
    name = container
    env = await _container_env(name)
    shadowing = sorted(key for key in env if key.startswith(SHADOWING_PREFIX))
    if shadowing:
        raise ApplyError(
            f"容器 {name} 启动时带了 {', '.join(shadowing)} 环境变量，"
            "它优先于指纹文件，写文件不会生效",
            detail=[
                "两个办法：",
                "1. 去掉这些环境变量重建容器，让指纹完全由 /data/fingerprint.json 决定；",
                "2. 或者直接改环境变量重启（docker update 改不了 env，必须重建）。",
                "重建命令可以用内核管理页「运行方式」里那段，"
                f"再把 -e {shadowing[0]}=<新值> 换成你想要的。",
            ],
        )

    await _write_file(name, json.dumps(rendered.payload, ensure_ascii=False, indent=2))
    restarted = await _restart(name)

    return ApplyResult(
        container=name,
        payload=rendered.payload,
        ignored=rendered.ignored,
        restarted=restarted,
        note="重启只重建浏览器进程，/data 下的 profile 不动，登录态和历史都还在",
    )


async def _container_env(name: str) -> dict[str, str]:
    """取容器的环境变量。容器不存在时抛一句能照着做的错误。"""
    proc = await asyncio.to_thread(
        kernel_image.run,
        ["inspect", "--format", "{{json .Config.Env}}", name],
        timeout=30,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip().splitlines()
        hint = message[-1] if message else f"退出码 {proc.returncode}"
        raise ApplyError(
            f"找不到容器 {name}（{hint}）",
            detail=[
                f"指纹是按「实例 ID = 容器名」找容器的：{name}。",
                "先在实例上点「启动」把容器拉起来，容器名会自动用这个 ID。",
            ],
        )

    raw = json.loads(proc.stdout or "[]")
    env: dict[str, str] = {}
    for entry in raw:
        key, _, value = str(entry).partition("=")
        env[key] = value
    return env


async def _write_file(name: str, content: str) -> None:
    """写进容器。走临时文件 + docker cp，避免把 JSON 塞进 shell 参数。"""
    handle, path = tempfile.mkstemp(prefix="wv-fp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(content)
        # docker cp 在 Windows 上认不了反斜杠
        source = Path(path).as_posix()
        proc = await asyncio.to_thread(
            kernel_image.run,
            ["cp", source, f"{name}:{CONTAINER_FINGERPRINT_PATH}"],
            timeout=60,
        )
    finally:
        Path(path).unlink(missing_ok=True)

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ApplyError(
            f"写 {CONTAINER_FINGERPRINT_PATH} 失败："
            f"{message[-1] if message else f'退出码 {proc.returncode}'}",
            detail=["确认容器还在运行，并且 /data 目录在容器里是可写的。"],
        )


async def _restart(name: str) -> bool:
    proc = await asyncio.to_thread(kernel_image.run, ["restart", name], timeout=120)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ApplyError(
            f"重启容器失败：{message[-1] if message else f'退出码 {proc.returncode}'}"
        )

    # restart 命令返回只代表 Docker 接受了请求，还要确认它真的活了。
    # 镜像坏了、Xvfb 起不来都会让容器立刻退出，这时候说「已生效」是在骗人。
    deadline = asyncio.get_running_loop().time() + RESTART_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        proc = await asyncio.to_thread(
            kernel_image.run,
            ["inspect", "--format", "{{.State.Running}}", name],
            timeout=20,
        )
        if (proc.stdout or "").strip() == "true":
            return True
        await asyncio.sleep(0.6)

    logs = await asyncio.to_thread(
        kernel_image.run, ["logs", "--tail", "15", name], timeout=20
    )
    tail = "\n".join(filter(None, [(logs.stdout or "").strip(), (logs.stderr or "").strip()]))
    raise ApplyError(
        f"容器重启后 {RESTART_TIMEOUT:.0f} 秒内没有跑起来，指纹可能有问题",
        detail=[f"容器日志：\n{tail[-600:]}" if tail else "容器没有输出日志"],
    )
