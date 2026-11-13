"""演示种子数据：把前端展示用的集群数据写入 PostgreSQL。

数据量与真实集群相仿但规模很小（十来张表、百余行），方便本地开发和联调时
有内容可看。写入是幂等的：库里已经有数据就跳过；需要重建时加 ``--reset``。

用法::

    cd backend
    uv run python -m app.services.seed           # 空库时写入
    uv run python -m app.services.seed --reset   # 先清空全部表再写入
"""

import argparse
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, dispose
from app.core.security import hash_password
from app.models import (
    Account,
    AccountStatus,
    AuditAction,
    AuditLog,
    AuditResourceType,
    AuditResult,
    AuditSource,
    AuthSession,
    BindingAction,
    BindingSource,
    Browser,
    BrowserAccountBinding,
    BrowserFingerprintBinding,
    BrowserIpBinding,
    BrowserStatus,
    Fingerprint,
    FingerprintMode,
    Group,
    GroupKind,
    Ip,
    IpBindingMode,
    IpKind,
    IpProtocol,
    IpStatus,
    Kernel,
    KernelChannel,
    KernelStatus,
    PasswordResetToken,
    Permission,
    PlatformFamily,
    RbacAction,
    RbacModule,
    Role,
    RolePermission,
    User,
    UserRole,
    UserStatus,
    Workspace,
)
from app.models.base import utcnow
from app.services.platforms import detect_platform

# 演示数据的时间都相对「now」生成，保证 humanize 出来是「2 小时前」这类文案
NOW = utcnow()

# 直连实例的本机公网 IP 快照；203.0.113.0/24 是文档保留段，不会指向真实主机
DIRECT_ADDRESS = "203.0.113.24"


