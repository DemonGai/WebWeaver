# 07 · 接口参考

在线文档（运行时）：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`。
所有业务接口挂在 `settings.api_prefix` 下，默认 `/api`。本文列的是**完整路径**。

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 编码 | JSON（UTF-8）；CSV 模板接口返回 `text/csv` |
| 鉴权 | `wv_at` Cookie（浏览器）或 `Authorization: Bearer <token>`（脚本，优先） |
| 时间 | ISO 8601，服务端存 UTC |
| ID | UUID 字符串 |
| 分页 | `limit` / `offset`，返回 `total` / `limit` / `offset` |
| 错误 | 非 2xx 时 `{"detail": "中文说明"}`；422 的 `detail` 是字段错误数组 |
| 成功信封 | 大多数接口直接返回业务对象；认证接口返回 `{ok, action, message, ...}` |

**写接口需要权限点（因而必须先登录）；读接口目前大多没有鉴权。** 权限点格式
`模块:动作`，见 [04 认证与权限](04-auth-rbac.md#82-权限点35-个)。超级管理员跳过校验。

> ⚠️ **已知安全缺口**：只有 `/api/user/*` 与 `/api/auth/me` 要求登录；浏览器池、账号
> （含 Cookie）、代理（含密码）、指纹、内核、审计、RBAC 的 GET 都能匿名访问。不要把
> 8000 端口直接暴露到公网，细节与修复建议见
> [04 认证](04-auth-rbac.md#84-接口侧的实际用法)。下表的「权限」列中，`登录` 表示
> **路由上挂了 `CurrentUser`**，`匿名` 表示没有挂；未注明 `登录` 的 GET 实际上是匿名可读。

登录失败是 `200 + {ok:false}`，不是 4xx——前端必须判断 `ok`（原因见 04 文档）。

```bash
# 带 Cookie 调试
curl -c /tmp/wv.jar -H 'Content-Type: application/json' \
  -d '{"action":"login","account":"admin","password":"admin"}' \
  http://127.0.0.1:8010/api/auth
curl -b /tmp/wv.jar http://127.0.0.1:8010/api/browsers | python -m json.tool
```

## 2. 健康检查

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 匿名 | 服务状态 + `database.status` / `database.version` |

## 3. 认证 `/api/auth`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth` | 匿名 / 登录 | **统一入口**，`action` 决定分支 |
| POST | `/api/auth/refresh` | 刷新 Cookie | 轮转刷新令牌，换一对新令牌；失败 401 并清 Cookie |
| GET | `/api/auth/session` | 匿名 | 登录状态检测，未登录返回 200 + `authenticated:false` |
| GET | `/api/auth/me` | 登录 | 当前成员、角色、权限点 |
| GET | `/api/auth/workspaces` | 匿名 | 工作区列表（登录页下拉用） |
| GET | `/api/auth/captcha` | 匿名 | 图形验证码（120 秒，进程内存） |

`POST /api/auth` 的 `action`：

| action | 必填字段 | 说明 |
|---|---|---|
| `login` | `account`, `password`；可选 `remember` | 账号可以是用户名或邮箱 |
| `register` | `username`, `email`, `password`；可选 `confirm`, `display_name`, `workspace` | 受 `AUTH_ALLOW_REGISTER` 控制 |
| `logout` | — | 吊销当前会话并清 Cookie |
| `logout_all` | 可选 `keep_current`（默认 true） | 下线其他设备 |
| `change_password` | `current_password`, `password`, `confirm` | 需要登录 |
| `forgot_password` | `email`, `captcha`；可选 `workspace` | 下发一次性重置令牌 |
| `resend_reset` | `email` | 有冷却时间 |
| `reset_password` | `token`, `password`, `confirm`；可选 `email` | 成功后吊销该成员全部会话 |

登录成功响应（令牌只在 Cookie 里，响应体不含明文）：

```json
{
  "ok": true,
  "action": "login",
  "message": "登录成功",
  "authenticated": true,
  "user": {
    "id": "…", "username": "admin", "email": "admin@webweaver.local",
    "display_name": "超级管理员", "status": "active", "is_superuser": true,
    "roles": ["owner"],
    "permissions": ["browser:read", "…"],
    "last_login_at": "2026-11-14T12:58:00Z"
  },
  "access_expires_at": "2026-11-14T13:30:00Z",
  "refresh_expires_at": "2026-11-21T13:00:00Z",
  "absolute_expires_at": "2026-12-14T13:00:00Z",
  "access_ttl": 1800,
  "refresh_ttl": 604800,
  "remember": false,
  "session_id": "…",
  "other_sessions": 0
}
```

## 4. 总览

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/overview?range=7d` | 匿名 | 集群健康分、资源水位、活跃实例、事件、趋势 |

`range` ∈ `24h` / `7d` / `30d`，默认 `7d`。响应结构：

| 字段 | 说明 |
|---|---|
| `cluster` | `total` / `online` / `health` / `updated_seconds` |
| `health_parts[]` | 四个分项：`key` / `label` / `score` / `weight` / `detail` / `tone` |
| `pool_status[]` | 实例状态分布 |
| `cards[]` | 资源水位迷你卡（`title` / `value` / `unit` / `hint` / `progress`） |
| `instances[]` | 活跃实例摘要 |
| `events[]` | 最近审计事件（`tone` / `title` / `detail` / `time` / `tag`） |
| `trend` | `labels` / `series` / `companion` |
| `trend_stats[]` | 趋势统计条 |

健康分权重：实例 45、出口 25、账号 20、指纹 10。负载 / 趋势的实时采集尚未接入，
趋势来自审计活跃度，实例的 `fps` / `latency` 是占位读数。

## 5. 浏览器池

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/browsers` | 匿名 | 统计、实例卡片、实例列表、筛选项 |
| GET | `/api/browsers/options?browser_id=` | 匿名 | 新建/编辑弹窗的候选资源；传 ID 时排除自身占用的账号/IP |
| GET | `/api/browsers/{id}` | 匿名 | 实例详情（编辑回填） |
| POST | `/api/browsers` | `browser:create` | 新建实例 |
| PATCH | `/api/browsers/{id}` | `browser:update` | 编辑 / 绑定；显式 `null` 表示切回直连或默认指纹 |
| POST | `/api/browsers/{id}/duplicate` | `browser:create` | 复制实例（沿用内核与备注，不复制账号/出口/指纹） |
| DELETE | `/api/browsers/{id}` | `browser:delete` | 删除；运行中返回 409；容器删除、卷保留 |
| POST | `/api/browsers/{id}/actions` | `browser:execute` | `{"action":"start"\|"stop"\|"restart"}` |
| POST | `/api/browsers/batch` | `browser:execute` | `{"ids":[…],"action":"start"}`，最多 200 条 |
| GET | `/api/browsers/novnc` | 匿名 | 所有实例的 noVNC 可接管清单 |
| GET | `/api/browsers/{id}/novnc` | 匿名 | 单台实例的 noVNC 入口与原因 |

新建：

```json
{
  "name": "上海-01",
  "group_id": null,
  "kernel_id": "…",
  "kernel_version": null,
  "account_id": null,
  "ip_id": null,
  "fingerprint_id": null,
  "note": "可选"
}
```

- `name`：2–64 字符，支持中文，不能以标点开头；
- `kernel_version` 为空 = 跟随内核当前版本；
- `ip_id` / `fingerprint_id` 为空 = 直连 / 默认指纹。

批量响应：

```json
{"ok": true, "succeeded": 3, "failed": 1,
 "items": [{"id": "…", "name": "…", "ok": false, "message": "容器端口分配失败"}]}
```

noVNC 清单：

```json
{
  "totals": {"total": 8, "ready": 5, "offline": 2, "unsupported": 1, "blocked": 0},
  "instances": [{
    "id": "…", "name": "…", "status": "running", "group": "…",
    "account": "…", "ip": "…", "kernel": "CloakBrowser",
    "kernel_version": "146.0.7680.177.5",
    "image": "demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5",
    "port": 6081,
    "url": "http://127.0.0.1:6081/vnc.html?autoconnect=1&resize=scale",
    "supports_novnc": true, "ready": true,
    "availability": "ready", "reason": null
  }]
}
```

`availability`：`ready` / `stopped` / `unsupported` / `blocked`，含义见
[05 运行时](05-browser-runtime.md#62-四种可接管状态)。

## 6. 平台账号

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/accounts` | 匿名 | 账号池：统计、卡片、账号列表、平台筛选 |
| GET | `/api/accounts/template` | 匿名 | 下载 CSV 模板（带 BOM） |
| GET | `/api/accounts/detect?login_url=` | 匿名 | 从登录地址识别平台；未知域名返回 `known:false` |
| GET | `/api/accounts/{id}` | 匿名 | 详情，含明文 Cookie（仅单条） |
| POST | `/api/accounts` | `account:create` | 新建；平台由 `login_url` 推导 |
| PATCH | `/api/accounts/{id}` | `account:update` | 编辑；`cookies: null` 清空登录态 |
| POST | `/api/accounts/import` | `account:create` | 粘贴多行导入，`overwrite` 控制是否更新已存在 |

新建：

```json
{
  "login_url": "https://sellercentral.amazon.com/ap/signin",
  "username": "shop_us_101",
  "email": "shop_us_101@example.com",
  "region": "美国区",
  "health": 90,
  "note": "主店",
  "cookies": [{"name": "session-id", "value": "…", "domain": ".amazon.com"}]
}
```

导入：

```json
{"text": "https://…/signin,shop_01,shop_01@example.com,美国区,90,备注\n…", "overwrite": false}
```

列序：`login_url, username, email, region, health, note`。表头可省略；中文列名、常见别名
（账号 / 邮箱 / 地区 / 备注等）都能识别。Cookie 可贴 Playwright `storage_state` 整个对象
（`{"cookies": [...]}`），上限 500 条。

## 7. 代理 IP

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/ip-pool` | 匿名 | 代理列表、区域分布、供应商健康、轮换策略占位 |
| GET | `/api/ip-pool/template` | 匿名 | CSV 模板 |
| POST | `/api/ip-pool/import` | `ip:create` | 粘贴导入 |
| POST | `/api/ip-pool/check` | `ip:update` | 逐条 TCP 探测，回写延迟 / 健康度 / 状态 |

导入：

```json
{"text": "104.28.16.74:8000:socks5:user:pass:residential:Luminati:US:California:Los Angeles", "overwrite": false}
```

也接受 `host,port,protocol,username,password,type,supplier,country,region,city` 的 CSV 列序、
`host:port` 简写、`socks5://user:pass@host:port` URL 形式，以及带表头的多行文本。字段缺失时
用 `default_kind` / `default_supplier` 兜底。

> 冒号形式（`host:port:user:pass:…`）的密码里不能再含冒号——那本身就是有歧义的输入。
> 密码含冒号请改用 CSV 或 URL 形式。

检测响应：

```json
{"checked": 12, "ok": 9, "failed": 3,
 "items": [{"id": "…", "ip": "104.28.16.74", "port": 8000,
            "ok": false, "latency_ms": 0, "message": "连接超时"}]}
```

## 8. 指纹

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/fingerprints` | 匿名 | 模板列表、筛选计数、使用实例 |
| GET | `/api/fingerprints/capabilities` | 匿名 | 各内核的能力矩阵（seed 范围、支持字段） |
| GET | `/api/fingerprints/options` | 匿名 | 可下发的实例清单 |
| GET | `/api/fingerprints/{id}` | 匿名 | 详情：下发参数 + 实测人格 + 渲染后的物料 |
| POST | `/api/fingerprints` | `fingerprint:create` | 新建；`seed` 可空，先建后采 |
| PATCH | `/api/fingerprints/{id}` | `fingerprint:update` | 编辑；改 seed 后实测值作废 |
| DELETE | `/api/fingerprints/{id}` | `fingerprint:delete` | 删除 |
| POST | `/api/fingerprints/{id}/probe` | `fingerprint:update` | 起临时容器采集真实人格 |
| POST | `/api/fingerprints/{id}/apply` | `fingerprint:update` | 写入实例容器并重启 |

新建：

```json
{
  "name": "Win11-主力",
  "kernel_id": "…",
  "platform_family": "windows",
  "seed": 42817,
  "platform_version": "10.0.0",
  "brand": "Chrome",
  "brand_version": "146.0.7680.177",
  "hardware_concurrency": 8,
  "timezone": "Asia/Shanghai",
  "language": "zh-CN",
  "accept_lang": "zh-CN,zh",
  "canvas_noise": true,
  "webgl_noise": true,
  "audio_noise": true,
  "webrtc_protected": true
}
```

字段是否生效取决于内核能力：`platform_version` / `brand` / `brand_version` /
`hardware_concurrency` 仅 fingerprint-chromium 支持；ungoogled 不支持任何指纹补丁。
`GET /capabilities` 是唯一权威，前端据此决定表单显隐。

下发：

```json
{"instance_ids": ["…", "…"]}
```

响应逐台给出 `ok` / `message` / `restarted`；环境变量遮蔽指纹文件时该台会被拒绝并说明原因。

## 9. 内核

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/kernels` | 匿名 | 台账 + 本地镜像扫描 → 统计、卡片、`docker_ok` |
| POST | `/api/kernels/rescan` | 匿名 | 重新扫描（只读，不写审计） |
| GET | `/api/kernels/{slug}` | 匿名 | 详情：本地镜像清单 + `browser_engine/<slug>/README.md` |
| POST | `/api/kernels/{slug}/install` | `kernel:update` | 拉取镜像，返回 202 + 任务 |
| GET | `/api/kernels/jobs` | 匿名 | 拉取任务列表（内存态） |
| GET | `/api/kernels/jobs/{job_id}` | 匿名 | 单任务进度；服务重启后 404 |
| GET | `/api/kernels/{id}/instances?stale=&version=` | 匿名 | 迁移候选实例 |
| POST | `/api/kernels/{id}/version` | `kernel:update` | 切换当前版本（只移动指针） |
| POST | `/api/kernels/{id}/migrate` | `kernel:update` | 批量迁移实例版本（不重启容器） |

> 路由顺序：`/kernels/jobs` 必须排在 `/kernels/{slug}` 之前，否则 `jobs` 会被当成 slug。
> 新增固定段路由时注意同样的问题。

拉取：

```json
{"version": "146.0.7680.177.5"}
```

`tag` / `version` / 空 body 三选一；返回：

```json
{"id": "…", "slug": "cloakbrowser", "version": "146.0.7680.177.5",
 "tag": "cloakbrowser-146.0.7680.177.5",
 "image_ref": "demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5",
 "status": "running", "progress": 0.12, "message": "下载中 3/25 层", "started_at": "…"}
```

切换 / 迁移：

```json
{"version": "146.0.7680.177.5"}
{"version": "146.0.7680.177.5", "browser_ids": []}
```

## 10. noVNC 详情（旧）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/novnc/{instance_id}` | 匿名 | 会话详情：状态、账号、出口 IP、指纹、操作日志 |

这是早期的单页接口。新前端用 `/api/browsers/novnc` 与 `/api/browsers/{id}/novnc`，
本接口保留给外部集成。

## 11. 审计

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/audit-logs` | 匿名 | 全量审计，支持筛选与分页 |

查询参数：`action`、`resource_type`、`resource_id`、`operator`、`result`、`since`、`until`、
`limit`（1–200，默认 50）、`offset`。响应 `{items, total, limit, offset}`。

## 12. RBAC

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/rbac/permissions` | 匿名 | 权限点目录（按模块分组） |
| GET | `/api/rbac/roles` | 匿名 | 角色列表（含权限点与成员数） |
| GET | `/api/rbac/users` | 匿名 | 成员列表（含角色，不含密码哈希） |

当前没有角色/成员的写接口；成员与授权由 seed 或直接改库维护。

## 13. 个人中心 `/api/user`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/user/menu` | 登录 | 头像浮层：成员、默认工作区、菜单、在线设备 badge |
| GET | `/api/user/profile` | 登录 | 个人信息 |
| PATCH | `/api/user/profile` | 登录 | 只允许改 `display_name` |
| GET | `/api/user/sessions` | 登录 | 登录设备：有效的在前，标记本机 |
| DELETE | `/api/user/sessions/{id}` | 登录 | 踢掉自己的某个设备；踢当前会话等于退出 |
| GET | `/api/user/security` | 登录 | 安全概览：改密时间、失败次数、在线设备、最近认证事件 |
| GET | `/api/user/audit-logs` | 登录 | 我的操作日志，`operator` 钉死为当前用户 |

## 14. 状态码与前端处理

| 状态码 | 前端行为 |
|---|---|
| 400 / 409 | 直接展示 `detail`（toast 或表单错误） |
| 401 | 先静默续期一次，失败广播 `auth:expired` 并跳登录 |
| 403 | 展示「缺少权限：xxx」，不跳转 |
| 404 | 页面空态或「资源不存在」 |
| 422 | 取 `detail[0].msg` 展示 |
| 503 | 展示「Docker 不可用」等环境提示，不重试 |

## 15. 接口清单核对

当前 OpenAPI 共 51 条路径、60 个操作。改动接口后可用下面的命令核对文档是否漏写：

```bash
cd backend
uv run python - <<'PY'
from app.main import app
for path, ops in sorted(app.openapi()["paths"].items()):
    for method, op in ops.items():
        print(method.upper(), path, op.get("summary", ""))
PY
```
