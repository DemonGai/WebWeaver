"""浏览器池的写操作：新建、编辑、绑定、删除与生命周期动作。

**关于「启动」**：这一版没有真正的内核进程，也没有调度器。``start`` 只做
「状态流转 + 分配一组 CDP / noVNC 端口 + 写审计」，让界面的行为与真实产品一致，
等接入调度器时把 :func:`_allocate_ports` 与 ``cdp_url`` 的生成换成真实拉起即可，
上层接口不用改。

**为什么写操作都带审计**：浏览器池是整个系统里最「容易被追责」的一块——
谁把谁的账号解绑了、谁在半夜停了实例，都得查得到。所以每个动作都落一条
``audit_logs``，绑定变化另外补一条 ``browser_*_bindings`` 流水（只追加）。

**为什么校验放在服务层**：路由只做鉴权与参数解析，业务规则（账号是否已被
别的实例占用、出口 IP 是否可达、运行中能否删除）集中在函数里，批量动作
才能复用同一套规则并对每条失败给出可读原因。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AccountStatus,
    AuditAction,
    AuditResourceType,
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
    Ip,
    IpBindingMode,
    IpStatus,
    Kernel,
    utcnow,
)
from app.schemas.browser import (
    BrowserActionItem,
    BrowserBatchResult,
    BrowserCreate,
    BrowserDetail,
    BrowserOption,
    BrowserOptions,
    BrowserUpdate,
)
from app.schemas.domain import InstanceStatus
from app.services import audit, kernel_image, kernel_scan

# 端口只分配不监听：预留一段固定区间，取当前库里没被占用的最小号。
# CDP 与 noVNC 的偏移（+3100）跟种子数据里的既有分配保持一致，方便对照日志
CDP_PORT_OFFSET = 3100
VNC_PORT_BASE = 6080

# 状态文案：批量动作的结果要能直接读
_STATUS_TEXT = {
    "running": "运行中",
    "idle": "空闲",
    "error": "异常",
    "stopped": "已停止",
    "queued": "排队中",
}


# ── 读取 ───────────────────────────────────────────────────


async def options(session: AsyncSession) -> BrowserOptions:
    """候选资源清单。

    已被别的实例绑定的账号与 IP 标成 ``disabled`` 而不是直接过滤掉：
    用户搜索某个账号却没找到时，会以为数据丢了；灰着并注明「已被 X 占用」
    才解释得清。
    """
    browsers = list((await session.scalars(select(Browser))).all())
    used_accounts = {b.account_id: b.name for b in browsers if b.account_id}
    used_ips = {b.ip_id: b.name for b in browsers if b.ip_id}

    groups = list(
        (await session.scalars(select(Group).order_by(Group.sort_order, Group.name))).all()
    )
    kernels = list((await session.scalars(select(Kernel).order_by(Kernel.name))).all())
    accounts = list((await session.scalars(select(Account).order_by(Account.username))).all())
    ips = list((await session.scalars(select(Ip).order_by(Ip.address))).all())
    fingerprints = list(
        (await session.scalars(select(Fingerprint).order_by(Fingerprint.platform))).all()
    )

    # 一次取全本地镜像，四个内核共用；docker 不可用时一律当「没有可选版本」，
    # 新建实例走内核当前版本兜底，不能让下拉框把整个页面拖挂
    try:
        images = kernel_image.list_images(kernel_scan.registry())
    except kernel_image.DockerError:
        images = []

    return BrowserOptions(
        groups=[BrowserOption(id=str(g.id), label=g.name, hint=g.code) for g in groups],
        kernels=[
            BrowserOption(id=str(k.id), label=k.name, hint=f"{k.engine} · {k.version}")
            for k in kernels
        ],
        # 只列本地确有镜像的版本；空列表时前端退回内核当前版本
        kernel_versions={
            str(k.id): [v.version for v in kernel_scan.scan_versions(k.name, images=images)]
            for k in kernels
        },
        accounts=[
            BrowserOption(
                id=str(a.id),
                label=a.username,
                hint=f"{a.platform} · {a.region}",
                disabled=a.id in used_accounts,
            )
            for a in accounts
        ],
        ips=[
            BrowserOption(
                id=str(ip.id),
                label=ip.address,
                hint=f"{ip.supplier} · {ip.region} · 延迟 {ip.latency_ms or '—'}ms",
                disabled=ip.id in used_ips or ip.status is IpStatus.failed,
            )
            for ip in ips
        ],
        fingerprints=[
            BrowserOption(
                id=str(fp.id),
                label=f"{fp.name}",
                hint=f"{fp.platform} · 唯一度 {fp.uniqueness or '—'}%",
            )
            for fp in fingerprints
        ],
    )


async def get_browser(session: AsyncSession, browser_id: str) -> Browser:
    """按 UUID 或实例名取实例；两种都支持，前端路由里可能给的是名字。"""
    try:
        row = await session.get(Browser, UUID(browser_id))
    except ValueError:
        row = await session.scalar(select(Browser).where(Browser.name == browser_id))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"实例 {browser_id} 不存在"
        )
    return row


async def detail(session: AsyncSession, browser_id: str) -> BrowserDetail:
    browser = await get_browser(session, browser_id)
    return await _detail_of(session, browser)


async def _detail_of(session: AsyncSession, browser: Browser) -> BrowserDetail:
    group = await session.get(Group, browser.group_id) if browser.group_id else None
    kernel = await session.get(Kernel, browser.kernel_id) if browser.kernel_id else None
    account = await session.get(Account, browser.account_id) if browser.account_id else None
    ip = await session.get(Ip, browser.ip_id) if browser.ip_id else None
    fingerprint = (
        await session.get(Fingerprint, browser.fingerprint_id) if browser.fingerprint_id else None
    )

    return BrowserDetail(
        id=str(browser.id),
        name=browser.name,
        status=InstanceStatus(browser.status.value),
        group_id=str(browser.group_id) if browser.group_id else None,
        group=group.name if group else "未分组",
        kernel_id=str(browser.kernel_id) if browser.kernel_id else None,
        kernel=(
            f"{kernel.name} · {browser.kernel_version or kernel.version}" if kernel else "未指定"
        ),
        kernel_version=((browser.kernel_version or kernel.version) if kernel else None),
        account_id=str(browser.account_id) if browser.account_id else None,
        account=account.username if account else "未绑定",
        ip_id=str(browser.ip_id) if browser.ip_id else None,
        ip=ip.address if ip else "直连 · 本机 IP",
        ip_mode=browser.ip_mode.value,
        region=ip.region if ip else "本机",
        fingerprint_id=str(browser.fingerprint_id) if browser.fingerprint_id else None,
        fingerprint=f"{fingerprint.platform} · {fingerprint.code}" if fingerprint else "默认指纹",
        fingerprint_mode=browser.fingerprint_mode.value,
        cdp_url=browser.cdp_url,
        vnc_url=browser.vnc_url,
        vnc_port=browser.vnc_port,
        fps=browser.fps,
        latency_ms=browser.latency_ms,
        started_at=_ago(browser.started_at),
        last_active_at=_ago(browser.last_active_at),
        created_at=browser.created_at.isoformat(),
        updated_at=browser.updated_at.isoformat(),
        note=browser.note,
    )


# ── 新建 / 编辑 / 删除 ─────────────────────────────────────


async def create(
    session: AsyncSession,
    payload: BrowserCreate,
    *,
    operator: str,
    request: Request | None = None,
) -> BrowserDetail:
    name = payload.name.strip()
    if await session.scalar(select(Browser).where(Browser.name == name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"实例名 {name} 已被占用")

    await _require(session, Group, payload.group_id, "分组")
    await _require(session, Kernel, payload.kernel_id, "内核")
    account = await _require(session, Account, payload.account_id, "账号")
    ip = await _require(session, Ip, payload.ip_id, "出口 IP")
    await _require(session, Fingerprint, payload.fingerprint_id, "指纹模板")
    await _ensure_free(session, account=account, ip=ip)

    browser = Browser(
        name=name,
        status=BrowserStatus.stopped,
        group_id=payload.group_id,
        kernel_id=payload.kernel_id,
        kernel_version=payload.kernel_version,
        account_id=payload.account_id,
        ip_mode=IpBindingMode.proxy if payload.ip_id else IpBindingMode.direct,
        ip_id=payload.ip_id,
        fingerprint_mode=FingerprintMode.template
        if payload.fingerprint_id
        else FingerprintMode.default,
        fingerprint_id=payload.fingerprint_id,
        note=payload.note,
    )
    session.add(browser)
    await session.flush()

    # 初始绑定也留流水：否则「这台机器什么时候用上这个账号的」查不到
    if browser.account_id:
        await _bind_log(
            session, browser, account=account, operator=operator, action=BindingAction.bind
        )
    if browser.ip_id and ip:
        await _bind_log(session, browser, ip=ip, operator=operator, action=BindingAction.bind)
    if browser.fingerprint_id:
        fp = await session.get(Fingerprint, browser.fingerprint_id)
        if fp:
            await _bind_log(
                session, browser, fingerprint=fp, operator=operator, action=BindingAction.bind
            )
    await session.commit()

    await audit.record(
        session,
        action=AuditAction.create,
        resource_type=AuditResourceType.browser,
        resource_id=browser.id,
        resource_name=browser.name,
        operator=operator,
        detail=f"新建实例 {browser.name}",
        changes={"name": {"before": None, "after": browser.name}},
        request=request,
    )
    return await _detail_of(session, browser)


async def update(
    session: AsyncSession,
    browser_id: str,
    payload: BrowserUpdate,
    *,
    operator: str,
    request: Request | None = None,
) -> BrowserDetail:
    browser = await get_browser(session, browser_id)
    fields = payload.model_fields_set

    before = _snapshot_fields(browser)

    if "name" in fields and payload.name:
        name = payload.name.strip()
        if name != browser.name:
            clash = await session.scalar(select(Browser).where(Browser.name == name))
            if clash is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=f"实例名 {name} 已被占用"
                )
            browser.name = name

    if "group_id" in fields:
        await _require(session, Group, payload.group_id, "分组")
        browser.group_id = payload.group_id
    if "kernel_id" in fields:
        await _require(session, Kernel, payload.kernel_id, "内核")
        browser.kernel_id = payload.kernel_id
        # 换引擎后旧版本号不再适用，回到「跟随内核当前版本」
        browser.kernel_version = None
    if "kernel_version" in fields:
        browser.kernel_version = payload.kernel_version
    if "note" in fields:
        browser.note = payload.note

    # 账号：换绑要写两条流水（解绑旧的、绑定新的），并保证新账号没被别人占着
    if "account_id" in fields and payload.account_id != browser.account_id:
        old_account = await session.get(Account, browser.account_id) if browser.account_id else None
        new_account = await _require(session, Account, payload.account_id, "账号")
        await _ensure_free(session, account=new_account, browser=browser)
        if old_account:
            await _bind_log(
                session,
                browser,
                account=old_account,
                operator=operator,
                action=BindingAction.unbind,
            )
        browser.account_id = payload.account_id
        if new_account:
            await _bind_log(
                session, browser, account=new_account, operator=operator, action=BindingAction.bind
            )

    # 出口 IP：传 null 就是切回直连，模式字段必须跟着改，否则 CHECK 约束会拒绝
    if "ip_id" in fields and payload.ip_id != browser.ip_id:
        old_ip = await session.get(Ip, browser.ip_id) if browser.ip_id else None
        new_ip = await _require(session, Ip, payload.ip_id, "出口 IP")
        if new_ip and new_ip.status is IpStatus.failed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"出口 IP {new_ip.address} 探测失败，请先在 IP 池处理",
            )
        await _ensure_free(session, ip=new_ip, browser=browser)
        if old_ip:
            await _bind_log(
                session, browser, ip=old_ip, operator=operator, action=BindingAction.unbind
            )
        browser.ip_id = payload.ip_id
        browser.ip_mode = IpBindingMode.proxy if payload.ip_id else IpBindingMode.direct
        if new_ip:
            await _bind_log(
                session, browser, ip=new_ip, operator=operator, action=BindingAction.bind
            )

    # 指纹：同上，传 null 就是默认模式
    if "fingerprint_id" in fields and payload.fingerprint_id != browser.fingerprint_id:
        old_fp = (
            await session.get(Fingerprint, browser.fingerprint_id)
            if browser.fingerprint_id
            else None
        )
        new_fp = await _require(session, Fingerprint, payload.fingerprint_id, "指纹模板")
        if old_fp:
            await _bind_log(
                session,
                browser,
                fingerprint=old_fp,
                operator=operator,
                action=BindingAction.unbind,
            )
        browser.fingerprint_id = payload.fingerprint_id
        browser.fingerprint_mode = (
            FingerprintMode.template if payload.fingerprint_id else FingerprintMode.default
        )
        if new_fp:
            await _bind_log(
                session, browser, fingerprint=new_fp, operator=operator, action=BindingAction.bind
            )

    browser.updated_at = utcnow()
    await session.commit()

    changes = audit.snapshot_diff(before, _snapshot_fields(browser))
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.browser,
        resource_id=browser.id,
        resource_name=browser.name,
        operator=operator,
        detail=f"更新实例 {browser.name}",
        changes=changes,
        request=request,
    )
    return await _detail_of(session, browser)


async def remove(
    session: AsyncSession,
    browser_id: str,
    *,
    operator: str,
    request: Request | None = None,
) -> None:
    browser = await get_browser(session, browser_id)
    if browser.status is BrowserStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="实例正在运行，请先停止再删除",
        )

    # 绑定流水有外键指向 browsers.id，不先删会挡住删除；
    # 历史审计保留（audit_logs.resource_id 故意不建外键），删了实例仍可追溯
    for model in (BrowserAccountBinding, BrowserIpBinding, BrowserFingerprintBinding):
        rows = await session.scalars(select(model).where(model.browser_id == browser.id))
        for row in rows:
            await session.delete(row)
    name = browser.name
    await session.delete(browser)
    await session.commit()

    await audit.record(
        session,
        action=AuditAction.delete,
        resource_type=AuditResourceType.browser,
        resource_id=browser_id,
        resource_name=name,
        operator=operator,
        detail=f"删除实例 {name}",
        request=request,
    )


# ── 生命周期 ───────────────────────────────────────────────


async def act(
    session: AsyncSession,
    browser_id: str,
    action: str,
    *,
    operator: str,
    request: Request | None = None,
) -> BrowserActionItem:
    browser = await get_browser(session, browser_id)
    return await _apply(session, browser, action, operator=operator, request=request)


async def batch(
    session: AsyncSession,
    ids: list[str],
    action: str,
    *,
    operator: str,
    request: Request | None = None,
) -> BrowserBatchResult:
    """批量动作：逐条执行，失败不中断。

    一条失败就把整批回滚，用户还得自己找出是哪台出的问题；逐条执行并把
    失败原因带回去，界面上可以直接标红那几张卡。
    """
    items: list[BrowserActionItem] = []
    for raw_id in ids:
        # 先解析实例，失败时也能把实例名带回去——只甩一串 UUID 用户没法定位
        try:
            browser = await get_browser(session, raw_id)
        except HTTPException as exc:
            items.append(
                BrowserActionItem(
                    id=str(raw_id),
                    name=str(raw_id),
                    ok=False,
                    status="unknown",
                    message=str(exc.detail),
                )
            )
            continue

        try:
            items.append(await _apply(session, browser, action, operator=operator, request=request))
        except HTTPException as exc:
            items.append(
                BrowserActionItem(
                    id=str(browser.id),
                    name=browser.name,
                    ok=False,
                    status=browser.status.value,
                    message=str(exc.detail),
                )
            )

    failed = sum(1 for item in items if not item.ok)
    return BrowserBatchResult(
        ok=failed == 0,
        action=action,
        succeeded=len(items) - failed,
        failed=failed,
        items=items,
    )


async def _apply(
    session: AsyncSession,
    browser: Browser,
    action: str,
    *,
    operator: str,
    request: Request | None,
) -> BrowserActionItem:
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=422, detail=f"不支持的动作：{action}")

    before = browser.status
    if action == "start":
        if browser.status is BrowserStatus.running:
            raise HTTPException(status_code=409, detail=f"{browser.name} 已在运行")
        await _start(session, browser)
        done, message = AuditAction.start, f"启动 {browser.name}"
    elif action == "stop":
        if browser.status is BrowserStatus.stopped:
            raise HTTPException(status_code=409, detail=f"{browser.name} 已经是停止状态")
        _stop(browser)
        done, message = AuditAction.stop, f"停止 {browser.name}"
    else:
        # 重启允许从任何状态发起：停止状态点重启的语义就是「拉起来」
        _stop(browser)
        await _start(session, browser)
        done, message = AuditAction.start, f"重启 {browser.name}"

    await session.commit()
    await audit.record(
        session,
        action=done,
        resource_type=AuditResourceType.browser,
        resource_id=browser.id,
        resource_name=browser.name,
        operator=operator,
        detail=message,
        duration_ms=None,
        changes={
            "status": {"before": before.value, "after": browser.status.value},
        },
        request=request,
    )
    return BrowserActionItem(
        id=str(browser.id),
        name=browser.name,
        ok=True,
        status=browser.status.value,
        message=f"{message}完成（{_STATUS_TEXT.get(browser.status.value, browser.status.value)}）",
    )


async def _start(session: AsyncSession, browser: Browser) -> None:
    """分配端口、写运行时字段、置为运行中。"""
    if browser.ip_id:
        ip = await session.get(Ip, browser.ip_id)
        if ip is not None and ip.status is IpStatus.failed:
            raise HTTPException(
                status_code=409,
                detail=f"{browser.name} 绑定的出口 IP {ip.address} 不可达，请先更换",
            )

    cdp_port, vnc_port = await _allocate_ports(session, browser)
    browser.status = BrowserStatus.running
    browser.started_at = utcnow()
    browser.last_active_at = utcnow()
    browser.cdp_url = f"http://127.0.0.1:{cdp_port}"
    browser.vnc_port = vnc_port
    browser.vnc_url = f"http://127.0.0.1:{vnc_port}/vnc.html?autoconnect=1&resize=scale"
    # 帧率与延迟是占位读数：真实值要等画面通道接上后由采集侧回写
    browser.fps = 30
    browser.latency_ms = 18 + vnc_port % 40
    browser.updated_at = utcnow()


def _stop(browser: Browser) -> None:
    browser.status = BrowserStatus.stopped
    browser.started_at = None
    browser.last_active_at = utcnow()
    browser.cdp_url = None
    browser.vnc_url = None
    browser.vnc_port = None
    browser.fps = None
    browser.latency_ms = None
    browser.updated_at = utcnow()


async def _allocate_ports(session: AsyncSession, browser: Browser) -> tuple[int, int]:
    """从固定区间里取最小的空闲端口对。

    只看数据库里别的实例占了哪些号——这台机器上真实有没有被系统进程占用
    无法从这里判断，接调度器时这里要换成探测 + 加锁分配。
    """
    used = set(
        await session.scalars(
            select(Browser.vnc_port).where(Browser.vnc_port.is_not(None), Browser.id != browser.id)
        )
    )
    vnc_port = VNC_PORT_BASE
    while vnc_port in used:
        vnc_port += 1
    return vnc_port + CDP_PORT_OFFSET, vnc_port


# ── 内部小工具 ─────────────────────────────────────────────


async def _require(session: AsyncSession, model, value: UUID | None, label: str):
    """校验外键指向的资源存在；``None`` 合法（表示不绑定）。"""
    if value is None:
        return None
    row = await session.get(model, value)
    if row is None:
        raise HTTPException(status_code=422, detail=f"{label}不存在或已被删除")
    return row


async def _ensure_free(
    session: AsyncSession,
    *,
    account: Account | None = None,
    ip: Ip | None = None,
    browser: Browser | None = None,
) -> None:
    """一个账号 / 一个出口 IP 只能挂在一台实例上。

    放开这条会立刻出问题：两台实例用同一个账号并发登录，平台侧的风控
    把账号锁掉，排查起来还找不到原因。
    """
    if account is not None:
        other = await session.scalar(
            select(Browser).where(Browser.account_id == account.id, Browser.id != _id(browser))
        )
        if other is not None:
            raise HTTPException(
                status_code=409,
                detail=f"账号 {account.username} 已绑定实例 {other.name}",
            )
        if account.status is AccountStatus.restricted:
            raise HTTPException(
                status_code=422,
                detail=f"账号 {account.username} 处于风控状态，处理后再绑定",
            )
    if ip is not None:
        other = await session.scalar(
            select(Browser).where(Browser.ip_id == ip.id, Browser.id != _id(browser))
        )
        if other is not None:
            raise HTTPException(
                status_code=409, detail=f"出口 IP {ip.address} 已被 {other.name} 占用"
            )


def _id(browser: Browser | None) -> UUID:
    # 新建时还没有实例，用一个不可能命中的 UUID 占位，避免 SQL 里出现 id != NULL
    return browser.id if browser else UUID(int=0)


async def _bind_log(
    session: AsyncSession,
    browser: Browser,
    *,
    account: Account | None = None,
    ip: Ip | None = None,
    fingerprint: Fingerprint | None = None,
    operator: str,
    action: BindingAction,
) -> None:
    common = {
        "browser_id": browser.id,
        "action": action,
        "operator": operator,
        "source": BindingSource.api,
    }
    if account is not None:
        session.add(BrowserAccountBinding(**common, account_id=account.id))
    if ip is not None:
        session.add(
            BrowserIpBinding(
                **common,
                mode=IpBindingMode.proxy,
                ip_id=ip.id,
                resolved_address=ip.address,
            )
        )
    if fingerprint is not None:
        session.add(
            BrowserFingerprintBinding(
                **common,
                mode=FingerprintMode.template,
                fingerprint_id=fingerprint.id,
            )
        )


def _snapshot_fields(browser: Browser) -> dict[str, object]:
    """审计用的字段快照：只放「改了什么值得留痕」的那些列。"""
    return {
        "name": browser.name,
        "status": browser.status.value,
        "group_id": str(browser.group_id) if browser.group_id else None,
        "kernel_id": str(browser.kernel_id) if browser.kernel_id else None,
        "account_id": str(browser.account_id) if browser.account_id else None,
        "ip_id": str(browser.ip_id) if browser.ip_id else None,
        "ip_mode": browser.ip_mode.value,
        "fingerprint_id": str(browser.fingerprint_id) if browser.fingerprint_id else None,
        "fingerprint_mode": browser.fingerprint_mode.value,
        "note": browser.note,
    }


def _ago(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    seconds = int((utcnow() - moment).total_seconds())
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"
