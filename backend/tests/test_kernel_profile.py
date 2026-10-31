"""引擎档案与安装落盘的单元测试（不碰数据库、不联网）。"""

from __future__ import annotations

import json
import zipfile

import pytest

from app.core.config import settings
from app.services import kernel_install, kernel_profile, kernel_scan

PROFILE = {
    "schema": 1,
    "name": "CloakBrowser",
    "engine": "Chromium",
    "tagline": "主力内核",
    "pros": ["C++ 层补丁"],
    "cons": ["只能 pip 装"],
    "acquire": {
        "kind": "pip",
        "installer": "cloakbrowser",
        "pin": "0.5.10",
        "fetch": ["-m", "cloakbrowser", "install"],
        "cache_dirs": ["~/.cloakbrowser"],
        "executable": "chrome.exe",
    },
    "versions": [
        {
            "version": "151.0.7922.108.3",
            "channel": "stable",
            "packages": [
                {"kind": "pip", "installer": "cloakbrowser", "pin": "0.5.10"},
                {
                    "kind": "archive",
                    "os": "windows",
                    "arch": "x64",
                    "url": "https://example.com/a.zip",
                    "sha256": "abc",
                },
            ],
        }
    ],
}


@pytest.fixture
def root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "kernel_root", str(tmp_path))
    # 缓存按 mtime 记，不同用例复用同一路径时需要清掉，避免读到上一个用例的结果
    kernel_profile._cache.clear()
    return tmp_path


def _write_profile(root, slug: str, payload: object) -> None:
    directory = root / slug
    directory.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (directory / "engine.json").write_text(text, encoding="utf-8")


def test_loads_profile_and_resolves_version(root) -> None:
    _write_profile(root, "CloakBrowser", PROFILE)

    loaded = kernel_profile.load("CloakBrowser")

    assert loaded.ok is True
    assert loaded.error is None
    assert loaded.profile is not None
    assert loaded.profile.tagline == "主力内核"
    assert loaded.profile.acquire is not None
    assert loaded.profile.acquire.kind == "pip"

    spec = kernel_profile.find_version(loaded.profile, "151.0.7922.108.3")
    assert spec is not None
    assert kernel_profile.find_version(loaded.profile, "9.9.9") is None


def test_missing_profile_degrades_without_raising(root) -> None:
    loaded = kernel_profile.load("camoufox")

    assert loaded.ok is False
    assert loaded.profile is None
    assert "engine.json" in (loaded.error or "")


def test_broken_json_reports_line_instead_of_crashing(root) -> None:
    _write_profile(root, "CloakBrowser", '{"name": "CloakBrowser",}')

    loaded = kernel_profile.load("CloakBrowser")

    assert loaded.ok is False
    assert loaded.profile is None
    assert "合法 JSON" in (loaded.error or "")


def test_unknown_fields_are_tolerated(root) -> None:
    # 档案是人工维护的，多写一个字段不该让整页挂掉
    payload = dict(PROFILE, unknown_future_field={"x": 1})
    _write_profile(root, "CloakBrowser", payload)

    loaded = kernel_profile.load("CloakBrowser")

    assert loaded.ok is True


def test_pick_package_prefers_matching_platform(root) -> None:
    _write_profile(root, "CloakBrowser", PROFILE)
    profile = kernel_profile.load("CloakBrowser").profile
    spec = kernel_profile.find_version(profile, "151.0.7922.108.3")

    win = kernel_profile.pick_package(spec, profile, "windows", "x64")
    linux = kernel_profile.pick_package(spec, profile, "linux", "x64")

    assert win is not None and win.kind == "archive"
    # linux 没有对应包时回落到 any 平台（这里的 pip 包）
    assert linux is not None and linux.kind == "pip"


def test_install_tree_writes_meta_so_scanner_sees_it(root) -> None:
    source = root / ".staging" / "src"
    source.mkdir(parents=True)
    (source / "chrome.exe").write_bytes(b"x" * 2048)

    target = root / "cloakbrowser" / "151.0"
    size = kernel_install.install_tree(source, target, {"version": "151.0", "kind": "pip"})

    assert size == 2048
    assert (target / "meta.json").is_file()
    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    assert meta["version"] == "151.0"
    assert meta["size_bytes"] == 2048
    assert meta["packaged_at"]

    versions = kernel_scan.scan_versions("cloakbrowser")
    assert [(v.version, v.ready) for v in versions] == [("151.0", True)]


def test_install_tree_replaces_existing_version(root) -> None:
    source = root / ".staging" / "src2"
    source.mkdir(parents=True)
    (source / "chrome.exe").write_bytes(b"y")

    target = root / "cloakbrowser" / "151.0"
    target.mkdir(parents=True)
    (target / "stale.dll").write_bytes(b"old")

    kernel_install.install_tree(source, target, {"version": "151.0"})

    assert not (target / "stale.dll").exists()


def test_safe_extract_rejects_path_traversal(tmp_path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "boom")

    with pytest.raises(ValueError, match="越界"):
        kernel_install.safe_extract(archive, tmp_path / "out")


def test_find_executable_respects_depth(tmp_path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "chrome.exe").write_bytes(b"x")

    assert kernel_install.find_executable(tmp_path, "chrome.exe") == nested / "chrome.exe"
    assert kernel_install.find_executable(tmp_path, "chrome.exe", max_depth=1) is None


def test_purge_never_raises(tmp_path, monkeypatch) -> None:
    """清理临时目录失败必须只记日志。

    解压后的 Chromium 有六七百个文件，某些环境（沙箱、杀软、被占用的 dll）在 rmtree
    时会抛 ``BaseException``。这一步在任务收尾的 finally 里，抛出去会连带把整个服务
    进程带走——实测就是这样把 uvicorn 干掉的。
    """

    def boom(*args, **kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(kernel_install.shutil, "rmtree", boom)
    kernel_install._purge(tmp_path)  # 不抛就算过


def test_find_aria2_prefers_bundled_binary(tmp_path, monkeypatch) -> None:
    """项目自带的 backend/bin/aria2c.exe 要优先于 PATH。"""
    bundled = tmp_path / "bin"
    bundled.mkdir()
    fake = bundled / ("aria2c.exe" if kernel_install.os.name == "nt" else "aria2c")
    fake.write_bytes(b"x")

    monkeypatch.setattr(kernel_install, "__file__", str(tmp_path / "app" / "services" / "x.py"))
    monkeypatch.setattr(kernel_install.shutil, "which", lambda name: "/usr/bin/aria2c")

    assert kernel_install._find_aria2() == str(fake)
