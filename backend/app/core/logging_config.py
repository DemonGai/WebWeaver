"""企业级日志配置：loguru 控制台 + 滚动文件 + ELK JSON + request_id 链路追踪。

来源：hwkj 项目 app/core/logging_config.py，迁入 WebWeaver 后端并做了三点适配：
1. 日志目录/级别改由 settings 控制（默认 backend/logs、INFO）；
2. setup_logger() 幂等，可重复调用；
3. 接管标准库 logging（uvicorn 等），让三方库日志走同一套格式。
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

from loguru import logger

from app.core.config import BACKEND_ROOT, settings

# 全局 request_id 上下文变量，默认 "N/A"
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="N/A")

# 幂等标记：避免多处 import / 重复调用时日志被重复挂载
_configured = False


def _force_utf8_stdio() -> None:
    """把 stdout / stderr 的编码切到 UTF-8。

    Windows 下 Python 默认按系统代码页（cp936）编码输出，而 Git Bash / xterm 是
    UTF-8，于是中文日志变成「□□□□」这种方块。这里显式改编码；已经跑在 UTF-8
    环境（设置了 PYTHONIOENCODING / PYTHONUTF8）时什么都不做。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 已经被替换成不支持 reconfigure 的流（如 pytest 捕获），忽略即可
            continue


class InterceptHandler(logging.Handler):
    """把标准库 logging 的记录转发给 loguru，uvicorn 日志也能落到同一份文件里。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 跳过 logging 模块内部的 handle/_log/info 等包装帧，定位到真正的调用行。
        # 起点 2 对应 Handler.handle，故最终再减 1。
        frame = logging.currentframe().f_back
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        depth -= 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logger(force: bool = False) -> None:
    """企业级日志初始化配置（幂等）。"""
    global _configured
    if _configured and not force:
        return
    _configured = True

    # 必须在 logger.add(sys.stdout) 之前：sink 会记住当时的流编码
    _force_utf8_stdio()

    logger.remove()

    def request_id_filter(record: dict) -> bool:
        record["extra"]["request_id"] = request_id_ctx.get()
        return True

    # 控制台彩色格式
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<magenta>{extra[request_id]}</magenta> | "
        "<cyan>{file}:{line}</cyan> - "
        "<level>{message}</level>"
    )
    # JSON 模式下只保留核心字段，不需要颜色与排版
    json_format = "{time} | {level} | {file}:{line} | {message} | {extra}"

    log_path = Path(settings.log_dir)
    if not log_path.is_absolute():
        log_path = BACKEND_ROOT / log_path
    log_path.mkdir(parents=True, exist_ok=True)

    # 1. 控制台（人类可读）
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
        filter=request_id_filter,
    )
    # 2. 普通日志文件（按天 + 100MB 滚动，保留 30 天）
    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        format=log_format,
        level=settings.log_level,
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        # 落盘不做变量快照：本项目涉及账号密码、会话令牌，diagnose=True 会把局部变量
        # 打进日志。需要排查时临时把 LOG_DIAGNOSE 设为 True 即可。
        diagnose=settings.log_diagnose,
        filter=request_id_filter,
    )
    # 3. 错误日志（单独一份，保留 90 天）
    logger.add(
        log_path / "error.log",
        format=log_format,
        level="ERROR",
        rotation="50 MB",
        retention="90 days",
        compression="zip",
        enqueue=True,
        filter=lambda record: record["level"].no >= logger.level("ERROR").no,
    )
    # 4. ELK 分析的 JSON 日志
    logger.add(
        log_path / "elk_{time:YYYY-MM-DD}.json",
        format=json_format,
        level=settings.log_level,
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,  # 异步写入，提高高并发下的性能
        serialize=True,  # 核心参数：开启 JSON 序列化
        filter=request_id_filter,
    )

    _attach_stdlib_logging()


def _attach_stdlib_logging() -> None:
    """接管标准库 logging，避免 uvicorn 与 loguru 各自打一套格式。"""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    # 访问日志由应用层中间件统一记录（带 request_id + 耗时），关掉 uvicorn 自带的
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False

    # 降噪：第三方 HTTP 客户端每次请求都会打一条 INFO，会淹没业务日志
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


# ================== 上下文管理器 ==================
class RequestContext:
    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.token = None

    def __enter__(self):
        self.token = request_id_ctx.set(self.request_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        request_id_ctx.reset(self.token)


# ================== FastAPI 专用的异步上下文管理器 ==================
class AsyncRequestContext:
    """专为 FastAPI 设计的异步上下文管理器"""

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.token = None

    async def __aenter__(self):
        self.token = request_id_ctx.set(self.request_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        request_id_ctx.reset(self.token)


setup_logger()
