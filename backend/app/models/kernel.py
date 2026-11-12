"""内核表：CloakBrowser / Camoufox / fingerprint-chromium / ungoogled-chromium 等浏览器内核。"""

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import IdMixin, TimestampMixin, enum_type
from app.models.enums import KernelChannel, KernelStatus


class Kernel(IdMixin, TimestampMixin, table=True):
    __tablename__ = "kernels"
    __table_args__ = ({"comment": "内核表：浏览器内核及其版本、发布通道与反检测能力"},)

    name: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="内核名称",
        sa_column_kwargs={"comment": "内核名称（唯一）"},
    )
    # Chromium / Firefox
    engine: str = Field(
        max_length=32,
        index=True,
        description="上游引擎",
        sa_column_kwargs={"comment": "上游引擎：Chromium / Firefox"},
    )
    base_version: str | None = Field(
        default=None,
        max_length=32,
        description="上游基线版本",
        sa_column_kwargs={"comment": "上游基线版本号"},
    )
    version: str = Field(
        max_length=64,
        description="当前部署版本",
        sa_column_kwargs={"comment": "当前部署的版本号"},
    )
    latest_version: str | None = Field(
        default=None,
        max_length=64,
        description="可用的最新版本",
        sa_column_kwargs={"comment": "可升级到的最新版本号"},
    )
    channel: KernelChannel = Field(
        default=KernelChannel.stable,
        sa_type=enum_type(KernelChannel, 16),
        description="发布通道：stable / beta / nightly",
        sa_column_kwargs={"comment": "发布通道：stable 稳定版 / beta 测试版 / nightly 每日构建"},
    )
    arch: str = Field(
        default="x64",
        max_length=16,
        description="架构：x64 / arm64",
        sa_column_kwargs={"comment": "目标架构：x64 / arm64"},
    )
    image: str | None = Field(
        default=None,
        max_length=255,
        description="镜像或安装包地址（registry/name:tag）",
        sa_column_kwargs={"comment": "镜像或安装包地址（registry/name:tag）"},
    )
    repo_url: str | None = Field(
        default=None,
        max_length=255,
        description="上游源码仓库地址（GitHub）",
        sa_column_kwargs={"comment": "上游源码仓库地址（GitHub 页面）"},
    )
    mirror_url: str | None = Field(
        default=None,
        max_length=255,
        description="国内镜像仓库地址（Gitee 等）",
        sa_column_kwargs={"comment": "国内镜像仓库地址（Gitee），为空表示未配置镜像"},
    )
    detection_level: str | None = Field(
        default=None,
        max_length=64,
        description="反检测实现层级，如「C++ 层注入」",
        sa_column_kwargs={"comment": "反检测实现层级，如「C++ 层注入」"},
    )
    status: KernelStatus = Field(
        default=KernelStatus.active,
        sa_type=enum_type(KernelStatus, 16),
        index=True,
        description="状态：active / testing / deprecated",
        sa_column_kwargs={"comment": "状态：active 可用 / testing 测试中 / deprecated 已弃用"},
    )
    pass_rate: int = Field(
        default=0,
        ge=0,
        le=100,
        description="反检测通过率 %",
        sa_column_kwargs={"comment": "反检测通过率（百分比）"},
    )
    share: int = Field(
        default=0,
        ge=0,
        le=100,
        description="实例占比 %",
        sa_column_kwargs={"comment": "实例占比（百分比）"},
    )
    note: str | None = Field(
        default=None,
        sa_type=Text,
        description="备注 / 建议用途",
        sa_column_kwargs={"comment": "备注与建议用途"},
    )
