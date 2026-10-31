"""请求链路日志中间件：为每个请求生成 request_id，并记录耗时与状态码。"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import logger, request_id_ctx

CallNext = Callable[[Request], Awaitable[Response]]


class RequestLogMiddleware(BaseHTTPMiddleware):
    """把 request_id 写进 contextvar，后续任何一行日志都会自动带上它。"""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        path = request.url.path
        method = request.method

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("{} {} 处理异常", method, path)
            raise
        else:
            cost_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            log = logger.warning if status >= 400 else logger.info
            log("{} {} -> {} ({:.1f}ms)", method, path, status, cost_ms)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
