"""认证 Cookie 的读写。

两个令牌都放 httpOnly Cookie：JavaScript 读不到，XSS 就拿不走它们。
这是把令牌从 localStorage 挪过来的全部理由——localStorage 里的东西
任何一个注入脚本都能顺手 `fetch` 出去。

分工：

===========  ==================  ==============  ====================
Cookie       内容                有效期          作用域
===========  ==================  ==============  ====================
``wv_at``    访问令牌（JWT）      30 分钟          ``/api``
``wv_rt``    刷新令牌（随机串）     7 / 30 天       ``/api/auth``
===========  ==================  ==============  ====================

刷新令牌的 ``path`` 收窄到 ``/api/auth``：其他业务接口的请求根本不会带上它，
被日志、反向代理、浏览器扩展看到的概率都更小。

**CSRF**：两个 Cookie 都是 ``SameSite=Lax``，跨站的 POST 表单不会携带它们；
再加上所有写接口都要求 ``Content-Type: application/json``（跨站发这种请求
要先过预检），这套组合足够挡住常见的 CSRF。真要防到最严，得再加 double-submit
令牌，但那要求前端能读到其中一个 Cookie，等于把「JS 读不到令牌」这条好处让出去。
"""

from fastapi import Response

from app.core.config import settings

ACCESS_COOKIE = "wv_at"
REFRESH_COOKIE = "wv_rt"

# 访问令牌给整个 API 用；刷新令牌只在认证接口上出现
ACCESS_PATH = "/api"
REFRESH_PATH = "/api/auth"


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    access_max_age: int,
    refresh_max_age: int,
) -> None:
    """写入两个令牌 Cookie。

    ``max_age`` 与令牌本身的过期时间保持一致：让浏览器和服务端对「什么时候失效」
    有同一个判断，避免出现「Cookie 还在、令牌已经不可用」的中间态。
    """
    common = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=max(0, access_max_age),
        path=ACCESS_PATH,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max(0, refresh_max_age),
        path=REFRESH_PATH,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    """清掉两个 Cookie。路径必须与写入时一致，否则删不掉。"""
    common = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_PATH, **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **common)
    # 兜底：早期版本可能用默认路径写过同名 Cookie，不清掉会一直跟着请求跑
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path="/", **common)
