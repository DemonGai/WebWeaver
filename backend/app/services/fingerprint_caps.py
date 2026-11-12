"""内核指纹能力矩阵：每个内核认哪些指纹参数、seed 是什么范围、怎么下发。

三个内核的指纹机制完全不同，参数名也**不通用**。传错名字不会报错 —— Chromium
只是忽略不认识的参数，表面上一切正常、实际指纹没生效。所以下发前必须按内核
查表，不能一套参数到处塞。

| 能力                 | CloakBrowser        | fingerprint-chromium      | ungoogled-chromium |
|----------------------|---------------------|---------------------------|--------------------|
| 指纹补丁             | 有（专有）          | 有（专有）                | 无                 |
| 统一入口             | `--fingerprint=<n>` | `--fingerprint=<n>`       | 无                 |
| 时区                 | `--fingerprint-timezone` | `--timezone`         | 无                 |
| 界面语言             | `--fingerprint-locale` + `--lang` | `--lang`       | 无                 |
| Accept-Language      | 无                  | `--accept-lang`           | 无                 |
| WebRTC 出口 IP       | `--fingerprint-webrtc-ip` | 无（只能禁非代理 UDP） | 无               |
| 平台版本 / 品牌      | 无                  | `--fingerprint-platform-version` 等 | 无        |
| 硬件并发             | 无                  | `--fingerprint-hardware-concurrency` | 无        |
| 单独关噪声           | 无                  | `--disable-spoofing=canvas,audio,gpu` | 无       |
| seed 范围            | 10000–99999         | 1–2147483647              | —                  |

`seed` 是两者的公共语言：同一个整数在两边都会算出"一个人"，但**算出来的具体
人格不一样**（两套补丁算法不同）。所以跨内核搬迁种子只能保证"换个人"，不能
保证"还是同一个人"。
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field

# 逻辑能力名。对外一律用这套名字，具体参数名在各自的 arg_templates 里。
SEED = "seed"
PLATFORM = "platform"
# 伪移动标记：内核装不成手机，只能把 UA / 视口 / DPR 换成移动端，
# platform 与 Client Hints 仍然是桌面。entrypoint 认这个字段做覆盖。
MOBILE = "mobile"
PLATFORM_VERSION = "platform_version"
BRAND = "brand"
BRAND_VERSION = "brand_version"
HARDWARE_CONCURRENCY = "hardware_concurrency"
TIMEZONE = "timezone"
LOCALE = "locale"
ACCEPT_LANG = "accept_lang"
WEBRTC_IP = "webrtc_ip"
NOISE_TOGGLE = "noise_toggle"

# 生成随机种子用的区间：取两个内核的交集，这样同一个种子两边都能用，
# 后端不用维护两套生成逻辑。CloakBrowser 的下限就是 10000。
PORTABLE_SEED_RANGE: tuple[int, int] = (10000, 99999)

# 平台族 → 内核认的平台 token。内核只有三档桌面平台（上游 `--fingerprint-platform`
# 只认 windows / macos / linux），写 android 会被当成未知值回落成 Linux 桌面人格。
#
# 所以移动族走「伪移动」：按最接近的桌面族起底（Android→Linux、iOS→macOS），
# UA / 视口 / DPR 由 entrypoint 按 `mobile` 字段覆盖。边界写清楚：navigator.platform、
# Client Hints、TLS（JA3/JA4）仍然是桌面，骗得过只看 UA 的站点，骗不过带风控的。
MOBILE_FAMILIES: frozenset[str] = frozenset({"android", "ios"})

_PLATFORM_TOKENS: dict[str, str] = {
    "windows": "windows",
    "macos": "macos",
    "linux": "linux",
    "android": "linux",
    "ios": "macos",
}


@dataclass(frozen=True)
class KernelCaps:
    """一个内核的指纹能力。"""

    slug: str
    engine_label: str
    supported: bool
    # seed 合法区间（闭区间）；不支持指纹时为 None
    seed_range: tuple[int, int] | None
    features: frozenset[str]
    # 逻辑能力名 → chrome 参数模板，`{}` 是占位
    arg_templates: Mapping[str, str]
    # 一句话说明这个内核的指纹机制
    note: str
    # supported=False 时给前端的理由
    reason: str | None = None

    def supports(self, feature: str) -> bool:
        return self.supported and feature in self.features

    def validate_seed(self, seed: int) -> str | None:
        """返回错误文案；合法时返回 None。"""
        if not self.supported or self.seed_range is None:
            return f"{self.engine_label} 不支持指纹，不能设置种子"
        low, high = self.seed_range
        if not (low <= seed <= high):
            return f"{self.engine_label} 的种子必须是 {low}–{high} 之间的整数"
        return None


CLOAKBROWSER = KernelCaps(
    slug="cloakbrowser",
    engine_label="CloakBrowser",
    supported=True,
    seed_range=(10000, 99999),
    features=frozenset({
        SEED, PLATFORM, MOBILE, TIMEZONE, LOCALE, WEBRTC_IP,
    }),
    arg_templates={
        SEED: "--fingerprint={}",
        PLATFORM: "--fingerprint-platform={}",
        TIMEZONE: "--fingerprint-timezone={}",
        LOCALE: "--fingerprint-locale={}",
        WEBRTC_IP: "--fingerprint-webrtc-ip={}",
    },
    note="一个种子决定整套人格，只能单独覆盖时区 / 语言 / WebRTC 出口 IP",
)

FINGERPRINT_CHROMIUM = KernelCaps(
    slug="fingerprint-chromium",
    engine_label="fingerprint-chromium",
    supported=True,
    seed_range=(1, 2147483647),
    features=frozenset({
        SEED, PLATFORM, MOBILE, PLATFORM_VERSION, BRAND, BRAND_VERSION,
        HARDWARE_CONCURRENCY, TIMEZONE, LOCALE, ACCEPT_LANG, NOISE_TOGGLE,
    }),
    arg_templates={
        SEED: "--fingerprint={}",
        PLATFORM: "--fingerprint-platform={}",
        PLATFORM_VERSION: "--fingerprint-platform-version={}",
        BRAND: "--fingerprint-brand={}",
        BRAND_VERSION: "--fingerprint-brand-version={}",
        HARDWARE_CONCURRENCY: "--fingerprint-hardware-concurrency={}",
        TIMEZONE: "--timezone={}",
        LOCALE: "--lang={}",
        ACCEPT_LANG: "--accept-lang={}",
        NOISE_TOGGLE: "--disable-spoofing={}",
    },
    note="种子之外还能单独指定品牌、平台版本、硬件并发，也能逐个关掉噪声",
    reason=None,
)

UNGOOGLED = KernelCaps(
    slug="ungoogled-chromium",
    engine_label="ungoogled-chromium",
    supported=False,
    seed_range=None,
    features=frozenset(),
    arg_templates={},
    note="纯净 Chromium，没打指纹补丁；拿它当基线对照用，不是拿来伪装的",
    reason="这个内核是纯净 Chromium，不带指纹补丁，套模板不会生效",
)

CAMOUFOX = KernelCaps(
    slug="camoufox",
    engine_label="Camoufox",
    supported=False,
    seed_range=None,
    features=frozenset(),
    arg_templates={},
    note="Firefox 系内核，指纹机制与 Chromium 系完全不同",
    reason="Firefox 系内核还没有做镜像，指纹下发暂时走不通",
)

CAPS: dict[str, KernelCaps] = {
    caps.slug: caps for caps in (CLOAKBROWSER, FINGERPRINT_CHROMIUM, UNGOOGLED, CAMOUFOX)
}

# 不指定内核时的兜底：宁可当作不支持，也不要瞎塞参数
UNKNOWN = KernelCaps(
    slug="",
    engine_label="未知内核",
    supported=False,
    seed_range=None,
    features=frozenset(),
    arg_templates={},
    note="",
    reason="认不出这个内核，无法确定它接受哪些指纹参数",
)


def caps_for(slug: str | None) -> KernelCaps:
    if not slug:
        return UNKNOWN
    return CAPS.get(slug, UNKNOWN)


def platform_token(family: str | None) -> str | None:
    """平台族 → 内核认的 token。

    移动族返回的是「最接近的桌面族」而不是它自己：内核没有移动平台这一档，
    写 android 会被当成未知值静默回落（实测串成 Linux 桌面人格）。真正的移动
    外观靠 `mobile` 字段在 entrypoint 里覆盖 UA / 视口 / DPR。
    """
    if not family:
        return None
    return _PLATFORM_TOKENS.get(family)


def is_pseudo_mobile(family: str | None) -> bool:
    """这个平台族是不是「伪移动」——内核人格仍是桌面。"""
    return family in MOBILE_FAMILIES


def random_seed() -> int:
    low, high = PORTABLE_SEED_RANGE
    return random.randint(low, high)


def _derive_accept_lang(lang: str) -> str:
    """`zh-CN` → `zh-CN,zh`；`en` 原样返回。

    和 entrypoint 里的派生规则保持一致：把主语言再挂一个次级语言，比只给一个
    zh-CN 更像真浏览器发出来的头。
    """
    primary = lang.split(",")[0].strip()
    if "-" in primary:
        return f"{primary},{primary.split('-')[0]}"
    return primary


# 参与摘要的字段。顺序固定，否则同一个 spec 会算出不同的摘要。
_DIGEST_FIELDS: tuple[str, ...] = (
    "seed",
    "platform_family",
    "platform_version",
    "brand",
    "brand_version",
    "hardware_concurrency",
    "timezone",
    "locale",
    "accept_lang",
    "webrtc_ip",
    "canvas_noise",
    "webgl_noise",
    "audio_noise",
    "webrtc_protected",
)


def spec_digest(spec: FingerprintSpec) -> str:
    """下发输入的指纹摘要。

    用途只有一个：判断「采集到的实测值还对不对应当前参数」。比时间戳靠谱 ——
    采集完立刻改参数也能抓到，而改完又改回原值则判定为没变。
    空值和 False 要区分开：`accept_lang=""` 和 `accept_lang=None` 对内核是一回事，
    所以空串统一归一成 None。
    """
    parts: list[str] = []
    for name in _DIGEST_FIELDS:
        value = getattr(spec, name)
        if isinstance(value, str) and value == "":
            value = None
        parts.append(f"{name}={value!r}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


# ── 渲染 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FingerprintSpec:
    """一次下发要用到的全部输入。

    特意不直接吃 ORM 对象：渲染是纯函数，这样测试不用碰数据库。
    """

    seed: int | None = None
    platform_family: str | None = None
    platform_version: str | None = None
    brand: str | None = None
    brand_version: str | None = None
    hardware_concurrency: int | None = None
    timezone: str | None = None
    locale: str | None = None
    accept_lang: str | None = None
    webrtc_ip: str | None = None
    canvas_noise: bool = True
    webgl_noise: bool = True
    audio_noise: bool = True
    webrtc_protected: bool = True


@dataclass(frozen=True)
class Rendered:
    """渲染结果：给用户看的三种下发物料。"""

    slug: str
    # /data/fingerprint.json 的内容
    payload: dict[str, object] = field(default_factory=dict)
    # 容器环境变量（含 FINGERPRINT_* 与内核特有的开关）
    env: dict[str, str] = field(default_factory=dict)
    # 等价的 chrome 参数，拼在 command 里用
    args: list[str] = field(default_factory=list)
    # 字段给了但该内核不认 —— 必须显式告诉用户，否则是静默失效
    ignored: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.payload or self.env or self.args)


# 逻辑能力名 → 给人看的名字，用于 ignored 提示
_FEATURE_LABELS: dict[str, str] = {
    SEED: "种子",
    PLATFORM: "平台",
    MOBILE: "伪移动",
    PLATFORM_VERSION: "平台版本",
    BRAND: "品牌",
    BRAND_VERSION: "品牌版本",
    HARDWARE_CONCURRENCY: "硬件并发",
    TIMEZONE: "时区",
    LOCALE: "界面语言",
    ACCEPT_LANG: "Accept-Language",
    WEBRTC_IP: "WebRTC 出口 IP",
    NOISE_TOGGLE: "噪声开关",
}


def _spec_values(spec: FingerprintSpec) -> dict[str, object]:
    """把 spec 摊平成「逻辑能力名 → 值」，只保留真正给了值的项。"""
    values: dict[str, object] = {}

    if spec.seed is not None:
        values[SEED] = spec.seed
    token = platform_token(spec.platform_family)
    if token:
        values[PLATFORM] = token
    # 伪移动：UA / 视口 / DPR 交给 entrypoint 覆盖，这里是唯一的开关
    if spec.platform_family in MOBILE_FAMILIES:
        values[MOBILE] = spec.platform_family
    for name, value in (
        (PLATFORM_VERSION, spec.platform_version),
        (BRAND, spec.brand),
        (BRAND_VERSION, spec.brand_version),
        (HARDWARE_CONCURRENCY, spec.hardware_concurrency),
        (TIMEZONE, spec.timezone),
        (LOCALE, spec.locale),
        (ACCEPT_LANG, spec.accept_lang),
        (WEBRTC_IP, spec.webrtc_ip),
    ):
        if value not in (None, ""):
            values[name] = value
    return values


def _noise_tokens(spec: FingerprintSpec) -> list[str]:
    """关掉的噪声项。`--disable-spoofing` 只认 font/audio/canvas/clientrects/gpu。

    WebGL 归到 gpu：官方没有单独的 webgl 开关，renderer 伪装就在 gpu 这一项里。
    """
    tokens: list[str] = []
    if not spec.canvas_noise:
        tokens.append("canvas")
    if not spec.audio_noise:
        tokens.append("audio")
    if not spec.webgl_noise:
        tokens.append("gpu")
    return tokens


def render(spec: FingerprintSpec, caps: KernelCaps) -> Rendered:
    """按内核能力把 spec 渲染成 payload / env / args，并列出被跳过的字段。"""
    if not caps.supported:
        return Rendered(slug=caps.slug)

    values = _spec_values(spec)
    noise = _noise_tokens(spec)
    if noise:
        values[NOISE_TOGGLE] = noise

    payload: dict[str, object] = {}
    env: dict[str, str] = {}
    args: list[str] = []
    ignored: list[str] = []

    for name, value in values.items():
        if not caps.supports(name):
            ignored.append(_FEATURE_LABELS.get(name, name))
            continue

        if name == NOISE_TOGGLE:
            joined = ",".join(value)  # type: ignore[arg-type]
            # 指纹文件里叫 disable_spoofing，环境变量叫 FINGERPRINT_DISABLE_SPOOFING
            payload["disable_spoofing"] = joined
            env["FINGERPRINT_DISABLE_SPOOFING"] = joined
        elif name == SEED:
            payload["seed"] = int(value)
            env["FINGERPRINT_SEED"] = str(value)
        else:
            payload[name] = value
            env[f"FINGERPRINT_{name.upper()}"] = str(value)

        template = caps.arg_templates.get(name)
        if template:
            arg_value = ",".join(value) if name == NOISE_TOGGLE else value  # type: ignore[arg-type]
            args.append(template.format(arg_value))

    # locale 必须成对下发成 --lang：CloakBrowser 的 --fingerprint-locale 只影响
    # Intl 的默认值，不改 navigator.language；两者不一起给，会出现「日期是日文、
    # 网站语言是英文」这种自相矛盾的人格。fingerprint-chromium 的 entrypoint 本来
    # 就会自己派生 --lang，这里显式给出也没坏处（FP_LANG 优先）。
    if "locale" in payload:
        payload["lang"] = payload["locale"]
        env["FINGERPRINT_LANG"] = str(payload["locale"])
        if caps.slug == CLOAKBROWSER.slug:
            args.append(f"--lang={payload['locale']}")

    # Accept-Language 同理：entrypoint 会在没给的时候按 lang 派生（zh-CN → zh-CN,zh）。
    # 这里提前算出来，预览里显示的就是最终真正生效的那份，不会少一行。
    if caps.supports(ACCEPT_LANG) and "accept_lang" not in payload and "lang" in payload:
        derived = _derive_accept_lang(str(payload["lang"]))
        payload["accept_lang"] = derived
        env["FINGERPRINT_ACCEPT_LANG"] = derived
        args.append(f"--accept-lang={derived}")

    # WebRTC 防泄漏：CloakBrowser 靠上面的出口 IP 参数；fingerprint-chromium 没有
    # 那个参数，只能禁止非代理 UDP。默认就是禁的，只有显式关掉才需要给 env。
    if caps.slug == FINGERPRINT_CHROMIUM.slug and not spec.webrtc_protected:
        env["ALLOW_NON_PROXIED_UDP"] = "1"

    return Rendered(slug=caps.slug, payload=payload, env=env, args=args, ignored=ignored)
