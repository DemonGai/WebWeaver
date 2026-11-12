"""drop kernel is_primary

「设为主力内核」这个功能删掉了：新建实例时并不是按这个标记选内核，页面上
唯一的入口是详情页一个按钮，和「当前版本」这类真正影响运行时的设置在
心智上容易混。字段一并删除，避免留下没人读的列。

Revision ID: c4e2a17b8d90
Revises: b3d84f1a6c27
Create Date: 2026-11-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e2a17b8d90'
down_revision: Union[str, Sequence[str], None] = 'b3d84f1a6c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('kernels', 'is_primary')


def downgrade() -> None:
    op.add_column(
        'kernels',
        sa.Column(
            'is_primary',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment='是否为主力内核，新建实例默认使用',
        ),
    )
