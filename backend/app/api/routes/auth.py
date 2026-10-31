"""认证接口：一个写入口 + 三个查询口。

写操作全部收敛到 ``POST /api/auth``，用 ``action`` 区分
``login`` / ``register`` / ``logout`` / ``forgot_password`` / ``resend_reset`` /
``reset_password``。这么做的好处是认证相关的策略（限流、验证码、审计、
令牌签发）只有一处；代价是响应变成一个「超集」信封，见 ``schemas/auth.py``。

保留成独立 GET 的是纯查询：工作区列表、图形验证码、当前登录成员——它们没有副作用，
放进 POST 反而丢了缓存与幂等语义。
"""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, OptionalUser, SessionDep, bearer_token
from app.schemas.auth import (
    AuthAction,
    AuthResponse,
    Captcha,
    ForgotPasswordRequest,
    LoginRequest,
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


@router.post("", response_model=AuthResponse, summary="认证统一入口（按 action 分发）")
async def auth_action(
    payload: AuthAction,
    request: Request,
    session: SessionDep,
) -> AuthResponse:
    """一个入口做六件事。

    ``action`` 决定走哪条分支；请求体按动作校验（判别联合），
    缺字段或字段类型不对由 Pydantic 直接 422，不需要在这里写 if 判空。
    """
    match payload:
        case LoginRequest():
            return await auth_service.login(
                session,
                request=request,
                account=payload.account,
                password=payload.password,
                remember=payload.remember,
            )

        case RegisterRequest():
            return await auth_service.register(
                session,
                request=request,
                username=payload.username,
                email=payload.email,
                password=payload.password,
                confirm=payload.confirm,
                display_name=payload.display_name,
                workspace=payload.workspace,
            )

        case LogoutRequest():
            return await auth_service.logout(session, request=request, token=bearer_token(request))

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
            return await auth_service.reset_password(
                session,
                request=request,
                token=payload.token,
                password=payload.password,
                confirm=payload.confirm,
                email=payload.email,
            )

    # 判别联合已保证进不来，留一句兜底便于将来新增 action 时立刻暴露问题
    return AuthResponse(ok=False, action="unknown", message="不支持的 action")


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
