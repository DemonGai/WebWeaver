"""账号安全相关模型：找回密码 → 邮件已发送 → 重置密码。"""

from pydantic import BaseModel, Field


class Workspace(BaseModel):
    id: str
    name: str
    members: int


class WorkspaceList(BaseModel):
    items: list[Workspace]
    default_id: str


class Captcha(BaseModel):
    """图形验证码；前端直接渲染 code 字形（加旋转/干扰线）。"""

    code: str
    expires_in: int = 120


class ForgotPasswordRequest(BaseModel):
    workspace: str = Field(min_length=1, description="工作区 id")
    email: str = Field(min_length=3, description="登录邮箱")
    captcha: str = Field(min_length=1, description="用户填写的图形验证码")


class ForgotPasswordResponse(BaseModel):
    ok: bool
    email: str
    expires_in: int
    cooldown: int
    message: str


class ResendRequest(BaseModel):
    email: str = Field(min_length=3)


class ResendResponse(BaseModel):
    ok: bool
    cooldown: int
    message: str


class PasswordRule(BaseModel):
    key: str
    label: str
    passed: bool


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=1)
    confirm: str = Field(min_length=1)
    email: str = "lin.zhiyuan@webweaver.io"


class ResetPasswordResponse(BaseModel):
    ok: bool
    checks: list[PasswordRule]
    strength: int
    revoked_sessions: int
    message: str
