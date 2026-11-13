"""从登录页地址推导平台。

账号本身不绑平台，绑的是「登录页面」——同一个 Amazon 卖家可能在 .com / .co.jp
开两个店，也可能同一套登录页服务多个站点。所以库里只让用户填 URL，平台是算出来的：

1. 取主机名的**注册域主体**（``sellercentral.amazon.co.uk`` → ``amazon``），
   这样二级后缀（co.uk / com.au / co.jp）和任意子域都不用单独列；
2. 用主体查内置映射，命中就是 Amazon / Shopify / TikTok 这些常见平台；
3. 没收录的域名就把主体首字母大写当平台名（``mysite.example`` → ``Example``），
   而不是塞一个「未知」——筛选标签里按域名分组反而更有用。

这里**不发起任何网络请求**：服务端去访问外部登录页既慢（几十秒的超时），
又会撞上各家的风控和墙，还拿不到可靠结果（登录页多数是 JS 渲染的）。
域名映射是确定性的、可测的，也正是「用户填了 URL 就知道是哪家」这一步需要的。
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

# 常见的二级后缀：包含它们时注册域要多取一段
_MULTI_SUFFIX = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "co.jp",
    "or.jp",
    "com.br",
    "com.mx",
    "com.sg",
    "com.hk",
    "com.tw",
    "co.kr",
    "co.nz",
    "com.tr",
    "com.cn",
    "com.my",
    "co.th",
    "co.id",
    "co.in",
}

# 注册域主体 → 平台名。键都小写，值是要展示的名字
_LABEL_MAP = {
    "amazon": "Amazon",
    "shopify": "Shopify",
    "myshopify": "Shopify",
    "tiktok": "TikTok",
    "facebook": "Meta",
    "fb": "Meta",
    "meta": "Meta",
    "instagram": "Instagram",
    "x": "X",
    "twitter": "X",
    "youtube": "YouTube",
    "shopee": "Shopee",
    "lazada": "Lazada",
    "ebay": "eBay",
    "etsy": "Etsy",
    "walmart": "Walmart",
    "aliexpress": "AliExpress",
    "alibaba": "Alibaba",
    "1688": "1688",
    "taobao": "淘宝",
    "tmall": "天猫",
    "pinduoduo": "拼多多",
    "yangkeduo": "拼多多",
    "temu": "Temu",
    "shein": "SHEIN",
    "wish": "Wish",
}


class InvalidLoginUrl(ValueError):
    """URL 认不出来（没主机名、协议不对），调用方转成 422。"""


def normalize_login_url(raw: str | None) -> str:
    """把用户填的地址补全成可比较的形式。

    - 没写协议按 ``https://`` 处理（粘贴 ``sellercentral.amazon.com`` 很常见）；
    - 主机名转小写，去掉末尾斜杠和 ``#`` 片段；
    - 保留 path 与 query：登录入口常在路径里（``/ap/signin``），
      丢掉的话「同一域名的两个入口」会被当成同一条记录。
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidLoginUrl("登录地址不能为空")
    if "://" not in text:
        # 允许直接粘域名（sellercentral.amazon.com:8443 这种常见），
        # 但纯单词不算网址——「Amazon」是平台名，不是域名（IPv6 字面量除外）
        head = text.split("/")[0]
        if "." not in head and not head.startswith("["):
            raise InvalidLoginUrl("登录地址要是完整网址，例如 https://sellercentral.amazon.com")
        text = "https://" + text

    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise InvalidLoginUrl("只支持 http / https 登录地址")
    host = (parts.hostname or "").strip()
    if not host:
        raise InvalidLoginUrl("登录地址里没有主机名")

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidLoginUrl("登录地址里的端口不合法") from exc

    # hostname 会把 IPv6 的方括号去掉，重建 netloc 时要加回来；
    # 端口也必须带上——内网登录页常用 :8443 这类非标准端口
    netloc = f"[{host.lower()}]" if ":" in host else host.lower()
    if port is not None:
        netloc = f"{netloc}:{port}"

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def registered_label(host: str) -> str:
    """取注册域的主体部分：``sellercentral.amazon.co.uk`` → ``amazon``。"""
    host = (host or "").strip().lower().strip(".")
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_SUFFIX:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def detect_platform(login_url: str | None) -> tuple[str, bool]:
    """返回 ``(平台名, 是否命中内置映射)``。

    URL 不合法时抛 :class:`InvalidLoginUrl`；调用方（接口层）转 422，
    这样「填错了」和「没收录」不会混成一个错误。
    """
    normalized = normalize_login_url(login_url)
    host = urlsplit(normalized).hostname or ""
    label = registered_label(host)
    if not label:
        raise InvalidLoginUrl("登录地址里没有主机名")

    known = _LABEL_MAP.get(label)
    if known:
        return known, True

    # 纯 IP 的登录页（内网 / 自建站）没有注册域可言，直接给个中性名字
    if all(part.isdigit() for part in host.split(".")):
        return "IP 站点", False

    return label[:1].upper() + label[1:], False
