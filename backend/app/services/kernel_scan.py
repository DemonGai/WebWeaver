"""内核识别：一个内核有哪些版本，完全由本地 Docker 镜像决定。

tag 命名约定（见仓库 ``browser_engine/DOCKERHUB.md``）::

    <registry>:cloakbrowser                    <- 滚动 tag，指向该内核最近一次构建
    <registry>:cloakbrowser-146.0.7680.177.5   <- 固定 tag，钉死一个版本

两个 tag 常常指向同一个镜像（``image_id`` 相同），所以扫描时按 ``image_id``
**去重**：一个版本只出现一次，把它身上挂的所有 tag 收进 ``tags``。

版本号优先信镜像自带的 OCI 标签 ``org.opencontainers.image.version``
（Dockerfile 里写了），滚动 tag 的名字里没有版本号，只能从标签读；
标签缺失时才退回从 tag 名里切。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import BACKEND_ROOT, settings
from app.schemas.kernels import KernelVersion
from app.services import kernel_image
from app.services.kernel_image import ImageInfo

# 内核说明文档放在仓库根的 browser_engine/<slug>/README.md，不在 backend 下面
REPO_ROOT = BACKEND_ROOT.parent
DOCS_ROOT = REPO_ROOT / "browser_engine"
README = "README.md"


def registry() -> str:
    return settings.kernel_image_registry


def engine_slug(name: str) -> str:
    """内核名 → 目录名/镜像 tag 前缀：``CloakBrowser`` → ``cloakbrowser``。"""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """把版本号切成可比较的元组。

    数字段按数值比、字母段按字典序比，这样 ``148.0.7778.9 < 148.0.7778.10``
    不会被当成字符串比出 ``"10" < "9"`` 的笑话，``0.9.4-beta`` 也能排。
    """
    parts = re.findall(r"\d+|[a-zA-Z]+", version)
    return tuple((0, int(p)) if p.isdigit() else (1, p.lower()) for p in parts)


def human_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit != "GB" else f"{value:.1f} GB"
        value /= 1024
    return f"{value:.1f} GB"


def pretty_time(value: str | None) -> str | None:
    """UTC 的 ISO 时间串 → 本地时区的 ``YYYY-MM-DD HH:MM``。

    Docker 给的是 ``2026-11-10T13:50:54.693761427Z``；直接截前 16 位会显示成 UTC，
    和用户看到的「22 小时前」对不上。
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:16].replace("T", " ") or None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def parse_tag(tag: str, slugs: Iterable[str]) -> tuple[str, str | None]:
    """``cloakbrowser-146.0.7680.177.5`` → ``("cloakbrowser", "146.0.7680.177.5")``。

    按 slug 从长到短匹配，否则 ``fingerprint-chromium`` 会被更短的
    ``chromium`` 之类截走。返回的版本为 None 表示这是滚动 tag。
    """
    ordered = sorted({slug for slug in slugs if slug}, key=len, reverse=True)
    lowered = tag.lower()
    for slug in ordered:
        if lowered == slug:
            return slug, None
        if lowered.startswith(f"{slug}-"):
            rest = tag[len(slug) + 1 :]
            if rest:
                return slug, rest
    return engine_slug(tag), None


def _version_of(image: ImageInfo, tag_version: str | None) -> str:
    """版本号：先信镜像标签，再信 tag 名，最后退成 latest。"""
    return image.version or tag_version or "latest"


def scan_versions(
    engine_name: str, *, images: list[ImageInfo] | None = None
) -> list[KernelVersion]:
    """某个内核在本地镜像仓库里的全部版本，按版本号从新到旧。

    ``images`` 可传入已拉好的镜像清单，避免一页四个内核把 ``docker image ls``
    跑四遍。
    """
    slug = engine_slug(engine_name)
    items = images if images is not None else kernel_image.list_images(registry())
    slugs = {slug}

    grouped: dict[str, list[tuple[ImageInfo, str, str | None]]] = {}
    for image in items:
        owner, tag_version = parse_tag(image.tag, slugs)
        if owner != slug:
            continue
        # 同一 image_id 的多个 tag 归到一组；镜像 id 缺失时用 digest 兜底
        grouped.setdefault(image.image_id or image.ref, []).append((image, image.tag, tag_version))

    versions: list[KernelVersion] = []
    for group in grouped.values():
        first = group[0][0]
        # 固定 tag 优先当首选引用：滚动 tag 会被下次构建覆盖，不适合钉住
        fixed = [entry for entry in group if entry[2]]
        chosen = (fixed or group)[0]
        chosen_image, chosen_tag, tag_version = chosen
        tags = sorted({entry[1] for entry in group})

        versions.append(
            KernelVersion(
                version=_version_of(first, tag_version),
                tag=chosen_tag,
                image_ref=chosen_image.ref,
                image_id=chosen_image.short_id,
                digest=first.digest,
                size=human_size(first.size_bytes),
                size_bytes=first.size_bytes,
                created_at=pretty_time(first.created_at),
                rolling=any(entry[2] is None for entry in group),
                tags=tags,
                pinned=bool(fixed),
                arch=first.arch,
            )
        )

    versions.sort(key=lambda item: version_key(item.version), reverse=True)
    return versions


def readme_path(engine_name: str) -> Path:
    return DOCS_ROOT / engine_slug(engine_name) / README


def readme(engine_name: str, limit: int = 256 * 1024) -> str | None:
    """读内核目录里的 README（端口、环境变量、构建说明）；读不到返回 None。"""
    path = readme_path(engine_name)
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) > limit:
        return text[:limit] + "\n\n…（正文过长，已截断）"
    return text
