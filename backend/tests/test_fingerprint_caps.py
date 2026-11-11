"""内核指纹能力矩阵的纯函数测试。

这里不碰数据库也不碰 docker —— `render()` 就是「给定参数 + 内核，算出下发物料」，
所以能逐条钉住「哪个内核认哪个参数」这件事。这几个断言是这轮改动的地基：
参数名传错内核不会报错，只会静默失效，只有测试能拦住。
"""

from __future__ import annotations

import pytest

from app.services import fingerprint_caps as caps


def _spec(**overrides: object) -> caps.FingerprintSpec:
    base: dict[str, object] = {
        "seed": 42817,
        "platform_family": "windows",
        "platform_version": "10.0.0",
        "brand": "Chrome",
        "brand_version": "146.0.7680.177",
        "hardware_concurrency": 8,
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN",
        "accept_lang": "zh-CN,zh",
        "webrtc_ip": "203.0.113.10",
        "canvas_noise": True,
        "webgl_noise": True,
        "audio_noise": True,
        "webrtc_protected": True,
    }
    base.update(overrides)
    return caps.FingerprintSpec(**base)  # type: ignore[arg-type]


# ── 内核支持面 ────────────────────────────────────────────


def test_only_chromium_fingerprint_kernels_support_spoofing() -> None:
    assert caps.CLOAKBROWSER.supported is True
    assert caps.FINGERPRINT_CHROMIUM.supported is True
    # 纯净 Chromium 没打补丁，套模板没有任何效果，必须明确判不支持
    assert caps.UNGOOGLED.supported is False
    assert caps.CAMOUFOX.supported is False


def test_unknown_kernel_never_pretends_to_support() -> None:
    unknown = caps.caps_for("some-new-engine")
    assert unknown.supported is False
    assert caps.render(_spec(), unknown).usable is False


# ── 下发参数名 ────────────────────────────────────────────


def test_cloakbrowser_uses_its_own_parameter_names() -> None:
    result = caps.render(_spec(), caps.CLOAKBROWSER)
    assert result.args == [
        "--fingerprint=42817",
        "--fingerprint-platform=windows",
        "--fingerprint-timezone=Asia/Shanghai",
        "--fingerprint-locale=zh-CN",
        "--fingerprint-webrtc-ip=203.0.113.10",
        # locale 必须同时落到 --lang，否则 navigator.language 还是英文
        "--lang=zh-CN",
    ]


def test_fingerprint_chromium_uses_different_parameter_names() -> None:
    result = caps.render(_spec(), caps.FINGERPRINT_CHROMIUM)
    assert "--timezone=Asia/Shanghai" in result.args
    assert "--lang=zh-CN" in result.args
    assert "--accept-lang=zh-CN,zh" in result.args
    assert "--fingerprint-hardware-concurrency=8" in result.args
    assert "--fingerprint-brand=Chrome" in result.args
    # CloakBrowser 那套名字塞给它是无效的，这里绝对不能出现
    assert not any(arg.startswith("--fingerprint-timezone") for arg in result.args)
    assert not any(arg.startswith("--fingerprint-locale") for arg in result.args)


def test_webrtc_ip_is_ignored_by_fingerprint_chromium() -> None:
    result = caps.render(_spec(), caps.FINGERPRINT_CHROMIUM)
    assert "webrtc_ip" not in result.payload
    assert "WebRTC 出口 IP" in result.ignored


def test_platform_version_is_ignored_by_cloakbrowser() -> None:
    result = caps.render(_spec(), caps.CLOAKBROWSER)
    assert "platform_version" not in result.payload
    assert "品牌" in result.ignored
    assert "硬件并发" in result.ignored


# ── payload 内容 ─────────────────────────────────────────


def test_locale_always_lands_as_lang() -> None:
    for kernel in (caps.CLOAKBROWSER, caps.FINGERPRINT_CHROMIUM):
        result = caps.render(_spec(), kernel)
        assert result.payload["locale"] == "zh-CN"
        assert result.payload["lang"] == "zh-CN"


