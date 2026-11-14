# WebWeaver · 浏览器集群控制台

前后端分离的浏览器集群管理控制台。前端 **React + Vite + TypeScript + Tailwind CSS v4**（包管理用 **bun**），后端 **Python 3.12+ / FastAPI**（包管理用 **uv**），数据库 **PostgreSQL 18**（Docker 部署）。

页面按 Calicat 设计稿还原（设计文件 `2115610777576079360`），共 10 个页面：控制台 5 页 + 指纹库列表 + 内核管理 + 账号安全 3 页。导航为 6 项（总览 / 浏览器池 / 账号池 / IP 池 / 指纹库 / 内核管理）。

## 目录结构

```
WebWeaver/
├── Dockerfile                    # 一体化镜像：PostgreSQL + FastAPI + 前端页面
├── docker-compose.yml            # 一体化部署（服务名 webweaver）；dev profile 里是独立 PostgreSQL
├── frontend/                     # 前端工程（bun 管理）
│   ├── index.html
│   ├── package.json
│   ├── bun.lock
│   ├── vite.config.ts            # /api -> 后端 开发代理
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx              # 入口 + BrowserRouter
│       ├── App.tsx               # 路由表
│       ├── index.css             # Tailwind + 设计令牌（取自设计稿实测色值）
│       ├── api/
│       │   ├── client.ts         # fetch 封装：错误处理、token 注入
│       │   └── endpoints.ts      # 接口定义
│       ├── components/
│       │   ├── Layout.tsx        # Header / PageHeader / PageShell
│       │   ├── Brand.tsx         # 品牌标识（Header 与账号安全页共用）
│       │   ├── AuthShell.tsx     # 账号安全页外壳：居中卡片 + 品牌区
│       │   ├── fields.tsx        # Field / IconInput / SelectField / CaptchaBox
│       │   ├── ui.tsx            # Card / StatCard / HeroCard / PillTabs / AreaChart …
│       │   └── icons.tsx         # 内联 SVG 图标集
│       ├── hooks/useApi.ts       # 数据请求 hook
│       ├── pages/                # 控制台 5 页 + 指纹库 + auth/ 四页 + 账号中心四页（个人 / 安全 / 设备 / 日志） + 404
│       └── types/domain.ts       # 与后端 schema 对应的类型
└── backend/                      # 后端工程（uv 管理）
    ├── pyproject.toml            # 依赖 + 清华源 + ruff/pytest 配置
    ├── uv.lock
    ├── .env.example
    ├── alembic.ini               # 迁移配置（连接串由 env.py 注入，此处留空）
    ├── alembic/
    │   ├── env.py                # 异步迁移环境：settings.database_url + SQLModel.metadata
    │   └── versions/             # 迁移脚本（按时间前缀命名）
    ├── app/
    │   ├── main.py               # 应用工厂 + CORS + 路由挂载 + lifespan（启动探测数据库）
    │   ├── core/config.py        # pydantic-settings 配置
    │   ├── core/db.py            # SQLAlchemy 异步引擎 / 会话工厂 / 连通性探测
    │   ├── core/logging_config.py # loguru 日志（控制台 + 滚动文件 + ELK JSON + request_id）
    │   ├── core/middleware.py    # 请求日志中间件（request_id / 耗时 / X-Request-ID）
    │   ├── api/router.py         # 路由汇总
    │   ├── api/routes/           # health / overview / browsers / accounts / ip_pool / novnc / fingerprints / kernels / account
    │   ├── models/               # SQLModel 表模型（6 张表，UUID 主键）
    │   │   ├── base.py           # IdMixin / TimestampMixin / enum_type
    │   │   ├── enums.py          # 与前端对齐的枚举
    │   │   └── group / kernel / fingerprint / ip / account / browser
    │   ├── schemas/domain.py     # Pydantic 模型
    │   └── services/
    │       ├── cluster.py        # 真实查询层：6 张表 → 各页面 payload
    │       ├── seed.py           # 演示种子数据（幂等，支持 --reset）
    │       └── kernel_*.py       # 内核：scan（磁盘扫描）/ pool（payload·切版本·迁移·详情）
    │                             #       profile（读 engine.json）/ install（pip·archive·manual 获取任务）
    ├── browser_engine/<slug>/    # 内核落盘目录：engine.json（档案）+ README.md（详情页正文）
    │                             # + <版本>/meta.json（完工标记，二进制不入库）
    ├── bin/aria2c.exe            # 大包多连接下载器（scripts/get-aria2.sh 拉取，不入库）
    └── tests/                    # conftest.py（种子夹具） / test_api.py（接口） / test_models.py（表结构）
```

