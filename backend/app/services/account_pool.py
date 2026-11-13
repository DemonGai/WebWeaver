"""账号管理的写操作：新建、编辑、批量导入。

Cookie 是这层的关键数据：它等价于「已登录」，所以整份存 ``accounts.cookies``
（JSONB，明文，按用户要求不做加密）。接口不把它塞进列表响应，只在单条详情里
下发——列表一屏几十行，每行几十条 Cookie，纯粹是把带宽花在不需要的地方。

导入的格式容忍度按真实用法来：供应商 / 同事给的多半是 CSV 或者从表格里
直接复制的一段文本，所以支持表头映射与「平台,账号,邮箱,地区,健康度,备注」
的位置约定；只有一列账号名时用弹窗里选的默认平台兜底。坏行单独报错，
不牵连整批。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AuditAction, AuditResourceType
from app.models.base import utcnow
from app.models.enums import AccountStatus
from app.schemas.domain import (
    AccountCreateRequest,
    AccountDetail,
    AccountImportRequest,
    AccountImportResult,
    AccountImportRow,
    AccountUpdateRequest,
)
from app.services import audit
from app.services.platforms import InvalidLoginUrl, detect_platform, normalize_login_url

# 模板列序：解析器认这一份，前端「下载模板」下的也是这一份。
# 第一列是登录地址而不是平台——平台由地址推导，不需要用户填
ACCOUNT_TEMPLATE_COLUMNS = ("login_url", "username", "email", "region", "health", "note")

ACCOUNT_TEMPLATE_ROWS = (
    (
        "https://sellercentral.amazon.com/ap/signin",
        "shop_us_101",
        "shop_us_101@example.com",
        "美国区",
        "90",
        "主店，待绑定实例",
    ),
    (
        "https://www.tiktok.com/login",
        "kol_jp_022",
        "kol_jp_022@example.com",
        "日本区",
        "100",
        "",
    ),
    (
        "https://admin.shopify.com/store/shop-uk-007",
        "shop_uk_007",
        "shop_uk_007@example.com",
        "英国区",
        "85",
        "需要更换 Cookie",
    ),
)

# 表头别名：中文列名、复数、常见简写都收，省得用户对着模板逐列改
_HEADER_ALIASES = {
    "login_url": "login_url",
    "url": "login_url",
    "login": "login_url",
    "login_page": "login_url",
    "登录地址": "login_url",
    "登录页": "login_url",
    "登录页面": "login_url",
    "登录链接": "login_url",
    "url地址": "login_url",
    "username": "username",
    "account": "username",
    "user": "username",
    "name": "username",
    "账号": "username",
    "用户名": "username",
    "email": "email",
    "mail": "email",
    "邮箱": "email",
    "region": "region",
    "country": "region",
    "地区": "region",
    "区域": "region",
    "health": "health",
    "健康度": "health",
    "note": "note",
    "remark": "note",
    "备注": "note",
}

# Cookie 条数上限：正常店铺几十条，几千条八成是粘错了文件
MAX_COOKIES = 500


@dataclass(slots=True)
class ParsedAccount:
    login_url: str
    # 由 login_url 推导，解析阶段就算好，写库时直接用
    platform: str
    username: str
    email: str | None
    region: str
    health: int
    note: str | None

    @property
    def label(self) -> str:
        return f"{self.platform} / {self.username}"


def account_template_csv() -> str:
    """导入模板：带 BOM，Excel 打开中文列名不乱码。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ACCOUNT_TEMPLATE_COLUMNS)
    writer.writerows(ACCOUNT_TEMPLATE_ROWS)
    return "\ufeff" + buffer.getvalue()


# ── Cookie 归一化 ────────────────────────────────────────


