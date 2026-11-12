"""密码哈希与会话令牌。

**密码**用标准库 ``hashlib.scrypt``：内存硬函数，抗 GPU 爆破，且不需要额外依赖
（argon2-cffi 也同样可用，但这里不想为了一件事拉一个需要编译的包）。
存储格式自带参数，日后调参可以把旧哈希平滑升级::

    scrypt$n=16384,r=8,p=1$<salt_b64>$<hash_b64>

**令牌分两种，职责完全不同**：

- *访问令牌*（access）是一段自包含的 JWT（HS256），只活 30 分钟。服务端验签即可
  知道「是谁、属于哪个会话」，不必回表——它被偷走的窗口也就这么长。
- *刷新令牌*（refresh）是 ``secrets.token_urlsafe(32)`` 这样的随机串，活 7 天
  （勾「记住我」30 天），库里存它的 SHA-256 摘要。它只在 ``/auth/refresh``
  一个接口上出现，用来换新的访问令牌。

两者都不落明文：JWT 靠签名防篡改，刷新令牌靠摘要不可逆。JWT 的 HS256 用标准库
手写（约 40 行），不引入 PyJWT——和这里用 ``hashlib.scrypt`` 而不装 argon2 是同一个理由。
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

# scrypt 参数：16 MiB 内存、单线程，单次校验约 30~60ms，登录场景够用
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    """生成带参数的密码哈希串（每次调用都会用新的随机盐）。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
    )
    return f"scrypt$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str | None) -> bool:
    """校验密码；哈希串损坏或为空一律返回 False，不抛异常。

    走 ``hmac.compare_digest`` 做定长比较，避免按字节提前返回泄漏信息。
    """
    if not stored:
        return False

    try:
        scheme, params, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        cfg = dict(item.split("=") for item in params.split(","))
        n, r, p = int(cfg["n"]), int(cfg["r"]), int(cfg["p"])
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, KeyError):
        return False

    actual = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    """会话 / 重置令牌的明文，只在签发时出现一次。"""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """令牌摘要（存库用）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_token(token: str) -> str:
    """日志里用的短标识，不要打出完整令牌。"""
    return f"{token[:6]}…{token[-4:]}" if len(token) > 12 else "***"


# ── 访问令牌：HS256 JWT ────────────────────────────────────────
#
# 只做 JWT 里够用的那一小块：固定 header、payload 是 JSON、签名是
# HMAC-SHA256(base64url(header).base64url(payload))。不做 alg 协商——
# ``alg: none`` 之类的降级攻击正是「按 header 里的算法验签」造成的，
# 这里把算法写死在代码里，header 只作为输出。


class TokenError(Exception):
    """访问令牌不合法：签名错、格式错、过期。**不区分**具体原因给调用方。"""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def encode_access_token(
    *,
    subject: str,
    session_id: str,
    ttl: timedelta,
    secret: str,
    now: datetime | None = None,
) -> tuple[str, datetime, str]:
    """签发访问令牌，返回 ``(令牌, 到期时间, 令牌 id)``。

    载荷里带 ``sid``（会话 id）：服务端据此判断这场登录是否已被踢下线。
    没有它的话，访问令牌在过期前就完全无法撤销了。
    """
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + ttl
    token_id = secrets.token_urlsafe(9)
    payload = {
        "sub": subject,
        "sid": session_id,
        "jti": token_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "access",
    }
    header = _b64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header}.{body}"
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}", expires_at, token_id


def decode_access_token(token: str, *, secret: str) -> dict:
    """校验并解析访问令牌；任何问题统一抛 :class:`TokenError`。

    签名用 ``hmac.compare_digest`` 定长比较，先验签再解 JSON——
    内容在签名通过之前一律不可信。
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("令牌格式不正确")

    header_b64, body_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{body_b64}"
    try:
        expected = hmac.new(
            secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        actual = _b64url_decode(signature_b64)
    except (ValueError, UnicodeEncodeError) as exc:
        raise TokenError("令牌格式不正确") from exc

    if not hmac.compare_digest(actual, expected):
        raise TokenError("签名校验失败")

    try:
        payload = json.loads(_b64url_decode(body_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError("令牌载荷无法解析") from exc

    if not isinstance(payload, dict) or payload.get("typ") != "access":
        raise TokenError("令牌类型不正确")

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(datetime.now(UTC).timestamp()):
        raise TokenError("令牌已过期")

    if not payload.get("sub") or not payload.get("sid"):
        raise TokenError("令牌缺少必要字段")

    return payload