## 启动

### 0. 一体化部署（数据库 + 后端 + 页面在同一个容器里）

```bash
docker compose up -d --build                 # 首次构建约 5~10 分钟（装 PostgreSQL 与 Python 依赖）
docker compose logs -f webweaver             # 看到 “Uvicorn running on http://0.0.0.0:8000” 即就绪
```

打开 http://127.0.0.1:8000 ，用 `admin / admin` 登录（首启自动建库、跑迁移、写超管）。

- **一个容器三件事**：PostgreSQL（只监听容器内 127.0.0.1）、uvicorn（同时托管前端 dist）、docker CLI。
- **浏览器实例是兄弟容器**：`/var/run/docker.sock` 挂进容器，页面里的启动 / 停止 / 重启 / 删除
  都作用在宿主机 Docker 上，`docker ps` 里直接能看到 `wv-*` 与实例 ID 命名的容器。
- **端口**：`APP_PORT`（默认 8000）是控制台端口；实例的 noVNC 端口仍发布在宿主机 6080+，
  页面里的画面地址跟随访问控制台时的 host，也可用 `NOVNC_HOST` 显式指定。
- **配置**：`AUTH_JWT_SECRET` 生产必须改；`DB_PASSWORD` 可改；改了 `DB_PASSWORD` 后重建容器即可生效。
- **数据**：命名卷 `webweaver-appdata`，`docker compose down` 不删数据，`down -v` 才会。

### 1. 数据库（仅本机开发需要，PostgreSQL 18，端口 5432）

```bash
docker compose --profile dev up -d postgres   # 首次会拉取 postgres:18 并创建 webweaver-pgdata-dev 卷
docker compose ps                             # 期望状态：Up (healthy)
```

- 连接串：`postgresql://webweaver:webweaver@127.0.0.1:5432/webweaver`
- 数据持久化在命名卷 `webweaver-pgdata-dev`；`docker compose down -v` 会连同数据一起删除。
- 本机若 `docker compose` 不可用，可直接用 `docker-compose.exe up -d`（compose v2 独立版）。

### 2. 后端（端口 8010）

> 开发期端口用 8010，与一体化部署占用的 8000 错开，两个进程可以同时跑。

```bash
cd backend
cp .env.example .env                     # 首次：按需改 DATABASE_URL
uv sync                                  # 首次：创建 .venv 并安装依赖
uv run alembic upgrade head              # 首次 / 拉取新迁移后：建表或升级表结构
uv run python -m app.services.seed       # 首次：写工作区 / 权限 / 角色 / 超管（幂等）
uv run uvicorn app.main:app --reload --port 8010
```

启动日志出现 `PostgreSQL 已连接（server_version=18.3）` 与 `表结构由 Alembic 管理，当前版本 <rev>` 即表示数据库可用；连不上时服务照常启动，仅打印 warning。已装依赖：`sqlalchemy[asyncio]` + `asyncpg` + `sqlmodel` + `alembic`。

- 接口文档（Swagger UI）：http://127.0.0.1:8010/docs
- 备用文档（ReDoc）：http://127.0.0.1:8010/redoc
- OpenAPI 描述：http://127.0.0.1:8010/openapi.json
- 新增依赖：`uv add <pkg>`；同步环境：`uv sync`

### 3. 前端（端口 5173）

```bash
cd frontend
bun install
bun run dev
```

打开 http://localhost:5173

