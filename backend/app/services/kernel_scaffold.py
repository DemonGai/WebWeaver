"""生成演示用的内核目录骨架。

真实部署时，内核目录由构建/下载流水线写入（解压发行包 + 写 ``meta.json``）。
本仓库不可能塞进几百 MB 的二进制，所以这里按同样的目录约定放一份只有
``meta.json`` 的骨架，让内核页面在本地就能看到「已下载 / 可更新 / 未下载」
三种状态。

用法::

    cd backend
    uv run python -m app.services.kernel_scaffold            # 缺什么补什么
    uv run python -m app.services.kernel_scaffold --reset     # 先删掉再重建

注意：它**只写 meta.json**，不写任何可执行文件；上线前请用真实的发行包
覆盖同目录，或直接让下载器接管 ``settings.kernel_root``。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.services.kernel_scan import META_FILE, engine_slug, kernel_root

# 与种子数据里的 kernels.version / latest_version 对齐：
# cloakbrowser、fingerprint-chromium 各多一个更新版本；camoufox 已是最新；
# ungoogled-chromium 故意留空，用来演示"未下载"状态。
DEMO_LAYOUT: dict[str, list[dict[str, object]]] = {
    "cloakbrowser": [
        {
            "version": "128.0.6613.2",
            "base": "Chromium 128.0.6613.120",
            "arch": "x64",
            "channel": "stable",
            "size_mb": 412,
            "released_at": "2026-10-18",
            "packaged_at": "2026-10-19T09:12:00+08:00",
            "source": "https://github.com/CloakHQ/CloakBrowser/releases",
        },
        {
            "version": "128.0.6613.5",
            "base": "Chromium 128.0.6613.120",
            "arch": "x64",
            "channel": "stable",
            "size_mb": 415,
            "released_at": "2026-10-27",
            "packaged_at": "2026-10-28T10:03:00+08:00",
            "source": "https://github.com/CloakHQ/CloakBrowser/releases",
        },
    ],
    "camoufox": [
        {
            "version": "128.0.3",
            "base": "Firefox 128.0",
            "arch": "x64",
            "channel": "stable",
            "size_mb": 268,
            "released_at": "2026-10-11",
            "packaged_at": "2026-10-11T20:41:00+08:00",
            "source": "https://github.com/daijro/camoufox/releases",
        },
    ],
    "fingerprint-chromium": [
        {
            "version": "126.0.6478.1",
            "base": "Chromium 126.0.6478.126",
            "arch": "x64",
            "channel": "stable",
            "size_mb": 459,
            "released_at": "2026-09-20",
            "packaged_at": "2026-09-21T14:22:00+08:00",
            "source": "https://github.com/adryfish/fingerprint-chromium/releases",
        },
        {
            "version": "128.0.6613.2",
            "base": "Chromium 128.0.6613.120",
            "arch": "x64",
            "channel": "stable",
            "size_mb": 462,
            "released_at": "2026-10-24",
            "packaged_at": "2026-10-25T11:05:00+08:00",
            "source": "https://github.com/adryfish/fingerprint-chromium/releases",
        },
    ],
    # ungoogled-chromium 故意不落盘
}


def scaffold(root: Path, *, reset: bool = False) -> list[str]:
    """按 DEMO_LAYOUT 补齐目录，返回写入了哪些版本。"""
    written: list[str] = []
    for slug, versions in DEMO_LAYOUT.items():
        engine_path = root / engine_slug(slug)
        if reset and engine_path.exists():
            shutil.rmtree(engine_path)
        for item in versions:
            version_path = engine_path / str(item["version"])
            version_path.mkdir(parents=True, exist_ok=True)
            meta_path = version_path / META_FILE
            if meta_path.is_file():
                continue
            meta_path.write_text(
                json.dumps(item, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written.append(f"{engine_path.name}/{item['version']}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="生成演示用内核目录骨架（仅 meta.json）")
    parser.add_argument("--root", default=None, help="内核根目录，默认取 settings.kernel_root")
    parser.add_argument("--reset", action="store_true", help="先删掉已有引擎目录再重建")
    args = parser.parse_args()

    root = Path(args.root) if args.root else kernel_root()
    if not root.is_absolute():
        root = BACKEND_ROOT / root

    written = scaffold(root, reset=args.reset)
    print(f"内核根目录：{root}")
    if written:
        for item in written:
            print(f"  + {item}")
        print(f"共写入 {len(written)} 个版本标记")
    else:
        print("目录已就绪，没有新增版本")


if __name__ == "__main__":
    main()
