"""内核池：把「数据库台账 + 磁盘版本目录」拼成页面要的卡片数据，并提供版本切换与实例迁移。

设计要点：

- **磁盘是版本真相**：能装哪些版本、哪个版本更新，全部来自扫描，
  不在数据库里维护一份可能过期的版本清单。
- **数据库只记指针**：``kernels.version`` 是当前生效版本，
  ``browsers.kernel_version`` 是实例实际跑的版本。升级只是移动指针，
  旧版本目录原样保留，随时可以切回去。
- **升级不改老实例**：切换当前版本后，老实例继续留在旧版本上（``stale``），
  直到被显式批量迁移。这样升级不会在一次操作里把全部实例推上未经灰度验证的版本。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditAction,
    AuditResourceType,
    Browser,
    Group,
    Kernel,
    KernelStatus,
)
from app.schemas.kernels import (
    EngineVersionView,
    KernelCard,
    KernelDetailPayload,
    KernelInstance,
    KernelPayload,
    KernelStat,
    KernelVersion,
    MigrationResult,
    PrimaryResponse,
)
from app.services import audit, kernel_install, kernel_profile, kernel_scan
from app.services.kernel_scan import engine_slug, scan_versions, version_key

# 4 套引擎的展示属性（配色 / 一句话定位）。目录名做 key，
# 库里新增了计划外的内核也不会崩，走 DEFAULT_SPEC 兜底。
ENGINE_SPECS: dict[str, dict[str, str]] = {
    "cloakbrowser": {
        "tone": "blue",
        "tagline": "Chromium 源码级反检测，主力内核",
    },
    "camoufox": {
        "tone": "amber",
        "tagline": "Firefox 源码级反检测，跨引擎备份",
    },
    "fingerprint-chromium": {
        "tone": "violet",
        "tagline": "指纹种子可复现，问题复现专用",
    },
    "ungoogled-chromium": {
        "tone": "zinc",
        "tagline": "去 Google 依赖的干净基线",
    },
}

DEFAULT_SPEC = {"tone": "sky", "tagline": "Chromium 定制内核"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _effective_version(browser: Browser, kernel: Kernel) -> str | None:
    """实例实际使用的版本：为空表示跟随内核当前版本（历史数据口径）。"""
    return browser.kernel_version or kernel.version


async def _browsers_of(session: AsyncSession, kernel_ids: list[UUID]) -> list[tuple[Browser, str]]:
    """取出这些内核下所有实例，连带分组名。"""
    if not kernel_ids:
        return []
    rows = (
        await session.execute(
            select(Browser, Group.name)
            .outerjoin(Group, Group.id == Browser.group_id)
            .where(Browser.kernel_id.in_(kernel_ids))
            .order_by(Browser.name)
        )
    ).all()
    return [(browser, group or "未分组") for browser, group in rows]


async def payload(session: AsyncSession) -> KernelPayload:
    """扫描 4 个引擎目录 + 读台账，组装完整页面数据。"""
    kernels = list(
        (
            await session.scalars(select(Kernel).order_by(Kernel.is_primary.desc(), Kernel.name))
        ).all()
    )
    browsers = await _browsers_of(session, [k.id for k in kernels])
    scanned_at = _now()

    by_kernel: dict[UUID, list[tuple[Browser, str]]] = {}
    for browser, group in browsers:
        by_kernel.setdefault(browser.kernel_id, []).append((browser, group))

    cards: list[KernelCard] = []
    for kernel in kernels:
        spec = ENGINE_SPECS.get(engine_slug(kernel.name), DEFAULT_SPEC)
        versions = scan_versions(kernel.name)
        ready_versions = [v for v in versions if v.ready]
        latest = ready_versions[0].version if ready_versions else None
        current = kernel.version or None

        # 每个版本上有多少台实例
        usage: dict[str, int] = {}
        stale = 0
        for browser, _group in by_kernel.get(kernel.id, []):
            effective = _effective_version(browser, kernel)
            if effective:
                usage[effective] = usage.get(effective, 0) + 1
            if current and effective != current:
                stale += 1
        for version in versions:
            version.instances = usage.get(version.version, 0)
            version.current = version.version == current

        cards.append(
            KernelCard(
                id=str(kernel.id),
                slug=engine_slug(kernel.name),
                name=kernel.name,
                engine=kernel.engine,
                channel=_channel_label(kernel.channel),
                arch=kernel.arch,
                tone=spec["tone"],
                tagline=kernel.note or spec["tagline"],
                detection_level=kernel.detection_level,
                repo_url=kernel.repo_url,
                mirror_url=kernel.mirror_url,
                is_primary=kernel.is_primary,
                current_version=current,
                latest_version=latest,
                update_available=bool(
                    latest and (current is None or version_key(latest) > version_key(current))
                ),
                downloaded=bool(ready_versions),
                version_count=len(ready_versions),
                instance_count=len(by_kernel.get(kernel.id, [])),
                stale_count=stale,
                disk_path=str(kernel_scan.engine_dir(kernel.name)),
                scanned_at=scanned_at,
                versions=versions,
                note=kernel.note,
            )
        )

    total_instances = sum(card.instance_count for card in cards)
    downloaded = sum(1 for card in cards if card.downloaded)
    updatable = sum(1 for card in cards if card.update_available)
    stale_total = sum(card.stale_count for card in cards)

    if not total_instances:
        instances_hint = "暂无实例绑定"
    else:
        instances_hint = f"{stale_total} 台待迁移" if stale_total else "无待迁移实例"

    return KernelPayload(
        stats=[
            KernelStat(
                key="engines",
                label="内核引擎",
                value=str(len(cards)),
                hint="固定 4 套",
                tone="dark",
                icon="layers",
            ),
            KernelStat(
                key="downloaded",
                label="已下载",
                value=f"{downloaded}/{len(cards)}",
                hint=(
                    f"{sum(c.version_count for c in cards)} 个版本"
                    if downloaded
                    else "还没有装任何版本"
                ),
                tone="emerald",
                icon="download",
            ),
            KernelStat(
                key="update",
                label="可更新",
                value=str(updatable),
                hint="磁盘上已有更新版本" if updatable else "全部已是最新",
                tone="blue",
                icon="trend",
            ),
            KernelStat(
                key="instances",
                label="绑定实例",
                value=str(total_instances),
                hint=instances_hint,
                tone="amber",
                icon="monitor",
            ),
        ],
        cards=cards,
        root=str(kernel_scan.kernel_root()),
        scanned_at=scanned_at,
        total_instances=total_instances,
        total_versions=sum(card.version_count for card in cards),
    )


async def detail(session: AsyncSession, slug: str) -> KernelDetailPayload:
    """单引擎详情：台账卡片 + 人工维护的档案 + 磁盘版本状态 + 正文。

    档案写坏了不报错，``profile_ok=False`` 带回原因，页面照常展示磁盘状态。
    """
    data = await payload(session)
    key = engine_slug(slug)
    card = next((item for item in data.cards if item.slug == key), None)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有这个内核引擎")

    loaded = kernel_profile.load(card.name)
    profile = loaded.profile
    on_disk = {item.version: item for item in card.versions if item.ready}

    views: list[EngineVersionView] = []
    for spec in profile.versions if profile else []:
        disk = on_disk.pop(spec.version, None)
        views.append(
            EngineVersionView(
                **spec.model_dump(),
                installed=disk is not None,
                installed_size=disk.size if disk else None,
                is_current=spec.version == card.current_version,
            )
        )

    # 磁盘上有、档案没登记的版本（手工放进去的旧版本）也要列出来，否则用户会以为丢了
    for version, disk in on_disk.items():
        views.append(
            EngineVersionView(
                version=version,
                base=disk.base,
                channel=disk.channel,
                released_at=disk.released_at,
                notes="档案里没有登记，仅在磁盘上发现",
                installed=True,
                installed_size=disk.size,
                is_current=version == card.current_version,
                on_disk_only=True,
            )
        )

    views.sort(key=lambda item: version_key(item.version), reverse=True)
    os_name, arch = kernel_install.default_platform()

    return KernelDetailPayload(
        slug=key,
        card=card,
        profile=profile,
        profile_ok=loaded.ok,
        profile_error=loaded.error,
        versions=views,
        docs=kernel_profile.docs(card.name),
        docs_path=str(kernel_profile.docs_path(card.name)),
        install_hint=(
            f"页面点「安装」会走 {profile.acquire.kind} 通道"
            if profile and profile.acquire
            else f"手动把发行包解压到 {card.disk_path}/<版本>/ 并写入 meta.json"
        )
        + f"；当前识别平台 {os_name}/{arch}",
    )


def _channel_label(channel: object) -> str:
    value = getattr(channel, "value", channel)
    return {"stable": "稳定通道", "beta": "测试通道", "nightly": "每日构建"}.get(
        str(value), str(value)
    )


async def _get_kernel(session: AsyncSession, kernel_id: str) -> Kernel:
    try:
        key = UUID(kernel_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="内核不存在，请刷新页面"
        ) from None
    kernel = await session.get(Kernel, key)
    if kernel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内核不存在，请刷新页面")
    return kernel


def _require_installed(kernel: Kernel, version: str) -> KernelVersion:
    for item in scan_versions(kernel.name):
        if item.version == version and item.ready:
            return item
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{kernel.name} 目录里没有可用的 {version} 版本，请先把内核文件解压到 "
        f"{kernel_scan.engine_dir(kernel.name) / version}",
    )


async def switch_version(
    session: AsyncSession,
    kernel_id: str,
    version: str,
    *,
    operator: str,
    request: Request | None = None,
) -> KernelPayload:
    """把某个已落盘的版本设为该内核的当前版本；旧版本目录保留不动。"""
    kernel = await _get_kernel(session, kernel_id)
    _require_installed(kernel, version)

    before = kernel.version
    if before != version:
        kernel.version = version
        if kernel.latest_version is None or version_key(version) > version_key(
            kernel.latest_version
        ):
            kernel.latest_version = version
        await audit.record(
            session,
            action=AuditAction.update,
            resource_type=AuditResourceType.kernel,
            resource_id=kernel.id,
            resource_name=kernel.name,
            operator=operator,
            detail=f"{kernel.name} 当前版本切换为 {version}",
            changes={"version": {"before": before, "after": version}},
            request=request,
        )
        await session.commit()

    return await payload(session)


async def migrate(
    session: AsyncSession,
    kernel_id: str,
    version: str,
    browser_ids: list[str],
    *,
    operator: str,
    request: Request | None = None,
) -> MigrationResult:
    """把实例批量迁到指定版本。不传 ids 时视为「该内核下所有不在目标版本上的实例」。"""
    kernel = await _get_kernel(session, kernel_id)
    _require_installed(kernel, version)

    rows = (await session.execute(select(Browser).where(Browser.kernel_id == kernel.id))).scalars()
    targets: list[Browser] = []
    wanted = {bid for bid in browser_ids}
    for browser in rows:
        if wanted and str(browser.id) not in wanted:
            continue
        if _effective_version(browser, kernel) == version:
            continue
        targets.append(browser)

    if not targets:
        return MigrationResult(
            ok=True,
            version=version,
            migrated=0,
            message="没有需要迁移的实例",
        )

    for browser in targets:
        browser.kernel_version = version
    await session.flush()

    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.browser,
        resource_id=kernel.id,
        resource_name=kernel.name,
        operator=operator,
        detail=f"{len(targets)} 台实例迁移到 {kernel.name} {version}",
        changes={"kernel_version": {"before": "多个版本", "after": version}},
        request=request,
    )
    await session.commit()

    return MigrationResult(
        ok=True,
        version=version,
        migrated=len(targets),
        message=f"已把 {len(targets)} 台实例迁移到 {kernel.name} {version}",
    )


async def instances(
    session: AsyncSession,
    kernel_id: str,
    *,
    stale: bool = False,
    version: str | None = None,
) -> list[KernelInstance]:
    """迁移弹窗的候选项：默认返回该内核下所有实例。"""
    kernel = await _get_kernel(session, kernel_id)
    rows = await _browsers_of(session, [kernel.id])

    items: list[KernelInstance] = []
    for browser, group in rows:
        effective = _effective_version(browser, kernel)
        if stale and effective == kernel.version:
            continue
        if version and effective != version:
            continue
        items.append(
            KernelInstance(
                id=str(browser.id),
                name=browser.name,
                version=effective,
                group=group,
                status=browser.status.value,
            )
        )
    return items


async def set_primary(
    session: AsyncSession,
    kernel_id: str,
    *,
    operator: str,
    request: Request | None = None,
) -> PrimaryResponse:
    """设为主力内核：新建实例时默认选中它。"""
    kernel = await _get_kernel(session, kernel_id)
    if kernel.status is KernelStatus.deprecated:
        return PrimaryResponse(
            ok=False,
            primary_id="",
            message=f"{kernel.name} 已弃用，不能设为主力内核",
        )

    for other in (await session.scalars(select(Kernel))).all():
        if other.is_primary and other.id != kernel.id:
            other.is_primary = False
    kernel.is_primary = True
    await session.flush()

    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.kernel,
        resource_id=kernel.id,
        resource_name=kernel.name,
        operator=operator,
        detail=f"{kernel.name} 设为主力内核",
        changes={"is_primary": {"before": False, "after": True}},
        request=request,
    )
    await session.commit()

    return PrimaryResponse(
        ok=True,
        primary_id=str(kernel.id),
        message=f"{kernel.name} 已设为主力内核，新建实例默认使用该引擎",
    )