其他脚本：`bun run build`（生产构建）、`bun run typecheck`（类型检查）。

### 后端测试

```bash
cd backend
uv run pytest
```

数据类用例（`test_api.py` 里涉及总览 / 浏览器池 / 账号 / IP / 指纹 / noVNC 的）依赖数据库，`tests/conftest.py` 的 `seeded_database` 夹具会幂等地写入种子数据；数据库连不上时这些用例自动 skip，认证与内核用例照常运行。

测试里通过 `DB_POOL_DISABLED=true` 关掉连接池：`TestClient` 不进入上下文管理器时每个请求都会新建事件循环，池化的 asyncpg 连接跨循环会直接抛 `Event loop is closed`。生产/开发进程不受影响（默认开启池化）。

## 数据模型

`backend/app/models/` 使用 **SQLModel**，共 18 张表（6 张业务表 + 3 张绑定日志 + 审计日志 + 5 张 RBAC + 2 张认证凭证 + 工作区）。主键统一是 **UUID**（`uuid4`，应用侧生成），**不用自增 ID**：多实例部署不撞号、不暴露数据量、写库前就能把 ID 交出去。

| 表 | 模型 | 说明 | 主要关联 |
|---|---|---|---|
| `groups` | `Group` | 分组（北美店铺 / 日本社媒…），支持二级 | `parent_id` → groups |
| `kernels` | `Kernel` | 内核引擎及版本、主力标记、通过率 | — |
| `fingerprints` | `Fingerprint` | 指纹模板（UA / 时区 / 分辨率 / 噪声开关 / 唯一性） | `kernel_id` → kernels |
| `ips` | `Ip` | 出口代理（协议、地区、供应商、健康度、到期） | — |
| `accounts` | `Account` | 平台账号（密码加密存储、健康度、注册/登录时间） | `group_id` → groups |
| `browsers` | `Browser` | 实例：内核 + 指纹 + IP + 账号的组合，含 noVNC/CDP 运行时信息 | `group_id` / `kernel_id` / `fingerprint_id` / `ip_id` / `account_id` |
| `browser_account_bindings` | `BrowserAccountBinding` | 账号绑定**操作日志**：谁、何时、把哪个账号绑到 / 解绑自哪个实例 | `browser_id` / `account_id` |
| `browser_ip_bindings` | `BrowserIpBinding` | IP 绑定**操作日志**：代理绑定、直连切换的完整流水 | `browser_id` / `ip_id` |
| `browser_fingerprint_bindings` | `BrowserFingerprintBinding` | 指纹绑定**操作日志**：套模板与回到默认模式的流水 | `browser_id` / `fingerprint_id` |

约定：

- 公共字段由 `IdMixin`（UUID 主键）与 `TimestampMixin`（`created_at` / `updated_at`，`timestamptz`，DB 默认 `now()`，更新时自动刷新）提供。
- 枚举落库为 `VARCHAR(16) + CHECK` 约束，不用 PostgreSQL 原生 enum（加值不必 `ALTER TYPE`），回读自动转回枚举成员。
- 外键列一律带索引；`browsers` 上的关联均可为空，实例可以先建再逐个绑定。
- 唯一约束：`groups(code)`、`groups(kind, name)`、`kernels(name)`、`fingerprints(code)`、`ips(address, port)`、`accounts(platform, username)`、`browsers(name)`。
- 敏感字段只存密文：`ips.password_encrypted`、`accounts.password_encrypted`。
- **表与字段都有中文注释**：注释写在模型的 `__table_args__`（表级）与 `sa_column_kwargs={"comment": ...}`（字段级），迁移后落成数据库的 `COMMENT ON`。psql 里 `\d+ browsers` 的 `Description` 列即可看到；`tests/test_models.py` 会校验每张表、每一列都不缺注释。
- 表结构由 **Alembic** 迁移管理（`DB_AUTO_CREATE` 默认 `false`）。想临时起个空库可以把 `DB_AUTO_CREATE` 设为 `true`，启动时按模型建表并跳过已存在的表。

### 绑定日志与默认模式

