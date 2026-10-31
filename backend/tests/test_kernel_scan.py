"""内核目录扫描的单元测试（不碰数据库）。"""

from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.services.kernel_scan import (
    engine_slug,
    human_size,
    scan_versions,
    version_key,
)


@pytest.fixture
def root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "kernel_root", str(tmp_path))
    return tmp_path


def _write(root, slug: str, version: str, meta: dict | None) -> None:
    directory = root / slug / version
    directory.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_version_key_compares_numerically() -> None:
    # 字符串比较会把 "10" 排在 "9" 前面，这里必须按数字比
    assert version_key("128.0.6613.9") < version_key("128.0.6613.10")
    assert version_key("0.9.4") < version_key("0.10.0")
    assert sorted(["1.2.0", "1.10.0", "1.9.9"], key=version_key) == ["1.2.0", "1.9.9", "1.10.0"]


def test_engine_slug_normalises_name() -> None:
    assert engine_slug("CloakBrowser") == "cloakbrowser"
    assert engine_slug("fingerprint-chromium") == "fingerprint-chromium"
    assert engine_slug(" Ungoogled Chromium ") == "ungoogled-chromium"


def test_scan_reads_meta_and_sorts_desc(root) -> None:
    _write(root, "cloakbrowser", "128.0.6613.2", {"version": "128.0.6613.2", "size_mb": 412})
    _write(
        root,
        "cloakbrowser",
        "128.0.6613.5",
        {
            "version": "128.0.6613.5",
            "base": "Chromium 128",
            "released_at": "2026-10-27",
            "size_mb": 415,
        },
    )

    versions = scan_versions("CloakBrowser")
    assert [v.version for v in versions] == ["128.0.6613.5", "128.0.6613.2"]
    assert all(v.ready for v in versions)
    assert versions[0].size == "415 MB"
    assert versions[1].size == "412 MB"
    assert versions[0].base == "Chromium 128"
    assert versions[0].released_at == "2026-10-27"


def test_scan_falls_back_to_directory_size(root) -> None:
    # meta 里没写 size_mb 时用目录实际体积兜底，不至于显示成空
    _write(root, "camoufox", "1.0.0", {"version": "1.0.0"})
    (root / "camoufox" / "1.0.0" / "payload.bin").write_bytes(b"0" * 2048)

    version = scan_versions("Camoufox")[0]
    assert version.size is not None
    assert version.size.endswith("KB")


def test_scan_flags_directories_without_meta(root) -> None:
    _write(root, "cloakbrowser", "1.0.0", None)  # 有文件但没有 marker
    (root / "cloakbrowser" / "1.0.0" / "chrome.exe").write_bytes(b"x")
    _write(root, "cloakbrowser", "2.0.0", {"version": "2.0.0"})
    (root / "cloakbrowser" / "3.0.0").mkdir(parents=True)  # 空目录

    versions = scan_versions("CloakBrowser")
    assert [v.version for v in versions] == ["3.0.0", "2.0.0", "1.0.0"]
    broken = {v.version: v for v in versions if not v.ready}
    assert set(broken) == {"1.0.0", "3.0.0"}
    assert "meta.json" in broken["1.0.0"].warning
    assert "为空" in broken["3.0.0"].warning


def test_scan_returns_empty_for_unknown_engine(root) -> None:
    assert scan_versions("NotInstalled") == []


def test_human_size() -> None:
    assert human_size(0) == "—"
    assert human_size(412 * 1024 * 1024) == "412 MB"
    assert human_size(2 * 1024 * 1024 * 1024) == "2.0 GB"
