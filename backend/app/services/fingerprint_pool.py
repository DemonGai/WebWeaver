"""指纹池：把一条指纹记录翻译成「下发给内核的参数」和「采集回来的人格」。

这一层只做三件事：
1. 读：把库里的字段拼成列表 / 详情，并按内核能力算出适配状态；
2. 写：新建、编辑、删除，顺手校验种子范围和平台是否被该内核接受；
3. 动作：采集（起容器读人格回填）、下发（写进实例容器并重启）。

参数与内核的对应关系不在这里判断，全部交给 `fingerprint_caps`。这样「某个内核
认哪些参数」只有一处定义，改内核不用翻遍业务代码。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditResourceType, Browser, Fingerprint, Kernel
from app.models.base import utcnow
from app.models.enums import FingerprintMode, PlatformFamily
from app.schemas.domain import (
    FilterItem,
    FingerprintApplyItem,
    FingerprintApplyResult,
    FingerprintCreate,
    FingerprintDetailPayload,
    FingerprintInstanceRef,
    FingerprintPayload,
    FingerprintRender,
    FingerprintTemplate,
    FingerprintUpdate,
    KernelFingerprintCaps,
)
from app.services import audit, fingerprint_apply, fingerprint_caps, fingerprint_probe
from app.services.cluster import Snapshot
from app.services.fingerprint_caps import FingerprintSpec, KernelCaps
from app.services.kernel_scan import engine_slug

_FAMILY_LABELS: dict[str, str] = {
    PlatformFamily.windows.value: "Windows",
    PlatformFamily.macos.value: "macOS",
    PlatformFamily.linux.value: "Linux",
    PlatformFamily.android.value: "Android",
    PlatformFamily.ios.value: "iOS",
}


# ── 内核 → 能力 ─────────────────────────────────────────────


def caps_of(kernel: Kernel | None) -> KernelCaps:
    """内核记录 → 指纹能力。没有绑定内核时一律当不支持：不知道按哪套参数下发。"""
    if kernel is None:
        return fingerprint_caps.UNKNOWN
    return fingerprint_caps.caps_for(engine_slug(kernel.name))


def unsupported_reason(fp: Fingerprint, caps: KernelCaps) -> str | None:
    """这条指纹在当前内核上为什么不能用。None 表示能用。"""
    if caps is fingerprint_caps.UNKNOWN:
        return "还没绑定内核，不知道按哪套参数下发"
    if not caps.supported:
        return caps.reason or f"{caps.engine_label} 不支持指纹"
    if fingerprint_caps.platform_token(fp.platform_family.value) is None:
        family = _FAMILY_LABELS.get(fp.platform_family.value, fp.platform_family.value)
        return f"{caps.engine_label} 是桌面内核，伪装不成 {family}"
    return None


def spec_of(fp: Fingerprint) -> FingerprintSpec:
    return FingerprintSpec(
        seed=fp.seed,
        platform_family=fp.platform_family.value,
        platform_version=fp.platform_version,
        brand=fp.brand,
        brand_version=fp.brand_version,
        hardware_concurrency=fp.hardware_concurrency,
        timezone=fp.timezone,
        locale=fp.language,
        accept_lang=fp.accept_lang,
        webrtc_ip=fp.webrtc_ip,
        canvas_noise=fp.canvas_noise,
        webgl_noise=fp.webgl_noise,
        audio_noise=fp.audio_noise,
        webrtc_protected=fp.webrtc_protected,
    )


def probe_state(fp: Fingerprint) -> str:
    """never / fresh / stale / failed —— 实测值还能不能信。

    判断依据是「下发参数摘要」而不是时间戳：采集完立刻改种子也能抓到，
    而改完又改回原值则判定为没变（人格确实没变，不需要重采）。
    """
    if fp.probe_error:
        return "failed"
    if fp.probed_at is None:
        return "never"
    if fp.probed_digest and fp.probed_digest != fingerprint_caps.spec_digest(spec_of(fp)):
        return "stale"
    return "fresh"


def _gpu_of(fp: Fingerprint) -> str | None:
    renderer = ((fp.probe or {}).get("webgl") or {}).get("renderer")
    return fingerprint_probe.shorten_gpu(renderer) if renderer else None


def _disguises(fp: Fingerprint) -> list[str]:
    """伪装项摘要。

    这里只列「这条指纹要求内核做的事」，不列「内核实际做到了什么」—— 后者要看
    实测快照，见 `gpu` / `canvas_hash`。两个概念混在一起最容易让人误判。
    """
    items: list[str] = []
    if fp.canvas_noise:
        items.append("Canvas 噪声")
    if fp.webgl_noise:
        items.append("WebGL 噪声")
    if fp.audio_noise:
        items.append("Audio 噪声")
    if fp.webrtc_protected:
        items.append("WebRTC 防泄漏")
    return items


# ── 读 ─────────────────────────────────────────────────────


def _row(
    fp: Fingerprint,
    kernel: Kernel | None,
    caps: KernelCaps,
    instances: int,
) -> FingerprintTemplate:
    reason = unsupported_reason(fp, caps)
    state = probe_state(fp)
    return FingerprintTemplate(
        id=str(fp.id),
        name=fp.name,
        fp_id=fp.code,
        platform_family=fp.platform_family.value,
        platform=fp.platform,
        ua=fp.user_agent,
        timezone=fp.timezone,
        language=fp.language,
        resolution=fp.resolution,
        dpr=f"Dpr {fp.dpr}" if fp.dpr else "",
        disguises=_disguises(fp),
        uniqueness=fp.uniqueness,
        warning=fp.warning,
        instances=instances,
        action=None,
        seed=fp.seed,
        kernel=kernel.name if kernel else None,
        kernel_slug=engine_slug(kernel.name) if kernel else None,
        supported=reason is None,
        unsupported_reason=reason,
        gpu=_gpu_of(fp),
        canvas_hash=(fp.probe or {}).get("canvasHash"),
        probed_at=fp.probed_at.isoformat() if fp.probed_at else None,
        probe_state=state,
    )


def fingerprints(snapshot: Snapshot) -> FingerprintPayload:
    """列表。按「能用 / 不能用」分组，组内按编号排，方便对照着看。"""
    rows: list[FingerprintTemplate] = []
    caps_by_slug: dict[str, KernelCaps] = {}
    supported_kernels = 0
    for kernel in snapshot.kernels.values():
        caps = caps_of(kernel)
        caps_by_slug[engine_slug(kernel.name)] = caps
        if caps.supported:
            supported_kernels += 1

    family_count = {family: 0 for family in PlatformFamily}
    for fp in snapshot.fingerprints.values():
        kernel = snapshot.kernels.get(fp.kernel_id) if fp.kernel_id else None
        caps = caps_of(kernel)
        rows.append(
            _row(fp, kernel, caps, len(snapshot.browsers_by_fingerprint.get(fp.id, []))),
        )
        family_count[fp.platform_family] += 1

    rows.sort(key=lambda item: (not item.supported, item.fp_id))
    mobile = family_count[PlatformFamily.android] + family_count[PlatformFamily.ios]
    probed = sum(1 for item in rows if item.probe_state in ("fresh", "stale"))

    return FingerprintPayload(
        total=len(rows),
        kernels=len(snapshot.kernels),
        supported_kernels=supported_kernels,
        probed=probed,
        stale=sum(1 for item in rows if item.probe_state == "stale"),
        filters=[
            FilterItem(key="all", label="全部", count=len(rows)),
            FilterItem(key="windows", label="Windows", count=family_count[PlatformFamily.windows]),
            FilterItem(key="macos", label="macOS", count=family_count[PlatformFamily.macos]),
            FilterItem(key="mobile", label="移动", count=mobile),
        ],
        templates=rows,
        shown=len(rows),
        selected=0,
        page=1,
        pages=1,
    )


async def get(session: AsyncSession, fingerprint_id: str) -> Fingerprint:
    try:
        key = UUID(fingerprint_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="指纹不存在") from exc
    fp = await session.get(Fingerprint, key)
    if fp is None:
        raise HTTPException(status_code=404, detail="指纹不存在")
    return fp


async def detail(session: AsyncSession, fingerprint_id: str) -> FingerprintDetailPayload:
    return await _build_detail(session, await get(session, fingerprint_id))


async def _build_detail(
    session: AsyncSession, fp: Fingerprint
) -> FingerprintDetailPayload:
    kernel = await session.get(Kernel, fp.kernel_id) if fp.kernel_id else None
    caps = caps_of(kernel)
    reason = unsupported_reason(fp, caps)

    browsers = list(
        await session.scalars(
            select(Browser).where(Browser.fingerprint_id == fp.id).order_by(Browser.name)
        )
    )

    rendered: FingerprintRender | None = None
    if reason is None:
        result = fingerprint_caps.render(spec_of(fp), caps)
        rendered = FingerprintRender(
            payload=result.payload,
            env=result.env,
            args=result.args,
            ignored=result.ignored,
        )

    warns = list((fp.probe or {}).get("_warnings") or [])
    return FingerprintDetailPayload(
        id=str(fp.id),
        name=fp.name,
        fp_id=fp.code,
        kernel=kernel.name if kernel else None,
        kernel_slug=engine_slug(kernel.name) if kernel else None,
        supported=reason is None,
        unsupported_reason=reason,
        note=caps.note or None,
        seed=fp.seed,
        seed_range=list(caps.seed_range) if caps.seed_range else None,
        platform_family=fp.platform_family.value,
        platform_version=fp.platform_version,
        brand=fp.brand,
        brand_version=fp.brand_version,
        hardware_concurrency=fp.hardware_concurrency,
        timezone=fp.timezone,
        language=fp.language,
        accept_lang=fp.accept_lang,
        webrtc_ip=fp.webrtc_ip,
        canvas_noise=fp.canvas_noise,
        webgl_noise=fp.webgl_noise,
        audio_noise=fp.audio_noise,
        webrtc_protected=fp.webrtc_protected,
        ua=fp.user_agent,
        resolution=fp.resolution,
        dpr=fp.dpr,
        gpu=_gpu_of(fp),
        canvas_hash=(fp.probe or {}).get("canvasHash"),
        languages=list((fp.probe or {}).get("languages") or []),
        webdriver=(fp.probe or {}).get("webdriver"),
        probed_at=fp.probed_at.isoformat() if fp.probed_at else None,
        probe_state=probe_state(fp),
        probe_error=fp.probe_error,
        warnings=warns,
        instances=[
            FingerprintInstanceRef(
                id=str(browser.id), name=browser.name, status=browser.status.value
            )
            for browser in browsers
        ],
        render=rendered,
    )


# ── 写 ─────────────────────────────────────────────────────


async def _kernel_or_404(session: AsyncSession, kernel_id: str | None) -> Kernel | None:
    if not kernel_id:
        return None
    try:
        kernel = await session.get(Kernel, UUID(kernel_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="内核 ID 不合法") from exc
    if kernel is None:
        raise HTTPException(status_code=404, detail="内核不存在")
    return kernel


def _validate(fp: Fingerprint, caps: KernelCaps) -> None:
    """保存前把「这个内核根本做不到的事」挡掉，别等到下发才失败。"""
    reason = unsupported_reason(fp, caps)
    if reason:
        raise HTTPException(status_code=422, detail=reason)
    if fp.seed is not None:
        error = caps.validate_seed(fp.seed)
        if error:
            raise HTTPException(status_code=422, detail=error)


async def _unique_code(session: AsyncSession, base: str) -> str:
    """生成一个没被占用的编号。撞了就加后缀，不做静默覆盖。"""
    candidate = base
    index = 1
    while await session.scalar(select(Fingerprint).where(Fingerprint.code == candidate)):
        index += 1
        candidate = f"{base}-{index}"
    return candidate


def _default_code(family: PlatformFamily, seed: int | None) -> str:
    short = {
        PlatformFamily.windows: "win",
        PlatformFamily.macos: "mac",
        PlatformFamily.linux: "linux",
        PlatformFamily.android: "android",
        PlatformFamily.ios: "ios",
    }[family]
    return f"fp-{short}-{seed}" if seed else f"fp-{short}"


async def create(
    session: AsyncSession,
    payload: FingerprintCreate,
    *,
    operator: str,
    request: Request | None = None,
) -> FingerprintDetailPayload:
    kernel = await _kernel_or_404(session, payload.kernel_id)
    caps = caps_of(kernel)

    try:
        family = PlatformFamily(payload.platform_family)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="平台族只能是 windows/macos/linux/android/ios"
        ) from exc

    seed = payload.seed if payload.seed is not None else fingerprint_caps.random_seed()
    fp = Fingerprint(
        code=await _unique_code(
            session, payload.code or _default_code(family, seed)
        ),
        name=payload.name.strip(),
        platform_family=family,
        platform=_FAMILY_LABELS.get(family.value, family.value),
        user_agent="",
        timezone=payload.timezone,
        language=payload.language,
        resolution="",
        dpr="1",
        seed=seed,
        platform_version=payload.platform_version,
        brand=payload.brand,
        brand_version=payload.brand_version,
        hardware_concurrency=payload.hardware_concurrency,
        accept_lang=payload.accept_lang,
        webrtc_ip=payload.webrtc_ip,
        canvas_noise=payload.canvas_noise,
        webgl_noise=payload.webgl_noise,
        audio_noise=payload.audio_noise,
        webrtc_protected=payload.webrtc_protected,
        kernel_id=kernel.id if kernel else None,
    )
    _validate(fp, caps)

    session.add(fp)
    await session.commit()

    await audit.record(
        session,
        action=AuditAction.create,
        resource_type=AuditResourceType.fingerprint,
        resource_id=fp.id,
        resource_name=fp.name,
        operator=operator,
        detail=f"新建指纹 {fp.code}（种子 {fp.seed}）",
        changes={"seed": {"before": None, "after": fp.seed}},
        request=request,
    )
    await session.refresh(fp)
    return await _build_detail(session, fp)


async def update(
    session: AsyncSession,
    fingerprint_id: str,
    payload: FingerprintUpdate,
    *,
    operator: str,
    request: Request | None = None,
) -> FingerprintDetailPayload:
    fp = await get(session, fingerprint_id)
    before_seed = fp.seed

    fields = payload.model_dump(exclude_unset=True)
    if "kernel_id" in fields:
        kernel = await _kernel_or_404(session, fields.pop("kernel_id"))
        fp.kernel_id = kernel.id if kernel else None
    if "platform_family" in fields:
        raw = fields.pop("platform_family")
        try:
            fp.platform_family = PlatformFamily(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="平台族不合法") from exc
    for key, value in fields.items():
        if value is not None:
            setattr(fp, key, value)

    kernel = await session.get(Kernel, fp.kernel_id) if fp.kernel_id else None
    caps = caps_of(kernel)
    _validate(fp, caps)

    fp.updated_at = utcnow()
    await session.commit()

    changes: dict[str, Any] = {}
    if before_seed != fp.seed:
        changes["seed"] = {"before": before_seed, "after": fp.seed}
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.fingerprint,
        resource_id=fp.id,
        resource_name=fp.name,
        operator=operator,
        detail=f"编辑指纹 {fp.code}",
        changes=changes or None,
        request=request,
    )
    await session.refresh(fp)
    return await _build_detail(session, fp)


async def remove(
    session: AsyncSession,
    fingerprint_id: str,
    *,
    operator: str,
    request: Request | None = None,
) -> None:
    fp = await get(session, fingerprint_id)
    users = list(await session.scalars(select(Browser).where(Browser.fingerprint_id == fp.id)))
    if users:
        names = "、".join(browser.name for browser in users[:5])
        more = f" 等 {len(users)} 台" if len(users) > 5 else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{names}{more}还在用这条指纹，先给它们换一条再删",
        )

    code, name = fp.code, fp.name
    await session.delete(fp)
    await session.commit()
    await audit.record(
        session,
        action=AuditAction.delete,
        resource_type=AuditResourceType.fingerprint,
        resource_id=None,
        resource_name=name,
        operator=operator,
        detail=f"删除指纹 {code}",
        request=request,
    )


# ── 采集 ───────────────────────────────────────────────────


async def probe(
    session: AsyncSession,
    fingerprint_id: str,
    *,
    operator: str,
    request: Request | None = None,
) -> FingerprintDetailPayload:
    """起一个临时容器，按当前参数装配一次人格，把结果写回记录。"""
    fp = await get(session, fingerprint_id)
    kernel = await session.get(Kernel, fp.kernel_id) if fp.kernel_id else None
    caps = caps_of(kernel)
    reason = unsupported_reason(fp, caps)
    if reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)

    try:
        result = await fingerprint_probe.collect(caps, spec_of(fp))
    except fingerprint_probe.ProbeError as exc:
        fp.probe_error = str(exc)[:512]
        await session.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    _absorb(fp, result)
    await session.commit()

    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.fingerprint,
        resource_id=fp.id,
        resource_name=fp.name,
        operator=operator,
        detail=f"采集指纹 {fp.code}（{result.duration}s，镜像 {result.image_ref}）",
        changes={"probe": {"before": None, "after": result.gpu or "已采集"}},
        request=request,
    )
    await session.refresh(fp)
    return await _build_detail(session, fp)


def _absorb(fp: Fingerprint, result: fingerprint_probe.ProbeResult) -> None:
    """把采集结果回填到记录。UA / 分辨率 / 时区这些一律以实测为准。"""
    raw = result.raw
    fp.user_agent = result.user_agent or fp.user_agent
    fp.resolution = result.resolution or fp.resolution
    fp.dpr = result.dpr or fp.dpr
    # platform 是「Windows 11」「Pixel 8 / Android 14」这种稳定的设备描述，
    # 列表里的短标识（Win11 / C128）就是从它派生的。采集只能从 UA 推出
    # 「Windows · Chrome 146」这种更粗的摘要，覆盖它等于用信息量更低的值
    # 换掉更好的值，还会让短标识变成「Win· Chrome 146」。所以不动这一列，
    # 实测到的平台信息本来就在 probe 快照里。

    family = result.platform_family
    if family and family in PlatformFamily.__members__:
        fp.platform_family = PlatformFamily(family)

    timezone = raw.get("timezone")
    if timezone:
        fp.timezone = str(timezone)
    language = raw.get("language")
    if language:
        fp.language = str(language)
    languages = raw.get("languages") or []
    if languages:
        fp.accept_lang = ",".join(str(item) for item in languages)

    concurrency = raw.get("hardwareConcurrency")
    if isinstance(concurrency, int) and concurrency > 0:
        fp.hardware_concurrency = concurrency

    # 一致性告警存进 warning，和 probe 快照一起，页面上直接能看到
    warnings = result.warnings
    fp.warning = "；".join(warnings) if warnings else None

    fp.probe = {**raw, "_warnings": warnings}
    fp.probed_digest = fingerprint_caps.spec_digest(spec_of(fp))
    fp.probed_at = utcnow()
    fp.probe_error = None


# ── 下发 ───────────────────────────────────────────────────


async def apply_to(
    session: AsyncSession,
    fingerprint_id: str,
    instance_ids: list[str],
    *,
    operator: str,
    request: Request | None = None,
) -> FingerprintApplyResult:
    """把指纹写进这些实例的容器并重启，顺便把绑定关系落到实例上。"""
    fp = await get(session, fingerprint_id)
    kernel = await session.get(Kernel, fp.kernel_id) if fp.kernel_id else None
    caps = caps_of(kernel)
    reason = unsupported_reason(fp, caps)
    if reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)

    targets = await _resolve_instances(session, instance_ids)
    spec = spec_of(fp)
    items: list[FingerprintApplyItem] = []

    for raw_id, browser in targets:
        if browser is None:
            items.append(
                FingerprintApplyItem(
                    instance_id=raw_id,
                    instance_name=raw_id,
                    container="",
                    ok=False,
                    message="找不到这个实例",
                )
            )
            continue

        container = f"{fingerprint_apply.CONTAINER_PREFIX}{browser.name}"
        try:
            result = await fingerprint_apply.apply(caps, spec, instance_name=browser.name)
        except fingerprint_apply.ApplyError as exc:
            detail = " ".join(exc.detail) if exc.detail else ""
            items.append(
                FingerprintApplyItem(
                    instance_id=str(browser.id),
                    instance_name=browser.name,
                    container=container,
                    ok=False,
                    message=f"{exc}{(' ' + detail) if detail else ''}",
                )
            )
            continue

        # 写进去就说明这台机器以后归这条指纹管，绑定关系跟着落库
        browser.fingerprint_id = fp.id
        browser.fingerprint_mode = FingerprintMode.template
        browser.updated_at = utcnow()
        items.append(
            FingerprintApplyItem(
                instance_id=str(browser.id),
                instance_name=browser.name,
                container=result.container,
                ok=True,
                message="已写入指纹文件并重启容器" if result.restarted else "已写入指纹文件",
                restarted=result.restarted,
                ignored=result.ignored,
            )
        )

    await session.commit()
    succeeded = sum(1 for item in items if item.ok)
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.fingerprint,
        resource_id=fp.id,
        resource_name=fp.name,
        operator=operator,
        detail=f"下发指纹 {fp.code} 到 {succeeded}/{len(items)} 台实例",
        changes={"apply": {"before": None, "after": fp.code}},
        request=request,
    )
    return FingerprintApplyResult(
        ok=succeeded == len(items) and succeeded > 0,
        succeeded=succeeded,
        failed=len(items) - succeeded,
        items=items,
    )


async def _resolve_instances(
    session: AsyncSession, keys: list[str]
) -> list[tuple[str, Browser | None]]:
    """实例 ID 和实例名都接受 —— 前端手里可能只有其中一种。"""
    out: list[tuple[str, Browser | None]] = []
    for key in keys:
        browser: Browser | None = None
        try:
            browser = await session.get(Browser, UUID(key))
        except ValueError:
            browser = await session.scalar(select(Browser).where(Browser.name == key))
        out.append((key, browser))
    return out


async def apply_options(session: AsyncSession) -> list[FingerprintInstanceRef]:
    """下发时可选的实例。全部列出，由用户自己挑。"""
    rows = await session.scalars(select(Browser).order_by(Browser.name))
    return [
        FingerprintInstanceRef(id=str(row.id), name=row.name, status=row.status.value)
        for row in rows
    ]


async def capabilities(session: AsyncSession) -> list[KernelFingerprintCaps]:
    """每个内核的指纹能力。前端据此决定表单里哪些字段可用。"""
    kernels = await session.scalars(select(Kernel).order_by(Kernel.name))
    out: list[KernelFingerprintCaps] = []
    for kernel in kernels:
        caps = caps_of(kernel)
        out.append(
            KernelFingerprintCaps(
                kernel_id=str(kernel.id),
                slug=engine_slug(kernel.name),
                label=kernel.name,
                supported=caps.supported,
                seed_range=list(caps.seed_range) if caps.seed_range else None,
                features=sorted(caps.features),
                note=caps.note,
                reason=caps.reason,
            )
        )
    return out
