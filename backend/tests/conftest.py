"""测试夹具：数据类接口依赖数据库，这里保证库里有演示数据。

演示集群数据（内核 / 实例 / 账号 / 代理 / 指纹 / 审计样例 / 额外成员）现在放在
``tests/demo_cluster.py``，只在跑测试时写入；生产初始化脚本只建工作区、权限
目录和超级管理员。

种子脚本是幂等的（库里已有数据就跳过），所以重复跑测试不会叠加行数。
数据库连不上时跳过依赖它的用例，认证 / 内核那些纯内存接口照常跑。
"""

import os

# 必须在导入 app 之前设好：TestClient 不进入上下文管理器时每个请求都会新建
# 事件循环，连接池里绑定旧循环的 asyncpg 连接会直接抛 “Event loop is closed”。
os.environ["DB_POOL_DISABLED"] = "true"

import asyncio  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from demo_cluster import seed_demo_cluster  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.db import SessionLocal, dispose  # noqa: E402
from app.models import AuditLog  # noqa: E402
from app.services.seed import seed  # noqa: E402

# TestClient 的请求没有真实来源地址，client.host 固定是 "testclient"，
# 正好可以作为「这条审计是测试写的」的标记
TEST_CLIENT_HOST = "testclient"


@pytest.fixture(scope="session", autouse=True)
def clean_test_audit_logs() -> Iterator[None]:
    """跑完清掉测试期间认证接口写下的审计日志。

    发信 / 重置密码接口现在会真实落审计，每跑一次测试就多几行；
    不清掉会让开发库越堆越多。只删 ip_address 为 testclient 的行，
    种子数据和手工操作的记录都不受影响。
    """
    yield

    async def run() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(AuditLog).where(AuditLog.ip_address == TEST_CLIENT_HOST))
            await session.commit()

    try:
        asyncio.run(run())
    except Exception:  # noqa: BLE001 - 清理失败不应让测试结果变红
        pass
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture(scope="session")
def seeded_database() -> None:
    """确保各张表里有种子数据；连不上库时跳过当前用例。"""

    async def run() -> None:
        async with SessionLocal() as session:
            # 先建运行必需的数据（工作区 / 权限 / 超管），再灌演示集群数据；
            # 演示数据只属于测试，不再由 app.services.seed 写入业务库
            await seed(session)
            await seed_demo_cluster(session)

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - 连不上库就跳过，不阻塞其它用例
        pytest.skip(f"数据库不可用，跳过数据类用例：{exc}")
    finally:
        # NullPool 下 dispose 基本是空操作，包一层避免清理异常掩盖真实结果
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass
