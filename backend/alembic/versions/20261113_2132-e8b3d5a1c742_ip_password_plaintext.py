"""rename ips.password_encrypted to ips.password (plaintext)

代理密码改成明文存。原因很实际：前端「复制代理地址」要直接拼出
``socks5://user:pass@host:port`` 交给别的工具用，加密列在这条链路上只能
先解密再拼，而库里的代理密码本来就是供应商随订阅下发的凭据，单独加密
并不能提高多少安全性，反而让接口层必须多带一个解密依赖。

列名同步从 ``password_encrypted`` 改成 ``password``，否则名实不符。

Revision ID: e8b3d5a1c742
Revises: d7a4c2f1e8b3
Create Date: 2026-11-13 21:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b3d5a1c742'
down_revision: Union[str, Sequence[str], None] = 'd7a4c2f1e8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'ips',
        'password_encrypted',
        new_column_name='password',
        existing_type=sa.String(length=255),
        type_=sa.String(length=128),
        existing_nullable=True,
        comment='代理认证密码（明文，供前端复制带认证的地址）',
    )


def downgrade() -> None:
    op.alter_column(
        'ips',
        'password',
        new_column_name='password_encrypted',
        existing_type=sa.String(length=128),
        type_=sa.String(length=255),
        existing_nullable=True,
        comment='代理认证密码（加密存储，不落明文）',
    )
