"""内核池：把「台账 + 本地 Docker 镜像」拼成页面要的卡片数据。

设计要点：

- **镜像即真相**：本地 ``docker image ls`` 里有这个内核的 tag，就算它有版本；
  一个都没有就是「未获取」。不再扫磁盘目录、不再读 ``meta.json``。
- **数据库只记指针**：``kernels.version`` 是当前生效版本（存版本号不存 tag，
  因为滚动 tag 会飘）。升级只是移动指针，旧镜像留在本地随时可以切回去。
- **升级不碰老实例**：切换当前版本后，老实例继续留在旧版本上（``stale``），
  直到被显式批量迁移。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.models import (
    AuditAction,
    AuditResourceType,
    Browser,
    Group,
    Kernel,
)
from app.schemas.kernels import (
    KernelCard,
    KernelDetailPayload,
    KernelInstance,
    KernelPayload,
    KernelStat,
    KernelVersion,
    MigrationResult,
)
from app.services import audit, kernel_image, kernel_scan
from app.services.kernel_scan import engine_slug, human_size, version_key

# 展示属性（配色 / 定位 / 端口）。端口按内核错开，四个可以同时跑。
ENGINE_SPECS: dict[str, dict[str, object]] = {
    "cloakbrowser": {
        "tone": "blue",
        "tagline": "Chromium 源码级反检测，主力内核",
        "cdp": 9232,
        "novnc": 6082,
    },
    "camoufox": {
        "tone": "amber",
        "tagline": "Firefox 源码级反检测，跨引擎备份",
        "cdp": None,
        "novnc": None,
    },
    "fingerprint-chromium": {
        "tone": "violet",
        "tagline": "指纹种子可复现，问题复现专用",
        "cdp": 9242,
        "novnc": 6084,
    },
    "ungoogled-chromium": {
        "tone": "zinc",
        "tagline": "去 Google 依赖的干净基线",
        "cdp": 9222,
        "novnc": 6080,
    },
}

DEFAULT_SPEC: dict[str, object] = {
    "tone": "sky",
    "tagline": "Chromium 定制内核",
    "cdp": None,
    "novnc": None,
}

# 还没做成镜像的内核：页面上灰掉，只显示「暂未支持」
UNSUPPORTED: dict[str, str] = {
    "camoufox": "Firefox 系内核暂未提供镜像，敬请期待",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _effective_version(browser: Browser, kernel: Kernel) -> str | None:
    """实例实际使用的版本：为空表示跟随内核当前版本（历史数据口径）。"""
    return browser.kernel_version or kernel.version


def _pick_current(versions: list[KernelVersion], stored: str | None) -> KernelVersion | None:
    """当前版本：台账登记的版本号在本地就认它，否则退到最新镜像。"""
    if stored:
        for item in versions:
            if item.version == stored:
                return item
    return versions[0] if versions else None


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


async def _load_images() -> tuple[list[kernel_image.ImageInfo], bool, str | None]:
    """一次拿全本地镜像；docker 不可用时返回空列表 + 原因。"""
    ok, reason = await asyncio.to_thread(kernel_image.available)
    if not ok:
        return [], False, reason
    try:
        images = await asyncio.to_thread(kernel_image.list_images, kernel_scan.registry())
    except kernel_image.DockerError as exc:
        return [], False, str(exc)
    return images, True, None


async def payload(session: AsyncSession) -> KernelPayload:
    """读台账 + 扫本地镜像，组装页面数据。"""
    # 按引擎的展示顺序排（ENGINE_SPECS 的键序），不按名字：名字序会把
    # Camoufox 排到最前，而 CloakBrowser 才是默认引擎。
    kernels = list((await session.scalars(select(Kernel))).all())
    order = {slug: index for index, slug in enumerate(ENGINE_SPECS)}
    kernels.sort(key=lambda k: order.get(engine_slug(k.name), len(order)))
    browsers = await _browsers_of(session, [k.id for k in kernels])
    images, docker_ok, docker_error = await _load_images()
    scanned_at = _now()

    by_kernel: dict[UUID, list[tuple[Browser, str]]] = {}
    for browser, group in browsers:
        by_kernel.setdefault(browser.kernel_id, []).append((browser, group))

    cards: list[KernelCard] = []
    for kernel in kernels:
        slug = engine_slug(kernel.name)
        spec = ENGINE_SPECS.get(slug, DEFAULT_SPEC)
        reason = UNSUPPORTED.get(slug)
        supported = reason is None

        versions = kernel_scan.scan_versions(kernel.name, images=images) if supported else []
        current = _pick_current(versions, kernel.version)

        usage: dict[str, int] = {}
        stale = 0
        for browser, _group in by_kernel.get(kernel.id, []):
            effective = _effective_version(browser, kernel)
            if effective:
                usage[effective] = usage.get(effective, 0) + 1
            if current and effective != current.version:
                stale += 1
        for item in versions:
            item.instances = usage.get(item.version, 0)
            item.current = bool(current and item.version == current.version)

        latest = versions[0].version if versions else None
        cards.append(
            KernelCard(
                id=str(kernel.id),
                slug=slug,
                name=kernel.name,
                engine=kernel.engine,
                channel=_channel_label(kernel.channel),
                arch=kernel.arch,
                tone=str(spec["tone"]),
                tagline=kernel.note or str(spec["tagline"]),
                detection_level=kernel.detection_level,
                repo_url=kernel.repo_url,
                mirror_url=kernel.mirror_url,
                registry=kernel_scan.registry(),
                supported=supported,
                unsupported_reason=reason,
                current_version=current.version if current else None,
                current_ref=current.image_ref if current else None,
                latest_version=latest,
                update_available=bool(
                    latest
                    and (current is None or version_key(latest) > version_key(current.version))
                ),
                installed=bool(versions),
                version_count=len(versions),
                total_size=(
                    human_size(sum(item.size_bytes for item in versions)) if versions else None
                ),
                instance_count=len(by_kernel.get(kernel.id, [])),
                stale_count=stale,
                scanned_at=scanned_at,
                versions=versions,
                note=kernel.note,
            )
        )

    total_instances = sum(card.instance_count for card in cards)
    supported_cards = [card for card in cards if card.supported]
    installed = sum(1 for card in supported_cards if card.installed)
    updatable = sum(1 for card in supported_cards if card.update_available)
    stale_total = sum(card.stale_count for card in cards)
    total_size = sum(sum(item.size_bytes for item in card.versions) for card in cards)

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
                hint=f"{len(supported_cards)} 套已支持",
                tone="dark",
                icon="layers",
            ),
            KernelStat(
                key="installed",
                label="镜像就绪",
                value=f"{installed}/{len(supported_cards)}",
                hint=(
                    f"共占用 {human_size(total_size)}"
                    if installed
                    else "还没有拉取任何镜像"
                ),
                tone="emerald",
                icon="download",
            ),
            KernelStat(
                key="update",
                label="可切换",
                value=str(updatable),
                hint="本地已有更新的镜像" if updatable else "全部已是最新",
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
        registry=kernel_scan.registry(),
        docker_ok=docker_ok,
        docker_error=docker_error,
        scanned_at=scanned_at,
        total_instances=total_instances,
        total_versions=sum(card.version_count for card in cards),
    )


def _run_command(card: KernelCard, ref: str) -> str | None:
    """拼一条能直接复制的 ``docker run``：端口按内核固定分配。"""
    spec = ENGINE_SPECS.get(card.slug, DEFAULT_SPEC)
    cdp, novnc = spec.get("cdp"), spec.get("novnc")
    if not cdp or not novnc:
        return None
    return "\n".join(
        [
            f"docker run -d --name webweaver-{card.slug}",
            f"  -p {cdp}:9222 -p {novnc}:6080",
            "  -e MODE=vnc -e SCREEN=1920x1080x24",
            "  --shm-size=1g --init",
            f"  {ref}",
        ]
    )


async def detail(session: AsyncSession, slug: str) -> KernelDetailPayload:
    """单内核详情：台账卡片 + 本地镜像清单 + 说明文档。"""
    data = await payload(session)
    key = engine_slug(slug)
    card = next((item for item in data.cards if item.slug == key), None)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有这个内核引擎")

    ref = card.current_ref or f"{card.registry}:{card.slug}"
    if not card.supported:
        hint = card.unsupported_reason
    elif card.installed:
        hint = f"本地有 {card.version_count} 个版本，当前生效 {card.current_version}"
    else:
        hint = f"本地还没有镜像。点「获取内核」会执行 docker pull {card.registry}:{card.slug}"

    return KernelDetailPayload(
        slug=key,
        card=card,
        versions=card.versions,
        docs=kernel_scan.readme(card.name),
        docs_path=str(kernel_scan.readme_path(card.name)),
        hint=hint,
        run_command=_run_command(card, ref) if card.supported else None,
        docker_ok=data.docker_ok,
        docker_error=data.docker_error,
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


def _require_installed(
    kernel: Kernel, version: str, versions: list[KernelVersion]
) -> KernelVersion:
    for item in versions:
        if item.version == version:
            return item
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"本地没有 {kernel.name} {version} 的镜像，请先拉取。"
            f"当前仓库 {kernel_scan.registry()}"
        ),
    )


async def _versions_of(kernel: Kernel) -> list[KernelVersion]:
    images, ok, reason = await _load_images()
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Docker 不可用：{reason}",
        )
    return kernel_scan.scan_versions(kernel.name, images=images)


async def switch_version(
    session: AsyncSession,
    kernel_id: str,
    version: str,
    *,
    operator: str,
    request: Request | None = None,
) -> KernelPayload:
    """把某个本地镜像设为该内核的当前版本；旧镜像不删。"""
    kernel = await _get_kernel(session, kernel_id)
    _require_installed(kernel, version, await _versions_of(kernel))

    before = kernel.version
    if before != version:
        kernel.version = version
        latest = kernel.latest_version
        if latest is None or version_key(version) > version_key(latest):
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


async def adopt_pulled(slug: str, version: str) -> None:
    """拉完镜像后把台账拉回事实。

    种子数据里的版本号是写死的旧值（128 / 126 / 124），而实际拉下来的镜像往往是
    新版本（146 / 148 / 156）。台账只要还指着本地不存在的版本，新建实例就会一直
    撞上「本地没有这个版本的镜像」。所以拉取成功后，若登记版本已经悬空，就改记
    成当前最新的已装版本；登记版本仍然装着时不动——那可能是用户特意选的旧版本。
    """
    if not version or version == "latest":
        return
    images, ok, _ = await _load_images()
    if not ok:
        return

    async with SessionLocal() as session:
        kernels = (await session.scalars(select(Kernel))).all()
        for kernel in kernels:
            if engine_slug(kernel.name) != slug:
                continue
            installed = kernel_scan.scan_versions(kernel.name, images=images)
            names = {item.version for item in installed}
            if not names or kernel.version in names:
                return
            current = _pick_current(installed, kernel.version)
            if current is None:
                return
            before = kernel.version
            kernel.version = current.version
            latest = kernel.latest_version
            if latest is None or version_key(current.version) > version_key(latest):
                kernel.latest_version = current.version
            await session.commit()
            logger.info(
                "{} 登记的版本 {} 本地已不存在，台账改为 {}（拉取 {} 后校正）",
                kernel.name,
                before,
                current.version,
                version,
            )
            return


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
    _require_installed(kernel, version, await _versions_of(kernel))

    rows = (await session.execute(select(Browser).where(Browser.kernel_id == kernel.id))).scalars()
    targets: list[Browser] = []
    wanted = set(browser_ids)
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
