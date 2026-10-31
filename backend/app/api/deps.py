"""接口层公共依赖：把 ``Authorization: Bearer <token>`` 解析成当前成员。

为什么要依赖而不是中间件：不是每个接口都需要登录（健康检查、验证码、
找回密码都要匿名可访问），中间件会对所有请求都做一次数据库查询。
用依赖则只有声明了 ``CurrentUser`` 的路由才付这个成本。

解析成功后顺手把 ``user_id`` 写到 ``request.state``，方便日志与审计补链路字段。
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import AuthSession, User
from app.services import auth_service, rbac

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def bearer_token(request: Request) -> str | None:
    """取 Bearer 令牌；没带或格式不对返回 ``None``。"""
    header = request.headers.get("Authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


async def get_current_context(request: Request, session: SessionDep) -> tuple[User, AuthSession]:
    """要求登录，并把手上的会话行一起交出去。

    「登录设备管理」要标出「当前这台」，只有成员对象是不够的：
    得知道这次请求用的是哪一行 ``auth_sessions``。解析逻辑与鉴权完全一致，
    所以让 ``get_current_user`` 也挂在这个依赖上（FastAPI 按依赖缓存，
    同一请求里只会查一次库）。
    """
    resolved = await auth_service.resolve_session(session, bearer_token(request))
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, row = resolved
    request.state.user_id = user.id
    request.state.username = user.username
    await auth_service.touch_session(session, row)
    return user, row


async def get_current_user(
    context: Annotated[tuple[User, AuthSession], Depends(get_current_context)],
) -> User:
    """只要成员对象时的便捷依赖。"""
    return context[0]


async def get_optional_user(request: Request, session: SessionDep) -> User | None:
    """可选登录：用于「登录后展示更多」但不强制登录的接口。"""
    resolved = await auth_service.resolve_session(session, bearer_token(request))
    if resolved is None:
        return None
    user, _ = resolved
    request.state.user_id = user.id
    request.state.username = user.username
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentContext = Annotated[tuple[User, AuthSession], Depends(get_current_context)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_permission(code: str):
    """依赖工厂：先要求登录，再校验权限点。

    超级管理员直接放行（只用于初始化与应急）；其余走角色并集。
    错误信息带上缺失的权限编码，前端和排查都省事。
    """

    async def checker(user: CurrentUser, session: SessionDep) -> None:
        if user.is_superuser:
            return
        if not await rbac.has_permission(session, user.id, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限：{code}")

    return checker
