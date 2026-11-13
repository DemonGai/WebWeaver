"""accounts: add login_url, 唯一约束从平台改成登录地址

账号不再由用户指定平台，改填登录页地址，平台从域名推导。

- 新增 ``login_url``（可空：历史数据没有这个信息，不强行补假值）
- 唯一约束换成 ``(login_url, username)``：同一登录页下账号名唯一。
  Postgres 的唯一约束不约束 NULL，所以历史数据可以多条留空并存
- 旧约束 ``(platform, username)`` 去掉：同一平台的不同站点
  （amazon.com / amazon.co.jp）本来就允许同名账号

Revision ID: f1c7d2b93a40
Revises: e8b3d5a1c742
Create Date: 2026-11-13 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c7d2b93a40'
down_revision: Union[str, Sequence[str], None] = 'e8b3d5a1c742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'accounts',
        sa.Column(
            'login_url',
            sa.String(length=512),
            nullable=True,
            comment='登录页地址；平台由域名推导，不单独指定',
        ),
    )
    op.create_index('ix_accounts_login_url', 'accounts', ['login_url'], unique=False)

    op.drop_constraint('uq_accounts_platform_username', 'accounts', type_='unique')
    op.create_unique_constraint(
        'uq_accounts_login_url_username', 'accounts', ['login_url', 'username']
    )


def downgrade() -> None:
    op.drop_constraint('uq_accounts_login_url_username', 'accounts', type_='unique')
    op.create_unique_constraint(
        'uq_accounts_platform_username', 'accounts', ['platform', 'username']
    )
    op.drop_index('ix_accounts_login_url', table_name='accounts')
    op.drop_column('accounts', 'login_url')