`browsers` 上的 `account_id` / `ip_id` / `fingerprint_id` 是**当前生效值**；三张 `*_bindings` 是**操作日志**，只追加、不修改（没有 `updated_at`）。一次「换 IP」就是一条 `unbind` + 一条 `bind`，历史不会被覆盖。日志列：`action`（bind / unbind）、`operator`、`source`（manual / api / scheduler / bulk）、`note`、`created_at`。

IP 与指纹都允许「不指向具体资源」的默认取值，这两种是正常状态，**不是未绑定**：

| 模式 | 含义 | 资源字段 |
|---|---|---|
| `ip_mode = direct` | 直连，直接用本机公网 IP 出网（默认） | `ip_id` 为空，日志的 `resolved_address` 记录当时的本机 IP |
| `ip_mode = proxy` | 绑定一条代理 IP | `ip_id` 必填 |
| `fingerprint_mode = default` | 默认模式，用浏览器与系统原生指纹（默认） | `fingerprint_id` 为空 |
| `fingerprint_mode = template` | 套用一条指纹模板 | `fingerprint_id` 必填 |

对应关系由数据库的 CHECK 约束保证（`ck_browsers_ip_mode_target` 等），`mode` 与资源 ID 不可能错配；前端展示时直连显示「直连 · 本机 IP」，默认指纹显示「默认指纹」，与「未分配 / 未绑定」区分开。

### 查询层与演示数据

`services/cluster.py` 是唯一的数据出口：

- `load_snapshot(session)` 一次读 6 张表（几百行量级），顺带建好 `browser_by_account` / `browser_by_ip` / `browsers_by_fingerprint` 索引，避免 N+1；
- `overview()` / `browsers()` / `accounts()` / `ip_pool()` / `fingerprints()` / `novnc()` 都是纯函数，只接收快照，便于单测与复用；
- 路由通过 `Depends(get_snapshot)` 拿快照，本身不再关心 SQL。

字段是这样拼出来的（都是库里真实字段，不是硬编码）：实例卡片的 `group` / `account` / `ip` / `fingerprint` 来自四个外键的 join；`started_at`、事件时间用 `_humanize()` 转成「2 小时前」；IP 地区分布按国家码聚合到美国 / 欧洲 / 亚洲 / 其他；账号的 `bound_instance`、IP 的 `bound_instance` 反查 `browsers`。

`services/seed.py` 只写初始化数据：默认工作区 `webweaver-team`、35 个权限点、4 个内置角色、超级管理员 `admin / admin`。演示用的分组 / 内核 / 账号 / IP / 实例都在 `backend/tests/demo_cluster.py` 里，只有测试会用到，不进部署库。

```bash
uv run python -m app.services.seed   # 幂等：缺什么补什么，可反复执行
```

仍是固定值、需要后续接入的部分（接口形状已固定，替换实现即可）：

| 位置 | 现状 |
|---|---|
| 集群负载 `load`（CPU / 内存 / 带宽） | 固定值，待调度器指标采集 |
| 趋势曲线 `trend` | 固定曲线，需要时序表或 Prometheus |
| 事件流 `events` | 由实例 / IP / 账号的当前状态推导，接事件表后改为审计日志 |
| 任务卡 `tasks` | 恒为 0，暂无任务表 |
| noVNC `state.memory` | `—`，容器内存指标暂无采集 |

### 迁移

迁移环境是异步模板（`alembic/env.py`），连接串来自 `settings.database_url`（`backend/.env`），元数据来自 `SQLModel.metadata` —— 改模型后不用再维护一份 DDL。

```bash
cd backend
uv run alembic upgrade head                       # 应用迁移到最新
uv run alembic revision --autogenerate -m "说明"  # 按模型与库的差异生成迁移
uv run alembic check                              # 检查模型与库是否一致（CI 可用）
uv run alembic current / history                  # 查看当前版本 / 历史
uv run alembic downgrade -1                       # 回退一步（已验证可回到 base）
```

约定：

