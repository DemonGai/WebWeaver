"""Alembic 运行环境（异步）：连接串取自应用配置，元数据取自 SQLModel 模型。

用法：
    uv run alembic upgrade head                       # 应用全部迁移
    uv run alembic revision --autogenerate -m "说明"  # 按模型差异生成迁移
    uv run alembic downgrade -1                       # 回退一步
    uv run alembic current / history
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

import app.models  # noqa: F401 - 导入以把 6 张表注册到 SQLModel.metadata
from alembic import context
from app.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串统一从 settings 取（backend/.env 的 DATABASE_URL），不写死在 alembic.ini 里
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = SQLModel.metadata


def render_item(type_, obj, autogen_context):
    """把 SQLModel 的包装类型渲染成标准 SQLAlchemy 类型。

    否则 autogenerate 会写出 ``sqlmodel.sql.sqltypes.AutoString(...)`` 却不 import
    sqlmodel，迁移脚本一跑就 NameError。
    """
    from sqlmodel.sql.sqltypes import AutoString, UTCDateTime

    if type_ == "type":
        if isinstance(obj, AutoString):
            length = getattr(obj, "length", None)
            return f"sa.String(length={length})" if length else "sa.String()"
        if isinstance(obj, UTCDateTime):
            return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # 列类型、服务端默认值的变更也纳入 autogenerate 比对
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
