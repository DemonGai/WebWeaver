"""引擎档案读取：``browser_engine/<slug>/engine.json`` + 同目录 ``README.md``。

档案是人工维护的（介绍、优劣势、下载源、可下载版本清单），所以读取这一层必须
**宽容**：文件缺失、JSON 写坏、字段类型不对，都不能让整个页面 500，而是退化成
「没有档案」并由调用方用台账数据兜底。

按 mtime 缓存解析结果：改完 json 不用重启服务，刷新页面就生效；文件没动时不重复读盘。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.schemas.kernels import EnginePackage, EngineProfile, EngineVersionSpec
from app.services.kernel_scan import engine_dir

PROFILE_FILE = "engine.json"
DOCS_FILE = "README.md"
DOCS_MAX_BYTES = 256 * 1024  # 正文再大也不该走接口，防止把畸形文件整个读进内存


@dataclass(frozen=True)
class ProfileLoad:
    profile: EngineProfile | None
    ok: bool
    error: str | None
    path: Path


_cache: dict[str, tuple[float, ProfileLoad]] = {}


def profile_path(name: str) -> Path:
    return engine_dir(name) / PROFILE_FILE


def docs_path(name: str) -> Path:
    return engine_dir(name) / DOCS_FILE


def _invalid(path: Path, error: str) -> ProfileLoad:
    return ProfileLoad(profile=None, ok=False, error=error, path=path)


def load(name: str) -> ProfileLoad:
    """读档案；任何异常都折成 ``ok=False + error``，不抛。"""
    path = profile_path(name)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _invalid(path, f"目录里没有 {PROFILE_FILE}，页面用台账数据兜底")

    cached = _cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result = _invalid(path, f"{PROFILE_FILE} 不是合法 JSON：第 {exc.lineno} 行 {exc.msg}")
    except OSError as exc:
        result = _invalid(path, f"{PROFILE_FILE} 读取失败：{exc.strerror or exc}")
    else:
        if not isinstance(raw, dict):
            result = _invalid(path, f"{PROFILE_FILE} 顶层应该是对象")
        else:
            try:
                result = ProfileLoad(
                    profile=EngineProfile.model_validate(raw),
                    ok=True,
                    error=None,
                    path=path,
                )
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(part) for part in first["loc"]) or "根"
                result = _invalid(path, f"{PROFILE_FILE} 字段 {where}：{first['msg']}")

    _cache[str(path)] = (mtime, result)
    return result


def docs(name: str) -> str | None:
    """读 README.md 正文；超过上限截断，读不到就返回 None。"""
    path = docs_path(name)
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) > DOCS_MAX_BYTES:
        return text[:DOCS_MAX_BYTES] + "\n\n…（正文过长，已截断）"
    return text


def find_version(profile: EngineProfile | None, version: str) -> EngineVersionSpec | None:
    if profile is None:
        return None
    for item in profile.versions:
        if item.version == version:
            return item
    return None


def pick_package(
    spec: EngineVersionSpec | None,
    profile: EngineProfile | None,
    os_name: str,
    arch: str,
) -> EnginePackage | None:
    """按平台挑一个包：先精确匹配 os+arch，再退到 ``any``。

    平台标为 any 的包（比如 pip）永远可选，因为 pip 自己能挑对 wheel。
    """
    if spec is None:
        return None
    candidates = list(spec.packages)
    if profile and profile.acquire and profile.acquire.kind == "pip":
        # 档案在版本级没写包时，用引擎级配置兜底
        candidates.append(
            EnginePackage(
                kind="pip",
                installer=profile.acquire.installer,
                pin=profile.acquire.pin,
                note=profile.acquire.note,
            )
        )
    if not candidates:
        return None

    def score(pkg: EnginePackage) -> tuple[int, int]:
        if pkg.os == "any" and pkg.arch == "any":
            return (0, 0)
        same_os = 1 if pkg.os in (os_name, "any") else -1
        same_arch = 1 if pkg.arch in (arch, "any") else -1
        return (same_os, same_arch)

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    if score(best)[0] < 0:
        return None
    return best