- 生成的脚本一律**先 review 再提交**：`render_item` 已把 SQLModel 的 `AutoString` / `UTCDateTime` 渲染成 `sa.String` / `sa.DateTime(timezone=True)`，脚本不依赖 `sqlmodel` 包。
- 注释也纳入 autogenerate：`alembic check` 会加载 `alembic.autogenerate.comments` 插件，改了模型里的 `comment` 就能生成对应的 `COMMENT ON` 变更。
- `alembic.ini` 里 `sqlalchemy.url` 留空，且**必须是纯 ASCII**（Windows 下 alembic 按 GBK 读 ini，中文注释会直接 `UnicodeDecodeError`）。
- `alembic/versions` 已加入 ruff 的 `extend-exclude`，生成脚本的格式不参与 lint。

## 认证与权限

**一个写入口**：`POST /api/auth`，请求体用 `action` 区分六种动作——`login` / `register` / `logout` / `forgot_password` / `resend_reset` / `reset_password`。

请求体是**判别联合**（`discriminator="action"`），每个动作有独立的 schema：`/docs` 里能看到六个请求模型，字段缺失或类型不对直接 422，业务代码里不用写判空。代价在响应侧：只能给一个超集信封 `AuthResponse`（`ok` / `action` / `message` + 按动作可选的字段）。

保留为独立 GET 的是纯查询：`/api/auth/workspaces`、`/api/auth/captcha`、`/api/auth/me`。

| 环节 | 实现 |
|---|---|
| 密码 | `hashlib.scrypt`（n=16384, r=8, p=1，随机盐），格式 `scrypt$n=...,r=...,p=...$salt$hash`，库里没有明文也没有可逆密文 |
| 会话 | `auth_sessions`，令牌用 `secrets.token_urlsafe(32)`，**库里只存 SHA-256 摘要**；默认 12 小时，勾「记住我」30 天 |
| 鉴权 | `Authorization: Bearer <token>`；`app/api/deps.py` 的 `CurrentUser` 依赖解析，401 带 `WWW-Authenticate`；`require_permission("browser:create")` 再叠一层权限点校验 |
| 防爆破 | 连续失败 5 次锁 15 分钟（`users.locked_until`），锁定期间密码正确也拒绝；账号不存在与密码错误的提示完全一致，避免账号枚举 |
| 重置密码 | `password_reset_tokens` 一次性令牌（30 分钟），成功后改密 + 吊销该成员全部会话；`AUTH_EXPOSE_RESET_TOKEN=true` 时令牌直接放在响应里，本地不走邮件也能点通流程 |
| 审计 | 登录成功/失败、注册、注销、找回与重置全部落 `audit_logs`（`resource_type=auth`），失败记录同样是证据 |