def _ago(*, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    return NOW - timedelta(minutes=minutes, hours=hours, days=days)


def _cookies(domain: str, *items: tuple[str, str]) -> list[dict[str, object]]:
    """拼一份演示用的登录态 Cookie。

    字段与 Playwright ``storage_state.cookies`` 对齐，值全部是伪造的演示串；
    域名、名称取真实平台的常见键，方便前端按平台预览时看起来合理。
    """
    expires = int((NOW + timedelta(days=30)).timestamp())
    return [
        {
            "name": name,
            "value": value,
            "domain": domain,
            "path": "/",
            "expires": expires,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
        for name, value in items
    ]


# 工作区：成员默认落点。三名演示成员分属两个工作区，
# 这样浮层上「默认工作区」不是人人一样的假数据
WORKSPACES = [
    {
        "code": "webweaver-team",
        "name": "webweaver-team",
        "note": "主力工作区，北美与日本业务",
        "sort_order": 0,
    },
    {
        "code": "webweaver-lab",
        "name": "webweaver-lab",
        "note": "测试环境，只有只读成员",
        "sort_order": 1,
    },
    {
        "code": "acme-growth",
        "name": "acme-growth",
        "note": "外部客户工作区",
        "sort_order": 2,
    },
]

GROUPS = [
    {"code": "na-store", "name": "北美店铺", "kind": GroupKind.browser, "color": "#4171f1"},
    {"code": "jp-social", "name": "日本社媒", "kind": GroupKind.browser, "color": "#a855f7"},
    {"code": "eu-ads", "name": "欧美广告", "kind": GroupKind.browser, "color": "#f59e0b"},
    {"code": "sea-store", "name": "东南亚店铺", "kind": GroupKind.browser, "color": "#10b981"},
    {"code": "apac-content", "name": "亚太内容", "kind": GroupKind.browser, "color": "#06b6d4"},
    {"code": "eu-store", "name": "欧美店铺", "kind": GroupKind.browser, "color": "#6366f1"},
]

KERNELS = [
    {
        "name": "CloakBrowser",
        "engine": "Chromium",
        "base_version": "128.0.6613",
        "version": "128.0.6613.2",
        "latest_version": "128.0.6613.5",
        "channel": KernelChannel.stable,
        "image": "webweaver/cloak:128.0.6613",
        "repo_url": "https://github.com/CloakHQ/CloakBrowser",
        "detection_level": "C++ 层注入",
        "status": KernelStatus.active,
        "pass_rate": 98,
        "share": 46,
        "note": "主力内核，反检测通过率最高",
    },
    {
        "name": "Camoufox",
        "engine": "Firefox",
        "base_version": "128.0",
        "version": "128.0.3",
        "latest_version": "128.0.4",
        "channel": KernelChannel.stable,
        "image": "webweaver/camoufox:128.0.3",
        "repo_url": "https://github.com/daijro/camoufox",
        "detection_level": "Juggler 层修改",
        "status": KernelStatus.active,
        "pass_rate": 94,
        "share": 28,
        "note": "Firefox 系，适合对 Chromium 敏感的平台",
    },
    {
        "name": "fingerprint-chromium",
        "engine": "Chromium",
        "base_version": "126.0.6478",
        "version": "126.0.6478.1",
        "latest_version": "128.0.6613.2",
        "channel": KernelChannel.stable,
        "image": "webweaver/fp-chromium:126.0.6478",
        "repo_url": "https://github.com/adryfish/fingerprint-chromium",
        "detection_level": "前端 JS 注入",
        "status": KernelStatus.testing,
        "pass_rate": 87,
        "share": 18,
        "note": "开源方案，等待升级到 128 基线",
    },
    {
        "name": "ungoogled-chromium",
        "engine": "Chromium",
        "base_version": "124.0.6367",
        "version": "124.0.6367.9",
        "latest_version": "128.0.6613",
        "channel": KernelChannel.beta,
        "image": "webweaver/ungoogled:124.0.6367",
        "repo_url": "https://github.com/ungoogled-software/ungoogled-chromium",
        "detection_level": "原生隐私加固",
        "status": KernelStatus.deprecated,
        "pass_rate": 72,
        "share": 8,
        "note": "版本偏旧，仅用于问题复现",
    },
]

# 指纹矩阵：2 个能做指纹的内核 × 4 个平台族，正好八条。
# 摆成矩阵是为了演示两件事：同一平台换个内核会有什么差别、同一内核换个平台会怎样。
#
# 只写「种子 + 声明式参数」，不写 UA / 分辨率 / DPR —— 那三项是内核按种子算出来的，
# 手填进种子只会造出与真实人格矛盾的假数据（采集流程会把实测值回填进来）。
FINGERPRINTS = [
    # ── CloakBrowser：只认 seed / 平台 / 时区 / 语言 / WebRTC IP ─────────
    {
        "code": "fp-cloak-win11",
        "name": "Win11 · Chrome 128 · 美国",
        "seed": 24760,
        "platform_family": PlatformFamily.windows,
        "platform": "Windows 11",
        "timezone": "America/Los_Angeles",
        "language": "en-US",
        "uniqueness": 96,
        "kernel": "CloakBrowser",
    },
    {
        "code": "fp-cloak-macos",
        "name": "macOS 14 · Chrome 128 · 日本",
        "seed": 70379,
        "platform_family": PlatformFamily.macos,
        "platform": "macOS 14",
        "timezone": "Asia/Tokyo",
        "language": "ja-JP",
        "uniqueness": 94,
        "kernel": "CloakBrowser",
    },
    {
        "code": "fp-cloak-android",
        "name": "Android 14 · Pixel 8 · 新加坡",
        "seed": 75658,
        "platform_family": PlatformFamily.android,
        "platform": "Pixel 8 / Android 14",
        "timezone": "Asia/Singapore",
        "language": "en-US",
        "uniqueness": 91,
        "kernel": "CloakBrowser",
    },
    {
        "code": "fp-cloak-ios",
        "name": "iOS 17 · iPhone 15 · 香港",
        "seed": 51204,
        "platform_family": PlatformFamily.ios,
        # 伪移动：内核按 macOS 起人格，UA / 视口由 entrypoint 换成 iPad
        "platform": "iPhone 15 / iOS 17",
        "timezone": "Asia/Hong_Kong",
        "language": "zh-HK",
        "uniqueness": 89,
        "kernel": "CloakBrowser",
    },
    # ── fingerprint-chromium：多一组平台版本 / 品牌 / 硬件并发 ───────────
    {
        "code": "fp-fpcr-win10",
        "name": "Win10 · Chrome 126 · 德国",
        "seed": 10452,
        "platform_family": PlatformFamily.windows,
        "platform": "Windows 10",
        "timezone": "Europe/Berlin",
        "language": "de-DE",
        "accept_lang": "de-DE,de",
        "platform_version": "10.0.0",
        "brand": "Chrome",
        "brand_version": "126.0.6478.126",
        "hardware_concurrency": 8,
        # 关掉 Canvas 噪声：fingerprint-chromium 会把它翻译成
        # --disable-spoofing=canvas。这条正好演示「单关一项反而更好认」
        "canvas_noise": False,
        "uniqueness": 92,
        "kernel": "fingerprint-chromium",
    },
    {
        "code": "fp-fpcr-macos",
        "name": "macOS 14 · Chrome 128 · 加拿大",
        "seed": 37572,
        "platform_family": PlatformFamily.macos,
        "platform": "macOS 14",
        "timezone": "America/Toronto",
        "language": "en-CA",
        "accept_lang": "en-CA,en",
        "platform_version": "14.5.0",
        "brand": "Chrome",
        "brand_version": "128.0.6613.120",
        "hardware_concurrency": 10,
        "uniqueness": 95,
        "kernel": "fingerprint-chromium",
    },
    {
        "code": "fp-fpcr-android",
        "name": "Android 13 · Pixel 7 · 英国",
        "seed": 83373,
        "platform_family": PlatformFamily.android,
        "platform": "Pixel 7 / Android 13",
        "timezone": "Europe/London",
        "language": "en-GB",
        "accept_lang": "en-GB,en",
        "platform_version": "13.0.0",
        "brand": "Chrome",
        "brand_version": "128.0.6613.120",
        "hardware_concurrency": 8,
        "uniqueness": 90,
        "kernel": "fingerprint-chromium",
    },
    {
        "code": "fp-fpcr-ios",
        "name": "iOS 17 · iPhone 14 · 澳洲",
        "seed": 62481,
        "platform_family": PlatformFamily.ios,
        "platform": "iPhone 14 / iOS 17",
        "timezone": "Australia/Sydney",
        "language": "en-AU",
        "accept_lang": "en-AU,en",
        "platform_version": "17.5.0",
        "brand": "Safari",
        "brand_version": "17.5",
        "hardware_concurrency": 6,
        "uniqueness": 88,
        "kernel": "fingerprint-chromium",
    },
]

IPS = [
    ("104.28.16.73", "US", "加利福尼亚", "洛杉矶", "BrightData", IpKind.residential, 112),
    ("133.18.204.5", "JP", "东京都", "东京", "Oxylabs", IpKind.residential, 72),
    ("45.132.88.19", "DE", "黑森", "法兰克福", "Smartproxy", IpKind.datacenter, 28),
    ("27.124.9.140", "SG", "", "新加坡", "IPRoyal", IpKind.residential, 0),
    ("61.8.212.44", "HK", "", "香港", "BrightData", IpKind.residential, 32),
    ("81.44.197.62", "GB", "英格兰", "伦敦", "Oxylabs", IpKind.residential, 64),
    ("45.132.88.20", "DE", "黑森", "法兰克福", "Smartproxy", IpKind.datacenter, 26),
    ("104.28.16.74", "US", "加利福尼亚", "洛杉矶", "BrightData", IpKind.residential, 108),
    ("133.18.204.6", "JP", "东京都", "东京", "Oxylabs", IpKind.residential, 76),
    ("27.124.9.188", "SG", "", "新加坡", "IPRoyal", IpKind.mobile, 95),
    ("185.220.101.4", "NL", "北荷兰", "阿姆斯特丹", "Smartproxy", IpKind.datacenter, 24),
    ("23.129.64.131", "CA", "安大略", "多伦多", "IPRoyal", IpKind.residential, 88),
]

# 代理认证凭据。住宅 / 移动代理几乎都要账号密码，机房那三条走 IP 白名单，
# 故意留空，好在界面上同时覆盖「带认证」和「不带认证」两种复制结果。
IP_AUTH: dict[str, tuple[str, str]] = {
    "104.28.16.73": ("brd-customer-hl_9f2c1a", "ww9xk2mq"),
    "104.28.16.74": ("brd-customer-hl_us02", "uS8nC5mQ"),
    "61.8.212.44": ("brd-customer-hl_hk02", "hK4vN8tR"),
    "133.18.204.5": ("customer-ww_jp01", "Ox9pQ2mZ"),
    "133.18.204.6": ("customer-ww_jp02", "Jp2rT7vX"),
    "81.44.197.62": ("customer-ww_uk02", "Uk3wY6pD"),
    "27.124.9.140": ("ww_sg01", "IpR7k2Lq"),
    "27.124.9.188": ("ww_sg02", "Mv6bH1sK"),
    "23.129.64.131": ("ww_ca01", "Ca5dF9jW"),
}

ACCOUNTS = [
    {
        "platform": "Amazon",
        "login_url": "https://sellercentral.amazon.com/ap/signin",
        "username": "shop_us_042",
        "email": "shop_us_042@webweaver.io",
        "status": AccountStatus.logged_in,
        "region": "美国区",
        "health": 88,
        "registered_at": _ago(days=128),
        "last_login_at": _ago(hours=2),
        "group": "na-store",
        "cookies": _cookies(
            ".amazon.com",
            ("session-id", "137-4829173-2849102"),
            ("session-token", "demo_amz_token_9f3c"),
            ("ubid-acbus", "261-7391024-5518203"),
        ),
    },
    {
        "platform": "Shopify",
        "login_url": "https://admin.shopify.com/store/shop-uk-014",
        "username": "shop_uk_014",
        "email": "shop_uk_014@webweaver.io",
        "status": AccountStatus.logged_in,
        "region": "英国区",
        "health": 82,
        "registered_at": _ago(days=96),
        "last_login_at": _ago(hours=3),
        "group": "eu-store",
    },
    {
        "platform": "TikTok",
        "login_url": "https://www.tiktok.com/login",
        "username": "kol_jp_018",
        "email": "kol_jp_018@webweaver.io",
        "status": AccountStatus.in_session,
        "region": "日本区",
        "health": 74,
        "registered_at": _ago(days=214),
        "last_login_at": _ago(minutes=45),
        "group": "jp-social",
        "cookies": _cookies(
            ".tiktok.com",
            ("sessionid", "demo_tt_session_7d21"),
            ("sid_tt", "demo_tt_sid_4b8e"),
        ),
    },
    {
        "platform": "Amazon",
        "login_url": "https://sellercentral.amazon.sg/ap/signin",
        "username": "store_sg_031",
        "email": "store_sg_031@webweaver.io",
        "status": AccountStatus.restricted,
        "region": "新加坡区",
        "health": 28,
        "registered_at": _ago(days=32),
        "last_login_at": _ago(days=1),
        "group": "sea-store",
        "note": "代理不可达，触发风控",
    },
    {
        "platform": "Meta",
        "login_url": "https://business.facebook.com/adsmanager",
        "username": "ads_de_007",
        "email": "ads_de_007@webweaver.io",
        "status": AccountStatus.logged_in,
        "region": "德国区",
        "health": 80,
        "registered_at": _ago(days=76),
        "last_login_at": _ago(hours=5),
        "group": "eu-ads",
        "cookies": _cookies(
            ".facebook.com",
            ("c_user", "100094821735"),
            ("xs", "demo_fb_xs_2a91"),
            ("datr", "demo_fb_datr_5c7e"),
        ),
    },
    {
        "platform": "Instagram",
        "login_url": "https://www.instagram.com/accounts/login/",
        "username": "media_hk_025",
        "email": "media_hk_025@webweaver.io",
        "status": AccountStatus.unbound,
        "region": "香港区",
        "health": 60,
        "registered_at": _ago(days=168),
        "group": "apac-content",
    },
    {
        "platform": "X",
        "login_url": "https://x.com/i/flow/login",
        "username": "brand_sg_009",
        "email": "brand_sg_009@webweaver.io",
        "status": AccountStatus.logged_in,
        "region": "新加坡区",
        "health": 86,
        "registered_at": _ago(days=54),
        "last_login_at": _ago(hours=8),
        "group": "sea-store",
    },
    {
        "platform": "Shopify",
        "login_url": "https://admin.shopify.com/store/shop-ca-003",
        "username": "shop_ca_003",
        "email": "shop_ca_003@webweaver.io",
        "status": AccountStatus.logged_in,
        "region": "加拿大区",
        "health": 78,
        "registered_at": _ago(days=40),
        "last_login_at": _ago(days=2),
        "group": "na-store",
    },
]

# name, status, group, fingerprint, ip, account, 启动/活跃时间, fps, latency
BROWSERS = [
    {
        "name": "brw-us-west-042",
        "status": BrowserStatus.running,
        "group": "na-store",
        "fingerprint": "fp-cloak-win11",
        "ip": "104.28.16.73",
        "account": "shop_us_042",
        "fps": 32,
        "latency_ms": 48,
        "vnc_port": 5901,
        "started_at": _ago(hours=2),
        "last_active_at": _ago(minutes=1),
    },
    {
        "name": "brw-jp-tokyo-018",
        "status": BrowserStatus.running,
        "group": "jp-social",
        "fingerprint": "fp-cloak-macos",
        "ip": "133.18.204.5",
        "account": "kol_jp_018",
        "fps": 28,
        "latency_ms": 72,
        "vnc_port": 5902,
        "started_at": _ago(minutes=45),
        "last_active_at": _ago(minutes=2),
    },
    {
        "name": "brw-de-fra-007",
        "status": BrowserStatus.idle,
        "group": "eu-ads",
        "fingerprint": "fp-fpcr-win10",
        "ip": "45.132.88.19",
        "account": "ads_de_007",
        "fps": 0,
        "latency_ms": 28,
        "vnc_port": 5903,
        "started_at": _ago(hours=5),
        "last_active_at": _ago(minutes=12),
    },
    {
        "name": "brw-sg-sin-031",
        "status": BrowserStatus.error,
        "group": "sea-store",
        "fingerprint": "fp-cloak-android",
        "ip": "27.124.9.140",
        "account": "store_sg_031",
        "fps": None,
        "latency_ms": None,
        "vnc_port": 5904,
        "started_at": _ago(hours=7),
        "last_active_at": _ago(minutes=20),
        "note": "代理不可达，尝试重连 3 次",
    },
    {
        "name": "brw-hk-hkg-025",
        "status": BrowserStatus.running,
        "group": "apac-content",
        "fingerprint": "fp-cloak-ios",
        "ip": "61.8.212.44",
        "account": "media_hk_025",
        "fps": 36,
        "latency_ms": 32,
        "vnc_port": 5905,
        "started_at": _ago(hours=6),
        "last_active_at": _ago(minutes=3),
    },
    {
        "name": "brw-uk-lon-014",
        "status": BrowserStatus.running,
        "group": "eu-store",
        "fingerprint": "fp-fpcr-android",
        "ip": "81.44.197.62",
        "account": "shop_uk_014",
        "fps": 30,
        "latency_ms": 64,
        "vnc_port": 5906,
        "started_at": _ago(hours=3),
        "last_active_at": _ago(minutes=1),
    },
    {
        "name": "brw-ca-tor-009",
        "status": BrowserStatus.stopped,
        "group": "na-store",
        "fingerprint": "fp-fpcr-macos",
        "ip": "23.129.64.131",
        "account": "shop_ca_003",
        "fps": None,
        "latency_ms": None,
        "vnc_port": 5907,
        "started_at": _ago(days=1),
        "last_active_at": _ago(hours=9),
    },
    {
        "name": "brw-au-syd-011",
        "status": BrowserStatus.queued,
        "group": "apac-content",
        # 直连 + 默认指纹：排队阶段还没分配代理与模板，先用本机 IP 与原生指纹跑通。
        # 内核固定成 Camoufox —— 它不做指纹注入，正好是「原生指纹」该落的地方；
        # 否则这个内核在新矩阵下连一台实例都没有，卡片上看着像坏了。
        "fingerprint": None,
        "kernel": "Camoufox",
        "ip": None,
        "account": None,
        "fps": None,
        "latency_ms": None,
        "vnc_port": 5908,
        "started_at": None,
        "last_active_at": None,
        "note": "等待调度",
    },
]


async def _seed_workspaces(session: AsyncSession) -> dict[str, Workspace]:
    """写入工作区，返回 code → 对象；已存在的按 code 复用。

    做成「补齐」而不是「判空跳过」：空库初始化与老库补数据走同一条路径，
    以后再加工作区只要往 ``WORKSPACES`` 里追加即可。
    """
    existing = {row.code: row for row in await session.scalars(select(Workspace))}
    added = False
    for item in WORKSPACES:
        if item["code"] in existing:
            continue
        workspace = Workspace(**item)
        session.add(workspace)
        existing[item["code"]] = workspace
        added = True

    if added:
        await session.flush()
    return existing


async def _clear(session: AsyncSession) -> None:
    """按外键依赖顺序清空，避免违反外键约束。"""
    for model in (
        AuditLog,
        AuthSession,
        PasswordResetToken,
        RolePermission,
        UserRole,
        User,
        Role,
        Permission,
        BrowserAccountBinding,
        BrowserFingerprintBinding,
        BrowserIpBinding,
        Browser,
        Account,
        Fingerprint,
        Ip,
        Kernel,
        Group,
        Workspace,
    ):
        await session.execute(model.__table__.delete())


async def seed(session: AsyncSession, *, reset: bool = False) -> dict[str, int]:
    """写入演示数据，返回各表最终行数。"""
    if reset:
        await _clear(session)

    existing = await session.scalar(select(func.count()).select_from(Kernel))
    if existing:
        # 审计日志单独判空：库里可能早就灌过业务数据，这里只补审计样例
        await _seed_audit_logs(session)
        # cookies 是后加的列，老库里的账号还是 NULL，按种子定义补一份
        await _backfill_demo_cookies(session)
        # RBAC 同样是后加的表，单独判空后补数据
        await _seed_rbac(session)
        # 登录流程也是后加的，老库里成员密码为空，补一份演示口令
        await _backfill_demo_passwords(session)
        # 工作区同样是后加的表，给还没分配的成员补上默认工作区
        await _backfill_default_workspace(session)
        return await counts(session)

    # 工作区要先落库：成员表的 default_workspace_id 指着它
    await _seed_workspaces(session)

    groups: dict[str, Group] = {}
    for index, item in enumerate(GROUPS):
        group = Group(**item, sort_order=index)
        session.add(group)
        groups[item["code"]] = group

    kernels: dict[str, Kernel] = {}
    for item in KERNELS:
        kernel = Kernel(**item)
        session.add(kernel)
        kernels[item["name"]] = kernel
    await session.flush()
    # 直连实例没有指纹模板，内核取列表里的第一个（CloakBrowser）
    primary_kernel = next(iter(kernels.values()))

    fingerprints: dict[str, Fingerprint] = {}
    for item in FINGERPRINTS:
        payload = dict(item)
        payload["kernel_id"] = kernels[payload.pop("kernel")].id
        fingerprint = Fingerprint(**payload)
        session.add(fingerprint)
        fingerprints[item["code"]] = fingerprint

    ips: dict[str, Ip] = {}
    for address, code, region, city, supplier, kind, latency in IPS:
        auth = IP_AUTH.get(address)
        ip = Ip(
            address=address,
            port=8000,
            protocol=IpProtocol.socks5,
            kind=kind,
            supplier=supplier,
            country_code=code,
            region=region,
            city=city,
            username=auth[0] if auth else None,
            password=auth[1] if auth else None,
            latency_ms=latency,
            health=100 if kind != IpKind.mobile else 96,
            status=IpStatus.failed if latency == 0 else IpStatus.available,
            last_checked_at=_ago(minutes=5),
        )
        session.add(ip)
        ips[address] = ip

    accounts: dict[str, Account] = {}
    for item in ACCOUNTS:
        payload = dict(item)
        payload["group_id"] = groups[payload.pop("group")].id
        # 平台是派生值：以登录地址推导为准，种子里写的那份只起个可读作用
        payload["platform"] = detect_platform(payload["login_url"])[0]
        account = Account(**payload)
        session.add(account)
        accounts[item["username"]] = account
    await session.flush()

    browsers: dict[str, Browser] = {}
    for item in BROWSERS:
        payload = dict(item)
        group = groups[payload.pop("group")]
        fingerprint = fingerprints.get(payload.pop("fingerprint"))
        ip = ips.get(payload.pop("ip"))
        account = accounts.get(payload.pop("account"))
        # 内核默认跟着指纹走；条目写了 kernel 就以它为准（没有指纹的实例要自己指定）
        explicit_kernel = payload.pop("kernel", None)
        if explicit_kernel:
            assigned_kernel = kernels[explicit_kernel]
        else:
            assigned_kernel = next(
                (
                    k
                    for k in kernels.values()
                    if k.id == (fingerprint.kernel_id if fingerprint else None)
                ),
                primary_kernel,
            )
        browser = Browser(
            **payload,
            group_id=group.id,
            kernel_id=assigned_kernel.id,
            # 种子里实例与内核当前版本对齐，批量迁移才有"旧版本"可迁
            kernel_version=assigned_kernel.version,
            fingerprint_mode=(FingerprintMode.template if fingerprint else FingerprintMode.default),
            fingerprint_id=fingerprint.id if fingerprint else None,
            ip_mode=IpBindingMode.proxy if ip else IpBindingMode.direct,
            ip_id=ip.id if ip else None,
            account_id=account.id if account else None,
            cdp_url=f"http://127.0.0.1:{9000 + item['vnc_port'] % 100}",
            vnc_url=(
                f"http://127.0.0.1:6080/vnc.html?port={item['vnc_port']}&autoconnect=1"
                if item["status"] is not BrowserStatus.stopped
                else None
            ),
        )
        session.add(browser)
        browsers[browser.name] = browser
        # 日志表引用 browser_id，先落库再写流水，否则外键约束会挡住
        await session.flush()

        if item["status"] is BrowserStatus.running and ip:
            ip.status = IpStatus.in_use
        if item["status"] is BrowserStatus.running and account:
            account.status = AccountStatus.in_session

        # 绑定日志：起实例时把账号 / IP / 指纹各绑一次，各落一条流水
        bound_at = item["started_at"] or _ago(days=2)
        if account:
            session.add(
                BrowserAccountBinding(
                    browser_id=browser.id,
                    account_id=account.id,
                    action=BindingAction.bind,
                    operator="scheduler",
                    source=BindingSource.scheduler,
                    note=f"实例启动时自动绑定 {account.platform} 账号",
                    created_at=bound_at,
                )
            )
        session.add(
            BrowserIpBinding(
                browser_id=browser.id,
                mode=IpBindingMode.proxy if ip else IpBindingMode.direct,
                ip_id=ip.id if ip else None,
                resolved_address=ip.address if ip else DIRECT_ADDRESS,
                action=BindingAction.bind,
                operator="scheduler",
                source=BindingSource.scheduler,
                note=None if ip else "未分配代理，直连本机 IP",
                created_at=bound_at,
            )
        )
        session.add(
            BrowserFingerprintBinding(
                browser_id=browser.id,
                mode=FingerprintMode.template if fingerprint else FingerprintMode.default,
                fingerprint_id=fingerprint.id if fingerprint else None,
                action=BindingAction.bind,
                operator="scheduler",
                source=BindingSource.scheduler,
                note=None if fingerprint else "未选模板，使用浏览器原生指纹",
                created_at=bound_at,
            )
        )

    # 演示一条「换 IP」的历史：brw-us-west-042 几天前从 .74 换到 .73，
    # 日志里是一次解绑 + 一次绑定，两条独立的流水，不做覆盖
    rotated = browsers["brw-us-west-042"]
    old_ip = ips["104.28.16.74"]
    for action, moment, note in (
        (BindingAction.bind, _ago(days=4), "首次分配出口"),
        (BindingAction.unbind, _ago(days=3), "延迟升高，换到 104.28.16.73"),
    ):
        session.add(
            BrowserIpBinding(
                browser_id=rotated.id,
                mode=IpBindingMode.proxy,
                ip_id=old_ip.id,
                resolved_address=old_ip.address,
                action=action,
                operator="ops_lee",
                source=BindingSource.manual,
                note=note,
                created_at=moment,
            )
        )

    await _seed_audit_logs(session)
    await _seed_rbac(session)
    await session.commit()
    return await counts(session)


# 审计样例：覆盖「创建 / 改配置 / 换 IP / 批量绑定 / 失败操作 / 密码重置 / 导出」，
# 前端按动作筛选时每一类都有数据可看
AUDIT_SAMPLES = [
    {
        "operator": "ops_lee",
        "source": AuditSource.manual,
        "action": AuditAction.create,
        "resource_type": AuditResourceType.browser,
        "browser": "brw-us-west-042",
        "detail": "创建实例并发起首次启动",
        "changes": {
            "status": {"before": None, "after": "queued"},
            "ip_mode": {"before": None, "after": "proxy"},
        },
        "request_id": "a1f3c9d2",
        "ip_address": "203.0.113.24",
        "occurred_at": _ago(days=5),
        "duration_ms": 128,
    },
    {
        "operator": "ops_lee",
        "source": AuditSource.manual,
        "action": AuditAction.update,
        "resource_type": AuditResourceType.browser,
        "browser": "brw-us-west-042",
        "detail": "切换出口 IP：104.28.16.74 → 104.28.16.73（原 IP 延迟升高）",
        "changes": {"ip_id": {"before": "104.28.16.74", "after": "104.28.16.73"}},
        "request_id": "b7d21e40",
        "ip_address": "203.0.113.24",
        "occurred_at": _ago(days=3),
        "duration_ms": 342,
    },
    {
        "operator": "scheduler",
        "source": AuditSource.scheduler,
        "action": AuditAction.start,
        "resource_type": AuditResourceType.browser,
        "browser": "brw-us-west-042",
        "detail": "调度器拉起实例，CDP 与 noVNC 端口就绪",
        "request_id": "c0e8a551",
        "occurred_at": _ago(hours=2),
        "duration_ms": 2140,
    },
    {
        "operator": "scheduler",
        "source": AuditSource.scheduler,
        "action": AuditAction.start,
        "resource_type": AuditResourceType.browser,
        "browser": "brw-jp-tokyo-018",
        "detail": "调度器拉起实例，指纹模板 fp-cloak-macos 注入完成",
        "request_id": "c0e8a552",
        "occurred_at": _ago(minutes=45),
        "duration_ms": 1876,
    },
    {
        "operator": "ops_lee",
        "source": AuditSource.manual,
        "action": AuditAction.stop,
        "resource_type": AuditResourceType.browser,
        "browser": "brw-au-syd-011",
        "result": AuditResult.failure,
        "detail": "停止实例失败：noVNC 端口仍被占用",
        "error_message": "port 6080 is already in use",
        "request_id": "d94b7f13",
        "ip_address": "203.0.113.24",
        "occurred_at": _ago(hours=6),
        "duration_ms": 5012,
    },
    {
        "operator": "admin_chen",
        "source": AuditSource.bulk,
        "action": AuditAction.bind,
        "resource_type": AuditResourceType.account,
        "resource_name": "shop_sg_031",
        "detail": "批量绑定 12 个账号到东南亚店铺实例组",
        "changes": {"group_id": {"before": "未分组", "after": "东南亚店铺"}},
        "request_id": "e1c7d028",
        "ip_address": "198.51.100.8",
        "occurred_at": _ago(days=1),
        "duration_ms": 876,
    },
    {
        "operator": "admin_chen",
        "source": AuditSource.manual,
        "action": AuditAction.update,
        "resource_type": AuditResourceType.kernel,
        "resource_name": "CloakBrowser",
        "detail": "升级内核版本：128.0.6613.2 → 128.0.6613.5",
        "changes": {
            "version": {"before": "128.0.6613.2", "after": "128.0.6613.5"},
            "status": {"before": "testing", "after": "active"},
        },
        "request_id": "f26aa9c4",
        "ip_address": "198.51.100.8",
        "occurred_at": _ago(days=2),
        "duration_ms": 430,
    },
    {
        "operator": "admin_chen",
        "source": AuditSource.manual,
        "action": AuditAction.delete,
        "resource_type": AuditResourceType.fingerprint,
        "resource_name": "fp-win10-legacy",
        "detail": "删除已过期的指纹模板",
        "request_id": "0b5d6e71",
        "ip_address": "198.51.100.8",
        "occurred_at": _ago(days=4),
        "duration_ms": 96,
    },
    {
        "operator": "ops_lee@webweaver.io",
        "source": AuditSource.api,
        "action": AuditAction.reset_password,
        "resource_type": AuditResourceType.auth,
        "resource_name": "ops_lee@webweaver.io",
        "detail": "重置密码成功，强制下线 7 个会话",
        "request_id": "17f0c3ba",
        "ip_address": "203.0.113.24",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "occurred_at": _ago(days=6),
        "duration_ms": 210,
    },
    {
        "operator": "unknown",
        "source": AuditSource.api,
        "action": AuditAction.login,
        "resource_type": AuditResourceType.auth,
        "resource_name": "admin@webweaver.io",
        "result": AuditResult.failure,
        "detail": "登录失败：连续 5 次密码错误，已触发风控",
        "error_message": "密码错误次数过多，账号临时锁定 15 分钟",
        "request_id": "28e4b7d0",
        "ip_address": "192.0.2.77",
        "user_agent": "python-requests/2.32.3",
        "occurred_at": _ago(hours=9),
        "duration_ms": 64,
    },
    {
        "operator": "admin_chen",
        "source": AuditSource.manual,
        "action": AuditAction.export,
        "resource_type": AuditResourceType.system,
        "resource_name": "浏览器池 CSV",
        "detail": "导出实例清单（8 行），含出口 IP 与指纹摘要",
        "request_id": "3ca9221f",
        "ip_address": "198.51.100.8",
        "occurred_at": _ago(days=1, hours=3),
        "duration_ms": 512,
    },
]


async def _seed_audit_logs(session: AsyncSession) -> None:
    """补审计样例；表里已有记录就跳过，保证 seed 幂等。

    写业务数据的路径可能早就跑过了，所以这里单独判空，不跟 Kernel 的存在性绑定。
    """
    if await session.scalar(select(func.count()).select_from(AuditLog)):
        return

    # 实例名 -> 实例，用来把 resource_id 指向真实行；找不到就只留名字快照
    browsers = {browser.name: browser for browser in await session.scalars(select(Browser))}
    for item in AUDIT_SAMPLES:
        payload = dict(item)
        browser = browsers.get(payload.pop("browser", ""))
        name = payload.pop("resource_name", None)
        session.add(
            AuditLog(
                **payload,
                resource_id=browser.id if browser else None,
                resource_name=name or (browser.name if browser else None),
            )
        )
    await session.commit()


async def _backfill_demo_cookies(session: AsyncSession) -> None:
    """给存量账号补一份演示 Cookie。

    ``cookies`` 是后加的列，老库里的账号全是 NULL；这里只补空值，
    已经采过登录态的账号保持原样。找不到同名种子账号的就跳过。
    """
    demo = {item["username"]: item.get("cookies") for item in ACCOUNTS}
    accounts = await session.scalars(select(Account).where(Account.cookies.is_(None)))
    touched = 0
    for account in accounts:
        cookies = demo.get(account.username)
        if cookies:
            account.cookies = cookies
            touched += 1
    if touched:
        await session.commit()


# ── RBAC ──────────────────────────────────────────────────

# 权限点按「模块 → 动作」生成，避免手写三十多行重复定义
PERMISSION_MATRIX: dict[RbacModule, tuple[RbacAction, ...]] = {
    RbacModule.browser: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
        RbacAction.execute,
    ),
    RbacModule.account: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.ip: (RbacAction.read, RbacAction.create, RbacAction.update, RbacAction.delete),
    RbacModule.fingerprint: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.kernel: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.group: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.audit: (RbacAction.read, RbacAction.export),
    RbacModule.user: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
    RbacModule.role: (
        RbacAction.read,
        RbacAction.create,
        RbacAction.update,
        RbacAction.delete,
    ),
}

MODULE_LABELS = {
    RbacModule.browser: "浏览器",
    RbacModule.account: "平台账号",
    RbacModule.ip: "代理 IP",
    RbacModule.fingerprint: "指纹",
    RbacModule.kernel: "内核",
    RbacModule.group: "分组",
    RbacModule.audit: "审计日志",
    RbacModule.user: "成员",
    RbacModule.role: "角色",
}

ACTION_LABELS = {
    RbacAction.read: "查看",
    RbacAction.create: "新建",
    RbacAction.update: "修改",
    RbacAction.delete: "删除",
    RbacAction.execute: "执行",
    RbacAction.export: "导出",
}

# 内置角色的授权规则：用谓词表达比列几十条编码更好维护
ROLE_RULES = {
    # 所有者：全部权限
    "owner": lambda module, action: True,
    # 管理员：除「删除成员 / 删除角色」外全部，避免管理员能把自己锁死
    "admin": lambda module, action: (
        not (module in (RbacModule.user, RbacModule.role) and action == RbacAction.delete)
    ),
    # 运营：能看所有，能启停实例、改账号资料，不能新建/删除资源、不能管成员
    "operator": lambda module, action: (
        action == RbacAction.read
        or (
            module == RbacModule.browser
            and action in (RbacAction.create, RbacAction.update, RbacAction.execute)
        )
        or (module == RbacModule.account and action == RbacAction.update)
    ),
    # 只读：只给 read
    "viewer": lambda module, action: action == RbacAction.read,
}

ROLES = [
    {
        "code": "owner",
        "name": "所有者",
        "description": "拥有全部权限，通常是工作区创建者",
        "is_system": True,
        "sort_order": 0,
    },
    {
        "code": "admin",
        "name": "管理员",
        "description": "管理全部业务资源，但不能删除成员与角色",
        "is_system": True,
        "sort_order": 1,
    },
    {
        "code": "operator",
        "name": "运营",
        "description": "日常操作实例与账号，不能新建或删除资源、不能管理成员",
        "is_system": False,
        "sort_order": 2,
    },
    {
        "code": "viewer",
        "name": "只读",
        "description": "只能查看，不能做任何写操作",
        "is_system": False,
        "sort_order": 3,
    },
]

USERS = [
    {
        "username": "admin",
        "email": "admin@webweaver.local",
        "display_name": "管理员",
        "role": "owner",
        "workspace": "webweaver-team",
        # 单独给个弱口令：本地开发敲 admin / admin 直接进来，不用去翻常量。
        # 它是唯一的简口账号，正式环境必须改掉。
        "password": "admin",
        "note": "本地开发用的简口账号",
    },
    {
        "username": "admin_chen",
        "email": "admin_chen@webweaver.io",
        "display_name": "陈默",
        "role": "owner",
        "workspace": "webweaver-team",
        "last_login_at": _ago(hours=1),
        "note": "工作区所有者",
    },
    {
        "username": "ops_lee",
        "email": "ops_lee@webweaver.io",
        "display_name": "李航",
        "role": "operator",
        "workspace": "webweaver-team",
        "last_login_at": _ago(hours=3),
        "note": "日常运营：启停实例、切换出口 IP",
    },
    {
        "username": "viewer_lin",
        "email": "viewer_lin@webweaver.io",
        "display_name": "林可",
        "role": "viewer",
        "workspace": "webweaver-lab",
        "last_login_at": _ago(days=2),
        "note": "只读成员，用来对比权限差异",
    },
]

# 除 admin 外的演示成员共用的登录密码。用常量而不是写进每个 dict，
# 是为了让「演示口令是什么」只有一处定义，改的时候不会漏。
DEMO_PASSWORD = "WebWeaver@2026"


async def _seed_rbac(session: AsyncSession) -> None:
    """初始化权限目录、内置角色、成员与授权；已经有角色就跳过。"""
    if await session.scalar(select(func.count()).select_from(Role)):
        return

    permissions: dict[str, Permission] = {}
    for module, actions in PERMISSION_MATRIX.items():
        for action in actions:
            code = f"{module.value}:{action.value}"
            permission = Permission(
                code=code,
                name=f"{ACTION_LABELS[action]}{MODULE_LABELS[module]}",
                module=module,
                action=action,
                description=f"{code}：{MODULE_LABELS[module]} - {ACTION_LABELS[action]}",
            )
            session.add(permission)
            permissions[code] = permission
    await session.flush()

    roles: dict[str, Role] = {}
    for item in ROLES:
        role = Role(**item)
        session.add(role)
        roles[item["code"]] = role
    await session.flush()

    # 角色 → 权限点：按谓词逐条判定，写入 role_permissions
    for role_code, role in roles.items():
        allow = ROLE_RULES[role_code]
        for permission_code, permission in permissions.items():
            module_code, action_code = permission_code.split(":", 1)
            if allow(RbacModule(module_code), RbacAction(action_code)):
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    workspaces = await _seed_workspaces(session)
    for item in USERS:
        payload = dict(item)
        role = roles[payload.pop("role")]
        workspace = workspaces[payload.pop("workspace")]
        # 个别账号可以自带口令（目前只有 admin 用它换掉统一演示口令），
        # 没写就沿用 DEMO_PASSWORD
        password = payload.pop("password", DEMO_PASSWORD)
        user = User(
            **payload,
            status=UserStatus.active,
            password_hash=hash_password(password),
            default_workspace_id=workspace.id,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id, granted_by="system"))

    await session.commit()


