"""代理管理页的两个写操作：批量导入、连通性检测。

导入这层的重点不是「解析得多聪明」，而是「供应商给的清单能直接粘进来」。
真实场景里拿到的格式五花八门：``socks5://user:pass@host:port``、
``host:port:user:pass``、带表头的 CSV，甚至直接从表格里复制出来的制表符文本。
所以 :func:`parse_line` 按「表头 → URL → CSV 全列 → 位置约定」的顺序试探，
任何一种认得出来就收下；认不出来的行单独报错，不牵连整批。

检测只是端口可达性：TCP 建连成功 + 握手耗时。SOCKS5 认证、目标站点是否
放行这些得靠实例侧真正跑一次请求，这里不做——否则代理密码错的时候，
「检测通过」反而是个更糟的假象。
"""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import unquote, urlsplit

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditResourceType, Ip
from app.models.base import utcnow
from app.models.enums import IpKind, IpProtocol, IpStatus
from app.schemas.domain import (
    IpCheckItem,
    IpCheckResult,
    IpImportRequest,
    IpImportResult,
    IpImportRow,
)
from app.services import audit

# 模板列序：解析器认这一份，前端「下载模板」下的也是这一份，改这里两边同时生效
TEMPLATE_COLUMNS = (
    "ip",
    "port",
    "protocol",
    "username",
    "password",
    "type",
    "supplier",
    "country",
    "region",
    "city",
)

# 示例行故意覆盖三种典型情况：住宅带认证、机房走白名单、密码里有特殊字符
TEMPLATE_ROWS = (
    (
        "104.28.16.74",
        "8000",
        "socks5",
        "brd-customer-hl_us02",
        "uS8nC5mQ",
        "residential",
        "Luminati",
        "US",
        "California",
        "Los Angeles",
    ),
    (
        "45.132.88.19",
        "1080",
        "http",
        "",
        "",
        "datacenter",
        "IPRoyal",
        "DE",
        "Hesse",
        "Frankfurt",
    ),
    (
        "185.199.108.153",
        "3128",
        "https",
        "mobile-01",
        "p@ssw0rd",
        "mobile",
        "Oxylabs",
        "JP",
        "Tokyo",
        "Tokyo",
    ),
)

_PROTOCOL_ALIASES = {
    "http": IpProtocol.http,
    "https": IpProtocol.https,
    "socks5": IpProtocol.socks5,
    "socks5h": IpProtocol.socks5,
    "socks": IpProtocol.socks5,
}

_KIND_ALIASES = {
    "residential": IpKind.residential,
    "住宅": IpKind.residential,
    "datacenter": IpKind.datacenter,
    "机房": IpKind.datacenter,
    "机房代理": IpKind.datacenter,
    "mobile": IpKind.mobile,
    "移动": IpKind.mobile,
    "移动代理": IpKind.mobile,
}

# 表头里允许出现的近义列名，统一映射到模板列
_HEADER_ALIASES = {
    "host": "ip",
    "address": "ip",
    "addr": "ip",
    "代理地址": "ip",
    "ip地址": "ip",
    "端口": "port",
    "协议": "protocol",
    "账号": "username",
    "用户名": "username",
    "user": "username",
    "密码": "password",
    "pass": "password",
    "pwd": "password",
    "类型": "type",
    "kind": "type",
    "供应商": "supplier",
    "vendor": "supplier",
    "国家": "country",
    "country_code": "country",
    "地区": "region",
    "省": "region",
    "城市": "city",
}


