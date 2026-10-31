"""指纹表：浏览器指纹模板（UA / 时区 / 分辨率 / Canvas 等伪装项）。"""

from uuid import UUID

from sqlalchemy import String
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
    user_agent: str = Field(
        sa_type=String(512),
        description="User-Agent",
        sa_column_kwargs={"comment": "User-Agent 字符串"},
    )
    timezone: str = Field(
        max_length=64,
        description="时区，如 Asia/Shanghai",
        sa_column_kwargs={"comment": "时区，如 Asia/Shanghai"},
    )
    language: str = Field(
        max_length=64,
        description="语言，如 zh-CN,zh",
        sa_column_kwargs={"comment": "浏览器语言，如 zh-CN,zh"},
    )
    resolution: str = Field(
        max_length=32,
        description="屏幕分辨率，如 1920x1080",
        sa_column_kwargs={"comment": "屏幕分辨率，如 1920x1080"},
    )
    dpr: str = Field(
        default="1",
        max_length=16,
        description="设备像素比，如 1 / 2",
        sa_column_kwargs={"comment": "设备像素比，如 1 / 2"},
    )

    # 各类指纹噪声开关
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
