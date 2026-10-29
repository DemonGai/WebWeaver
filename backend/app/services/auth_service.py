"""账号安全服务：图形验证码、邮箱校验、密码强度规则。

演示环境的验证码与"最后发送记录"都放在进程内存里；接真实服务时替换为
Redis（验证码）与邮件队列（发送）。
"""

import re
import secrets
import time

from app.schemas.auth import Captcha, PasswordRule, Workspace

CAPTCHA_TTL = 120
CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RESET_COOLDOWN = 29 * 60 + 12  # 与设计稿 "链接有效期剩余 29:12" 对齐

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# 进程内保存最近一次下发的验证码
_captcha: dict[str, float | str | None] = {"code": None, "at": 0.0}

WORKSPACES = [
    Workspace(id="webweaver-team", name="webweaver-team", members=24),
    Workspace(id="webweaver-lab", name="webweaver-lab", members=8),
    Workspace(id="acme-growth", name="acme-growth", members=16),
]
DEFAULT_WORKSPACE = "webweaver-team"


def issue_captcha() -> Captcha:
    code = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(4))
    _captcha["code"] = code
    _captcha["at"] = time.time()
    return Captcha(code=code, expires_in=CAPTCHA_TTL)


def verify_captcha(text: str) -> bool:
    code = _captcha["code"]
    issued_at = float(_captcha["at"] or 0)
    if not code or time.time() - issued_at > CAPTCHA_TTL:
        return False
    return text.strip().upper() == str(code).upper()


def is_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def password_checks(password: str, email: str, confirm: str) -> list[PasswordRule]:
    local_part = email.split("@")[0].lower()
    tokens = [t for t in re.split(r"[._-]", local_part) if len(t) >= 3]
    lowered = password.lower()

    return [
        PasswordRule(key="length", label="至少 10 位字符", passed=len(password) >= 10),
        PasswordRule(key="digit", label="包含数字", passed=any(c.isdigit() for c in password)),
        PasswordRule(key="upper", label="包含大写字母", passed=any(c.isupper() for c in password)),
        PasswordRule(
            key="special",
            label="包含特殊符号",
            passed=any(not c.isalnum() and not c.isspace() for c in password),
        ),
        PasswordRule(key="lower", label="包含小写字母", passed=any(c.islower() for c in password)),
        PasswordRule(
            key="no_account",
            label="不含账号名",
            passed=bool(password) and not any(t in lowered for t in tokens),
        ),
    ]


def strength_of(checks: list[PasswordRule]) -> int:
    """0-4 段强度：字符类规则（长度/数字/大写/特殊/小写）各占一格。"""
    base = [c for c in checks if c.key != "no_account"]
    passed = sum(1 for c in base if c.passed)
    return 4 if passed == len(base) and all(c.passed for c in checks) else passed


def send_reset_mail(email: str) -> tuple[bool, str, int]:
    """模拟发送重置邮件，返回 (是否成功, 提示语, 有效期秒数)。"""
    if not is_email(email):
        return False, "邮箱格式不正确，请检查后重试", 0
    return True, f"重置邮件已发送至 {email}", RESET_COOLDOWN


def resend(email: str) -> tuple[bool, str, int]:
    if not is_email(email):
        return False, "邮箱格式不正确，无法重发", 0
    return True, "已重新发送，请留意收件箱与垃圾邮件目录", RESET_COOLDOWN


def revoked_sessions() -> int:
    """重置成功后被强制下线的会话数（演示值）。"""
    return 7