演示成员（种子数据，密码都是 `WebWeaver@2026`）：`admin_chen`（owner，35 个权限点）、`ops_lee`（operator，13 个）、`viewer_lin`（viewer，9 个）。前端 `/login` 页登录后令牌存在 localStorage，`UserMenu` 的「退出登录」会调 `action=logout` 并清掉本地令牌。

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（含 `database.status` / `database.version`） |
| GET | `/api/overview` | 集群总览（集群指标、负载、活跃实例、实时事件、趋势） |
| GET | `/api/browsers` | 浏览器池（统计、实例卡片、筛选项） |
| GET | `/api/accounts` | 账号池（统计、账号卡片、平台筛选） |
| GET | `/api/ip-pool` | IP 池（资源明细、区域分布、供应商健康、轮换策略） |
| GET | `/api/novnc/{instance_id}` | noVNC 会话详情（状态、账号、出口 IP、指纹、操作日志） |
| GET | `/api/fingerprints` | 指纹模板列表（筛选计数、伪装项、唯一性、使用实例） |
| GET | `/api/kernels` | 内核管理：4 套引擎台账 + 磁盘版本扫描（是否已下载 / 当前版本 / 可更新版本 / 待迁移实例） |
| POST | `/api/kernels/rescan` | 重新扫描内核目录，返回最新扫描结果（只读，不写审计） |
| GET | `/api/kernels/{kernel_id}/instances` | 该内核下的实例清单，`?stale=true` 只看留在旧版本上的（批量迁移候选） |
| POST | `/api/kernels/{kernel_id}/version` | 切换当前版本；旧版本目录保留，老实例不动，等显式迁移 |
| POST | `/api/kernels/{kernel_id}/migrate` | 把实例批量迁到指定版本（`browser_ids` 留空 = 全部旧版本实例） |
| POST | `/api/kernels/{kernel_id}/primary` | 将某套内核设为主力（落库 + 审计） |
| GET | `/api/kernels/{slug}` | 引擎详情：人工维护的档案（优劣势 / 下载源 / 版本清单）+ 磁盘状态 + README 正文 |
| POST | `/api/kernels/{slug}/install` | 按档案里的获取方式拉取一个版本（`pip` 装包取缓存 / `archive` 直链下载解压），返回 202 与任务 |
| GET | `/api/kernels/jobs` · `/api/kernels/jobs/{id}` | 获取任务列表与单个任务进度（内存态，重启即丢） |
| GET | `/api/account/menu` | 头像浮层：成员信息、默认工作区、菜单分组与实时 badge（在线设备数） |
| GET | `/api/account/profile` | 个人信息（登录名、邮箱、角色、默认工作区、加入时间、上次改密、在线设备数） |
| PATCH | `/api/account/profile` | 修改显示名（登录名与邮箱不支持自助修改），落一条 `resource_type=user` 审计 |
| GET | `/api/account/sessions` | 登录设备：有效的在前，标记「本机」，含已下线的历史 |
| DELETE | `/api/account/sessions/{id}` | 踢掉自己的某个会话；踢当前会话等于退出登录 |
| GET | `/api/account/security` | 安全概览：改密时间、失败次数与锁定、在线设备数、最近认证事件 |
| GET | `/api/account/audit-logs` | 我的操作日志（`operator` 由登录态钉死，不能查别人） |
| GET | `/api/audit-logs` | 全量审计日志（按动作 / 资源 / 操作人 / 结果 / 时间段筛选 + 分页） |
| GET | `/api/rbac/permissions` · `/roles` · `/users` | RBAC 目录：权限点、角色（含权限与成员数）、成员（不含密码哈希） |
| POST | `/api/auth` | **认证统一入口**，`action` 决定走登录 / 注册 / 注销 / 发重置邮件 / 重发 / 提交新密码 |
| GET | `/api/auth/me` | 当前登录成员（含角色与有效权限点），未登录 401 |
| GET | `/api/auth/workspaces` | 工作区列表，登录时 `default_id` 是本人的默认工作区 |
| GET | `/api/auth/captcha` | 下发图形验证码（进程内保存，120 秒有效） |

## 前后端联调约定

- 前端请求统一走 `/api` 前缀，开发期由 Vite 代理到 `http://127.0.0.1:8010`，不产生跨域问题。
- 后端路由统一挂在 `settings.api_prefix`（默认 `/api`）下；新增业务在 `backend/app/api/routes/` 建模块，再于 `api/router.py` 注册。
- 生产环境用 `VITE_API_BASE_URL` 指向真实后端域名，同时配置后端 `CORS_ORIGINS`。
- 字段命名：后端 snake_case，前端类型同名对应（`types/domain.ts` ↔ `schemas/domain.py`），不做自动转换，保持两侧一眼可对。

## 日志

`app/core/logging_config.py` 基于 **loguru**，控制台、文件、ELK 四处输出共用同一格式，每个请求自动带 `request_id`：

```
2026-10-31 13:01:14.363 | INFO     | 62657ae7 | middleware.py:34 - GET /api/health -> 200 (9.7ms)
```

| 输出 | 文件 | 滚动 / 保留 |
|---|---|---|
| 控制台（彩色） | stdout | — |
| 应用日志 | `backend/logs/app_{日期}.log` | 100MB，30 天，zip |
| 错误日志 | `backend/logs/error.log` | 50MB，90 天，zip |
| ELK JSON | `backend/logs/elk_{日期}.json` | 100MB，30 天，zip |

