"""内核识别层的单元测试：tag 解析、版本推导、去重合并（不碰数据库、不碰 docker）。"""

from __future__ import annotations

from app.services.kernel_image import ImageInfo
from app.services.kernel_scan import (
    engine_slug,
    human_size,
    parse_tag,
    scan_versions,
    version_key,
)


def _image(
    tag: str,
    version: str | None,
    *,
    image_id: str | None = None,
    size_mb: int = 500,
    created: str = "2026-11-10T13:50:54.693761427Z",
    digest: str | None = "sha256:abc123",
    labels: dict[str, str] | None = None,
) -> ImageInfo:
    """造一个 ImageInfo。默认把版本写进 OCI 标签，跟真实镜像一致。"""
    tag_labels = dict(labels or {})
    if version:
        tag_labels.setdefault("org.opencontainers.image.version", version)
    return ImageInfo(
        ref=f"demo/browser_engine:{tag}",
        repository="demo/browser_engine",
        tag=tag,
        image_id=image_id or f"sha256:{tag}",
        size_bytes=size_mb * 1024 * 1024,
        created_at=created,
        digest=digest,
        arch="amd64",
        os_name="linux",
        labels=tag_labels or None,
    )


def test_version_key_compares_numerically() -> None:
    # 字符串比较会把 "10" 排在 "9" 前面，这里必须按数字比
    assert version_key("128.0.6613.9") < version_key("128.0.6613.10")
    assert version_key("0.9.4") < version_key("0.10.0")
    assert sorted(["1.2.0", "1.10.0", "1.9.9"], key=version_key) == ["1.2.0", "1.9.9", "1.10.0"]


def test_engine_slug_normalises_name() -> None:
    assert engine_slug("CloakBrowser") == "cloakbrowser"
    assert engine_slug("fingerprint-chromium") == "fingerprint-chromium"
    assert engine_slug(" Ungoogled Chromium ") == "ungoogled-chromium"


def test_human_size() -> None:
    assert human_size(0) == "—"
    assert human_size(512) == "512 B"
    assert human_size(500 * 1024 * 1024) == "500 MB"
    assert human_size(int(2.13 * 1024**3)) == "2.1 GB"


def test_parse_tag_splits_version() -> None:
    slugs = ["cloakbrowser", "chromium"]
    assert parse_tag("cloakbrowser", slugs) == ("cloakbrowser", None)
    assert parse_tag("cloakbrowser-146.0.7680.177.5", slugs) == (
        "cloakbrowser",
        "146.0.7680.177.5",
    )


def test_parse_tag_prefers_longest_slug() -> None:
    # fingerprint-chromium 里也含 "chromium"，按最长前缀匹配才不会被截错
    slugs = ["chromium", "fingerprint-chromium"]
    owner, version = parse_tag("fingerprint-chromium-148.0.7778.215", slugs)
    assert owner == "fingerprint-chromium"
    assert version == "148.0.7778.215"


def test_scan_merges_tags_of_same_image() -> None:
    # 滚动 tag 与固定 tag 指向同一个镜像，应该合成一条版本
    images = [
        _image("cloakbrowser", "146.0.7680.177.5", image_id="sha256:aaa", size_mb=532),
        _image(
            "cloakbrowser-146.0.7680.177.5",
            "146.0.7680.177.5",
            image_id="sha256:aaa",
            size_mb=532,
        ),
    ]
    versions = scan_versions("CloakBrowser", images=images)

    assert len(versions) == 1
    item = versions[0]
    assert item.version == "146.0.7680.177.5"
    # 首选引用要用固定 tag：滚动 tag 会被下次构建覆盖
    assert item.tag == "cloakbrowser-146.0.7680.177.5"
    assert item.pinned is True
    assert item.rolling is True
    assert item.tags == ["cloakbrowser", "cloakbrowser-146.0.7680.177.5"]
    assert item.size == "532 MB"


def test_scan_sorts_newest_first() -> None:
    images = [
        _image("cloakbrowser-146.0.7680.10", "146.0.7680.10", image_id="sha256:a"),
        _image("cloakbrowser-146.0.7680.9", "146.0.7680.9", image_id="sha256:b"),
    ]
    versions = scan_versions("cloakbrowser", images=images)
    # 字符串排序会把 .10 排到 .9 前面，必须按数字比
    assert [v.version for v in versions] == ["146.0.7680.10", "146.0.7680.9"]


def test_scan_falls_back_to_tag_when_label_missing() -> None:
    # 自己 build 的镜像可能没打 OCI 标签，退回从 tag 名切版本
    images = [_image("cloakbrowser-9.9.9", None, image_id="sha256:zzz", labels={})]
    versions = scan_versions("cloakbrowser", images=images)
    assert versions[0].version == "9.9.9"


def test_scan_marks_image_without_fixed_tag_as_rolling() -> None:
    # 只有滚动 tag 时，页面要提示「下次构建会被覆盖」
    images = [_image("cloakbrowser", "146.0.7680.177.5", image_id="sha256:aaa")]
    item = scan_versions("cloakbrowser", images=images)[0]
    assert item.pinned is False
    assert item.rolling is True
    assert item.tag == "cloakbrowser"


def test_scan_ignores_other_engines() -> None:
    images = [
        _image("cloakbrowser-146.0", "146.0", image_id="sha256:a"),
        _image("ungoogled-chromium-156.0", "156.0", image_id="sha256:b"),
    ]
    versions = scan_versions("cloakbrowser", images=images)
    assert [v.version for v in versions] == ["146.0"]


def test_scan_without_images_returns_empty() -> None:
    assert scan_versions("cloakbrowser", images=[]) == []


def test_pretty_time_converts_to_local() -> None:
    from app.services.kernel_scan import pretty_time

    # Docker 给的是 UTC（Z 结尾），页面上要显示本地时间：形状要是 YYYY-MM-DD HH:MM
    value = pretty_time("2026-11-10T13:50:54.693761427Z")
    assert value is not None
    assert len(value) == 16 and "T" not in value and value[10] == " "
    assert pretty_time(None) is None