def test_accept_lang_is_derived_when_absent() -> None:
    spec = _spec(accept_lang=None)
    result = caps.render(spec, caps.FINGERPRINT_CHROMIUM)
    # entrypoint 会自己派生，我们提前算出来，保证预览和真实生效一致
    assert result.payload["accept_lang"] == "zh-CN,zh"


def test_noise_switches_map_to_disable_spoofing() -> None:
    spec = _spec(canvas_noise=False, audio_noise=False, webgl_noise=True)
    result = caps.render(spec, caps.FINGERPRINT_CHROMIUM)
    assert result.payload["disable_spoofing"] == "canvas,audio"
    assert "--disable-spoofing=canvas,audio" in result.args


def test_noise_toggles_are_ignored_by_cloakbrowser() -> None:
    spec = _spec(canvas_noise=False)
    result = caps.render(spec, caps.CLOAKBROWSER)
    # 种子里 Canvas 噪声一并决定，没有单独开关，不能说「已关闭」
    assert "disable_spoofing" not in result.payload
    assert "噪声开关" in result.ignored


def test_mobile_family_produces_no_platform_token() -> None:
    assert caps.platform_token("android") is None
    assert caps.platform_token("ios") is None
    assert caps.platform_token("windows") == "windows"
    # 桌面内核装不成手机：payload 里干脆没有 platform，交给调用方拦掉
    rendered = caps.render(_spec(platform_family="android"), caps.CLOAKBROWSER)
    assert "platform" not in rendered.payload


# ── 种子 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kernel", "seed", "ok"),
    [
        (caps.CLOAKBROWSER, 9999, False),
        (caps.CLOAKBROWSER, 10000, True),
        (caps.CLOAKBROWSER, 99999, True),
        (caps.CLOAKBROWSER, 100000, False),
        (caps.FINGERPRINT_CHROMIUM, 1, True),
        # 0 会被内核当成「没启用指纹」，这是静默失效的经典坑
        (caps.FINGERPRINT_CHROMIUM, 0, False),
        (caps.FINGERPRINT_CHROMIUM, 2147483647, True),
        (caps.FINGERPRINT_CHROMIUM, 2147483648, False),
    ],
)
def test_seed_range_is_enforced_per_kernel(
    kernel: caps.KernelCaps, seed: int, ok: bool
) -> None:
    assert (kernel.validate_seed(seed) is None) is ok


def test_unsupported_kernel_rejects_any_seed() -> None:
    assert caps.UNGOOGLED.validate_seed(42817) is not None


def test_generated_seed_is_portable_between_kernels() -> None:
    low, high = caps.PORTABLE_SEED_RANGE
    for _ in range(50):
        seed = caps.random_seed()
        assert low <= seed <= high
        # 生成的种子必须两个内核都收，否则「换内核重采」就废了
        assert caps.CLOAKBROWSER.validate_seed(seed) is None
        assert caps.FINGERPRINT_CHROMIUM.validate_seed(seed) is None


# ── 参数摘要（判断实测值是否过期）────────────────────────────


def test_digest_changes_with_any_downstream_input() -> None:
    base = caps.spec_digest(_spec())
    for overrides in (
        {"seed": 42818},
        {"timezone": "Europe/London"},
        {"locale": "en-GB"},
        {"hardware_concurrency": 16},
        {"webrtc_ip": "198.51.100.7"},
        {"canvas_noise": False},
        {"platform_family": "macos"},
    ):
        assert caps.spec_digest(_spec(**overrides)) != base, overrides


def test_digest_is_stable_for_identical_input() -> None:
    assert caps.spec_digest(_spec()) == caps.spec_digest(_spec())


def test_digest_treats_empty_string_as_absent() -> None:
    # 空串和 None 对内核是一回事，摘要里不该区分，否则会误判成「参数变了」
    assert caps.spec_digest(_spec(accept_lang=None)) == caps.spec_digest(_spec(accept_lang=""))
