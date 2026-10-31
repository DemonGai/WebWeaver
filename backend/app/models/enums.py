"""模型层枚举，取值与前端 types/domain.ts 保持一致。"""

from enum import StrEnum


class GroupKind(StrEnum):
    """分组适用的资源类型。"""

    browser = "browser"
    account = "account"
    ip = "ip"


class BrowserStatus(StrEnum):
    queued = "queued"
    running = "running"
    idle = "idle"
    error = "error"
    stopped = "stopped"


class KernelStatus(StrEnum):
    active = "active"
    testing = "testing"
    deprecated = "deprecated"


class KernelChannel(StrEnum):
    stable = "stable"
    beta = "beta"
    nightly = "nightly"


class FingerprintStatus(StrEnum):
    active = "active"
    needs_upgrade = "needs_upgrade"
    expired = "expired"


class PlatformFamily(StrEnum):
    """指纹模板对应的平台族，前端据此挑图标。"""

    windows = "windows"
    macos = "macos"
    linux = "linux"
    android = "android"
    ios = "ios"


class IpStatus(StrEnum):
    available = "available"
    in_use = "in_use"
    failed = "failed"


class IpProtocol(StrEnum):
    http = "http"
    https = "https"
    socks5 = "socks5"


class IpKind(StrEnum):
    residential = "residential"
    datacenter = "datacenter"
    mobile = "mobile"


class AccountStatus(StrEnum):
    logged_in = "logged_in"
    in_session = "in_session"
    restricted = "restricted"
    unbound = "unbound"


class IpBindingMode(StrEnum):
    """浏览器出口 IP 的取值方式。

    ``direct`` 是默认模式：不经过任何代理，直接用本机公网 IP 出网，
    此时浏览器不指向具体的 ``ips`` 记录；``proxy`` 才是绑定一条代理 IP。
    """

    proxy = "proxy"
    direct = "direct"


class FingerprintMode(StrEnum):
    """浏览器指纹的取值方式。

    ``default`` 是默认模式：不套用任何模板，使用浏览器与操作系统原生指纹；
    ``template`` 才是绑定一条 ``fingerprints`` 记录。
    """

    template = "template"
    default = "default"


class BindingAction(StrEnum):
    """绑定日志的动作：只记绑定与解绑，切换 = 一条解绑 + 一条绑定。"""

    bind = "bind"
    unbind = "unbind"


class BindingSource(StrEnum):
    """绑定操作的发起来源，便于审计时区分人工与自动。"""

    manual = "manual"
    api = "api"
    scheduler = "scheduler"
    bulk = "bulk"


class AuditAction(StrEnum):
    """审计动作：资源生命周期 + 绑定 + 会话三类。

    取有限枚举而不是自由字符串，是为了让「按动作筛选」在前端能直接列出来；
    新增动作需要改这里并补一条迁移（VARCHAR + CHECK，改动很小）。
    """

    create = "create"
    update = "update"
    delete = "delete"
    bind = "bind"
    unbind = "unbind"
    start = "start"
    stop = "stop"
    login = "login"
    logout = "logout"
    reset_password = "reset_password"
    export = "export"
    import_ = "import"


class AuditResourceType(StrEnum):
    """被操作的资源类型。

    ``auth`` 指登录、重置密码这类账号安全操作（不对应业务表）；
    ``binding`` 指浏览器与账号 / IP / 指纹的绑定关系，``system`` 指进程内任务；
    ``user`` / ``role`` 是控制台成员与角色（RBAC），与平台账号 ``account`` 无关。
    """

    browser = "browser"
    account = "account"
    ip = "ip"
    fingerprint = "fingerprint"
    kernel = "kernel"
    group = "group"
    binding = "binding"
    auth = "auth"
    user = "user"
    role = "role"
    system = "system"


class AuditResult(StrEnum):
    """操作结果：失败的操作同样要留痕，否则审计只能看到「成功」的假象。"""

    success = "success"
    failure = "failure"


class AuditSource(StrEnum):
    """审计记录里操作的发起渠道。

    前四个值与 ``BindingSource`` 对齐（人工 / 接口 / 调度器 / 批量），
    另外多一个 ``system``：应用启动、健康巡检这类没有外部触发者的内部动作。
    """

    manual = "manual"
    api = "api"
    scheduler = "scheduler"
    bulk = "bulk"
    system = "system"


class UserStatus(StrEnum):
    """控制台成员的状态。"""

    active = "active"
    disabled = "disabled"
    locked = "locked"


class RbacModule(StrEnum):
    """权限点归属的模块，与业务表 / 接口分组大致对应。

    ``audit`` 指审计日志，``user`` / ``role`` 指成员与角色管理本身；
    平台账号（Amazon 等）属于 ``account``，与 ``user`` 不是一回事。
    """

    browser = "browser"
    account = "account"
    ip = "ip"
    fingerprint = "fingerprint"
    kernel = "kernel"
    group = "group"
    audit = "audit"
    user = "user"
    role = "role"


class RbacAction(StrEnum):
    """对模块可执行的动作。权限点 = 模块 + 动作，如 ``browser:read``。"""

    read = "read"
    create = "create"
    update = "update"
    delete = "delete"
    execute = "execute"
    export = "export"
