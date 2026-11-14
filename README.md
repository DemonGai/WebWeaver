# WebWeaver · 浏览器集群控制台

把「浏览器实例」当成容器来管理的控制台：一个实例 = 内核 + 指纹 + 出口 IP + 平台账号。
在页面上新建、启动、停止、重启、删除实例，用 noVNC 直接看画面，或用 CDP 把实例接给
Playwright / Puppeteer；账号、代理、指纹、内核版本各自有独立的资源池与审计。

后端是 **FastAPI + SQLAlchemy 2（异步）+ PostgreSQL**，前端是 **React 19 + Vite + TypeScript +
Tailwind CSS v4**。生产部署只需要一个容器：PostgreSQL、API、前端页面都在里面，通过挂载
宿主机的 Docker Socket 去创建「兄弟容器」作为浏览器实例。

> 这份 README 只讲「怎么用起来」。每个模块的设计取舍、接口细节和排障方法在
> [`docs/`](docs/README.md)。**如果你是被派来改这个仓库的 AI，先读
> [`docs/11-ai-guide.md`](docs/11-ai-guide.md)。**

---

## 目录

- [能力](#能力)
- [架构](#架构)
- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [配置](#配置)
- [常用命令](#常用命令)
- [文档](#文档)
- [开发约定](#开发约定)
- [已知边界](#已知边界)
- [安全提示](#安全提示)

---

## 能力

| 模块 | 做什么 |
|---|---|
| **总览** | 集群健康分（实例 / 出口 / 账号 / 指纹四项加权）、资源水位、活跃实例、审计事件与趋势 |
| **浏览器池** | 实例卡片与表格两种视图、新建 / 编辑 / 复制、批量启停、绑定账号与出口、noVNC 入口、CDP 地址 |
| **noVNC 控制台** | 左侧实例列表、右侧画面；按镜像判定「能不能接管」，不可接管时给出原因并可原地启动 |
| **账号管理** | 平台账号增改查、CSV 粘贴导入（自动识别平台）、Cookie 查看、健康度与绑定实例 |
| **代理管理** | 代理资源池、CSV 导入、TCP 可达性检测、按地区与供应商聚合、出口绑定情况 |
| **指纹管理** | 指纹模板、按内核能力矩阵下发、起临时容器采集真实人格、批量应用到实例 |
| **内核管理** | 四个引擎台账 + 本地 Docker 镜像扫描、拉取镜像、切换当前版本、实例批量迁移 |
| **账号安全** | 登录 / 注册 / 找回密码、双令牌会话、登录设备管理、改密、个人审计日志 |
| **RBAC 与审计** | 35 个权限点、4 个内置角色；所有写操作落审计，绑定关系另有只追加流水 |

实例的启停删真正作用于 Docker：

```
容器名 = 实例 ID（UUID）        docker ps 里能直接对上页面上的 ID
数据卷 = wv-data-<实例 ID>      删容器不丢登录态，重建后账号还在
端口   = noVNC 6080 起顺延       CDP = noVNC + 3100（9180 起）
```

## 架构

```
浏览器
  │  httpOnly Cookie（wv_at / wv_rt）
  ▼
React SPA ── /api/* ──► FastAPI ──► PostgreSQL（18 张表，Alembic 管理）
                          │
                          ├─► Docker CLI ──► 宿主机 Docker
                          │                    ├─ 实例容器 <实例 ID>
                          │                    │    ├─ Chromium + CDP :9222
                          │                    │    ├─ Xvfb + x11vnc + noVNC :6080
                          │                    │    └─ /data ← 卷 wv-data-<ID>
                          │                    └─ 内核镜像 <registry>:<slug>-<version>
                          └─► 审计日志、内核拉取任务、指纹采集
```

- **单容器部署**：`webweaver` 容器里跑 PostgreSQL（只听 127.0.0.1）、uvicorn（同时托管前端
  `dist`）、docker CLI。挂载 `/var/run/docker.sock` 后，实例容器和它是兄弟关系，不是嵌套。
- **镜像即真相**：某个内核「有没有」只看本地 `docker image ls`，没有磁盘目录扫描，也没有
  「登记了但没下载」的中间态。
- **数据库只存指针**：`kernels.version` 是当前生效版本；切版本只是移动指针，旧镜像保留，
  老实例留在旧版本上，等显式迁移。

## 快速开始

### 方式一：Docker（推荐）

前置：Docker Desktop / Docker Engine 24+，compose v2，能访问 Docker Hub。

```bash
git clone <repo-url> webweaver
cd webweaver

# 可选：先改掉默认密钥与数据库口令
export AUTH_JWT_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export DB_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(16))')"

docker compose up -d --build
docker compose logs -f webweaver
```

看到 `Uvicorn running on http://0.0.0.0:8000` 后打开 **http://127.0.0.1:8000**，
用 `admin / admin` 登录（首次启动会自动建库、跑迁移、写超管与四个内核登记）。

首次构建约 5~10 分钟（前端 `npm install` + 后端依赖 + PostgreSQL）。国内网络默认走清华
apt / pip 源，可用 `PIP_INDEX_URL` 覆盖。

> **noVNC 端口**：实例画面发布在宿主机 `6080` 起。如果你在另一台机器上打开控制台，
> 需要能访问宿主机的这些端口；跨机器/反代场景请设置 `NOVNC_HOST`。

### 方式二：本地开发

前置：Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node 20+ / npm、Docker。

```bash
# 1) 开发用数据库（PostgreSQL 18，映射到 5432）
docker compose --profile dev up -d postgres

# 2) 后端（端口 8010，避开一体化部署的 8000）
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.services.seed
uv run uvicorn app.main:app --reload --port 8010

# 3) 前端（另开一个终端，端口 5173）
cd frontend
npm ci
npm run dev
```

打开 **http://127.0.0.1:5173**。Vite 会把 `/api` 代理到 `127.0.0.1:8010`，无需处理跨域。

也可以一条命令起两个进程（Git Bash）：

```bash
bash scripts/dev.sh          # 后端 8010 + 前端 5173，Ctrl+C 一起停
```

开发库连接串：`postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver`。
接口文档：http://127.0.0.1:8010/docs 。

## 目录结构

```
WebWeaver/
├── Dockerfile                  # 一体化镜像：前端构建 → docker CLI → PG + API
├── docker-compose.yml          # webweaver 服务；--profile dev 起独立 PostgreSQL
├── docker/entrypoint.sh        # initdb → 迁移 → seed → uvicorn，含优雅退出
├── backend/
│   ├── app/
│   │   ├── main.py             # 应用工厂、lifespan、SPA 托管
│   │   ├── api/routes/         # 12 个路由模块（见 docs/07）
│   │   ├── core/               # 配置、数据库、安全、Cookie、日志、中间件
│   │   ├── models/             # 18 张表的 SQLModel 定义
│   │   ├── schemas/            # 请求 / 响应模型（Pydantic）
│   │   └── services/           # 业务逻辑：实例运行时、内核、指纹、账号、代理…
│   ├── alembic/versions/       # 16 条迁移
│   └── tests/                  # pytest；演示数据只在 tests/demo_cluster.py
├── frontend/
│   └── src/
│       ├── App.tsx             # 路由表
│       ├── api/                # fetch 封装 + 接口定义
│       ├── auth/               # 登录态上下文与路由守卫
│       ├── components/         # 布局、UI 套件、弹窗、图标
│       ├── pages/              # 业务页、账号安全页、个人中心
│       └── types/domain.ts     # 与后端 schema 对齐的类型
├── browser_engine/             # 内核镜像源码：Dockerfile / entrypoint / 字体
├── scripts/                    # dev.sh、dev.mjs、ui-check.mjs、get-aria2.sh
└── docs/                       # 技术文档（本目录）
```

## 配置

配置来自环境变量或 `backend/.env`（见 `backend/.env.example`）。最常改的几项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver` | 异步连接串 |
| `AUTH_JWT_SECRET` | 开发占位值 | **生产必改**，访问令牌签名密钥 |
| `AUTH_COOKIE_SECURE` | `false` | 对外 HTTPS 时改 `true` |
| `AUTH_ALLOW_REGISTER` | `true` | 正式环境建议关掉，改由管理员建号 |
| `AUTH_EXPOSE_RESET_TOKEN` | `false` | 仅本地联调设 `true`，生产必须关 |
| `NOVNC_HOST` | 空 | 留空跟随请求 Host；反代/跨机时填外网域名或宿主 IP |
| `FRONTEND_DIST` | 空 | 配了就把前端 `dist` 交给 FastAPI 托管 |
| `KERNEL_IMAGE_REGISTRY` | `demon1315132284/browser_engine` | 内核镜像仓库 |
| `KERNEL_DOCKER_BIN` | `docker` | 容器内通常是 `docker` |
| `LOG_DIR` / `LOG_LEVEL` | `logs` / `INFO` | 相对路径以 `backend/` 为基准 |

Docker 部署额外用到：`APP_PORT`（宿主端口，默认 8000）、`DB_PASSWORD`、`DOCKER_SOCK`
（默认 `/var/run/docker.sock`）、`PIP_INDEX_URL`。

完整清单见 [`docs/09-deployment.md`](docs/09-deployment.md#4-环境变量)。

## 常用命令

| 目的 | 命令（在 `backend/` 下） |
|---|---|
| 装依赖 / 同步 | `uv sync` |
| 应用迁移 | `uv run alembic upgrade head` |
| 生成迁移 | `uv run alembic revision --autogenerate -m "说明"` |
| 检查模型与库是否一致 | `uv run alembic check` |
| 初始化数据（幂等） | `uv run python -m app.services.seed` |
| 启动 API | `uv run uvicorn app.main:app --reload --port 8010` |
| lint / 格式 | `uv run ruff check .` · `uv run ruff format .` |
| 测试 | `uv run pytest` |

| 目的 | 命令（在 `frontend/` 下） |
|---|---|
| 装依赖 | `npm ci` |
| 开发 | `npm run dev` |
| 类型检查 | `npm run typecheck` |
| 生产构建 | `npm run build` |

| 目的 | 命令（仓库根） |
|---|---|
| 构建并启动 | `docker compose up -d --build` |
| 看日志 | `docker compose logs -f webweaver` |
| 重启 | `docker compose restart webweaver` |
| 停止（保留数据） | `docker compose down` |
| 连库 | `docker exec -it webweaver psql -h 127.0.0.1 -U webweaver -d webweaver` |

## 文档

| 文档 | 内容 | 适合谁 |
|---|---|---|
| [`docs/01-architecture.md`](docs/01-architecture.md) | 系统边界、请求链路、部署拓扑、关键决策 | 所有人 |
| [`docs/02-backend.md`](docs/02-backend.md) | 后端分层、依赖注入、配置、日志、如何加接口 | 后端开发 |
| [`docs/03-data-model.md`](docs/03-data-model.md) | 18 张表、枚举、约束、绑定日志、迁移 | 后端 / DBA |
| [`docs/04-auth-rbac.md`](docs/04-auth-rbac.md) | 双令牌、Cookie、会话轮转、权限模型、审计 | 后端 / 安全 |
| [`docs/05-browser-runtime.md`](docs/05-browser-runtime.md) | 实例容器生命周期、端口、卷、noVNC、指纹下发与采集 | 后端 / 运维 |
| [`docs/06-kernels.md`](docs/06-kernels.md) | 镜像命名、扫描、拉取、切版本、批量迁移 | 后端 / 运维 |
| [`docs/07-api-reference.md`](docs/07-api-reference.md) | 51 条路径 / 60 个操作的方法、权限与示例 | 前后端 / 集成方 |
| [`docs/08-frontend.md`](docs/08-frontend.md) | 前端结构、路由、请求层、登录态、组件与设计令牌 | 前端开发 |
| [`docs/09-deployment.md`](docs/09-deployment.md) | 单容器原理、构建、升级、备份、反代、排障 | 运维 |
| [`docs/10-development.md`](docs/10-development.md) | 环境、命令、测试、CI、提交规范、Windows 注意 | 贡献者 |
| [`docs/11-ai-guide.md`](docs/11-ai-guide.md) | **给 AI / 自动化代理的操作手册**：不变量、任务配方、验证清单 | AI / 自动化 |
| [`docs/12-resource-pools.md`](docs/12-resource-pools.md) | 账号 / 代理 / 指纹：导入、健康度、能力矩阵、采集与下发 | 后端 / 前端 |
| [`docs/13-overview.md`](docs/13-overview.md) | 总览的健康分口径、水位、趋势与页面层级 | 后端 / 前端 |

文档索引与阅读路径：[`docs/README.md`](docs/README.md)。

## 开发约定

- 后端行宽 100，`ruff check` / `ruff format` 必须干净；Python 3.12+，全量类型标注。
- 前端提交前必须 `npm run typecheck` 与 `npm run build` 通过。
- 表结构只通过 Alembic 迁移变更，不手改数据库；新表 / 新字段必须带中文 `comment`。
- 写接口要有权限点与审计；绑定变化额外写只追加的 `browser_*_bindings` 流水。
- 接口路径统一挂在 `settings.api_prefix`（默认 `/api`），新增路由要在 `app/api/router.py` 注册。
- 字段命名后端 snake_case，前端 `types/domain.ts` 同名对应，不做自动转换。
- 提交信息用 Conventional Commits：`feat(scope): …`、`fix(scope): …`、`docs: …`。

## 已知边界

- 没有任务调度器：自动化请用 CDP 自行接管；总览的负载、趋势目前由审计与状态推导。
- 内核镜像只提供 `linux/amd64`；Camoufox 尚无镜像，页面上标记「暂未支持」。
- 镜像拉取任务在进程内存里，重启即丢；并发固定为 1。
- 指纹只能在实例启动时装配，改指纹需要重启容器（profile 不丢）。
- 单容器部署里 PostgreSQL 与应用同生命周期；要独立扩缩容需拆开部署。
- noVNC 地址按 `http://` 生成；控制台走 HTTPS 时需自行给 noVNC 端口加 TLS 或同源反代。

## 安全提示

1. **不要直接把控制台端口暴露到公网**：除 `/api/user/*` 与 `/api/auth/me` 外，当前读接口
   没有挂登录依赖，匿名请求可以读到浏览器池、账号 Cookie、代理口令、审计日志与成员列表。
   这是已知缺口（见 [docs/04](docs/04-auth-rbac.md#84-接口侧的实际用法)），至少加一层反代认证
   或限制来源 IP。
2. 首次登录后立刻修改 `admin` 密码；生产环境关闭自助注册。
3. 必须设置随机的 `AUTH_JWT_SECRET` 与 `DB_PASSWORD`，不要沿用仓库默认值。
4. 挂载 `docker.sock` 等于把宿主机 root 权限交给容器，只部署在受信主机上。
5. 对外提供服务时用 HTTPS，并设 `AUTH_COOKIE_SECURE=true`、`AUTH_COOKIE_DOMAIN`。
6. 实例的 CDP（9180+）与 noVNC（6080+）端口默认发布到 `0.0.0.0`，请用防火墙限制来源。

## 许可证

仓库目前未附带 `LICENSE` 文件。在补充许可证之前，默认保留所有权利；如果要正式以开源
许可证发布，建议补一份 MIT 或 Apache-2.0 的 `LICENSE`，并在本节注明。
