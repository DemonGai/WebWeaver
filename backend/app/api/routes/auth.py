"""认证接口：一个写入口 + 若干查询口。

写操作全部收敛到 ``POST /api/auth``，用 ``action`` 区分
``login`` / ``register`` / ``logout`` / ``logout_all`` / ``forgot_password`` /
``resend_reset`` / ``reset_password`` / ``change_password``。这么做的好处是
认证相关的策略（限流、验证码、审计、令牌签发）只有一处；代价是响应变成一个
「超集」信封，见 ``schemas/auth.py``。

单独留出来的三个：

- ``POST /auth/refresh``：用刷新令牌换一对新令牌。它不放进统一入口，是因为
  这是**前端在 401 之后自动调用**的，用固定路径比拿 action 拼请求体更直白；
- ``GET /auth/session``：登录态检测。未登录时返回 200 + ``authenticated: false``
  而不是 401——启动时 401 会触发前端的自动续期逻辑，白白多一轮请求；
- ``GET /auth/me`` / ``GET /auth/workspaces`` / ``GET /auth/captcha``：
  纯查询，没有副作用，放进 POST 反而丢了缓存与幂等语义。

**令牌只走 Cookie**：响应体里的 ``access_token`` / ``refresh_token`` 字段
在 Pydantic 侧就标了 ``exclude=True``，序列化时不会出现。浏览器拿不到明文，
脚本也不用自己管理——``curl -c/-b`` 或 requests 的 Session 都会自动带。
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    CurrentUser,
    OptionalUser,
    SessionDep,
    access_token,
    bearer_token,
    refresh_token,
)
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.schemas.auth import (
    AuthAction,
    AuthResponse,
    Captcha,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutAllRequest,
    LogoutRequest,
    MeResponse,
    RegisterRequest,
    ResendResetRequest,
    ResetPasswordRequest,
    WorkspaceList,
)
from app.services import auth_service
from app.services import user as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _write_tokens(response: Response, result: AuthResponse) -> None:
    """把服务层签好的令牌写进 Cookie。

    只有 ``ok`` 且确实签发了令牌时才写；失败分支没有令牌，
    不能拿一个空值去覆盖用户手上还能用的那份。
    """
    if not (result.ok and result.access_token and result.refresh_token):
        return
    set_auth_cookies(
        response,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_max_age=result.access_ttl or 0,
        refresh_max_age=result.refresh_ttl or 0,
    )


@router.post("", response_model=AuthResponse, summary="认证统一入口（按 action 分发）")
async def auth_action(
    payload: AuthAction,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthResponse:
    """一个入口做八件事。

    ``action`` 决定走哪条分支；请求体按动作校验（判别联合），
    缺字段或字段类型不对由 Pydantic 直接 422，不需要在这里写 if 判空。
    """
    match payload:
        case LoginRequest():
            result = await auth_service.login(
                session,
                request=request,
                account=payload.account,
                password=payload.password,
                remember=payload.remember,
            )
            _write_tokens(response, result)
            return result

        case RegisterRequest():
            result = await auth_service.register(
                session,
                request=request,
                username=payload.username,
                email=payload.email,
                password=payload.password,
                confirm=payload.confirm,
                display_name=payload.display_name,
                workspace=payload.workspace,
            )
            _write_tokens(response, result)
            return result

        case LogoutRequest():
            result = await auth_service.logout(
                session,
                request=request,
                access_token=access_token(request) or bearer_token(request),
                refresh_token=refresh_token(request),
            )
            # 无论服务端是否认得这个令牌，本地那份都必须清掉
            clear_auth_cookies(response)
            return result

        case ChangePasswordRequest():
            user, row = await _require_context(session, access_token(request))
            result = await auth_service.change_password(
                session,
                request=request,
                user=user,
                current_session=row,
                current_password=payload.current_password,
                password=payload.password,
                confirm=payload.confirm,
            )
            _write_tokens(response, result)
            return result

        case LogoutAllRequest():
            user, row = await _require_context(session, access_token(request))
            result = await auth_service.logout_everywhere(
                session,
                request=request,
                user=user,
                keep_session_id=row.id if payload.keep_current else None,
            )
            if not payload.keep_current:
                clear_auth_cookies(response)
            return result

        case ForgotPasswordRequest():
            return await auth_service.forgot_password(
                session,
                request=request,
                email=payload.email,
                captcha=payload.captcha,
                workspace=payload.workspace,
            )

        case ResendResetRequest():
            return await auth_service.resend_reset(session, request=request, email=payload.email)

        case ResetPasswordRequest():
            result = await auth_service.reset_password(
                session,
                request=request,
                token=payload.token,
                password=payload.password,
                confirm=payload.confirm,
                email=payload.email,
            )
            # 改完密码所有会话都被吊销了，本地的 Cookie 也该一起清掉
            if result.ok:
                clear_auth_cookies(response)
            return result

    # 判别联合已保证进不来，留一句兜底便于将来新增 action 时立刻暴露问题
    return AuthResponse(ok=False, action="unknown", message="不支持的 action")


async def _require_context(session, token: str | None):
    """从统一入口里做「必须先登录」的动作时，自己解析一次会话。

    这三个动作（改密、全局下线）挂在 POST /api/auth 上而不是独立路由，
    所以用不了 ``CurrentContext`` 依赖——请求体已经被 ``AuthAction`` 占住了。
    """
    resolved = await auth_service.resolve_access(session, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录后再操作",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolved


@router.post("/refresh", response_model=AuthResponse, summary="用刷新令牌换新令牌")
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthResponse | JSONResponse:
    """静默续期。

    浏览器里前端在访问令牌快到期（或已经收到 401）时自动调用，用户无感。
    刷新令牌失效 / 过期 / 检测到重放时返回 401，前端据此把用户请回登录页。
    """
    bundle = await auth_service.rotate_refresh(session, refresh_token(request), request)
    if bundle is None:
        # 这里不能 ``clear_auth_cookies(response)`` 之后 ``raise HTTPException``：
        # 异常会由 FastAPI 新造一个响应对象返回，之前挂在 ``response`` 上的
        # Set-Cookie 全部丢失，浏览器就会一直带着一个已经死掉的刷新令牌。
        # 自己构造 401 响应，才能在同一份响应上既报错又清 Cookie。
        failure = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "登录已过期，请重新登录"},
            headers={"WWW-Authenticate": "Bearer"},
        )
        clear_auth_cookies(failure)
        return failure

    result = AuthResponse(
        ok=True,
        action="refresh",
        message="令牌已续期",
        user=await auth_service.profile_of(session, bundle.user),
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        access_expires_at=bundle.access_expires_at,
        refresh_expires_at=bundle.refresh_expires_at,
        absolute_expires_at=bundle.absolute_expires_at,
        access_ttl=bundle.access_ttl_seconds,
        refresh_ttl=bundle.refresh_ttl_seconds,
        remember=bundle.remember,
    )
    _write_tokens(response, result)
    return result


@router.get("/session", response_model=AuthResponse, summary="登录状态检测")
async def session_state(request: Request, session: SessionDep) -> AuthResponse:
    """前端的「我现在登录着吗、还剩多久」。

    未登录是 200 + ``authenticated: false``，不是 401：这个接口在每次
    打开页面时都会被调用，返回 401 会让统一拦截器以为「令牌坏了」而去续期。
    """
    resolved = await auth_service.resolve_access(session, access_token(request))
    if resolved is None:
        return AuthResponse(
            ok=True,
            action="session",
            message="未登录",
            authenticated=False,
        )

    user, row = resolved
    return await auth_service.session_state(
        session,
        user,
        row,
        access_expires_at=auth_service.access_expiry_of(access_token(request)),
    )


@router.get("/me", response_model=MeResponse, summary="当前登录成员与权限")
async def me(user: CurrentUser, session: SessionDep) -> MeResponse:
    profile = await auth_service.profile_of(session, user)
    return MeResponse(
        ok=True,
        message="已登录",
        user=profile,
    )


@router.get("/workspaces", response_model=WorkspaceList, summary="可选工作区列表")
async def get_workspaces(user: OptionalUser, session: SessionDep) -> WorkspaceList:
    """工作区来自数据库；登录时 ``default_id`` 是本人的默认工作区。"""
    return await user_service.list_workspaces(session, user)


@router.get("/captcha", response_model=Captcha, summary="获取图形验证码")
async def get_captcha() -> Captcha:
    return auth_service.issue_captcha()
