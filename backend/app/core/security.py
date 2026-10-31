"""密码哈希与会话令牌。

**密码**用标准库 ``hashlib.scrypt``：内存硬函数，抗 GPU 爆破，且不需要额外依赖
（argon2-cffi 也同样可用，但这里不想为了一件事拉一个需要编译的包）。
存储格式自带参数，日后调参可以把旧哈希平滑升级::

    scrypt$n=16384,r=8,p=1$<salt_b64>$<hash_b64>

**令牌**是 ``secrets.token_urlsafe(32)`` 这样的随机串，只在签发那一刻以明文出现，
库里存的是它的 SHA-256 摘要。这样即使库被读走，也拿不到能直接用的 token
（摘要不可逆，且 token 本身是高熵随机值，不需要再加盐/慢哈希）。
"""

import base64
import hashlib
import hmac
import secrets

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
