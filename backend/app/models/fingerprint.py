"""指纹表：浏览器指纹模板。

一条指纹 = 一组「下发给内核的输入参数」+ 一份「采集回来的实测画像」。

镜像里的内核是动态指纹：`--fingerprint=<seed>` 一个整数决定整套人格
（UA、平台、硬件并发、显卡、屏幕、canvas/WebGL/audio 噪声）。所以 seed 才是
输入，UA / 分辨率 / DPR 是它算出来的结果 —— 前者我们存下来下发，后者只能
启动容器采集回来观察，不能反过来当输入用。参数差异见
`app/services/fingerprint_caps.py`。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import FingerprintStatus, PlatformFamily


class Fingerprint(IdMixin, TimestampMixin, table=True):
    __tablename__ = "fingerprints"
    __table_args__ = ({"comment": "指纹表：浏览器指纹模板，定义 UA、时区、分辨率与各类噪声伪装项"},)

    # 指纹业务编号（如 fp-win11-c128），配置与日志里引用它，不暴露 UUID
    code: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="指纹编号",
        sa_column_kwargs={"comment": "指纹编号（唯一，如 fp-win11-c128）"},
    )
    name: str = Field(
        max_length=64,
        description="指纹名称",
        sa_column_kwargs={"comment": "指纹名称"},
    )
    platform_family: PlatformFamily = Field(
        default=PlatformFamily.windows,
        sa_type=enum_type(PlatformFamily, 16),
        index=True,
        description="平台族：windows / macos / linux / android / ios",
        sa_column_kwargs={"comment": "平台族：windows / macos / linux / android / ios"},
    )
    platform: str = Field(
        max_length=64,
        description="平台描述，如 Windows 11 / macOS 14.5",
        sa_column_kwargs={"comment": "平台描述，如 Windows 11 / macOS 14.5"},
    )

    # ── 下发给内核的输入参数 ─────────────────────────────────────────
    # seed 是整套人格的唯一输入：同一个 seed 永远算出同一套 UA / 硬件 / 噪声，
    # 换个数字就是另一个人。留空表示不指定，让内核按 profile 里上次的种子走
    # （第一次启动则随机）—— 这时指纹记录里只有实测值，没有确定的种子。
    seed: int | None = Field(
        default=None,
        ge=1,
        description="指纹种子，决定整套人格",
        sa_column_kwargs={"comment": "指纹种子，一个整数决定整套人格；为空表示不指定"},
    )
    platform_version: str | None = Field(
        default=None,
        max_length=32,
        description="平台版本，如 10.0.0 / 14.5.0",
        sa_column_kwargs={"comment": "平台版本，如 10.0.0；仅 fingerprint-chromium 支持"},
    )
    brand: str | None = Field(
        default=None,
        max_length=32,
        description="浏览器品牌，如 Chrome / Edge",
        sa_column_kwargs={"comment": "浏览器品牌，如 Chrome / Edge；仅 fingerprint-chromium 支持"},
    )
    brand_version: str | None = Field(
        default=None,
        max_length=32,
        description="品牌版本号，如 146.0.7680.177",
        sa_column_kwargs={"comment": "品牌版本号，如 146.0.7680.177"},
    )
    hardware_concurrency: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description="navigator.hardwareConcurrency",
        sa_column_kwargs={"comment": "navigator.hardwareConcurrency；仅 fingerprint-chromium 支持"},
    )

    # UA 是种子算出来的结果，不是输入。存这份是为了列表能看、能搜索，
    # 由采集流程回填；手填的值不会影响内核行为，只会让人误判。
    user_agent: str = Field(
        default="",
        sa_type=String(512),
        description="User-Agent（采集回填的实测值）",
        sa_column_kwargs={"comment": "User-Agent，由采集流程回填的实测值，不参与下发"},
    )
    timezone: str = Field(
        max_length=64,
        description="时区，如 Asia/Shanghai",
        sa_column_kwargs={"comment": "时区，如 Asia/Shanghai"},
    )
    # locale 语义：界面语言。映射到 --fingerprint-locale（CloakBrowser）
    # 或 --lang（fingerprint-chromium）
    language: str = Field(
        max_length=64,
        description="界面语言，如 zh-CN",
        sa_column_kwargs={
            "comment": "界面语言（locale），如 zh-CN；映射 --lang / --fingerprint-locale"
        },
    )
    # HTTP Accept-Language，和界面语言是两套东西。留空按 language 派生。
    accept_lang: str | None = Field(
        default=None,
        max_length=128,
        description="HTTP Accept-Language，如 zh-CN,zh",
        sa_column_kwargs={"comment": "HTTP Accept-Language，如 zh-CN,zh；为空按 language 派生"},
    )
    # WebRTC 会绕过代理直连暴露本机 IP。CloakBrowser 用这个参数把候选地址
    # 压成指定 IP；fingerprint-chromium 没有对应参数，只能靠禁非代理 UDP。
    webrtc_ip: str | None = Field(
        default=None,
        max_length=64,
        description="WebRTC 对外暴露的 IP",
        sa_column_kwargs={"comment": "WebRTC 对外暴露的 IP；仅 CloakBrowser 支持"},
    )

    # 分辨率 / DPR 同样是算出来的结果，采集回填，不参与下发
    resolution: str = Field(
        default="",
        max_length=32,
        description="屏幕分辨率（采集回填）",
        sa_column_kwargs={"comment": "屏幕分辨率，由采集流程回填的实测值"},
    )
    dpr: str = Field(
        default="1",
        max_length=16,
        description="设备像素比（采集回填）",
        sa_column_kwargs={"comment": "设备像素比，由采集流程回填的实测值"},
    )

    # 噪声开关。在动态指纹内核里这些不能单独调（种子一并决定），只有
    # fingerprint-chromium 能通过 --disable-spoofing 逐个关掉；CloakBrowser
    # 没有对应参数，关掉也无效。能力矩阵里按内核声明，别默认全开就算生效。
    canvas_noise: bool = Field(
        default=True,
        description="Canvas 噪声",
        sa_column_kwargs={"comment": "是否开启 Canvas 指纹噪声"},
    )
    webgl_noise: bool = Field(
        default=True,
        description="WebGL 噪声",
        sa_column_kwargs={"comment": "是否开启 WebGL 指纹噪声"},
    )
    audio_noise: bool = Field(
        default=True,
        description="AudioContext 噪声",
        sa_column_kwargs={"comment": "是否开启 AudioContext 指纹噪声"},
    )
    webrtc_protected: bool = Field(
        default=True,
        description="WebRTC 防泄漏",
        sa_column_kwargs={"comment": "是否开启 WebRTC 防泄漏"},
    )

    # 唯一性评分；插件过期等无法评估时为 None，前端显示「—」
    uniqueness: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="唯一性得分",
        sa_column_kwargs={"comment": "唯一性得分（0-100），无法评估时为空"},
    )
    warning: str | None = Field(
        default=None,
        max_length=255,
        description="异常提示",
        sa_column_kwargs={"comment": "异常提示文案"},
    )
    status: FingerprintStatus = Field(
        default=FingerprintStatus.active,
        sa_type=enum_type(FingerprintStatus, 16),
        index=True,
        description="状态：active / needs_upgrade / expired",
        sa_column_kwargs={"comment": "状态：active 可用 / needs_upgrade 待升级 / expired 已过期"},
    )
    # 该模板绑定的内核；为空表示不限定
    kernel_id: UUID | None = Field(
        default=None,
        foreign_key="kernels.id",
        index=True,
        description="适配的内核 ID",
        sa_column_kwargs={"comment": "适配的内核 ID，为空表示不限内核"},
    )

    # ── 采集回执 ────────────────────────────────────────────────────
    # 采集 = 按 seed 起一个临时容器，读 navigator.* 把人格录回来。有了这个时间戳
    # 才能判断 UA / 分辨率这些实测值是不是还对应当前 seed（改过 seed 就过期了）。
    probed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="最近一次采集时间",
        sa_column_kwargs={"comment": "最近一次采集时间；为空表示从未采集，实测值不可信"},
    )
    # 采集时的下发参数摘要。和当前参数算出的摘要不一致，就说明实测值对不上
    # 现在的人格了 —— 换种子等于换个人，改时区也一样，旧快照全部作废。
    # 用摘要而不是时间戳：采集完立刻改参数也能抓到，改完又改回原值则不算变。
    probed_digest: str | None = Field(
        default=None,
        max_length=32,
        description="采集时的下发参数摘要",
        sa_column_kwargs={
            "comment": "采集时的下发参数摘要；与当前参数不一致说明实测值已过期"
        },
    )
    # 完整快照。GPU 型号、canvas hash、语言列表这些字段各内核差异大，
    # 而且只在详情里看，不适合摊成一堆列。
    probe: dict[str, Any] | None = Field(
        default=None,
        sa_type=JSONB,
        description="采集到的完整人格快照",
        sa_column_kwargs={
            "comment": "采集到的完整人格快照（JSONB）：GPU、canvas hash、语言列表等"
        },
    )
    probe_error: str | None = Field(
        default=None,
        max_length=512,
        description="最近一次采集失败原因",
        sa_column_kwargs={"comment": "最近一次采集失败原因，成功时清空"},
    )
