"""内核获取与落盘：pip 安装 / 归档下载 → ``browser_engine/<slug>/<version>/``。

四种引擎的上游形态各不相同，但落盘口径只有一条，所以这里是**一个安装器 + 三种策略**：

- ``pip``：在临时 venv 里装官方包，调它自己的 CLI 把二进制拉进缓存目录，
  再把包含可执行文件的那层目录整体搬进版本目录。CloakBrowser 走这条。
- ``archive``：下载官方便携包 → 校验 sha256 → 解压（拒绝目录穿越）→ 搬进版本目录。
  Camoufox、fingerprint-chromium 走这条。
- ``manual``：不代下（第三方构建、需要登录的源），提示用户手动下载后用导入器登记。

落盘顺序刻意做成「先占位目录 → 整体移动 → 最后写 meta.json」：
扫描器只认 meta.json，所以中途断电/失败不会留下一个看起来能用的残缺版本。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.core.config import settings
from app.schemas.kernels import EnginePackage, InstallJob
from app.services import kernel_profile, kernel_scan

MAX_JOBS = 20
META_FILE = kernel_scan.META_FILE
STAGING = ".staging"  # 以点开头，扫描器会跳过
CHUNK = 1024 * 1024
USER_AGENT = "WebWeaver/0.1 (kernel installer)"
# aria2 的进度行形如 [#1e839e 12MiB/535MiB(2%) CN:16 DL:401KiB ETA:22m14s]
ARIA2_PERCENT = re.compile(r"\((\d+)%\)")
# 单条 500MB+ 的连接在 400KB/s 下约 20 分钟，留一倍余量
ARIA2_TIMEOUT = 40 * 60

_jobs: dict[str, InstallJob] = {}
_lock = asyncio.Lock()
_semaphore = asyncio.Semaphore(1)  # 一次只装一个：400MB 起的包，并发会把带宽打满


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def jobs() -> list[InstallJob]:
    return sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)


def job(job_id: str) -> InstallJob | None:
    return _jobs.get(job_id)


def _remember(item: InstallJob) -> None:
    _jobs[item.id] = item
    if len(_jobs) <= MAX_JOBS:
        return
    finished = [j for j in _jobs.values() if j.status != "running"]
    for stale in sorted(finished, key=lambda j: j.started_at)[: len(_jobs) - MAX_JOBS]:
        _jobs.pop(stale.id, None)


def _staging_dir(slug: str, version: str, job_id: str) -> Path:
    path = kernel_scan.kernel_root() / STAGING / f"{slug}-{version}-{job_id[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _purge(path: Path) -> None:
    """删掉临时目录。删不掉只记日志，绝不让收尾动作拖死进程。

    解压后的 Chromium 有六七百个文件，某些环境（沙箱、杀软、被占用的 dll）会在
    rmtree 时抛出 ``BaseException`` 一类的东西——``ignore_errors=True`` 只吞
    ``OSError``，拦不住 ``SystemExit``。任务这时已经落盘成功，不该因为清理失败而
    把整个服务带下去。
    """
    try:
        shutil.rmtree(path, ignore_errors=True)
    except BaseException:  # noqa: BLE001 - 清理失败不该影响任务结果
        logger.warning("临时目录没能自动清理，可手动删除：{}", path)


# ── 可测的纯逻辑 ──────────────────────────────────────────────────────


def safe_extract(archive: Path, dest: Path) -> None:
    """解压 zip，拒绝绝对路径与 ``..``：压缩包可以由任何人上传，不能信。"""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(root)):
                raise ValueError(f"压缩包里有越界路径，已拒绝：{member.filename}")
        zf.extractall(dest)


def find_executable(root: Path, name: str, max_depth: int = 6) -> Path | None:
    """在目录里找可执行文件，限制深度避免在 1GB 的解压结果里漫游。"""
    root = root.resolve()
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).relative_to(root).parts)
        if depth >= max_depth:
            dirs[:] = []
            continue
        for filename in files:
            if filename.lower() == name.lower():
                return Path(current) / filename
    return None


def dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def install_tree(source: Path, target: Path, meta: dict) -> int:
    """把已经准备好的目录搬进版本目录，最后写 meta.json。

    meta.json 是扫描器认的完工标记，所以它必须是最后一步写的那个文件。
    返回落盘后的字节数。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        _purge(target)
    shutil.copytree(source, target, dirs_exist_ok=True)

    size_bytes = dir_size(target)
    payload = dict(meta)
    payload.setdefault("packaged_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    # 原始字节留着：四舍五入到 MB 会把小目录记成 0，扫描时会以为是空版本
    payload["size_bytes"] = size_bytes
    payload["size_mb"] = round(size_bytes / 1024 / 1024, 1)
    (target / META_FILE).write_text(
        _json_dump(payload),
        encoding="utf-8",
    )
    return size_bytes


def _json_dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ── 任务执行 ──────────────────────────────────────────────────────────


async def start(slug: str, version: str, os_name: str, arch: str) -> InstallJob:
    """建任务并立刻返回，真正的下载/安装丢到后台。"""
    loaded = kernel_profile.load(slug)
    if loaded.profile is None:
        raise ValueError(loaded.error or "引擎档案不可用，无法判断下载方式")

    spec = kernel_profile.find_version(loaded.profile, version)
    if spec is None:
        raise ValueError(f"档案里没有登记版本 {version}，请先在 engine.json 里补一条")

    package = kernel_profile.pick_package(spec, loaded.profile, os_name, arch)
    if package is None:
        raise ValueError(f"{version} 没有适用于 {os_name}/{arch} 的包")

    item = InstallJob(
        id=uuid.uuid4().hex,
        slug=slug,
        version=version,
        kind=package.kind,
        started_at=_now(),
        message="排队中",
    )
    _remember(item)
    asyncio.create_task(_run(item, loaded.profile, spec, package))
    return item


def _set(item: InstallJob, progress: float, message: str) -> None:
    item.progress = max(0.0, min(1.0, progress))
    item.message = message


async def _run(item: InstallJob, profile, spec, package: EnginePackage) -> None:
    stage = _staging_dir(item.slug, item.version, item.id)
    try:
        async with _semaphore:
            _set(item, 0.02, "准备临时目录")
            if package.kind == "manual":
                raise ValueError("这个版本只有手动下载链接，请下载后用导入器登记")
            if package.kind == "pip":
                payload = await _acquire_pip(item, profile, package, stage)
            else:
                payload = await _acquire_archive(item, package, stage)

            _set(item, 0.9, "写入版本目录")
            target = kernel_scan.engine_dir(item.slug) / item.version
            size = install_tree(payload["source"], target, payload["meta"])
            _set(item, 1.0, f"完成，落盘 {kernel_scan.human_size(size)}")
        item.status = "success"
        item.finished_at = _now()
    except Exception as exc:  # noqa: BLE001 - 任务失败要回传给页面，不能吞
        item.status = "failed"
        item.error = str(exc) or exc.__class__.__name__
        item.message = "失败"
        item.finished_at = _now()
    finally:
        _purge(stage)


async def _shell(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = 1800,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """跑外部命令，把输出逐行喂给回调，失败时带最后几行进异常。

    两个都必须做：

    - **超时**：官方 CLI 拉二进制时连接卡住不会自己退出（实测卡在 22MB 十几分钟），
      没有超时任务会永远停在「下载中」，用户只能重启服务；
    - **实时输出**：200MB 以上的下载，卡住时能看见它停在哪个进度，比一句
      「下载内核二进制」有信息量。
    """
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    lines: list[str] = []

    async def pump() -> None:
        if process.stdout is None:
            return
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace").rstrip()
            if not text:
                continue
            lines.append(text)
            if len(lines) > 200:  # 只需要尾巴，但别让它无限涨
                lines.pop(0)
            if on_line:
                on_line(text)

    try:
        await asyncio.wait_for(asyncio.gather(pump(), process.wait()), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        minutes = max(1, timeout // 60)
        raise RuntimeError(
            f"命令超过 {minutes} 分钟没有完成，大概卡在网络上了（{args[0]}）；"
            "已经终止，可以重试或换个网络环境"
        ) from None

    if process.returncode != 0:
        tail = "\n".join(lines[-4:])
        raise RuntimeError(f"命令执行失败（{args[0]}）：{tail or '无输出'}")


def _find_uv() -> str | None:
    """找 uv：服务进程的 PATH 常常没有它，所以要顺着常见安装位置找一遍。"""
    candidates = [
        shutil.which("uv"),
        os.path.expanduser("~/.local/bin/uv"),
        os.path.expanduser("~/.local/bin/uv.exe"),
        os.path.expanduser("~/.cargo/bin/uv"),
        os.path.expanduser("~/.cargo/bin/uv.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))


async def _acquire_pip_direct(item: InstallJob, acquire, binary_url: str, stage: Path) -> dict:
    """直取二进制：档案给了直链就别走官方 CLI 了。

    CLI 的价值是版本解析和签名校验，但它下载是单连接（~30 KB/s）。这个 zip 解开
    就是完整的 Chromium 目录（``chrome.exe`` 在根下），交给 aria2 下能快十几倍。
    """
    url = binary_url.format(version=item.version)
    archive = stage / "binary.zip"
    _set(item, 0.06, "连接二进制源")
    size, sha = await _download(item, url, archive)

    _set(item, 0.72, "校验完整性")
    if not zipfile.is_zipfile(archive):
        raise RuntimeError("下载到的不是有效 zip 包，可能拿到了错误页；去源仓库确认链接")

    _set(item, 0.8, "解压")
    extract_dir = stage / "extract"
    await asyncio.to_thread(safe_extract, archive, extract_dir)

    _set(item, 0.88, "定位可执行文件")
    executable = (acquire.executable if acquire else None) or "chrome.exe"
    found = find_executable(extract_dir, executable)
    if not found:
        raise RuntimeError(f"解压后没找到 {executable}，包结构和档案不符")

    return {
        "source": found.parent,
        "meta": {
            "version": item.version,
            "kind": "pip",
            "installer": acquire.installer if acquire else None,
            "executable": executable,
            "source": url,
            "sha256": sha,
            "archive_size_mb": round(size / 1024 / 1024, 1),
            "acquired_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }


async def _acquire_pip(item: InstallJob, profile, package: EnginePackage, stage: Path) -> dict:
    """pip 通道：装包 → 跑官方 CLI 取二进制 → 在缓存目录里找到它。

    建环境一律用 ``python -m venv``（自带 pip，任何 Python 都有），
    uv 只作为加速手段：装包时若找得到 uv 就用它，找不到退回 venv 自带的 pip。
    """
    acquire = profile.acquire
    installer = package.installer or (acquire.installer if acquire else None)
    if not installer:
        raise ValueError("档案里没写 pip 包名（installer）")

    # 档案给了二进制直链 → 直接下 zip，不装包也不跑 CLI（快十几倍）
    if acquire and acquire.binary_url:
        return await _acquire_pip_direct(item, acquire, acquire.binary_url, stage)

    pin = package.pin or (acquire.pin if acquire else None)
    target_spec = f"{installer}=={pin}" if pin else installer
    venv = stage / "venv"
    python = _venv_python(venv)

    _set(item, 0.12, f"创建临时环境 · {target_spec}")
    await _shell([sys.executable, "-m", "venv", str(venv)], timeout=180)

    _set(item, 0.25, f"安装 {target_spec}")
    uv = _find_uv()
    index = ["--index-url", settings.kernel_pip_index] if settings.kernel_pip_index else []
    if uv:
        await _shell(
            [uv, "pip", "install", "--python", str(python), *index, target_spec], timeout=600
        )
    else:
        await _shell([str(python), "-m", "pip", "install", *index, target_spec], timeout=600)

    fetch = list(acquire.fetch) if acquire and acquire.fetch else ["-m", installer, "install"]
    _set(item, 0.45, "下载内核二进制")
    await _shell(
        [str(python), *fetch],
        timeout=900,
        on_line=lambda text: _set(item, 0.45, text[:120]),
    )

    _set(item, 0.75, "定位二进制")
    executable = (acquire.executable if acquire else None) or "chrome.exe"
    roots = [_expand(p) for p in (acquire.cache_dirs if acquire else [])]
    roots = [p for p in roots if p.is_dir()] or [venv]

    for root in roots:
        found = find_executable(root, executable)
        if found:
            return {
                "source": found.parent,
                "meta": {
                    "version": item.version,
                    "kind": "pip",
                    "installer": installer,
                    "pin": pin,
                    "executable": executable,
                    "source": f"pip:{installer}",
                    "acquired_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
            }
    searched = "、".join(str(p) for p in roots)
    raise RuntimeError(f"装完了但没在 {searched} 里找到 {executable}，把路径补进档案的 cache_dirs")


def _apply_mirror(url: str) -> str:
    """给 github 链接套加速前缀。"""
    mirror = (settings.kernel_download_mirror or "").strip()
    if not mirror or "github.com" not in url:
        return url
    return f"{mirror.rstrip('/')}/{url}"


def _find_aria2() -> str | None:
    """找 aria2c：优先项目自带的 ``backend/bin``，其次 PATH。"""
    exe = "aria2c.exe" if os.name == "nt" else "aria2c"
    root = Path(__file__).resolve().parents[2]
    candidates = [root / "bin" / exe, root / "bin" / "aria2c", shutil.which("aria2c")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


async def _download_aria2(
    item: InstallJob,
    binary: str,
    url: str,
    dest: Path,
    base: float = 0.05,
    span: float = 0.6,
) -> None:
    """用 aria2 分段并发下载。

    单条连接会被限速到 ~30 KB/s（直连、走代理、走加速站都一样，实测），536MB
    要 5 小时，看起来就是卡死。aria2 开 16 条连接后同一文件能到 400~800 KB/s。
    进度从 aria2 的 summary 行里读（``[#id 12MiB/535MiB(2%) CN:16 ...]``）。
    """
    args = [
        binary,
        "-x16",
        "-s16",
        "-k1M",
        "-c",  # 支持断点续传：上次中断的 .aria2 控制文件还在就能接着下
        "--file-allocation=none",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--show-console-readout=false",  # 关掉 \r 刷新的进度行，只留可解析的 summary
        "--summary-interval=3",
        "--console-log-level=warn",
        "--download-result=hide",
        "--max-tries=3",
        "--retry-wait=2",
        "--timeout=60",
        "-d",
        str(dest.parent),
        "-o",
        dest.name,
        url,
    ]
    process = await asyncio.create_subprocess_exec(
        *args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )

    async def pump() -> None:
        if process.stdout is None:
            return
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            match = ARIA2_PERCENT.search(raw.decode("utf-8", errors="replace"))
            if match:
                percent = min(int(match.group(1)), 100)
                _set(item, base + span * percent / 100, f"下载中 {percent}%（16 连接）")

    try:
        await asyncio.wait_for(asyncio.gather(pump(), process.wait()), timeout=ARIA2_TIMEOUT)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("下载超过 40 分钟仍未完成，已中止；可重新点一次续传") from None

    if process.returncode != 0:
        raise RuntimeError(f"aria2 下载失败（退出码 {process.returncode}），换个网络或加速站再试")


def _download_single(item: InstallJob, url: str, dest: Path) -> None:
    """单连接下载，aria2 不可用时的兜底。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - 地址来自人工维护的档案
        total = int(response.headers.get("Content-Length") or 0)
        with dest.open("wb") as handle:
            written = 0
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                if total:
                    # 下载占整体进度的 0.05~0.65
                    _set(item, 0.05 + 0.6 * written / total, f"下载中 {written * 100 // total}%")


async def _download(item: InstallJob, url: str, dest: Path) -> tuple[int, str]:
    """下载内核包并算 sha256。有 aria2 走多连接，没有退回单连接。"""
    source = _apply_mirror(url)
    binary = _find_aria2()
    if binary:
        await _download_aria2(item, binary, source, dest)
    else:
        await asyncio.to_thread(_download_single, item, source, dest)

    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("下载结束但文件为空，可能拿到了错误页；去源仓库确认链接")

    digest = hashlib.sha256()
    size = 0
    with dest.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK * 4)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


async def _acquire_archive(item: InstallJob, package: EnginePackage, stage: Path) -> dict:
    if not package.url:
        raise ValueError("这个版本没有可下载地址（url 为空）")

    archive = stage / "package.zip"
    _set(item, 0.05, "连接下载源")
    size, sha = await _download(item, package.url, archive)

    _set(item, 0.72, "校验完整性")
    if package.sha256:
        if sha.lower() != package.sha256.lower():
            raise RuntimeError(f"sha256 不匹配：期望 {package.sha256[:12]}…，实际 {sha[:12]}…")
    if not zipfile.is_zipfile(archive):
        raise RuntimeError("下载到的不是有效 zip 包，可能拿到了错误页；去源仓库确认链接")

    _set(item, 0.8, "解压")
    extract_dir = stage / "extract"
    await asyncio.to_thread(safe_extract, archive, extract_dir)

    _set(item, 0.86, "定位可执行文件")
    loaded = kernel_profile.load(item.slug)
    executable = None
    if loaded.profile and loaded.profile.acquire:
        executable = loaded.profile.acquire.executable

    source = extract_dir
    if executable:
        found = find_executable(extract_dir, executable)
        if not found:
            raise RuntimeError(f"解压后没找到 {executable}，包结构和档案不符")
        source = found.parent
    else:
        children = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(children) == 1:
            source = children[0]

    return {
        "source": source,
        "meta": {
            "version": item.version,
            "kind": "archive",
            "executable": executable,
            "source": package.url,
            "sha256": sha,
            "archive_size_mb": round(size / 1024 / 1024, 1),
            "acquired_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }


def default_platform() -> tuple[str, str]:
    """当前机器的大致平台标识，页面默认值用它。"""
    if sys.platform.startswith("win"):
        return "windows", "x64"
    if sys.platform == "darwin":
        return "macos", "x64"
    return "linux", "x64"


__all__ = [
    "MAX_JOBS",
    "default_platform",
    "dir_size",
    "find_executable",
    "install_tree",
    "job",
    "jobs",
    "safe_extract",
    "start",
]
