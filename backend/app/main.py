from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }

    return app


app = create_app()