- 配置项：`LOG_DIR`（默认 `logs`，相对路径以 `backend/` 为基准）、`LOG_LEVEL`（默认 `INFO`）、`LOG_DIAGNOSE`（默认 `false`）。
- **落盘不记录变量快照**：`diagnose` 默认关闭，异常日志只有调用栈，不会把 `password`、token 这类局部变量写进文件。确实需要排查时临时设 `LOG_DIAGNOSE=true` 再复现，排查完改回来。
- `request_id` 由 `RequestLogMiddleware` 生成（优先取请求头 `X-Request-ID`），通过 `ContextVar` 注入，响应头会回写 `X-Request-ID`；异步代码里直接 `logger.info(...)` 即可自动带上。
- 标准库 `logging` 已被接管，uvicorn 的启动/关闭日志也走同一套格式；uvicorn 自带访问日志关闭，请求日志统一由中间件输出（4xx/5xx 记 WARNING）。
- `setup_logger()` 幂等，重复调用只会生效一次；需要手动包裹同步/异步上下文时可用 `RequestContext` / `AsyncRequestContext`。

```python
from app.core.logging_config import logger

logger.info("实例 {} 已接管", instance_id)          # 自动带 request_id
logger.opt(exception=exc).error("调度失败")          # 带堆栈
```

## 页面

| 路由 | 页面 | 数据来源 |
|---|---|---|
| `/` | 集群总览 | `/api/overview` |
| `/browsers` | 浏览器池 | `/api/browsers` |
| `/accounts` | 账号池 | `/api/accounts` |
| `/ip-pool` | IP 池 | `/api/ip-pool` |
| `/novnc/:id` | noVNC 实时视图 | `/api/novnc/{id}` |
| `/fingerprints` | 指纹库列表视图（筛选、搜索、唯一性、分页） | `/api/fingerprints` |
| `/kernels` | 内核管理（4 套引擎卡片：源仓库、磁盘版本扫描、当前/最新版本、启用新版本、实例批量迁移） | `/api/kernels` |
| `/kernels/:slug` | 引擎详情（优劣势对照、适合场景、版本清单与平台选择、安装注意、README 正文、磁盘状态侧栏） | `/api/kernels/{slug}` |
| `/forgot-password` | 找回密码（工作区 + 邮箱 + 图形验证码） | `/api/auth/*` |
| `/reset-email-sent` | 重置邮件已发送（倒计时、重发） | `/api/auth/*` |
| `/reset-password` | 设置新密码（强度条 + 规则校验） | `/api/auth/*` |

## 引擎档案（手动维护）

详情页的文案与版本清单**不在数据库里**，而是跟着引擎目录走：新增引擎或发新版只改文件，不动代码。

```
backend/browser_engine/<slug>/
├── engine.json      # 结构化档案：优劣势、适合场景、下载源、版本清单
├── README.md        # 详情页正文（Markdown）
└── <version>/       # 真实内核，meta.json 是「下载完成」标记
```

`engine.json` 关键字段：

| 字段 | 说明 |
|---|---|
| `tagline` / `best_for` / `detection_level` | 一句话定位、适合场景、反检测层级 |
| `pros[]` / `cons[]` | 优势 / 劣势，详情页两列对照 |
| `install_notes[]` | 安装注意，支持行内 `` `code` `` |
| `links[]` | `{label, url, kind}`，`kind` 取 `release` / `docs` / `bucket` / `mirror` |
| `acquire` | 引擎级默认获取方式（`kind` + `installer` + `pin` + `fetch` + `binary_url` + `cache_dirs` + `executable`） |
| `versions[]` | 版本清单：`version` / `base` / `channel` / `released_at` / `notes` / `packages[]` |
| `packages[]` | 每个平台一条：`kind` / `os` / `arch` / `size` / `url` / `sha256` / `installer` / `pin` |

`kind` 决定点「下载」后走哪条路：

