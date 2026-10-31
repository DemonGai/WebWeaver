"""表模型的结构约束（纯元数据断言，不需要数据库）。"""

from sqlalchemy import CheckConstraint, Uuid
from sqlmodel import SQLModel

import app.models  # noqa: F401 - 注册模型

BINDING_TABLES = {
    "browser_account_bindings",
    "browser_ip_bindings",
    "browser_fingerprint_bindings",
}


def test_all_tables_registered() -> None:
    assert set(SQLModel.metadata.tables) == {
        "accounts",
        "audit_logs",
        "auth_sessions",
        "browsers",
        "browser_account_bindings",
        "browser_fingerprint_bindings",
        "browser_ip_bindings",
        "fingerprints",
        "groups",
        "ips",
        "kernels",
        "password_reset_tokens",
        "permissions",
        "role_permissions",
        "roles",
        "user_roles",
        "users",
        "workspaces",
    }


def test_primary_key_is_uuid_without_autoincrement() -> None:
    for name, table in SQLModel.metadata.tables.items():
        pk_columns = list(table.primary_key.columns)
        assert len(pk_columns) == 1, f"{name} 应该有且只有一个主键"
        pk = pk_columns[0]
        assert pk.name == "id", f"{name} 的主键列名应为 id"
        assert isinstance(pk.type, Uuid), f"{name} 主键类型应为 UUID，实际是 {pk.type}"
        # 自增只对整数主键生效，这里显式断言没有打开
        assert pk.autoincrement in (False, "auto"), f"{name} 主键不应自增"


def test_foreign_keys_point_to_existing_tables() -> None:
    tables = SQLModel.metadata.tables
    for name, table in tables.items():
        for fk in table.foreign_keys:
            target = fk.column.table.name
            assert target in tables, f"{name}.{fk.parent.name} 指向了不存在的表 {target}"


def test_every_table_and_column_has_comment() -> None:
    """表与字段都必须带中文注释，落到数据库就是 COMMENT ON。"""
    for name, table in SQLModel.metadata.tables.items():
        assert table.comment, f"{name} 缺少表注释"
        for column in table.columns:
            assert column.comment, f"{name}.{column.name} 缺少字段注释"


def test_binding_logs_are_append_only() -> None:
    """绑定日志只追加：没有 updated_at，改历史应当是再写一条。"""
    for name in BINDING_TABLES:
        columns = {column.name for column in SQLModel.metadata.tables[name].columns}
        assert "created_at" in columns, f"{name} 缺少操作时间"
        assert "updated_at" not in columns, f"{name} 是日志表，不该有 updated_at"


def test_binding_logs_reference_browser_and_resource() -> None:
    tables = SQLModel.metadata.tables
    expected = {
        "browser_account_bindings": ("browser_id", "account_id"),
        "browser_ip_bindings": ("browser_id", "ip_id"),
        "browser_fingerprint_bindings": ("browser_id", "fingerprint_id"),
    }
    for name, columns in expected.items():
        fk_columns = {fk.parent.name for fk in tables[name].foreign_keys}
        assert set(columns) <= fk_columns, f"{name} 的外键列不完整：{fk_columns}"


def test_mode_always_matches_resource_id() -> None:
    """直连 / 默认模式不指向具体资源，代理 / 模板模式必须指向资源。"""
    expected = {
        "browsers": {
            "ck_browsers_ip_mode_target",
            "ck_browsers_fingerprint_mode_target",
        },
        "browser_ip_bindings": {"ck_browser_ip_bindings_mode_target"},
        "browser_fingerprint_bindings": {"ck_browser_fingerprint_bindings_mode_target"},
    }
    for name, names in expected.items():
        present = {
            constraint.name
            for constraint in SQLModel.metadata.tables[name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert names <= present, f"{name} 缺少模式约束：{names - present}"


def test_browser_mode_defaults() -> None:
    """默认模式是直连与原生指纹，不是「未绑定」。"""
    browser = SQLModel.metadata.tables["browsers"]
    assert browser.c.ip_mode.default.arg == "direct"
    assert browser.c.fingerprint_mode.default.arg == "default"


def test_audit_log_is_append_only() -> None:
    """审计表只追加：只有发生时间，没有更新时间。"""
    columns = {column.name for column in SQLModel.metadata.tables["audit_logs"].columns}
    assert "occurred_at" in columns
    assert "updated_at" not in columns


def test_audit_log_resource_id_has_no_foreign_key() -> None:
    """resource_id 是逻辑引用：资源删除后审计记录仍要能查。"""
    table = SQLModel.metadata.tables["audit_logs"]
    assert table.c.resource_id.nullable, "resource_id 应允许为空（如系统级操作）"
    assert not table.c.resource_id.foreign_keys, "resource_id 不应建外键"


def test_audit_log_keeps_request_context() -> None:
    """审计要能和请求日志对上号：request_id / IP / UA 三个链路字段都不能少。"""
    columns = {column.name for column in SQLModel.metadata.tables["audit_logs"].columns}
    assert {"request_id", "ip_address", "user_agent"} <= columns


def test_audit_log_changes_is_jsonb() -> None:
    table = SQLModel.metadata.tables["audit_logs"]
    assert table.c.changes.type.__class__.__name__ == "JSONB"