def template_csv() -> str:
    """模板 CSV。

    带 UTF-8 BOM：Excel 在中文 Windows 上默认按 GBK 打开，没有 BOM 会把
    「供应商」这类列名显示成乱码，用户会以为模板本身坏了。
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerows(TEMPLATE_ROWS)
    return "\ufeff" + buf.getvalue()


@dataclass(slots=True)
class ParsedIp:
    """一行清单解析出来的代理。字段与 ``Ip`` 表一一对应，缺省值已填好。"""

    address: str
    port: int
    protocol: IpProtocol
    kind: IpKind
    supplier: str
    country: str
    region: str
    city: str
    username: str | None = None
    password: str | None = None

    @property
    def label(self) -> str:
        return f"{self.address}:{self.port}"


def _split(line: str) -> list[str]:
    """按出现的最强分隔符切分。

    顺序有讲究：URL 整条不切（``socks5://u:p@h:port`` 里的冒号属于 URL 语法）；
    制表符优先，因为从 Excel / 网页表格复制出来是制表符分隔，而表格单元格里
    常常又带逗号；逗号比空白优先，是因为密码里可以没有空格，但供应商名里
    经常有空格（``Bright Data``）；最后才退到冒号（``host:port:user:pass``）。

    冒号形式的代价是密码不能再含冒号——那本身就是有歧义的输入，
    文档里引导用户改用 CSV 或 URL 形式。
    """
    if "://" in line:
        return [line]
    for sep in ("\t", ",", ";", "|"):
        if sep in line:
            return [cell.strip() for cell in line.split(sep)]
    if ":" not in line:
        return line.split()

    # [IPv6]:port 里的冒号属于地址本身，整段留住，只切后面的
    if line.startswith("["):
        end = line.find("]")
        if end > 0:
            return [line[: end + 1], *line[end + 1 :].lstrip(":").split(":")]
    return [cell.strip() for cell in line.split(":")]


def _looks_like_header(tokens: list[str]) -> bool:
    lowered = {token.lower() for token in tokens}
    return "ip" in lowered or "address" in lowered or "host" in lowered


def _header_map(tokens: list[str]) -> list[str]:
    """把表头行映射成模板列名；认不出的列保留原名，后面按未知列忽略。"""
    columns: list[str] = []
    for token in tokens:
        name = token.strip().lower()
        columns.append(_HEADER_ALIASES.get(name, name))
    return columns


def _as_kind(value: str | None, fallback: IpKind) -> IpKind:
    if not value:
        return fallback
    return _KIND_ALIASES.get(value.strip().lower(), fallback)


def _as_port(value: str) -> int:
    text = value.strip()
    if not text:
        return 0
    if not text.isdigit():
        raise ValueError(f"端口「{text}」不是数字")
    port = int(text)
    if not 0 <= port <= 65535:
        raise ValueError(f"端口 {port} 超出 0-65535")
    return port


def _clean(value: str | None) -> str | None:
    """空字符串等同于「没填」：CSV 里空单元格很常见，不该存成空账号。"""
    if value is None:
        return None
    text = value.strip()
    return text or None


def parse_line(
    raw: str,
    *,
    default_kind: IpKind,
    default_supplier: str,
    header: list[str] | None = None,
) -> ParsedIp:
    """解析一行清单。格式对不上时抛 ``ValueError``，消息直接给用户看。"""
    text = raw.strip()
    if not text:
        raise ValueError("空行")

    tokens = _split(text)

    # 1) 有表头就按列名取值，列序随便颠倒
    if header:
        cells = dict(zip(header, tokens, strict=False))
        address = _clean(cells.get("ip")) or ""
        return _build(
            address=address,
            port=_as_port(cells.get("port", "")),
            protocol=cells.get("protocol"),
            username=cells.get("username"),
            password=cells.get("password"),
            kind=cells.get("type"),
            supplier=cells.get("supplier"),
            country=cells.get("country"),
            region=cells.get("region"),
            city=cells.get("city"),
            default_kind=default_kind,
            default_supplier=default_supplier,
        )

    # 2) URL 形式：socks5://user:pass@host:port（也接受 http://host:port）
    if "://" in text:
        parts = urlsplit(text)
        try:
            port = parts.port or 0
        except ValueError as exc:  # 端口写成了非数字，urlsplit 会在这里炸
            raise ValueError("URL 里的端口不是数字") from exc
        return _build(
            address=parts.hostname or "",
            port=port,
            protocol=parts.scheme,
            username=unquote(parts.username) if parts.username else None,
            password=unquote(parts.password) if parts.password else None,
            kind=None,
            supplier=None,
            country=None,
            region=None,
            city=None,
            default_kind=default_kind,
            default_supplier=default_supplier,
        )

    # 3) CSV 全列（模板那种 6 列以上），按模板列序硬对
    if len(tokens) >= 6:
        cells = dict(zip(TEMPLATE_COLUMNS, tokens, strict=False))
        return _build(
            address=_clean(cells.get("ip")) or "",
            port=_as_port(cells.get("port", "")),
            protocol=cells.get("protocol"),
            username=cells.get("username"),
            password=cells.get("password"),
            kind=cells.get("type"),
            supplier=cells.get("supplier"),
            country=cells.get("country"),
            region=cells.get("region"),
            city=cells.get("city"),
            default_kind=default_kind,
            default_supplier=default_supplier,
        )

    # 4) 位置约定：host:port[:protocol][:user[:pass]]
    if len(tokens) < 2:
        raise ValueError("至少要写成 地址:端口")

    address = tokens[0]
    port = _as_port(tokens[1])
    rest = tokens[2:]
    protocol: str | None = None
    if rest and rest[0].lower() in _PROTOCOL_ALIASES:
        protocol = rest[0]
        rest = rest[1:]

    return _build(
        address=address,
        port=port,
        protocol=protocol,
        username=rest[0] if len(rest) > 0 else None,
        password=rest[1] if len(rest) > 1 else None,
        kind=rest[2] if len(rest) > 2 else None,
        supplier=rest[3] if len(rest) > 3 else None,
        country=rest[4] if len(rest) > 4 else None,
        region=rest[5] if len(rest) > 5 else None,
        city=rest[6] if len(rest) > 6 else None,
        default_kind=default_kind,
        default_supplier=default_supplier,
    )


def _build(
    *,
    address: str,
    port: int,
    protocol: str | None,
    username: str | None,
    password: str | None,
    kind: str | None,
    supplier: str | None,
    country: str | None,
    region: str | None,
    city: str | None,
    default_kind: IpKind,
    default_supplier: str,
) -> ParsedIp:
    address = _clean(address) or ""
    # [IPv6]:port 的方括号只是「这里到那儿是地址」的定界符，入库要剥掉
    if address.startswith("[") and address.endswith("]"):
        address = address[1:-1]
    if not address:
        raise ValueError("缺少代理地址")
    if " " in address or "/" in address:
        raise ValueError(f"代理地址「{address}」不合法")

    proto = _PROTOCOL_ALIASES.get((protocol or "").strip().lower(), IpProtocol.socks5)
    supplier_name = (_clean(supplier) or default_supplier)[:64]
    user = _clean(username)
    secret = _clean(password)

    return ParsedIp(
        address=address[:45],  # 表里是 VARCHAR(45)，超长域名直接截断而不是整批失败
        port=port,
        protocol=proto,
        kind=_as_kind(kind, default_kind),
        supplier=supplier_name,
        # 清单里常常没有地区：写个「未知」而不是空串，表格里才不会出现空白列
        country=(_clean(country) or "未知")[:8],
        region=(_clean(region) or "")[:64],
        city=(_clean(city) or "")[:64],
        username=user[:64] if user else None,
        password=secret[:128] if secret else None,
    )


def _kind_or_422(value: str) -> IpKind:
    kind = _KIND_ALIASES.get((value or "").strip().lower())
    if kind is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="默认类型只能是 residential / datacenter / mobile",
        )
    return kind


async def import_many(
    session: AsyncSession,
    payload: IpImportRequest,
    *,
    operator: str,
    request: Request | None = None,
) -> IpImportResult:
    """把清单批量写进 ``ips`` 表。

    同一批里重复出现的地址端口只留第一条——供应商的导出文件里
    「同一网关换个账号」很常见，全写进去会让唯一约束直接报错，整批都白导。
    """
    default_kind = _kind_or_422(payload.default_kind)
    default_supplier = payload.default_supplier.strip() or "未标注"

    existing = {(row.address, row.port): row for row in await session.scalars(select(Ip))}

    created = updated = skipped = failed = 0
    rows: list[IpImportRow] = []
    header: list[str] | None = None
    seen: set[tuple[str, int]] = set()

    for index, raw in enumerate(payload.text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # 表头只认第一次出现的，且只在还没有读到任何数据行时认，
        # 否则数据里恰好有个「ip」列的内容会被误当成表头吞掉
        if header is None and not seen:
            tokens = _split(line)
            if _looks_like_header(tokens):
                header = _header_map(tokens)
                continue

        try:
            item = parse_line(
                line,
                default_kind=default_kind,
                default_supplier=default_supplier,
                header=header,
            )
        except ValueError as exc:
            failed += 1
            rows.append(IpImportRow(line=index, ok=False, label=line[:48], message=str(exc)))
            continue

        key = (item.address, item.port)
        if key in seen:
            skipped += 1
            rows.append(
                IpImportRow(
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
                    IpImportRow(
                        line=index,
                        ok=False,
                        label=item.label,
                        message="已存在（勾选「覆盖同地址」可更新）",
                    )
                )
                continue
            current.protocol = item.protocol
            current.kind = item.kind
            current.supplier = item.supplier
            current.username = item.username
            current.password = item.password
            current.country_code = item.country
            current.region = item.region
            current.city = item.city
            current.updated_at = utcnow()
            updated += 1
            continue

        session.add(
            Ip(
                address=item.address,
                port=item.port,
                protocol=item.protocol,
                kind=item.kind,
                supplier=item.supplier,
                country_code=item.country,
                region=item.region,
                city=item.city,
                username=item.username,
                password=item.password,
                # 新导入的还没探测过，先按可用计，等「检测」跑一轮才有真实延迟
                status=IpStatus.available,
                health=100,
            )
        )
        created += 1

    await session.commit()

    # 明细只回前 50 条：导入几千行时把整份错误清单塞进响应没有意义
    await audit.record(
        session,
        action=AuditAction.create if created else AuditAction.update,
        resource_type=AuditResourceType.ip,
        operator=operator,
        detail=f"导入代理 {created} 条（更新 {updated}、跳过 {skipped}、失败 {failed}）",
        request=request,
    )
    return IpImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        failed=failed,
        rows=rows[:50],
    )


async def _tcp_probe(address: str, port: int, timeout: float = 4.0) -> tuple[bool, int, str]:
    """建一次 TCP 连接，返回 (是否可达, 握手毫秒, 说明)。"""
    if port <= 0:
        return False, 0, "未配置端口"

    started = perf_counter()
    writer = None
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(address, port), timeout)
    except TimeoutError:
        return False, 0, f"{int(timeout)} 秒内未响应"
    except OSError as exc:
        return False, 0, exc.strerror or exc.__class__.__name__
    finally:
        if writer is not None:
            writer.close()

    latency = round((perf_counter() - started) * 1000)
    try:
        await asyncio.wait_for(writer.wait_closed(), 1.0)  # type: ignore[union-attr]
    except (TimeoutError, OSError):
        pass
    return True, latency, "端口可达"


async def check_all(
    session: AsyncSession,
    *,
    operator: str,
    request: Request | None = None,
    concurrency: int = 16,
) -> IpCheckResult:
    """对全部代理跑一轮端口探测，回写延迟 / 健康度 / 状态。

    并发上限压在 16：住宅代理一轮几百条，开太大容易被供应商当成扫描；
    而且这里用的是同一台调度机的出口，堆连接只会让延迟数字失真。
    """
    ips = list(await session.scalars(select(Ip).order_by(Ip.address)))
    gate = asyncio.Semaphore(concurrency)

    async def probe(row: Ip) -> IpCheckItem:
        async with gate:
            ok, latency, message = await _tcp_probe(row.address, row.port)
        return IpCheckItem(
            id=str(row.id),
            ip=row.address,
            port=row.port,
            ok=ok,
            latency_ms=latency,
            message=message,
        )

    items = await asyncio.gather(*(probe(row) for row in ips))

    now = utcnow()
    for row, item in zip(ips, items, strict=True):
        row.last_checked_at = now
        if item.ok:
            row.latency_ms = item.latency_ms
            row.health = 100
            # 之前判失败、现在连上了：恢复可用。占用中的不碰，它还被实例绑着
            if row.status is IpStatus.failed:
                row.status = IpStatus.available
        else:
            row.latency_ms = None
            # 一次连不上就判死太激进（住宅代理常有抖动），掉 25 健康度，
            # 掉到一半以下才标失败；成功一次就能立刻回到 100
            row.health = max(row.health - 25, 0)
            if row.status is IpStatus.available and row.health <= 50:
                row.status = IpStatus.failed

    await session.commit()

    ok_count = sum(1 for item in items if item.ok)
    await audit.record(
        session,
        action=AuditAction.update,
        resource_type=AuditResourceType.ip,
        operator=operator,
        detail=f"检测代理 {len(items)} 条（可达 {ok_count}、失败 {len(items) - ok_count}）",
        request=request,
    )
    return IpCheckResult(
        checked=len(items),
        ok=ok_count,
        failed=len(items) - ok_count,
        items=items,
    )
