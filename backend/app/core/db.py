"""数据库连接：SQLAlchemy 2.x 异步引擎 + 会话工厂 + 连通性探测。"""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# NullPool 下不能传 pool_size / max_overflow，参数要分开建
_pool_options: dict[str, object] = (
    {"poolclass": NullPool}
    if settings.db_pool_disabled
    else {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }
)

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    **_pool_options,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：按请求提供一个会话。"""
    async with SessionLocal() as session:
        yield session


async def ping() -> tuple[bool, str | None]:
    """探测数据库连通性，返回 (是否可用, 版本号或错误信息)。"""
    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SHOW server_version"))
        return True, str(version)
    except Exception as exc:  # noqa: BLE001 - 健康检查需要吞掉所有异常
        return False, f"{type(exc).__name__}: {exc}"


async def alembic_revision() -> str | None:
    """当前数据库已应用的迁移版本；表不存在（没跑过迁移）时返回 None。"""
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text("select version_num from alembic_version"))
    except Exception:  # noqa: BLE001 - 仅用于启动日志提示
        return None


async def create_all() -> list[str]:
    """按模型定义建表（已存在则跳过）。开发期用，生产应交给 Alembic 迁移。"""
    from sqlmodel import SQLModel

    import app.models  # noqa: F401 - 导入以把 6 张表注册到 metadata

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    return sorted(SQLModel.metadata.tables)


async def dispose() -> None:
    await engine.dispose()
