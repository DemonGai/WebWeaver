"""指纹采集：按 seed 起一个临时容器，把内核实际装配出来的人格录回来。

为什么必须起真容器：seed 是内核内部的算法输入，我们复现不出「42817 会算出
哪块显卡」。想让指纹页显示真实信息，唯一的办法是让内核自己跑一遍再把结果读出来。

流程（实测 2 秒出头，镜像已在本地时）::

    docker run -d --rm -e MODE=vnc -e FINGERPRINT_SEED=... -p 127.0.0.1:0:9222 <image>
    docker port <name> 9222                    -> 宿主机随机端口，避开 9222 被占
    GET  http://127.0.0.1:<port>/json/list     -> 页面 target 的 ws 地址
    WS   Runtime.evaluate(COLLECT_JS)          -> 一次性把人格读全
    docker rm -f <name>

端口用 `127.0.0.1:0:` 让 Docker 自己分配：宿主机上很可能已经有实例占着 9222，
固定端口会撞。绑定 127.0.0.1 而不是 0.0.0.0 是因为采集是本机行为，没理由把
一个带指纹的浏览器暴露到局域网。

── 为什么用 vnc 模式而不是 headless ──────────────────────────────
`screen.width/height` 是 `navigator` 里最容易露馅的一项。headless 模式没有虚拟屏，
Chromium 报的是内置的 800x600（`--window-size` 只改窗口、不改 screen），而真正
跑起来时是 Xvfb 的 1920x1080 —— 采出来的人格和实际运行时对不上，等于白采。

所以默认按 `MODE=vnc` 起，让 Xvfb 真的存在。镜像如果是 `WITH_VNC=0` 构建的，
vnc 模式会带着明确日志退出，这时降级到 headless 并把这件事写进告警，不装作没差。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import websockets

from app.services import kernel_image, kernel_scan
from app.services.fingerprint_caps import FingerprintSpec, KernelCaps, render

CONTAINER_PREFIX = "wv-fp-probe-"
# 容器内 CDP 端口。entrypoint 的默认值，且 socat 会把它桥到 0.0.0.0
CDP_PORT = 9222
# 冷启动要解压镜像层 + 起 Chromium，实测 1.5s，给足余量
STARTUP_TIMEOUT = 90.0
# 连上 CDP 后单条求值的超时
EVAL_TIMEOUT = 30.0
# 同时最多起几个采集容器：每个都是完整的 Chromium，开多了吃内存
MAX_CONCURRENT = 2
# 默认按 vnc 起（Xvfb 存在，screen 才是真实大小）；镜像没编 Xvfb 时降级到 headless
MODE_VNC = "vnc"
MODE_HEADLESS = "headless"

_slots = asyncio.Semaphore(MAX_CONCURRENT)


class ProbeError(RuntimeError):
    """采集失败。message 直接给人看，所以要写清楚下一步该做什么。"""


# 一次求值读全人格。用 JSON.stringify 回传，避免 CDP 的深结构序列化踩坑。
# 每一项都单独 try：某个 API 被内核关掉时不应该拖垮整次采集。
COLLECT_JS = r"""
(() => {
  const safe = (fn, fallback) => { try { return fn() } catch (e) { return fallback } };

  const webgl = safe(() => {
    const c = document.createElement('canvas');
    const ctx = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!ctx) return null;
    const dbg = ctx.getExtension('WEBGL_debug_renderer_info');
    return {
      vendor: dbg ? ctx.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : ctx.getParameter(ctx.VENDOR),
      renderer: dbg
        ? ctx.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
        : ctx.getParameter(ctx.RENDERER),
    };
  }, null);

  const canvasHash = safe(() => {
    const c = document.createElement('canvas');
    c.width = 220; c.height = 30;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60'; ctx.fillRect(0, 0, 100, 20);
    ctx.fillStyle = '#069'; ctx.fillText('WebWeaver 指纹探针', 2, 2);
    const data = c.toDataURL();
    let h = 0x811c9dc5;
    for (let i = 0; i < data.length; i++) {
      h ^= data.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
  }, null);

  return JSON.stringify({
    userAgent: navigator.userAgent,
    appVersion: navigator.appVersion,
    platform: navigator.platform,
    uaDataPlatform: navigator.userAgentData ? navigator.userAgentData.platform : null,
    uaDataMobile: navigator.userAgentData ? navigator.userAgentData.mobile : null,
    vendor: navigator.vendor,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory === undefined ? null : navigator.deviceMemory,
    maxTouchPoints: navigator.maxTouchPoints,
    webdriver: navigator.webdriver,
    language: navigator.language,
    languages: navigator.languages,
    timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone, null),
    timezoneOffset: new Date().getTimezoneOffset(),
    screen: {
      width: screen.width, height: screen.height,
      availWidth: screen.availWidth, availHeight: screen.availHeight,
      colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
    },
    devicePixelRatio: window.devicePixelRatio,
    outerWidth: window.outerWidth,
    outerHeight: window.outerHeight,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    webgl,
    canvasHash,
  });
})()
"""


@dataclass(frozen=True)
class ProbeResult:
    """一次采集的结果。`raw` 是浏览器里读到的原样快照。"""

    raw: dict[str, Any]
    seed: int | None
    duration: float
    image_ref: str
    # 镜像没有 Xvfb，降级用 headless 采的 —— 这时 screen 不是真实运行时的大小
    headless_fallback: bool = False

    @property
    def user_agent(self) -> str:
        return str(self.raw.get("userAgent") or "")

    @property
    def platform_family(self) -> str | None:
        return _family_of(self.raw)

    @property
    def platform_label(self) -> str:
        return _platform_label(self.raw)

    @property
    def resolution(self) -> str:
        screen = self.raw.get("screen") or {}
        width, height = screen.get("width"), screen.get("height")
        if width and height:
            return f"{width}x{height}"
        return ""

    @property
    def dpr(self) -> str:
        value = self.raw.get("devicePixelRatio")
        return f"{value:g}" if isinstance(value, (int, float)) else "1"

    @property
    def gpu(self) -> str | None:
        """GPU 型号，去掉 ANGLE 那圈前缀，只留人能读的部分。"""
        renderer = (self.raw.get("webgl") or {}).get("renderer")
        return shorten_gpu(renderer) if renderer else None

    @property
    def warnings(self) -> list[str]:
        """实测人格里明显矛盾 / 会被识破的地方。"""
        items = _consistency_warnings(self.raw)
        if self.headless_fallback:
            items.insert(
                0,
                "这个镜像没有编 Xvfb（WITH_VNC=0），按无头模式采集，"
                "screen 是 800x600 而不是真实运行时的 1920x1080",
            )
        return items




# ── 公开入口 ────────────────────────────────────────────────────────


async def collect(
    caps: KernelCaps,
    spec: FingerprintSpec,
    *,
    image_ref: str | None = None,
) -> ProbeResult:
    """按 spec 起容器采集一次人格。失败抛 ProbeError，文案可直接展示。"""
    if not caps.supported:
        raise ProbeError(caps.reason or f"{caps.engine_label} 不支持指纹，无法采集")

    rendered = render(spec, caps)
    if not rendered.payload and not rendered.env:
        # 什么都没配就采集也能跑（内核会随机一个人格），但结果对不上任何记录，
        # 没有意义。这里要求至少给一个种子或平台。
        raise ProbeError("没有可下发的指纹参数，先至少填一个种子或平台再采集")

    ref = image_ref or await asyncio.to_thread(_resolve_image, caps.slug)

    async with _slots:
        try:
            return await _collect(caps, rendered.env, ref, spec.seed, mode=MODE_VNC)
        except ProbeError as exc:
            # 镜像可能是 WITH_VNC=0 构建的，没有 Xvfb 就起不来 vnc 模式。
            # 这时退到 headless：能采到 GPU / canvas / UA，只有 screen 不准。
            if "WITH_VNC" not in str(exc):
                raise
            result = await _collect(caps, rendered.env, ref, spec.seed, mode=MODE_HEADLESS)
            return ProbeResult(
                raw=result.raw,
                seed=result.seed,
                duration=result.duration,
                image_ref=result.image_ref,
                headless_fallback=True,
            )


def _resolve_image(slug: str) -> str:
    """取本地最新的那个镜像引用。没有镜像就别浪费时间起容器了。"""
    versions = kernel_scan.scan_versions(slug)
    if not versions:
        raise ProbeError(
            f"本地没有 {slug} 的镜像，先去「内核管理」点「获取内核」拉下来再采集"
        )
    return versions[0].image_ref


async def _collect(
    caps: KernelCaps,
    env: dict[str, str],
    image_ref: str,
    seed: int | None,
    *,
    mode: str,
) -> ProbeResult:
    name = f"{CONTAINER_PREFIX}{secrets.token_hex(4)}"
    started = time.monotonic()
    try:
        port = await _start_container(name, env, image_ref, mode=mode)
        page_ws = await _wait_for_page(port, name)
        raw = await _evaluate(page_ws)
    finally:
        # --rm 只在容器自己退出时生效，异常路径下它是还在跑的，必须显式删
        await asyncio.to_thread(_remove, name)

    return ProbeResult(
        raw=raw,
        seed=seed,
        duration=round(time.monotonic() - started, 1),
        image_ref=image_ref,
    )


async def _start_container(
    name: str, env: dict[str, str], image_ref: str, *, mode: str
) -> int:
    args = [
        "run", "-d", "--rm",
        "--name", name,
        "-e", f"MODE={mode}",
    ]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    args += [
        # 让 Docker 分配宿主机端口，避开已在跑的实例（9222 大概率被占）
        "-p", f"127.0.0.1:0:{CDP_PORT}",
        image_ref,
    ]

    proc = await asyncio.to_thread(kernel_image.run, args, timeout=180)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ProbeError(
            f"采集容器启动失败：{detail[-1] if detail else f'退出码 {proc.returncode}'}"
        )

    return await _published_port(name)


async def _published_port(name: str) -> int:
    """问 Docker 要它实际分配的宿主机端口。"""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        proc = await asyncio.to_thread(
            kernel_image.run, ["port", name, str(CDP_PORT)], timeout=15
        )
        line = (proc.stdout or "").strip().splitlines()
        if proc.returncode == 0 and line:
            # 输出形如 127.0.0.1:32769，也可能多行（IPv4 + IPv6）
            try:
                return int(line[0].rsplit(":", 1)[1])
            except (IndexError, ValueError):
                pass
        await asyncio.sleep(0.3)
    raise ProbeError("采集容器没有映射出 CDP 端口，可能是镜像没有暴露 9222")


async def _wait_for_page(port: int, name: str) -> str:
    """等 Chromium 起来并拿到页面 target 的 WebSocket 地址。"""
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        targets = await _http_json(f"http://127.0.0.1:{port}/json/list")
        for target in targets or []:
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                return str(target["webSocketDebuggerUrl"])
        # 起来得太快时可能还没有页面 target，主动开一个
        created = await _http_json(
            f"http://127.0.0.1:{port}/json/new?url=about:blank", method="PUT"
        )
        if created and created.get("webSocketDebuggerUrl"):
            return str(created["webSocketDebuggerUrl"])
        await asyncio.sleep(0.5)

    logs = await asyncio.to_thread(
        kernel_image.run, ["logs", "--tail", "15", name], timeout=20
    )
    tail = "\n".join(filter(None, [(logs.stdout or "").strip(), (logs.stderr or "").strip()]))
    raise ProbeError(
        f"容器起来了但 CDP 一直没就绪（{STARTUP_TIMEOUT:.0f} 秒）。"
        + (f"容器日志：{tail[-400:]}" if tail else "容器没有输出日志")
    )


async def _evaluate(page_ws: str) -> dict[str, Any]:
    try:
        async with asyncio.timeout(EVAL_TIMEOUT):
            async with websockets.connect(
                page_ws, max_size=2**24, open_timeout=10, close_timeout=5
            ) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": COLLECT_JS,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                }))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get("id") != 1:
                        continue
                    result = message.get("result", {})
                    if "exceptionDetails" in result:
                        raise ProbeError(
                            f"浏览器里执行采集脚本报错：{result['exceptionDetails']}"
                        )
                    value = result.get("result", {}).get("value")
                    if not value:
                        raise ProbeError("浏览器没有返回指纹数据")
                    return json.loads(value)
    except TimeoutError as exc:
        raise ProbeError(f"读取指纹超时（{EVAL_TIMEOUT:.0f} 秒）") from exc
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        # 握手被拒、连接中途断开都会走这里。原始异常信息比较隐晦，
        # 补一句"该往哪查"，否则用户只看到一串 InvalidStatusCode。
        raise ProbeError(f"连不上浏览器的调试端口：{exc}") from exc


async def _http_json(url: str, *, method: str = "GET") -> Any:
    def fetch() -> Any:
        request = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.load(response)

    try:
        return await asyncio.to_thread(fetch)
    except (urllib.error.URLError, OSError, ValueError):
        # 容器还没起来时这里必然失败，属于正常轮询，交给调用方继续等
        return None


def _remove(name: str) -> None:
    try:
        kernel_image.run(["rm", "-f", name], timeout=30)
    except kernel_image.DockerError:
        # 容器已经没了（--rm 生效过）就不算错
        pass


# ── 快照解读 ────────────────────────────────────────────────────────

_FAMILY_MARKERS: tuple[tuple[str, str], ...] = (
    ("Android", "android"),
    ("iPhone", "ios"),
    ("iPad", "ios"),
    ("Macintosh", "macos"),
    ("Mac OS X", "macos"),
    ("Windows", "windows"),
    ("Linux", "linux"),
    ("X11", "linux"),
)


def _family_of(raw: dict[str, Any]) -> str | None:
    """从 UA 判平台族。UA 是最终事实，navigator.platform 反而容易被内核改。"""
    ua = str(raw.get("userAgent") or "")
    for marker, family in _FAMILY_MARKERS:
        if marker in ua:
            return family
    return None


_BROWSER_MARKERS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
)


def _platform_label(raw: dict[str, Any]) -> str:
    """给人看的平台描述，如 `Windows · Chrome 146`。"""
    ua = str(raw.get("userAgent") or "")
    family = _family_of(raw)
    os_label = {
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
        "android": "Android",
        "ios": "iOS",
    }.get(family or "", "未知平台")

    for marker, browser in _BROWSER_MARKERS:
        if marker in ua:
            tail = ua.split(marker, 1)[1]
            major = tail.split(".", 1)[0].split()[0] if tail else ""
            return f"{os_label} · {browser} {major}".strip()
    return os_label


def shorten_gpu(renderer: str) -> str:
    """`ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Laptop GPU (0x2520) Direct3D11 ...)`
    → `NVIDIA GeForce RTX 3060 Laptop GPU`

    括号里是「厂商, 型号 (设备号) 驱动API」。只保留型号，页面上放得下。
    """
    text = renderer.strip()
    if text.startswith("ANGLE (") and text.endswith(")"):
        text = text[len("ANGLE ("):-1]
    parts = [part.strip() for part in text.split(",")]
    model = parts[1] if len(parts) > 1 else parts[0]
    # 去掉型号尾部那一串设备号和 D3D11 描述
    model = model.split(" Direct3D")[0].split(" (0x")[0].strip()
    return model or renderer


def _consistency_warnings(raw: dict[str, Any]) -> list[str]:
    """找出会被风控一眼看穿的自相矛盾。

    这些不是「评分」，是确定的事实：webdriver 为 true 就一定会被识别，
    UA 说 Windows 而平台族说 Linux 就一定是假的。
    """
    warnings: list[str] = []

    if raw.get("webdriver") is True:
        warnings.append("navigator.webdriver 为 true，会被直接识别为自动化")

    family = _family_of(raw)
    platform = str(raw.get("platform") or "")
    expected = {
        "windows": ("Win32", "Win64", "Windows"),
        "macos": ("MacIntel", "Macintosh", "Mac"),
        "linux": ("Linux", "X11"),
        "android": ("Linux", "Android"),
        "ios": ("iPhone", "iPad", "iOS"),
    }.get(family or "")
    if family and platform and expected and not any(token in platform for token in expected):
        warnings.append(f"UA 说是 {family}，navigator.platform 却是 {platform}，两处对不上")

    renderer = str((raw.get("webgl") or {}).get("renderer") or "")
    if "SwiftShader" in renderer or "llvmpipe" in renderer:
        warnings.append("WebGL 走的是软件渲染（SwiftShader/llvmpipe），容器没显卡的典型特征")

    if raw.get("hardwareConcurrency") in (0, None):
        warnings.append("hardwareConcurrency 取不到，硬件并发指纹缺失")

    # 容器里的虚拟屏偶尔没铺开（Xvfb 没就绪、MODE 回落等），此时 screen 是
    # Chromium 的兜底值 800x600。这个数字在桌面系统上早就不存在了，
    # 拿它当「实测人格」比不采集更糟 —— 直接照抄会得到一个人人可疑的分辨率。
    screen = raw.get("screen") or {}
    width, height = screen.get("width"), screen.get("height")
    if (
        family in ("windows", "macos", "linux")
        and isinstance(width, int)
        and isinstance(height, int)
        and (width <= 1024 or height <= 768)
    ):
        warnings.append(
            f"screen 只有 {width}x{height}，桌面系统上几乎没有这种分辨率，"
            "多半是采集时虚拟屏没铺开（检查容器是否以 MODE=vnc 启动）。"
            "这条实测值不要直接信"
        )

    return warnings
