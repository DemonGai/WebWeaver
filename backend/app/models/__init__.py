"""数据库表模型。

导入顺序即建表依赖顺序：被引用的表先导入，SQLModel.metadata 才能正确排序外键。
新增表时：写模块 -> 在此导出 -> 若需要自动建表，无需额外注册。
"""

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.auth import AuthSession, PasswordResetToken
from app.models.base import IdMixin, TimestampMixin, utcnow
from app.models.binding import (
    BrowserAccountBinding,
    BrowserFingerprintBinding,
    BrowserIpBinding,
)
from app.models.browser import Browser
from app.models.enums import (
    AccountStatus,
    AuditAction,
    AuditResourceType,
    AuditResult,
    AuditSource,
    BindingAction,
    BindingSource,
    BrowserStatus,
    FingerprintMode,
    FingerprintStatus,
    GroupKind,
    IpBindingMode,
    IpKind,
    IpProtocol,
    IpStatus,
    KernelChannel,
    KernelStatus,
    PlatformFamily,
    RbacAction,
    RbacModule,
    UserStatus,
)
from app.models.fingerprint import Fingerprint
from app.models.group import Group
from app.models.ip import Ip
from app.models.kernel import Kernel
from app.models.rbac import Permission, Role, RolePermission, User, UserRole
from app.models.workspace import Workspace

__all__ = [
    # 表
    "Browser",
    "Account",
    "AuditLog",
    "AuthSession",
    "BrowserAccountBinding",
    "BrowserFingerprintBinding",
    "BrowserIpBinding",
    "Fingerprint",
    "Group",
    "Ip",
    "Kernel",
    "PasswordResetToken",
    "Permission",
    "Role",
    "RolePermission",
    "User",
    "UserRole",
    "Workspace",
    # 公共
    "IdMixin",
    "TimestampMixin",
    "utcnow",
    # 枚举
    "AccountStatus",
    "AuditAction",
    "AuditResourceType",
    "AuditResult",
    "AuditSource",
    "BindingAction",
    "BindingSource",
    "BrowserStatus",
    "FingerprintMode",
    "FingerprintStatus",
    "GroupKind",
    "IpBindingMode",
    "IpKind",
    "IpProtocol",
    "IpStatus",
    "KernelChannel",
    "KernelStatus",
    "PlatformFamily",
    "RbacAction",
    "RbacModule",
    "UserStatus",
]