def normalize_cookies(raw: Any) -> list[dict[str, Any]] | None:
    """把用户粘的东西统一成 Playwright 的 cookies 数组。

    认两种输入：``storage_state.json`` 整个对象（``{"cookies": [...]}``）
    和裸的 cookies 数组。字符串会先当 JSON 解析——前端文本框传上来的就是串。
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cookie 不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 列）",
            ) from exc

    if isinstance(raw, dict):
        # storage_state 里还有 origins，这里只取 cookies
        raw = raw.get("cookies")
        if raw is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="JSON 对象里没有 cookies 字段",
            )

    if not isinstance(raw, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cookie 需要是数组，或 Playwright storage_state 对象",
        )
    if len(raw) > MAX_COOKIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cookie 条数过多（{len(raw)} > {MAX_COOKIES}）",
        )

    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"第 {index} 条 Cookie 不是对象",
            )
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"第 {index} 条 Cookie 缺少 name",
            )
        # 平台之间字段差异很大（同站、分区、分区键都是额外字段），原样保留，
        # 只把 name / value 规整成字符串，避免前端导出时类型炸掉
        cookie = dict(item)
        cookie["name"] = name
        cookie["value"] = value if isinstance(value, str) else str(value or "")
        result.append(cookie)

    return result or None


def _cookie_payload(cookies: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """审计里只记条数与域名，绝不把 Cookie 值写进日志。"""
    if not cookies:
        return None
    return {
        "count": len(cookies),
        "domains": sorted({str(c.get("domain") or "") for c in cookies})[:10],
    }


# ── 解析导入清单 ──────────────────────────────────────────


def _split(line: str) -> list[str]:
    """按出现的最强分隔符切分。制表符优先：从表格复制出来就是它。"""
    for sep in ("\t", ",", ";", "|"):
        if sep in line:
            return [cell.strip() for cell in line.split(sep)]
    return [line.strip()]


def _looks_like_header(tokens: list[str]) -> bool:
    hits = sum(1 for token in tokens if token.strip().lower() in _HEADER_ALIASES)
    return hits >= 2


def _header_map(tokens: list[str]) -> list[str]:
    return [_HEADER_ALIASES.get(token.strip().lower(), "") for token in tokens]


def _as_health(value: str | None) -> int:
    text = (value or "").strip().rstrip("%")
    if not text:
        return 100
    try:
        number = int(float(text))
    except ValueError as exc:
        raise ValueError(f"健康度「{value}」不是数字") from exc
    return max(0, min(100, number))


def parse_line(line: str, *, header: list[str] | None = None) -> ParsedAccount:
    """把一行文本解析成账号字段。认不出来就抛 ``ValueError``，由调用方记失败行。

    第一列是**登录地址**，平台从它推导。所以「复制一份旧模板（第一列写平台名）」
    会被判成失败行并提示第一列该填什么——这是有意为之：平台不该由人指定。
    """
    if header:
        mapping = dict(zip(header, _split(line), strict=False))
        login_url = (mapping.get("login_url") or "").strip()
        username = (mapping.get("username") or "").strip()
        email = (mapping.get("email") or "").strip() or None
        region = (mapping.get("region") or "").strip()
        health_raw = mapping.get("health")
        note = (mapping.get("note") or "").strip() or None
    else:
        tokens = _split(line)
        if len(tokens) < 2:
            raise ValueError("至少需要两列：登录地址, 账号")
        login_url, username = tokens[0].strip(), tokens[1].strip()
        email = tokens[2].strip() if len(tokens) > 2 and tokens[2].strip() else None
        region = tokens[3].strip() if len(tokens) > 3 else ""
        health_raw = tokens[4] if len(tokens) > 4 else None
        note = tokens[5].strip() if len(tokens) > 5 and tokens[5].strip() else None

    if not login_url:
        raise ValueError("缺少登录地址")
    if not username:
        raise ValueError("缺少账号名")

    try:
        # 平台与规范化的 URL 一起算出来，后面查重、写库都用规范化后的值
        platform, _known = detect_platform(login_url)
        normalized = normalize_login_url(login_url)
    except InvalidLoginUrl as exc:
        raise ValueError(f"登录地址无法识别：{exc}") from exc

    return ParsedAccount(
        login_url=normalized[:512],
        platform=platform[:64],
        username=username[:128],
        email=(email or None) and email[:255],
        region=(region or "")[:64],
        health=_as_health(health_raw),
        note=(note or None) and note[:255],
    )


# ── 写操作 ────────────────────────────────────────────────


def _resolve_status(
    explicit: AccountStatus | None,
    cookies: list[dict[str, Any]] | None,
) -> AccountStatus:
    """没指定状态时按 Cookie 推断：有 Cookie 说明拿得到登录态，否则还没绑定。"""
    if explicit is not None:
        return AccountStatus(explicit)
    return AccountStatus.logged_in if cookies else AccountStatus.unbound


async def create_account(
    session: AsyncSession,
    payload: AccountCreateRequest,
    *,
    operator: str,
    request: Request | None = None,
) -> str:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="账号名不能为空")

    # 平台不接收用户输入：只认登录地址，平台从域名推导
    try:
        platform = detect_platform(payload.login_url)[0]
        login_url = normalize_login_url(payload.login_url)
    except InvalidLoginUrl as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"登录地址无法识别：{exc}"
        ) from exc

    exists = await session.scalar(
        select(Account).where(Account.login_url == login_url, Account.username == username)
    )
    if exists is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"这个登录页下已经有账号「{username}」了",
        )

    cookies = normalize_cookies(payload.cookies)
    account = Account(
        login_url=login_url,
        platform=platform,
        username=username,
        email=(payload.email or "").strip() or None,
        region=(payload.region or "").strip(),
        health=payload.health,
        note=(payload.note or "").strip() or None,
        status=_resolve_status(payload.status, cookies),
        cookies=cookies,
        # 新建的账号从这一刻算起，前端「注册 N 天」才不会显示 0 天
        registered_at=utcnow(),
        last_login_at=utcnow() if cookies else None,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    await audit.record(
        session,
        action=AuditAction.create,
        resource_type=AuditResourceType.account,
        resource_id=account.id,
        resource_name=f"{platform}/{username}",
        operator=operator,
        detail=f"新建账号 {platform}/{username}（{login_url}），Cookie {len(cookies or [])} 条",
        changes={"cookies": _cookie_payload(cookies)} if cookies else None,
        request=request,
    )
    return str(account.id)


async def update_account(
    session: AsyncSession,
    account_id: UUID,
    payload: AccountUpdateRequest,
    *,
    operator: str,
    request: Request | None = None,
) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="账号不存在")

    fields = payload.model_fields_set

    # 换登录页要重新推导平台：否则改完地址，列表里还挂着旧平台
    if "login_url" in fields and payload.login_url is not None:
        try:
            platform = detect_platform(payload.login_url)[0]
            login_url = normalize_login_url(payload.login_url)
        except InvalidLoginUrl as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"登录地址无法识别：{exc}"
            ) from exc
        account.login_url = login_url
        account.platform = platform

    before_cookies = len(account.cookies or [])
    # cookies 传空串 / null 就是把登录态清掉，这是有意的操作，不是「没传」
    if "cookies" in fields:
        cookies = normalize_cookies(payload.cookies)
        account.cookies = cookies
        if "status" not in fields:
            # 清空 Cookie 后还挂着「已登录」会自相矛盾
            account.status = _resolve_status(None, cookies)

    if "username" in fields and payload.username:
        account.username = payload.username.strip()
    if "email" in fields:
        account.email = (payload.email or "").strip() or None
    if "region" in fields:
        account.region = (payload.region or "").strip()
    if "health" in fields and payload.health is not None:
        account.health = payload.health
    if "note" in fields:
        account.note = (payload.note or "").strip() or None
    if "status" in fields and payload.status is not None:
        account.status = AccountStatus(payload.status)

    # 同登录页下不能有两个同名账号。唯一约束会在 commit 时抛 IntegrityError，
    # 这里先查一次给出可读的 409；历史数据 login_url 为空时按 IS NULL 比
    same_url = (
        Account.login_url.is_(None)
        if account.login_url is None
        else Account.login_url == account.login_url
    )
    duplicate = await session.scalar(
        select(Account).where(
            same_url,
            Account.username == account.username,
            Account.id != account.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"这个登录页下已经有账号「{account.username}」了",
        )

    account.updated_at = utcnow()
    await session.commit()

    detail = f"编辑账号 {account.platform}/{account.username}"
    if "login_url" in fields:
        detail += f"，登录地址改为 {account.login_url}"
    if "cookies" in fields:
        detail += f"，Cookie {before_cookies} → {len(account.cookies or [])} 条"
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.account,
        resource_id=account.id,
        resource_name=f"{account.platform}/{account.username}",
        operator=operator,
        detail=detail,
        changes={"cookies": _cookie_payload(account.cookies)} if "cookies" in fields else None,
        request=request,
    )


async def get_detail(session: AsyncSession, account_id: UUID) -> AccountDetail:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return AccountDetail(
        id=str(account.id),
        platform=account.platform,
        login_url=account.login_url,
        username=account.username,
        email=account.email,
        region=account.region,
        health=account.health,
        status=account.status.value,
        note=account.note,
        cookies=account.cookies,
    )


async def import_accounts(
    session: AsyncSession,
    payload: AccountImportRequest,
    *,
    operator: str,
    request: Request | None = None,
) -> AccountImportResult:
    # 查重的键是「登录地址 + 账号名」。历史账号没有登录地址，不放进索引——
    # 拿 NULL 去比对谁都不相等，放进来反而会漏判
    existing = {
        (row.login_url, row.username): row
        for row in await session.scalars(select(Account))
        if row.login_url
    }

    created = updated = skipped = failed = 0
    rows: list[AccountImportRow] = []
    header: list[str] | None = None
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(payload.text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # 表头只认第一行数据之前的那一行，免得数据里正好有个叫「登录地址」的值被吞
        if header is None and not seen:
            tokens = _split(line)
            if _looks_like_header(tokens):
                header = _header_map(tokens)
                continue

        try:
            item = parse_line(line, header=header)
        except ValueError as exc:
            failed += 1
            rows.append(AccountImportRow(line=index, ok=False, label=line[:48], message=str(exc)))
            continue

        key = (item.login_url, item.username)
        if key in seen:
            skipped += 1
            rows.append(
                AccountImportRow(
                    line=index,
                    ok=False,
                    label=item.label,
                    message="本批内重复，已忽略",
                )
            )
            continue
        seen.add(key)

        current = existing.get(key)
        if current is not None:
            if not payload.overwrite:
                skipped += 1
                rows.append(
                    AccountImportRow(
                        line=index,
                        ok=False,
                        label=item.label,
                        message="已存在（勾选「覆盖同登录页账号」可更新）",
                    )
                )
                continue
            # 覆盖只动清单里有的字段，Cookie / 状态 / 绑定关系一律保留：
            # 重新导一份名单不该把已采集的登录态冲掉
            current.email = item.email
            current.region = item.region
            current.health = item.health
            current.note = item.note
            current.updated_at = utcnow()
            updated += 1
            continue

        session.add(
            Account(
                login_url=item.login_url,
                platform=item.platform,
                username=item.username,
                email=item.email,
                region=item.region,
                health=item.health,
                note=item.note,
                status=AccountStatus.unbound,
                registered_at=utcnow(),
            )
        )
        created += 1

    await session.commit()

    await audit.record(
        session,
        action=AuditAction.create if created else AuditAction.update,
        resource_type=AuditResourceType.account,
        operator=operator,
        detail=f"导入账号 {created} 条（更新 {updated}、跳过 {skipped}、失败 {failed}）",
        request=request,
    )
    return AccountImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        failed=failed,
        rows=rows[:50],
    )