async def _backfill_demo_passwords(session: AsyncSession) -> int:
    """给演示成员补登录密码（只补为空的，不覆盖已改过的密码）。

    登录流程是后加的，老库里三名成员 ``password_hash`` 还是 NULL，
    而 ``_seed_rbac`` 见到角色已存在就整段跳过，所以这里单独补一次。
    返回补齐的条数，方便命令行确认。
    """
    users = await session.scalars(
        select(User).where(User.username.in_([item["username"] for item in USERS]))
    )
    filled = 0
    for user in users:
        if user.password_hash:
            continue
        user.password_hash = hash_password(DEMO_PASSWORD)
        session.add(user)
        filled += 1

    if filled:
        await session.commit()
    return filled


async def _backfill_default_workspace(session: AsyncSession) -> int:
    """给还没有默认工作区的成员补一个（只补空值，不覆盖已选过的）。

    工作区是后加的表，老库里 ``default_workspace_id`` 全是 NULL，
    而 ``_seed_rbac`` 见到角色存在就整段跳过，所以这里单独补一次。
    返回补齐的条数，方便命令行确认。
    """
    workspaces = await _seed_workspaces(session)
    mapping = {item["username"]: item["workspace"] for item in USERS}

    users = await session.scalars(select(User).where(User.username.in_(list(mapping))))
    filled = 0
    for user in users:
        if user.default_workspace_id is not None:
            continue
        workspace = workspaces.get(mapping[user.username])
        if workspace is None:
            continue
        user.default_workspace_id = workspace.id
        session.add(user)
        filled += 1

    if filled:
        await session.commit()
    return filled


async def counts(session: AsyncSession) -> dict[str, int]:
    """各表当前行数，便于在命令行确认写入了多少。"""
    result: dict[str, int] = {}
    for model in (
        Group,
        Kernel,
        Fingerprint,
        Ip,
        Account,
        Browser,
        BrowserAccountBinding,
        BrowserIpBinding,
        BrowserFingerprintBinding,
        AuditLog,
        Permission,
        Role,
        RolePermission,
        User,
        UserRole,
        Workspace,
    ):
        name = model.__tablename__
        result[name] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
    return result


async def _main(reset: bool) -> None:
    async with SessionLocal() as session:
        result = await seed(session, reset=reset)
    await dispose()
    print("种子数据就绪：" + "、".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="写入 WebWeaver 演示数据")
    parser.add_argument("--reset", action="store_true", help="先清空全部表再写入")
    args = parser.parse_args()
    asyncio.run(_main(args.reset))
