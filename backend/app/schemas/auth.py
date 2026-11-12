"""认证相关的请求 / 响应模型。

所有会改变安全状态的动作都走同一个入口 ``POST /api/auth``，用 ``action`` 区分：
``login`` / ``register`` / ``logout`` / ``forgot_password`` / ``resend_reset`` /
``reset_password``。

请求用**判别联合**（``discriminator="action"``）而不是一个大而全的模型：
每个动作只声明自己需要的字段，校验规则、必填项、报错文案都各自独立，
OpenAPI 里也能看到六个独立的 schema，前端写错字段会被 422 直接拦住。

代价在响应侧：单入口只能给一个「超集」信封 ``AuthResponse``，
所以登录之外的字段都是可选。这是这个设计明码标价的成本。
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ── 查询类（GET 接口，不属于「动作」） ───────────────────────────


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


class PasswordRule(BaseModel):
    key: str
    label: str
    passed: bool


class AuthUser(BaseModel):
    """当前登录成员；权限点一并返回，前端据此决定按钮显隐。"""

    id: UUID
    username: str
    email: str
    display_name: str
    status: str
    is_superuser: bool
    roles: list[str]
    permissions: list[str]
    last_login_at: datetime | None = None


# ── 动作请求 ──────────────────────────────────────────────────


class LoginRequest(BaseModel):
    action: Literal["login"]
    account: str = Field(min_length=1, max_length=255, description="用户名或邮箱")
    password: str = Field(min_length=1, max_length=128)
    remember: bool = Field(default=False, description="记住我：token 有效期延长到 30 天")


class RegisterRequest(BaseModel):
    action: Literal["register"]
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # 允许不传 confirm：内部调用（脚本建号）没必要重复一次密码
    confirm: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    workspace: str | None = Field(default=None, description="工作区 id，仅用于审计")


class LogoutRequest(BaseModel):
    action: Literal["logout"]


class ForgotPasswordRequest(BaseModel):
    action: Literal["forgot_password"]
    email: str = Field(min_length=3, max_length=255)
    captcha: str = Field(min_length=1, description="用户填写的图形验证码")
    workspace: str | None = Field(default=None, description="工作区 id，仅用于审计")


class ResendResetRequest(BaseModel):
    action: Literal["resend_reset"]
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(BaseModel):
    action: Literal["reset_password"]
    token: str = Field(min_length=8, description="邮件里带的一次性重置令牌")
    password: str = Field(min_length=1, max_length=128)
    confirm: str = Field(min_length=1, max_length=128)
    # 只用于「密码里不能含账号名」这条规则的对照，服务端仍以令牌对应的成员为准
    email: str | None = Field(default=None, max_length=255)


class ChangePasswordRequest(BaseModel):
    """已登录改密码：必须给出原密码。"""

    action: Literal["change_password"]
    current_password: str = Field(min_length=1, max_length=128, description="当前密码")
    password: str = Field(min_length=1, max_length=128, description="新密码")
    confirm: str = Field(min_length=1, max_length=128)


class LogoutAllRequest(BaseModel):
    """下线所有其他设备；当前这台是否保留由 `keep_current` 决定。"""

    action: Literal["logout_all"]
    keep_current: bool = Field(default=True, description="是否保留当前设备的登录")


AuthAction = Annotated[
    LoginRequest
    | RegisterRequest
    | LogoutRequest
    | ForgotPasswordRequest
    | ResendResetRequest
    | ResetPasswordRequest
    | ChangePasswordRequest
    | LogoutAllRequest,
    Field(discriminator="action"),
]


# ── 统一响应 ──────────────────────────────────────────────────


class AuthResponse(BaseModel):
    """单入口的响应信封：``ok`` + ``message`` 是所有动作都有的两件事。

    其余字段按动作可选出现——登录/注册带 ``user`` 与各到期时间，
    找回密码带 ``email``/``cooldown``，重置换密码带 ``checks``/``strength``/
    ``revoked_sessions``。前端只读自己关心的那几个即可。

    **令牌明文始终不出现在 HTTP 响应体里**（路由层的 ``response_model_exclude``
    会把它们剔掉），只通过 httpOnly Cookie 下发。字段留在这里是为了在
    「服务层 → 路由层」之间传值：路由层拿到后写 Cookie，然后丢弃。
    """

    ok: bool
    action: str
    message: str

    # 登录状态检测：登录相关动作为 None，`/auth/session` 明确给出是/否
    authenticated: bool | None = None

    # 登录 / 注册 / me / session
    user: AuthUser | None = None

    # 令牌（仅内部传递，响应体里会被排除）
    access_token: str | None = Field(default=None, exclude=True)
    refresh_token: str | None = Field(default=None, exclude=True)

    # 令牌时长：前端据此安排静默续期与倒计时
    access_expires_at: datetime | None = None
    refresh_expires_at: datetime | None = None
    absolute_expires_at: datetime | None = None
    access_ttl: int | None = None
    refresh_ttl: int | None = None
    absolute_ttl: int | None = None
    remember: bool | None = None

    # 会话状态
    session_id: str | None = None
    signed_in_at: datetime | None = None
    last_seen_at: datetime | None = None
    other_sessions: int | None = None

    # 找回密码
    email: str | None = None
    cooldown: int | None = None
    expires_in: int | None = None
    # 仅当 AUTH_EXPOSE_RESET_TOKEN=true（本地联调）时返回，方便不走邮件点通流程
    reset_token: str | None = None

    # 重置 / 修改密码
    checks: list[PasswordRule] | None = None
    strength: int | None = None
    revoked_sessions: int | None = None


class MeResponse(AuthResponse):
    """``GET /api/auth/me`` 的返回：ok 恒为 true，user 必填。"""

    action: str = "me"
    user: AuthUser
