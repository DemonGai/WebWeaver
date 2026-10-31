"""add table and column comments

Revision ID: c07be0cb5088
Revises: 4f2f2d207b70
Create Date: 2026-10-31 13:24:00

为 6 张业务表补齐表级与字段级中文注释，数据库里可通过 psql 的 \\d+ 或
information_schema 直接查看。注释文本与 app/models 中的定义一一对应。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c07be0cb5088"
down_revision: str | None = "4f2f2d207b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 表注释：{表名: 中文说明}
TABLE_COMMENTS: dict[str, str] = {
    "accounts": "账号表：各平台店铺与社媒账号，可归属分组并绑定浏览器实例",
    "browsers": "浏览器表：一个浏览器实例，组合 profile、内核、指纹、出口 IP 与账号",
    "fingerprints": "指纹表：浏览器指纹模板，定义 UA、时区、分辨率与各类噪声伪装项",
    "groups": "分组表：按业务线或店铺划分浏览器、账号与 IP 资源，支持二级分组",
    "ips": "IP 表：出口代理资源（住宅 / 机房 / 移动），供浏览器实例绑定",
    "kernels": "内核表：浏览器内核及其版本、发布通道与反检测能力",
}

# 字段注释：{表名: {字段名: 中文说明}}
COLUMN_COMMENTS: dict[str, dict[str, str]] = {
    "accounts": {
        "created_at": "创建时间（UTC）",
        "email": "绑定邮箱",
        "group_id": "所属分组 ID，为空表示未分组",
        "health": "账号健康度（百分比）",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "last_login_at": "最近登录时间",
        "note": "备注",
        "password_encrypted": "登录密码（加密存储，不落明文）",
        "platform": "所属平台，如 Amazon / TikTok / Facebook",
        "region": "注册地或归属区域",
        "registered_at": "注册时间",
        "status": "状态：logged_in 已登录 / in_session 会话中 / restricted 受限 / unbound 未绑定",
        "updated_at": "最后更新时间（UTC）",
        "username": "平台登录名（与平台联合唯一）",
    },
    "browsers": {
        "account_id": "绑定的账号 ID",
        "cdp_url": "Chrome DevTools Protocol 调试地址",
        "created_at": "创建时间（UTC）",
        "fingerprint_id": "绑定的指纹 ID",
        "fps": "当前画面帧率",
        "group_id": "所属分组 ID，为空表示未分组",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "ip_id": "绑定的出口 IP ID",
        "kernel_id": "使用的内核 ID",
        "last_active_at": "最近活跃时间",
        "latency_ms": "操作链路延迟（毫秒）",
        "name": "实例名称（唯一，如 brw-us-west-042）",
        "note": "备注",
        "started_at": "本次启动时间",
        "status": "状态：queued 排队 / running 运行中 / idle 空闲 / error 异常 / stopped 已停止",
        "updated_at": "最后更新时间（UTC）",
        "vnc_port": "noVNC 监听端口",
        "vnc_url": "noVNC 远程会话地址",
    },
    "fingerprints": {
        "audio_noise": "是否开启 AudioContext 指纹噪声",
        "canvas_noise": "是否开启 Canvas 指纹噪声",
        "code": "指纹编号（唯一，如 fp-win11-c128）",
        "created_at": "创建时间（UTC）",
        "dpr": "设备像素比，如 1 / 2",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "kernel_id": "适配的内核 ID，为空表示不限内核",
        "language": "浏览器语言，如 zh-CN,zh",
        "name": "指纹名称",
        "platform": "平台描述，如 Windows 11 / macOS 14.5",
        "platform_family": "平台族：windows / macos / linux / android / ios",
        "resolution": "屏幕分辨率，如 1920x1080",
        "status": "状态：active 可用 / needs_upgrade 待升级 / expired 已过期",
        "timezone": "时区，如 Asia/Shanghai",
        "uniqueness": "唯一性得分（0-100），无法评估时为空",
        "updated_at": "最后更新时间（UTC）",
        "user_agent": "User-Agent 字符串",
        "warning": "异常提示文案",
        "webgl_noise": "是否开启 WebGL 指纹噪声",
        "webrtc_protected": "是否开启 WebRTC 防泄漏",
    },
    "groups": {
        "code": "分组业务标识（唯一 slug，配置与导入导出引用）",
        "color": "前端标签颜色，形如 #4171f1",
        "created_at": "创建时间（UTC）",
        "description": "分组说明",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "is_default": "是否为默认分组，新建资源默认落入",
        "kind": "分组类型：browser 浏览器 / account 账号 / ip 代理 IP",
        "name": "分组名称（同一类型下唯一）",
        "parent_id": "上级分组 ID，为空表示顶级分组",
        "sort_order": "排序值，越小越靠前",
        "updated_at": "最后更新时间（UTC）",
    },
    "ips": {
        "address": "IP 地址（IPv4 / IPv6）",
        "city": "城市",
        "country_code": "国家或地区代码，如 US / JP",
        "created_at": "创建时间（UTC）",
        "expires_at": "到期时间，为空表示长期有效",
        "health": "健康度（百分比）",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "kind": "IP 类型：residential 住宅 / datacenter 机房 / mobile 移动",
        "last_checked_at": "最近一次可用性探测时间",
        "latency_ms": "最近一次探测的延迟（毫秒）",
        "password_encrypted": "代理认证密码（加密存储，不落明文）",
        "port": "代理端口，0 表示使用协议默认端口",
        "protocol": "代理协议：http / https / socks5",
        "region": "州或省，如「加利福尼亚」",
        "status": "状态：available 可用 / in_use 使用中 / failed 失效",
        "supplier": "IP 供应商",
        "timezone": "出口时区",
        "updated_at": "最后更新时间（UTC）",
        "username": "代理认证账号",
    },
    "kernels": {
        "arch": "目标架构：x64 / arm64",
        "base_version": "上游基线版本号",
        "channel": "发布通道：stable 稳定版 / beta 测试版 / nightly 每日构建",
        "created_at": "创建时间（UTC）",
        "detection_level": "反检测实现层级，如「C++ 层注入」",
        "engine": "上游引擎：Chromium / Firefox",
        "id": "主键，应用侧生成的 UUID（非自增）",
        "image": "镜像或安装包地址（registry/name:tag）",
        "is_primary": "是否为主力内核，新建实例默认使用",
        "latest_version": "可升级到的最新版本号",
        "name": "内核名称（唯一）",
        "note": "备注与建议用途",
        "pass_rate": "反检测通过率（百分比）",
        "share": "实例占比（百分比）",
        "status": "状态：active 可用 / testing 测试中 / deprecated 已弃用",
        "updated_at": "最后更新时间（UTC）",
        "version": "当前部署的版本号",
    },
}


def _quote(text: str) -> str:
    """包成 SQL 字符串字面量，单引号按 SQL 规则翻倍转义。"""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    for table, comment in TABLE_COMMENTS.items():
        op.execute(f"COMMENT ON TABLE {table} IS {_quote(comment)}")
    for table, columns in COLUMN_COMMENTS.items():
        for column, comment in columns.items():
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS {_quote(comment)}")


def downgrade() -> None:
    # COMMENT ... IS NULL 即删除注释
    for table in TABLE_COMMENTS:
        op.execute(f"COMMENT ON TABLE {table} IS NULL")
    for table, columns in COLUMN_COMMENTS.items():
        for column in columns:
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
