"""drop fingerprints.webrtc_ip

「WebRTC 出口 IP」不该是指纹的属性。WebRTC 会把 ICE 候选里的地址报给页面，
绕过代理时就会泄露真实 IP —— 但「应该报哪个 IP」这件事，答案属于**实例绑定的
那条出口 IP**（`browsers.ip_id` → `ips.address`），属于网络层，不属于人格层。

留成模板上的自由文本有三个问题：手填的值和真实流量无关，填了反而制造
「WebRTC 说 A、HTTP 从 B 走」的矛盾；改一次就得重采一次；而且和 IP 池里
配好的地址、协议、认证完全脱节。列一并删除，等启动链路接上代理后，由实例
绑定的 IP 直接派生 `--fingerprint-webrtc-ip`。

Revision ID: d7a4c2f1e8b3
Revises: c4e2a17b8d90
Create Date: 2026-11-13 20:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a4c2f1e8b3'
down_revision: Union[str, Sequence[str], None] = 'c4e2a17b8d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('fingerprints', 'webrtc_ip')


def downgrade() -> None:
    op.add_column(
        'fingerprints',
        sa.Column(
            'webrtc_ip',
            sa.String(length=64),
            nullable=True,
            comment='WebRTC 对外暴露的 IP；仅 CloakBrowser 支持',
        ),
    )
