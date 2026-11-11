"""fingerprint seed and probe fields

镜像里的内核是动态指纹：`--fingerprint=<seed>` 一个整数决定整套人格。原来这张表
只有静态模板字段（UA / 分辨率 / 噪声开关），缺了下发真正需要的 seed 与各内核
专有参数；同时 UA / 分辨率其实是种子算出来的结果，只能采集回填。

Revision ID: a7c31e5b9d24
Revises: 16d16e77cc49
Create Date: 2026-11-11 20:45:12.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c31e5b9d24'
down_revision: Union[str, Sequence[str], None] = '16d16e77cc49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── 下发参数 ──────────────────────────────────────────────────
    op.add_column('fingerprints', sa.Column(
        'seed', sa.Integer(), nullable=True,
        comment='指纹种子，一个整数决定整套人格；为空表示不指定',
    ))
    op.add_column('fingerprints', sa.Column(
        'platform_version', sa.String(length=32), nullable=True,
        comment='平台版本，如 10.0.0；仅 fingerprint-chromium 支持',
    ))
    op.add_column('fingerprints', sa.Column(
        'brand', sa.String(length=32), nullable=True,
        comment='浏览器品牌，如 Chrome / Edge；仅 fingerprint-chromium 支持',
    ))
    op.add_column('fingerprints', sa.Column(
        'brand_version', sa.String(length=32), nullable=True,
        comment='品牌版本号，如 146.0.7680.177',
    ))
    op.add_column('fingerprints', sa.Column(
        'hardware_concurrency', sa.Integer(), nullable=True,
        comment='navigator.hardwareConcurrency；仅 fingerprint-chromium 支持',
    ))
    op.add_column('fingerprints', sa.Column(
        'accept_lang', sa.String(length=128), nullable=True,
        comment='HTTP Accept-Language，如 zh-CN,zh；为空按 language 派生',
    ))
    op.add_column('fingerprints', sa.Column(
        'webrtc_ip', sa.String(length=64), nullable=True,
        comment='WebRTC 对外暴露的 IP；仅 CloakBrowser 支持',
    ))

    # ── 采集回执 ──────────────────────────────────────────────────
    op.add_column('fingerprints', sa.Column(
        'probed_at', sa.DateTime(timezone=True), nullable=True,
        comment='最近一次采集时间；为空表示从未采集，实测值不可信',
    ))
    op.add_column('fingerprints', sa.Column(
        'probed_digest', sa.String(length=32), nullable=True,
        comment='采集时的下发参数摘要；与当前参数算出的摘要不一致说明实测值已过期',
    ))
    op.add_column('fingerprints', sa.Column(
        'probe', postgresql.JSONB(), nullable=True,
        comment='采集到的完整人格快照（JSONB）：GPU、canvas hash、语言列表等',
    ))
    op.add_column('fingerprints', sa.Column(
        'probe_error', sa.String(length=512), nullable=True,
        comment='最近一次采集失败原因，成功时清空',
    ))

    # ── 口径纠正：这几个字段是结果不是输入 ────────────────────────
    # 只改注释，不动数据。种子决定了 UA / 分辨率，手填的值不会传给内核，
    # 注释里写明来源，免得后来人以为改这里能改指纹。
    op.alter_column('fingerprints', 'user_agent',
                    comment='User-Agent，由采集流程回填的实测值，不参与下发',
                    existing_type=sa.String(length=512), existing_nullable=False)
    op.alter_column('fingerprints', 'resolution',
                    comment='屏幕分辨率，由采集流程回填的实测值',
                    existing_type=sa.String(length=32), existing_nullable=False)
    op.alter_column('fingerprints', 'dpr',
                    comment='设备像素比，由采集流程回填的实测值',
                    existing_type=sa.String(length=16), existing_nullable=False)
    op.alter_column('fingerprints', 'language',
                    comment='界面语言（locale），如 zh-CN；映射 --lang / --fingerprint-locale',
                    existing_type=sa.String(length=64), existing_nullable=False)

    # 采集回填字段允许为空串：新建指纹时还没采集，UA 和分辨率都是空的。
    # 原来这两列 NOT NULL 且无默认值，插入时不带就直接报错。
    op.alter_column('fingerprints', 'user_agent',
                    server_default='',
                    existing_type=sa.String(length=512), existing_nullable=False)
    op.alter_column('fingerprints', 'resolution',
                    server_default='',
                    existing_type=sa.String(length=32), existing_nullable=False)

    # ── 回填种子 ──────────────────────────────────────────────────
    # 老数据是「静态模板」，没有种子，等于人格不可复现：删了这个 profile 就再也
    # 装不回同一个人。按 code 算一个确定性的值补上，同一个 code 永远得到同一个
    # 种子，pool 里的每条模板立刻变得可复现。
    #
    # 用 hashtext 而不是 random()：迁移重跑（或换环境重建库）结果一致，
    # 调试时不会出现「本地和线上同一条指纹长得不一样」。
    op.execute(
        "UPDATE fingerprints "
        "SET seed = 10000 + (abs(hashtext(code)::bigint) % 90000) "
        "WHERE seed IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('fingerprints', 'user_agent', server_default=None,
                    existing_type=sa.String(length=512), existing_nullable=False)
    op.alter_column('fingerprints', 'resolution', server_default=None,
                    existing_type=sa.String(length=32), existing_nullable=False)
    op.alter_column('fingerprints', 'user_agent',
                    comment='User-Agent 字符串',
                    existing_type=sa.String(length=512), existing_nullable=False)
    op.alter_column('fingerprints', 'resolution',
                    comment='屏幕分辨率，如 1920x1080',
                    existing_type=sa.String(length=32), existing_nullable=False)
    op.alter_column('fingerprints', 'dpr',
                    comment='设备像素比，如 1 / 2',
                    existing_type=sa.String(length=16), existing_nullable=False)
    op.alter_column('fingerprints', 'language',
                    comment='浏览器语言，如 zh-CN,zh',
                    existing_type=sa.String(length=64), existing_nullable=False)

    for name in (
        'probe_error', 'probe', 'probed_digest', 'probed_at',
        'webrtc_ip', 'accept_lang',
        'hardware_concurrency', 'brand_version', 'brand',
        'platform_version', 'seed',
    ):
        op.drop_column('fingerprints', name)
