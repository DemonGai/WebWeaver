from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core import db
from app.core.config import settings
from app.core.logging_config import logger, setup_logger
from app.core.middleware import RequestLogMiddleware

# 导入即完成首次配置；此处显式再调一次，保证 reload / 测试入口也走同一套
setup_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("{} {} 启动中……", settings.app_name, settings.app_version)

    ok, info = await db.ping()
    if ok:
        logger.info("PostgreSQL 已连接（server_version={}）", info)
        if settings.db_auto_create:
            try:
                tables = await db.create_all()
                logger.info("数据表已就绪：{}", "、".join(tables))
            except Exception as exc:  # noqa: BLE001 - 建表失败不阻断服务启动
                logger.exception("数据表初始化失败：{}", exc)
        else:
            revision = await db.alembic_revision()
            if revision:
                logger.info("表结构由 Alembic 管理，当前版本 {}", revision)
            else:
                logger.warning("未检测到迁移版本，请先执行：uv run alembic upgrade head")
    else:
        logger.warning("PostgreSQL 连接失败，接口仍可启动：{}", info)

    yield

    await db.dispose()
    logger.info("{} 已关闭", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="WebWeaver 后端服务（前后端分离，前端位于 ../frontend）",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # 中间件后加的在外层：请求日志要能包住 CORS 预检
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)

    app.include_router(api_router, prefix=settings.api_prefix)

    # 单容器部署：前端构建产物由同一个进程顺带托管，省掉 nginx 那层。
    # 只有显式配了 FRONTEND_DIST 且目录里真有 index.html 才启用；开发期不配，
    # 行为与前后端分离时完全一致。
    dist = _frontend_dist()
    if dist is None:

        @app.get("/", include_in_schema=False)
        async def root() -> dict[str, str]:
            return {
                "service": settings.app_name,
                "docs": "/docs",
                "health": f"{settings.api_prefix}/health",
            }

    else:
        # 静态资源按目录挂载（带 ETag / 缓存头）；其余路径交给 SPA 兜底，
        # 这样刷新 /browsers 这类前端路由不会 404。
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path:
                candidate = (dist / full_path).resolve()
                # 只允许 dist 内的文件，挡住 ../ 之类的目录穿越
                if candidate.is_file() and candidate.is_relative_to(dist):
                    return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def _frontend_dist() -> Path | None:
    """前端 dist 目录；没配置或没构建过就返回 None。"""
    if not settings.frontend_dist:
        return None
    dist = Path(settings.frontend_dist).expanduser().resolve()
    if not (dist / "index.html").is_file():
        logger.warning("FRONTEND_DIST 指向的目录没有 index.html，跳过页面托管：{}", dist)
        return None
    return dist


app = create_app()
