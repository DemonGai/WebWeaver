"""内核文件目录扫描。

目录约定（``settings.kernel_root``，默认 ``backend/browser_engine``）::

    browser_engine/
      cloakbrowser/                  <- 引擎目录，名字是内核名的 slug
        128.0.6613.2/                <- 版本目录，目录名就是版本号
          meta.json                  <- 版本标记文件，由内核下载器写入
          chrome.exe ...             <- 真实二进制（本仓库不自带）
        128.0.6613.5/
          meta.json
      camoufox/
        128.0.3/
          meta.json

判断"是否已下载"的口径：版本目录里存在**能解析的 meta.json**。二进制体积太大，
不适合进仓库，所以 meta.json 才是可提交的版本标记；真实部署时下载器会把整个
发行包解压进同一个目录，meta.json 一并写入。

meta.json 允许的字段（都可缺）::

    {
      "version": "128.0.6613.2",
      "base": "Chromium 128.0.6613.120",
      "arch": "x64",
      "channel": "stable",
      "size_mb": 412,
      "released_at": "2026-10-18",
      "packaged_at": "2026-10-19T09:12:00+08:00",
      "source": "https://github.com/CloakHQ/CloakBrowser/releases"
    }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import BACKEND_ROOT, settings
from app.schemas.kernels import KernelVersion

# meta.json 里不认识的值不报错，只忽略；缺字段各有默认
META_FILE = "meta.json"


def kernel_root() -> Path:
    """内核根目录的绝对路径（相对路径以 backend/ 为基准）。"""
    root = Path(settings.kernel_root)
    return root if root.is_absolute() else BACKEND_ROOT / root


def engine_slug(name: str) -> str:
    """内核名 → 目录名：``fingerprint-chromium`` 保持原样，``CloakBrowser`` → ``cloakbrowser``。"""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def engine_dir(name: str) -> Path:
    return kernel_root() / engine_slug(name)


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """把版本号切成可比较的元组。

    数字段按数值比、字母段按字典序比，这样 ``128.0.6613.9 < 128.0.6613.10``
    不会被当成字符串比出 ``"10" < "9"`` 的笑话，``0.9.4-beta`` 也能排。
    """
    parts = re.findall(r"\d+|[a-zA-Z]+", version)
    return tuple((0, int(p)) if p.isdigit() else (1, p.lower()) for p in parts)


def human_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    units = ("B", "KB", "MB", "GB")
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit != "GB" else f"{value:.1f} GB"
        value /= 1024
    return f"{value:.1f} GB"


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


@dataclass(frozen=True)
class _Meta:
    version: str | None = None
    base: str | None = None
    arch: str | None = None
    channel: str | None = None
    size_mb: float | None = None
    released_at: str | None = None
    packaged_at: str | None = None
    source: str | None = None


def _read_meta(path: Path) -> tuple[_Meta | None, str | None]:
    """读 meta.json；返回 (内容, 错误提示)。"""
    meta_path = path / META_FILE
    if not meta_path.is_file():
        return None, "缺少 meta.json，下载器可能没写完"
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"meta.json 无法解析：{exc.__class__.__name__}"
    if not isinstance(raw, dict):
        return None, "meta.json 结构不对（应为对象）"

    def text(key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    size = raw.get("size_mb")
    try:
        size_mb = float(size) if size is not None else None
    except (TypeError, ValueError):
        size_mb = None

    return (
        _Meta(
            version=text("version"),
            base=text("base"),
            arch=text("arch"),
            channel=text("channel"),
            size_mb=size_mb,
            released_at=text("released_at"),
            packaged_at=text("packaged_at"),
            source=text("source"),
        ),
        None,
    )


def scan_versions(engine_name: str) -> list[KernelVersion]:
    """扫描某个引擎目录下的全部版本，按版本号从新到旧排序。"""
    directory = engine_dir(engine_name)
    if not directory.is_dir():
        return []

    versions: list[KernelVersion] = []
    for item in directory.iterdir():
        if not item.is_dir() or item.name.startswith("."):
            continue

        meta, error = _read_meta(item)
        size_bytes = int(meta.size_mb * 1024 * 1024) if meta and meta.size_mb else _dir_size(item)

        # 空目录比"缺 meta"更值得单独说：多半是下载中断，不是忘了写标记
        warning = error
        if not any(item.iterdir()):
            warning = "版本目录为空，下载器可能没写完"

        versions.append(
            KernelVersion(
                version=meta.version if meta and meta.version else item.name,
                base=meta.base if meta else None,
                arch=meta.arch if meta else None,
                channel=meta.channel if meta else None,
                size=human_size(size_bytes),
                released_at=meta.released_at if meta else None,
                packaged_at=pretty_time(meta.packaged_at) if meta else _mtime(item),
                source=meta.source if meta else None,
                path=str(item),
                ready=error is None,
                warning=warning,
            )
        )

    versions.sort(key=lambda v: version_key(v.version), reverse=True)
    return versions


def _mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return None


def pretty_time(value: str | None) -> str | None:
    """把 ISO 时间串压成 ``YYYY-MM-DD HH:MM``：表格里塞下 ``T10:03:00+08:00`` 只会换行。"""
    if not value:
        return None
    if "T" not in value:
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
