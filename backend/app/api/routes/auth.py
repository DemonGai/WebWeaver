from fastapi import APIRouter

from app.schemas.auth import (
    Captcha,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResendRequest,
    ResendResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    WorkspaceList,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/workspaces", response_model=WorkspaceList, summary="可选工作区列表")
async def get_workspaces() -> WorkspaceList:
    return WorkspaceList(items=auth_service.WORKSPACES, default_id=auth_service.DEFAULT_WORKSPACE)


@router.get("/captcha", response_model=Captcha, summary="获取图形验证码")
async def get_captcha() -> Captcha:
    return auth_service.issue_captcha()


@router.post("/forgot-password", response_model=ForgotPasswordResponse, summary="发送密码重置邮件")
async def forgot_password(payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
    if not auth_service.is_email(payload.email):
        return ForgotPasswordResponse(
            ok=False,
            email=payload.email,
            expires_in=0,
            cooldown=0,
            message="邮箱格式不正确，请检查后重试",
        )

    if not auth_service.verify_captcha(payload.captcha):
        return ForgotPasswordResponse(
            ok=False,
            email=payload.email,
            expires_in=0,
            cooldown=0,
            message="图形验证码不正确或已过期",
        )

    ok, message, cooldown = auth_service.send_reset_mail(payload.email)
    return ForgotPasswordResponse(
        ok=ok,
        email=payload.email.strip(),
        expires_in=cooldown,
        cooldown=cooldown,
        message=message,
    )


@router.post("/resend-reset", response_model=ResendResponse, summary="重新发送重置邮件")
async def resend_reset(payload: ResendRequest) -> ResendResponse:
    ok, message, cooldown = auth_service.resend(payload.email)
    return ResendResponse(ok=ok, cooldown=cooldown, message=message)


@router.post("/reset-password", response_model=ResetPasswordResponse, summary="校验并提交新密码")
async def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    checks = auth_service.password_checks(payload.password, payload.email, payload.confirm)
    strength = auth_service.strength_of(checks)

    if payload.password != payload.confirm:
        return ResetPasswordResponse(
            ok=False,
            checks=checks,
            strength=strength,
            revoked_sessions=0,
            message="两次输入的密码不一致",
        )

    failed = [c.label for c in checks if not c.passed]
    if failed:
        return ResetPasswordResponse(
            ok=False,
            checks=checks,
            strength=strength,
            revoked_sessions=0,
            message=f"密码未满足：{'、'.join(failed)}",
        )

    return ResetPasswordResponse(
        ok=True,
        checks=checks,
        strength=4,
        revoked_sessions=auth_service.revoked_sessions(),
        message="密码已重置，全部设备需要重新登录",
    )
