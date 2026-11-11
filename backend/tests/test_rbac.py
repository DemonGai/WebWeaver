"""RBAC：表结构约束、权限解析、三个只读接口。

种子数据是 35 个权限点、4 个角色、3 名成员：
owner 全部 35，admin 33（去掉成员/角色删除），operator 13，viewer 9。
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal, dispose
from app.main import app
from app.models import User
from app.services import rbac

client = TestClient(app)


def test_mapping_tables_have_unique_constraint() -> None:
    """同一成员不能被重复授权同一个角色，角色也不能重复挂同一权限点。"""
    from sqlmodel import SQLModel

    expected = {
        "user_roles": "uq_user_roles_user_role",
        "role_permissions": "uq_role_permissions_role_permission",
    }
    for table_name, constraint_name in expected.items():
        names = {constraint.name for constraint in SQLModel.metadata.tables[table_name].constraints}
        assert constraint_name in names, f"{table_name} 缺少唯一约束 {constraint_name}"


def test_users_table_never_exposes_password_hash_in_api(seeded_database: None) -> None:
    """成员表有密码哈希列，但接口响应里不能出现。"""
    from sqlmodel import SQLModel

    columns = {column.name for column in SQLModel.metadata.tables["users"].columns}
    assert {"username", "email", "password_hash", "is_superuser"} <= columns

    body = client.get("/api/rbac/users").json()
    for item in body["items"]:
        assert "password_hash" not in item


def test_permissions_catalog(seeded_database: None) -> None:
    body = client.get("/api/rbac/permissions").json()
    assert len(body["items"]) == 35
    codes = {item["code"] for item in body["items"]}
    assert {"browser:read", "browser:execute", "audit:export", "user:delete"} <= codes
    # 编码与 module/action 必须自洽
    for item in body["items"]:
        assert item["code"] == f"{item['module']}:{item['action']}"


def test_roles_carry_expected_permission_counts(seeded_database: None) -> None:
    body = client.get("/api/rbac/roles").json()
    roles = {item["code"]: item for item in body["items"]}
    assert list(roles) == ["owner", "admin", "operator", "viewer"]

    assert len(roles["owner"]["permission_codes"]) == 35
    # 管理员不能删除成员与角色，否则能把自己锁死
    assert len(roles["admin"]["permission_codes"]) == 33
    assert "user:delete" not in roles["admin"]["permission_codes"]
    assert len(roles["operator"]["permission_codes"]) == 13
    assert len(roles["viewer"]["permission_codes"]) == 9
    assert all(code.endswith(":read") for code in roles["viewer"]["permission_codes"])

    # 每名成员正好一个角色（admin、admin_chen、ops_lee、viewer_lin 共 4 人）
    assert sum(item["user_count"] for item in body["items"]) == 4
    assert roles["owner"]["is_system"] is True and roles["viewer"]["is_system"] is False


def test_users_carry_roles(seeded_database: None) -> None:
    body = client.get("/api/rbac/users").json()
    users = {item["username"]: item for item in body["items"]}
    # admin 是本地开发用的简口账号（admin / admin），其余三个是分工演示成员
    assert set(users) == {"admin", "admin_chen", "ops_lee", "viewer_lin"}
    assert users["admin"]["role_codes"] == ["owner"]
    assert users["admin_chen"]["role_codes"] == ["owner"]
    assert users["ops_lee"]["role_codes"] == ["operator"]
    assert users["viewer_lin"]["role_codes"] == ["viewer"]
    assert users["admin_chen"]["status"] == "active"


def test_effective_permissions_follow_roles(seeded_database: None) -> None:
    async def run() -> None:
        async with SessionLocal() as session:
            users = {user.username: user for user in await session.scalars(select(User))}
            owner = await rbac.permission_codes_of_user(session, users["admin_chen"].id)
            operator = await rbac.permission_codes_of_user(session, users["ops_lee"].id)
            viewer = await rbac.permission_codes_of_user(session, users["viewer_lin"].id)

            assert len(owner) == 35
            assert "audit:export" in owner

            # 运营能启停实例，但不能删资源、不能管成员
            assert "browser:execute" in operator
            assert "account:update" in operator
            assert "browser:delete" not in operator
            assert "user:delete" not in operator

            assert "browser:read" in viewer
            assert "browser:create" not in viewer

            assert await rbac.has_permission(session, users["ops_lee"].id, "browser:execute")
            assert not await rbac.has_permission(session, users["viewer_lin"].id, "browser:execute")

    try:
        asyncio.run(run())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001 - 清理失败不影响断言结果
            pass


def test_superuser_bypasses_roles(seeded_database: None) -> None:
    """超级管理员不挂角色也拿全部权限；用例自己清理成员。"""

    async def run() -> None:
        async with SessionLocal() as session:
            user = User(
                username="root_probe",
                email="root_probe@webweaver.io",
                display_name="临时超管",
                is_superuser=True,
            )
            session.add(user)
            await session.commit()

            codes = await rbac.permission_codes_of_user(session, user.id)
            assert len(codes) == 35
            assert "role:delete" in codes

            await session.delete(user)
            await session.commit()

            # 删掉之后不应再解析出任何权限
            assert await rbac.permission_codes_of_user(session, user.id) == set()

    try:
        asyncio.run(run())
    finally:
        try:
            asyncio.run(dispose())
        except Exception:  # noqa: BLE001
            pass
