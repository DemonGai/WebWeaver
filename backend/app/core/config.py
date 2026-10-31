from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 根目录：相对路径的配置（日志目录、内核目录）都以它为基准
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，可通过 backend/.env 覆盖。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WebWeaver API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    debug: bool = True

    # 前端开发服务器地址，用于 CORS 白名单
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # PostgreSQL 18（docker-compose.yml 的 webweaver-postgres 服务）
    database_url: str = "postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver"
    db_echo: bool = False
    # 启动时按模型自动建表。表结构现已交给 Alembic 管理，默认关闭；
    # 只想快速起个临时库时可以临时设 true。
    db_auto_create: bool = False
    # 关闭连接池：每次请求新建连接。用于测试（TestClient 每个请求一个事件循环，
    # 池化连接会跨循环，asyncpg 直接报 “Event loop is closed”）或无长驻进程的环境。
    db_pool_disabled: bool = False

    # ── 认证 ──────────────────────────────────────────────────────────
    # 会话令牌有效期；勾选「记住我」用较长的那一档
    auth_session_ttl_minutes: int = 720
    auth_session_ttl_remember_minutes: int = 60 * 24 * 30
    # 连续登录失败到多少次锁账号、锁多久
    auth_max_failed_logins: int = 5
    auth_lock_minutes: int = 15
    # 是否开放自助注册。内网演示期默认开着；正式环境应关掉，改由管理员建号
    auth_allow_register: bool = True
    # 密码重置链接有效期
    auth_reset_ttl_minutes: int = 30
    # DEBUG 下把重置令牌直接放进响应，方便本地不走邮件就把流程点通
    # （生产必须 false，否则等于任何人都能重置任意邮箱的密码）
    auth_expose_reset_token: bool = False

    # 日志：目录为相对路径时以 backend/ 为基准
    log_dir: str = "logs"
    log_level: str = "INFO"
    # 是否在异常日志中附带变量快照（含敏感数据的项目应保持 False）
    log_diagnose: bool = False

    # ── 内核文件 ──────────────────────────────────────────────────────
    # 内核目录根：相对路径以 backend/ 为基准。目录约定见 app/services/kernel_scan.py
    # 目录名固定为 browser_engine（存放各家浏览器内核的发行包解压结果）
    kernel_root: str = "browser_engine"
    # pip 通道装内核时用的索引；与 pyproject 里的默认索引保持一致，国内装包快
    kernel_pip_index: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    # 大包下载走 GitHub 加速站，形如 https://gh-proxy.com/ 。留空则直连；
    # 直连时 github release 资源在国内只有 ~30 KB/s（536MB 要 5 小时），基本等于卡死
    kernel_download_mirror: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
