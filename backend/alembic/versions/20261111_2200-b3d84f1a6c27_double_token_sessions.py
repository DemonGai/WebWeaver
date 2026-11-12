"""double token sessions

会话从「一个长期令牌」改为「短访问令牌 + 长刷新令牌」：

- 访问令牌是自包含 JWT，不进这张表，靠载荷里的 `sid` 关联会话；
- 刷新令牌仍是随机串，摘要落在 `refresh_hash`（原来的 `token_hash`）；
- 每次刷新都会轮转，上一代摘要留在 `prev_refresh_hash` 用于重放检测；
- `absolute_expires_at` 是会话硬上限，防止不断续期导致会话永不过期。

存量会话在迁移时统一吊销：它们手上的令牌是按旧协议签的随机串，没有配套的
刷新令牌，继续留着只会让前端在第一次续期时莫名其妙失败。让它明确地重新登录
一次，比留下一个半可用状态干净。

Revision ID: b3d84f1a6c27
Revises: a7c31e5b9d24
Create Date: 2026-11-11 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d84f1a6c27'
down_revision: Union[str, Sequence[str], None] = 'a7c31e5b9d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── 列语义调整：token_hash 存的是刷新令牌摘要 ──────────────────
    op.alter_column(
        'auth_sessions', 'token_hash', new_column_name='refresh_hash',
    )
    op.alter_column(
        'auth_sessions', 'refresh_hash',
        comment='刷新令牌的 SHA-256 摘要（64 位十六进制，明文不落库）',
        existing_type=sa.String(length=64), existing_nullable=False,
    )
    op.alter_column(
        'auth_sessions', 'expires_at',
        comment='刷新令牌过期时间（UTC），每次续期向后滑动',
        existing_type=sa.DateTime(timezone=True), existing_nullable=False,
    )

    # ── 轮转与重放检测 ────────────────────────────────────────────
    op.add_column('auth_sessions', sa.Column(
        'prev_refresh_hash', sa.String(length=64), nullable=True,
        comment='上一代刷新令牌摘要：再次出现说明令牌被复制，触发整场会话吊销',
    ))
    op.create_index(
        'ix_auth_sessions_prev_refresh_hash', 'auth_sessions', ['prev_refresh_hash'],
    )
    op.add_column('auth_sessions', sa.Column(
        'rotated_at', sa.DateTime(timezone=True), nullable=True,
        comment='最近一次刷新令牌轮转时间（UTC）',
    ))

    # ── 会话绝对上限 ──────────────────────────────────────────────
    # 先加可空列、回填、再置 NOT NULL：直接加非空列会让存量行没有值。
    # 存量会话按「签发后 30 天」封顶，与新的 auth_absolute_ttl_minutes 一致。
    op.add_column('auth_sessions', sa.Column(
        'absolute_expires_at', sa.DateTime(timezone=True), nullable=True,
        comment='会话绝对上限（UTC）：无论怎么续期，超过此时间必须重新登录',
    ))
    # 续期窗口按「记住我」分两档，所以得记住这个会话是哪一档：
    # 只看 expires_at 推不出来，因为它每次轮转都会被推后。
    op.add_column('auth_sessions', sa.Column(
        'remember', sa.Boolean(), nullable=False, server_default=sa.text('false'),
        comment='登录时是否勾选「记住我」：决定每次续期把有效期推到多长',
    ))
    op.execute(
        "UPDATE auth_sessions "
        "SET absolute_expires_at = issued_at + interval '30 days' "
        "WHERE absolute_expires_at IS NULL"
    )
    op.alter_column(
        'auth_sessions', 'absolute_expires_at', nullable=False,
        existing_type=sa.DateTime(timezone=True),
    )
    op.create_index(
        'ix_auth_sessions_absolute_expires_at', 'auth_sessions', ['absolute_expires_at'],
    )

    # ── 吊销原因取值扩充 ──────────────────────────────────────────
    op.alter_column(
        'auth_sessions', 'revoked_reason',
        comment='吊销原因：logout / logout_all / password_change / password_reset '
                '/ reuse_detected / admin / migration',
        existing_type=sa.String(length=64), existing_nullable=True,
    )

    # ── 旧令牌一次性作废 ──────────────────────────────────────────
    # 旧协议只发一个长期随机令牌，没有刷新令牌可轮转。留着这些行的话，
    # 客户端会在第一次续期时拿到 401，反而更难排查；直接标记清楚。
    op.execute(
        "UPDATE auth_sessions "
        "SET revoked_at = now(), revoked_reason = 'migration' "
        "WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_auth_sessions_absolute_expires_at', table_name='auth_sessions')
    op.drop_column('auth_sessions', 'absolute_expires_at')
    # IF EXISTS：这个迁移的早期版本在库里已经跑过一次（当时还没有 remember 列），
    # 回退时不能假设它一定存在
    op.execute('ALTER TABLE auth_sessions DROP COLUMN IF EXISTS remember')
    op.drop_column('auth_sessions', 'rotated_at')
    op.drop_index('ix_auth_sessions_prev_refresh_hash', table_name='auth_sessions')
    op.drop_column('auth_sessions', 'prev_refresh_hash')

    op.alter_column(
        'auth_sessions', 'expires_at',
        comment='过期时间（UTC），到期后不再接受该令牌',
        existing_type=sa.DateTime(timezone=True), existing_nullable=False,
    )
    op.alter_column(
        'auth_sessions', 'revoked_reason',
        comment='吊销原因：logout 主动注销 / password_reset 改密 / admin 被踢',
        existing_type=sa.String(length=64), existing_nullable=True,
    )
    op.alter_column(
        'auth_sessions', 'refresh_hash', new_column_name='token_hash',
    )
    op.alter_column(
        'auth_sessions', 'token_hash',
        comment='令牌的 SHA-256 摘要（64 位十六进制，明文不落库）',
        existing_type=sa.String(length=64), existing_nullable=False,
    )