- `pip`：建临时 venv → `pip install <installer>==<pin>` → 跑 `fetch` 命令，把缓存里的二进制搬进版本目录（CloakBrowser）。
  若 `acquire.binary_url` 有值，则跳过 CLI 直接下这个 zip——CLI 是单连接，慢十几倍
- `archive`：直链下载 → 校验 sha256（留空则跳过）→ 解压（拒 `../` 穿越）→ 找主程序（Camoufox、fingerprint-chromium）
- `manual`：不代下，页面只给跳转链接（ungoogled-chromium，社区构建来源不唯一）

发新版时加一条 `versions[]` 即可；`sha256` 宁可不填也别抄错——填错等于永远下不了，页面会标「未校验」。`engine.json` 写坏不会白屏：接口返回 `profile_ok=false` + 原因，磁盘状态照常显示。

### 大包下载为什么要用 aria2

内核包 500MB 起。实测**单条连接被限速到 ~30 KB/s**：直连 `cloakbrowser.dev`、走本地代理、走 GitHub 加速站（测了 16 个，只有 `gh-proxy.com` 和 `ghproxy.net` 有响应）全都是这个数，536MB 要跑 5 小时，页面上看起来就是卡死。

同一条网络下开 16 条连接，总带宽能到 400~800 KB/s，20 分钟量级——说明瓶颈是「单连接」而不是出口带宽。所以下载走 `backend/bin/aria2c.exe`（`-x16 -s16 -k1M -c`，带断点续传）。缺这个文件时后端会自动退回单连接，能跑但很慢。

```bash
bash scripts/get-aria2.sh   # 拉 aria2c 到 backend/bin/（可选，5.6MB 不进仓库）
```

另有一个兜底配置：`KERNEL_DOWNLOAD_MIRROR`（例如 `https://gh-proxy.com/`），设了会给 github 链接套加速前缀。默认留空，因为实测这类站点的单连接速度不比直连快。

## 设计令牌

从设计稿截图采样得到，集中定义在 `frontend/src/index.css` 的 `@theme` 与 `:root`：

| 用途 | 色值 |
|---|---|
| 页面背景 | `#fafafa` |
| 深色英雄卡渐变 | `#192236 → #283448` |
| 账号池渐变 | `#4171f1 → #4f48e6` |
| IP 池渐变 | `#0ea186 → #12b886` |
| 导航激活态 | `#18181b` |
| 主色（绿/蓝/紫/橙/红） | `#10b981` / `#3b82f6` / `#8b5cf6` / `#f59e0b` / `#f43f5e` |

## 后续

- [x] 总览 / 浏览器池 / 账号池 / IP 池 / 指纹库 / noVNC 已改为真实数据库查询
- [ ] 集群负载（CPU / 内存 / 带宽）与趋势曲线仍是固定值，待接入调度器指标采集
- [ ] 事件流从当前状态推导，接事件表后改为真实审计日志
- [x] 内核页面已改为真实扫描：目录 `backend/browser_engine/<引擎>/<版本>/meta.json` 即版本真相；
      切当前版本只移动指针、旧版本目录保留，实例按 `browsers.kernel_version` 单独记版本，可批量迁移
- [x] 引擎档案与获取链路：`browser_engine/<slug>/engine.json`（优劣势 / 下载源 / 版本清单，人工维护）+ `README.md`（详情页正文）；
      获取分 `pip`（CloakBrowser）/ `archive`（Camoufox、fingerprint-chromium）/ `manual`（ungoogled，只给链接不代下）三种策略
- [ ] `archive` 目前只解压 zip；fingerprint-chromium 的 Linux tar.xz / AppImage 需要补 tar 分支
- [ ] 获取任务无断点续传，且任务表在内存里（进程重启即丢，页面会提示重来）；并发固定 1，大包排队
- [ ] Gitee 镜像未做（单附件 100MB / 总量 1G 放不下 400MB 内核包），`mirror_url` 字段留空待用
- [ ] 账号安全三页目前接的是演示接口，真实的邮件投递与令牌校验待接入
- [ ] 实例操作（新建/接管/重连）接入真实接口
