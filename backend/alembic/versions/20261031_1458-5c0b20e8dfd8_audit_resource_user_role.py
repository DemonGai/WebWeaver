"""audit resource user role

Revision ID: 5c0b20e8dfd8
Revises: 0e614e6e3b01
Create Date: 2026-10-31 14:58:30.457563

给 audit_logs.resource_type 的 CHECK 加两个取值：user（控制台成员）与 role（角色）。
改成员显示名、以后改角色授权都要能落一条可读的审计，
归到 auth 或 system 都会让「按资源筛选」失去意义。

Alembic 不比对 CHECK 约束，所以这里手写 drop + create，约束名沿用
SQLAlchemy 由枚举名生成的那个（auditresourcetype）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c0b20e8dfd8'
down_revision: Union[str, Sequence[str], None] = '0e614e6e3b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "auditresourcetype"

OLD_VALUES = (
    "browser",
    "account",
    "ip",
    "fingerprint",
    "kernel",
    "group",
    "binding",
    "auth",
    "system",
)
NEW_VALUES = (
    "browser",
    "account",
    "ip",
    "fingerprint",
    "kernel",
    "group",
    "binding",
    "auth",
    "user",
    "role",
    "system",
)


def _check(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"resource_type IN ({joined})"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(CONSTRAINT, "audit_logs", type_="check")
    op.create_check_constraint(CONSTRAINT, "audit_logs", _check(NEW_VALUES))


def downgrade() -> None:
    """Downgrade schema."""
    # 回退前先把 user / role 的记录改归 auth，否则新约束加不上
    op.execute(
        "UPDATE audit_logs SET resource_type = 'auth' "
        "WHERE resource_type IN ('user', 'role')"
    )
    op.drop_constraint(CONSTRAINT, "audit_logs", type_="check")
    op.create_check_constraint(CONSTRAINT, "audit_logs", _check(OLD_VALUES))
