"""账号表的 Cookie 字段：列类型、种子数据与 JSONB 往返。

Cookie 是登录态凭证，接口层故意不返回（见 ``app/models/account.py`` 注释），
所以这里从数据库侧验证「写进去是数组、读出来还是数组」。
"""

import asyncio

from sqlalchemy import select
from sqlmodel import SQLModel

from app.core.db import SessionLocal, dispose
from app.models import Account


def test_cookies_column_is_jsonb_and_nullable() -> None:
    column = SQLModel.metadata.tables["accounts"].c.cookies
    assert column.type.__class__.__name__ == "JSONB"
    # 为空表示「尚未采集」，不能设成 NOT NULL 逼着写空数组
    assert column.nullable
    assert column.comment, "cookies 列缺少中文注释"


def test_seeded_accounts_carry_cookies(seeded_database: None) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            accounts = list(await session.scalars(select(Account)))
            with_cookies = [a for a in accounts if a.cookies]
            assert len(with_cookies) == 3, "种子数据里应有 3 个账号带 Cookie"

            sample = with_cookies[0].cookies
            assert isinstance(sample, list) and sample
            cookie = sample[0]
            # 结构对齐 Playwright storage_state.cookies
            assert {"name", "value", "domain", "path"} <= set(cookie)
            assert cookie["domain"].startswith(".")

    try:
        asyncio.run(run())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001 - 清理失败不影响断言结果
            pass
