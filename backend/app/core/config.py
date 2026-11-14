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
    # 双令牌：短令牌进 Authorization/Cookie 直接鉴权，长令牌只用来换短令牌。
    # 短令牌 30 分钟，到期由前端静默续期；长令牌 7 天，勾「记住我」延长到 30 天。
    auth_access_ttl_minutes: int = 30
    auth_refresh_ttl_minutes: int = 60 * 24 * 7
    auth_refresh_ttl_remember_minutes: int = 60 * 24 * 30
    # 会话绝对上限：无论怎么续期，超过这个时长必须重新登录。
    # 否则一个被偷走的刷新令牌可以靠不断续期永久有效。
    auth_absolute_ttl_minutes: int = 60 * 24 * 30
    # 访问令牌的签名密钥。生产必须通过环境变量覆盖，否则任何人都能伪造令牌。
    auth_jwt_secret: str = "webweaver-dev-only-secret-please-override-in-production"
    # Cookie 是否带 Secure：本地 http 调试必须 false，对外 https 部署必须 true
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_cookie_domain: str | None = None
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

    # ── 内核镜像 ──────────────────────────────────────────────────────
    # 内核以 Docker 镜像形式分发：这个仓库下每个 tag 对应一个内核的一个版本。
    # tag 命名见 app/services/kernel_scan.py 的 parse_tag()，形如
    # `cloakbrowser`（滚动）与 `cloakbrowser-146.0.7680.177.5`（固定版本）。
    # 「有没有这个内核」只看本地镜像，不再扫磁盘目录。
    kernel_image_registry: str = "demon1315132284/browser_engine"
    # docker 可执行文件；容器内跑后端时通常是 docker 或 /usr/bin/docker
    kernel_docker_bin: str = "docker"
    # 单个镜像拉取超时（秒）。500MB 压缩层的国内速度下留足余量
    kernel_image_pull_timeout: int = 1800

    # noVNC 地址里用的主机名。留空就跟随浏览器访问控制台时的 host，这样从别的
    # 机器打开页面，画面地址也指向这台宿主机；部署在反代后面时显式配一个外网域名。
    novnc_host: str | None = None

    # 打包部署时前端构建产物（dist）的目录。留空则只提供 API，页面由 Vite / 反向
    # 代理出；单容器部署把它指向 /app/frontend/dist，由 FastAPI 顺带托管页面。
    frontend_dist: str | None = None

    # ── 内核文件（旧：磁盘目录方式，已弃用） ───────────────────────────
    # 保留字段只为兼容还没迁移完的部署，新逻辑不再读写这个目录
    kernel_root: str = "browser_engine"
    kernel_pip_index: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    kernel_download_mirror: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
