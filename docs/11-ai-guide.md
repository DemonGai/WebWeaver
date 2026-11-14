# 11 · 给 AI / 自动化代理的操作手册

这份文档假设你（一个 AI 代理）被要求在这个仓库里改代码、排故障或操作运行中的实例。
它只写**能直接执行的事实**：路径、命令、约束、验证方式。读完这一篇再动手。

---

## 0. 三十秒读懂

- 这是一个**浏览器集群控制台**，不是爬虫框架。
- 一个「实例」= 数据库一行 `browsers` + 一个 Docker 容器 + 一个卷 + 一对端口。
- 容器名就是实例 ID（UUID）；`docker ps` 与页面上的 ID 能直接对上。
- 后端 FastAPI（`backend/app`），前端 React（`frontend/src`），数据库 PostgreSQL。
- 生产是一个容器：PG + uvicorn + 前端 dist + docker CLI，通过宿主 socket 创建兄弟容器。
- 默认入口 `http://127.0.0.1:8000`，账号 `admin / admin`。

## 1. 动手前的读取顺序

| 顺序 | 文件 | 目的 |
|---|---|---|
| 1 | `README.md` | 启动方式、目录、配置 |
| 2 | 本文第 2~4 节 | 环境事实、产品边界、不变量 |
| 3 | `docs/01-architecture.md` | 请求链路与关键决策 |
| 4 | `docs/03-data-model.md` | 数据落在哪、约束是什么 |
| 5 | 任务相关模块文档 | 05 实例 / 06 内核 / 04 认证 / 08 前端 / 07 接口 |

不要一开始就全量读代码。先定位任务属于哪一层，再读对应文件。

## 2. 环境事实（先核对，不要假设）

| 项 | 值 |
|---|---|
| 生产入口（单容器） | `http://127.0.0.1:8000`，容器名 `webweaver` |
| 开发后端 | `http://127.0.0.1:8010`，`uvicorn --reload` |
| 开发前端 | `http://127.0.0.1:5173`，Vite 代理 `/api` → 8010 |
| 开发数据库 | `127.0.0.1:5432`，`webweaver / webweaver / webweaver` |
| 容器内数据库 | `127.0.0.1:5432`（只听回环），库/用户 `webweaver` |
| 默认账号 | `admin / admin`（超级管理员） |
| 实例 noVNC 端口 | 宿主 `6080` 起顺延 |
| 实例 CDP 端口 | 宿主 `9180` 起（= noVNC + 3100） |
| 镜像仓库 | `demon1315132284/browser_engine` |
| 内核镜像 tag | `cloakbrowser-<version>` / `fingerprint-chromium-<version>` / `ungoogled-chromium-<version>`，无版本后缀的是滚动 tag |

先确认当前状态再动手：

```bash
cd /path/to/WebWeaver
git status --short
git log --oneline -3
docker compose ps
docker ps --filter label=webweaver.instance
curl -s http://127.0.0.1:8000/api/health
```

如果 `git status` 有未提交改动，先问清楚是不是用户的在途工作，不要覆盖或回滚。

## 3. 产品边界（用户明确要求，优先级高于你的审美）

- **已定版的页面不要重做**：登录页、忘记密码页、内核管理、指纹管理、代理管理。除非用户
  明确要求，不要改布局、交互与信息层级。
- **只做用户要求的改动**：用户说「只做简单修改」时，不要顺手加功能、加接口、加页面、
  重构目录。
- **总览是查看面，不是入口面**：不要加「新建实例」这类入口按钮。
- **noVNC 是左右分栏**：左侧实例列表、右侧画面；不要再拆成清单页 + 详情页。
- **浏览器池卡片**：主按钮只做电源（启动/停止），noVNC 是独立常驻按钮。
- **不要引入新框架**：没有状态管理库、没有 UI 组件库、没有任务队列。加依赖前先问。

## 4. 不变量（改代码时必须遵守）

### 4.1 运行时

1. **容器名 = `str(browser.id)`**。不要用实例名：Docker 不接受中文，改名也会导致容器迁移。
2. **卷名 = `wv-data-<id>`，删除实例不删卷**。清理卷是人工决定，不要在删除逻辑里加 `-v`。
3. **数据库里的端口是投影，不是真相**。启动/重启后用 `docker port` 回写；不要相信库里
   的旧值。
4. **启动顺序：先起容器，再落库**。反过来会留下「自称运行中、实际连不上」的实例。
5. **停止失败不要改状态**。界面显示已停止而容器还在跑，是最坏的谎。
6. **删除实例前必须是 stopped**（409），删除时清理三张绑定流水，保留审计与卷。
7. **指纹只能启动时装配**：写 `/data/fingerprint.json` 后必须重启容器；检查
   `FINGERPRINT_*` 环境变量是否遮蔽文件。
8. **noVNC 能力由镜像决定**，不是实例状态。判定顺序：镜像标签
   `com.webweaver.novnc` → `docker history` → 不支持。

### 4.2 数据与接口

9. **读接口目前大多没有鉴权**（见 4.3）。不要在此基础上再扩大匿名可读范围；新增写接口
   必须挂权限点。
10. **写操作必须审计**：`audit.record(...)`，失败也要落 `result=failure`。
11. **绑定变化必须写只看追加的流水**（`browser_*_bindings`），不要只改 `browsers.*_id`。
12. **`browsers` 的 `mode` 与资源 ID 必须成对**：`direct` ↔ `ip_id IS NULL`，
    `default` ↔ `fingerprint_id IS NULL`。数据库有 CHECK，服务层也要挡。
13. **PATCH 语义**：字段不出现 = 不改；显式 `null` = 切回直连/默认指纹。用
    `model_fields_set`，不要用 `is not None`。
14. **表结构只走 Alembic**。不要手改数据库当正式变更；临时排查可以，但要在交付说明里写清。
15. **新字段/新表必须有中文 `comment`**，`tests/test_models.py` 会校验。

### 4.3 已知安全缺口（不要误判为设计）

除 `/api/user/*` 与 `/api/auth/me` 外，当前 GET 路由没有挂 `CurrentUser`：
`/api/browsers`、`/api/accounts`（含 Cookie）、`/api/ip-pool`（含代理口令）、
`/api/audit-logs`、`/api/rbac/users` 等都能匿名读取。

- 不要向用户宣称「读接口需要登录」；
- 不要把这个缺口当成「可以继续加匿名读接口」的理由；
- 用户要求修复时，正确做法是给业务路由统一挂 `CurrentUser`（需要时再加
  `require_permission`），并同步更新测试与集成说明；这是行为变更，先确认影响面。

### 4.4 部署

16. **`FRONTEND_DIST` 没配时，`/` 返回服务信息**；配了才托管 SPA 并做 `index.html` 兜底。
17. **`docker.sock` 等于宿主 root**。不要把这个挂载写进面向公网的部署模板。
18. **不要把密钥、dump、`.env` 提交进仓库**。
19. **Dockerfile 与 `docker/**` 必须 LF**（`.gitattributes` 已钉）。

## 5. 代码地图（精确路径）

| 需求 | 从这里开始 |
|---|---|
| 加/改接口路径 | `backend/app/api/routes/<module>.py` → `backend/app/api/router.py` |
| 改业务规则 | `backend/app/services/<module>.py` |
| 改请求/响应结构 | `backend/app/schemas/*.py` |
| 改表结构 | `backend/app/models/*.py` → `alembic revision --autogenerate` |
| 改实例生命周期 | `backend/app/services/browser_runtime.py` + `browser_pool.py` |
| 改 noVNC 判定 | `backend/app/services/browser_novnc.py` |
| 改内核扫描/拉取 | `kernel_scan.py` / `kernel_image.py` / `kernel_install.py` / `kernel_pool.py` |
| 改指纹能力/下发 | `fingerprint_caps.py` / `fingerprint_apply.py` / `fingerprint_probe.py` |
| 改登录/会话 | `auth_service.py` + `core/security.py` + `core/cookies.py` |
| 改前端请求 | `frontend/src/api/client.ts` / `endpoints.ts` |
| 改页面 | `frontend/src/pages/*.tsx` |
| 改路由/导航 | `frontend/src/App.tsx` / `components/Layout.tsx` |
| 改部署 | `Dockerfile` / `docker-compose.yml` / `docker/entrypoint.sh` |
| 改内核镜像 | `browser_engine/<slug>/Dockerfile` + `entrypoint.sh` |

## 6. 常见任务配方

### 6.1 只改页面文案 / 布局

1. 定位 `frontend/src/pages/*.tsx` 或 `components/*`；
2. 改 JSX 与 Tailwind 类，复用现有设计令牌（`var(--ink-*)`、`var(--line)`）；
3. 不新增颜色体系，不引入组件库；
4. 跑 `cd frontend && npm run typecheck && npm run build`；
5. 用 1500 / 1280 两档宽度看布局（见第 8 节截图方法）。

### 6.2 加一个读接口

1. `schemas/` 定义响应模型；
2. `services/` 写查询/拼装函数（优先复用 `cluster.Snapshot`）；
3. `api/routes/` 加路由，`api/router.py` 注册；
4. 在 `docs/07-api-reference.md` 补一行；
5. 加一条接口测试（`tests/test_*.py`）；
6. `uv run ruff check . && uv run pytest -q`。

**注意**：读接口目前默认匿名。如果你希望它要求登录，显式加 `CurrentUser` 参数，并在
文档里注明；不要假设「框架会自动鉴权」。

### 6.3 加一个写接口

```python
@router.post(
    "/xxx",
    response_model=XxxResult,
    summary="做某事",
    dependencies=[Depends(require_permission("browser:update"))],
)
async def do_xxx(
    payload: XxxRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> XxxResult:
    result = await xxx_service.do(session, payload, operator=user.username, request=request)
    return result
```

服务层必须：

- 先校验（存在性、唯一性、状态机、外键归属）；
- 再变更数据库；
- 写 `audit.record(action=..., resource_type=..., resource_id=..., operator=..., detail=...)`；
- 绑定类变更额外写 `browser_*_bindings`；
- 需要调 Docker 的，放在事务提交后或处理好回滚。

### 6.4 加字段 / 加表

```bash
cd backend
# 1) 改 models/*.py（带 comment）
# 2) 生成迁移
uv run alembic revision --autogenerate -m "add_xxx"
# 3) 人工 review：重命名会被识别成删列+加列
# 4) 应用并校验
uv run alembic upgrade head
uv run alembic check
```

新表还要：在 `app/models/__init__.py` 导入并加入 `__all__`；需要初始化数据时改
`services/seed.py`（只放运行必需数据）；测试数据放 `tests/demo_cluster.py`。

### 6.5 改实例生命周期

先读 `docs/05-browser-runtime.md` 的「启动流程」「状态机」「端口分配」。改动时保持：

- `browser_runtime` 只碰 Docker，不管业务校验；
- `browser_pool` 负责状态、审计、端口回写；
- 任何新分支都要考虑：容器在跑 / 已停 / 不存在 / Docker 不可用。

### 6.6 改内核逻辑

先读 `docs/06-kernels.md`。记住：

- 版本真相是本地镜像，不是数据库、不是磁盘目录；
- 切版本只移动 `kernels.version`，不迁移实例、不重启；
- 拉取成功要 `browser_novnc.forget(image_ref)` 与 `kernel_pool.adopt_pulled(...)`；
- 滚动 tag 不能用来钉版本。

### 6.7 改部署

1. 先读 `docs/09-deployment.md`；
2. `Dockerfile` / `entrypoint.sh` 改动后必须 `docker compose build && up -d` 真机验证；
3. 确认 `docker compose config --quiet` 通过；
4. 确认容器 healthy、`/api/health` 200、页面能登录；
5. 确认迁移与 seed 幂等（重启一次，数据行数不翻倍）。

### 6.8 通过 API 操作（不打开浏览器）

```bash
BASE=http://127.0.0.1:8000/api
JAR=$(mktemp)

# 登录（Cookie 写入 jar）
curl -s -c "$JAR" -H 'Content-Type: application/json' \
  -d '{"action":"login","account":"admin","password":"admin"}' "$BASE/auth" >/dev/null

# 看实例 / 内核
curl -s -b "$JAR" "$BASE/browsers" | python -m json.tool
curl -s -b "$JAR" "$BASE/kernels"  | python -m json.tool

# 新建实例（kernel_id 从 /kernels 的 cards 里取）
curl -s -b "$JAR" -H 'Content-Type: application/json' \
  -d '{"name":"api-测试-01","kernel_id":"<uuid>"}' "$BASE/browsers"

# 启动 / 停止 / 重启
curl -s -b "$JAR" -H 'Content-Type: application/json' \
  -d '{"action":"start"}' "$BASE/browsers/<id>/actions"

# noVNC 入口
curl -s -b "$JAR" "$BASE/browsers/<id>/novnc" | python -m json.tool

# 拉内核镜像
curl -s -b "$JAR" -H 'Content-Type: application/json' \
  -d '{"version":"146.0.7680.177.5"}' "$BASE/kernels/<slug>/install"

# 删除（必须先 stop）
curl -s -b "$JAR" -X DELETE "$BASE/browsers/<id>"
```

写接口需要权限点；`admin` 是超管，直接放行。用普通账号时要先确认角色权限。

## 7. 验证矩阵

| 改动 | 必跑 | 期望 |
|---|---|---|
| 任何后端 Python | `uv run ruff check .` | 无输出、退出码 0 |
| 后端逻辑 | `uv run pytest -q`（临时库） | 全绿；数据库类用例不 skip |
| 表结构 | `uv run alembic check` | 无差异 |
| 任何前端 TS/TSX | `npm run typecheck` | 无错误 |
| 前端样式/布局 | `npm run build` | 构建成功，产物体积无异常 |
| 接口 | `curl` + Cookie | 状态码、字段与文档一致 |
| 实例启停 | 真机 API + `docker ps` | 容器出现/停止，端口回写，noVNC 200 |
| noVNC | `curl http://127.0.0.1:<port>/vnc.html` | 200 |
| 部署 | `docker compose build && up -d` | healthy，迁移与 seed 幂等 |
| 内核拉取 | 页面或 API + `docker images` | 新 tag 出现，版本列表更新 |

**不要**只跑 `npm run build` 就宣称后端没问题；也不要只看类型检查就宣称运行时正确。

## 8. 调试工具

```bash
# 请求日志（容器）
docker logs webweaver --tail 100 -f

# 数据库
docker exec -it webweaver psql -h 127.0.0.1 -U webweaver -d webweaver

# 实例容器
docker ps -a --filter label=webweaver.instance
docker logs <实例 ID> --tail 100
docker inspect <实例 ID> --format '{{json .Config.Env}}'

# 端口
docker port <实例 ID>

# 前端构建预览
cd frontend && npm run build && npm run preview
```

页面截图（本机有 Edge 时）：

```bash
# 无头 Edge + CDP，登录后截图
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --headless=new --remote-debugging-port=9333 \
  --window-size=1500,1000 --user-data-dir="$TEMP/wv_edge_prof" about:blank &
```

仓库里的 `scripts/ui-check.mjs` 会自动跑登录态相关流程并截图到临时目录，适合回归
「登录 → 守卫 → 续期 → 改密 → 设备页」。

## 9. 已知坑

| 坑 | 现象 | 规避 |
|---|---|---|
| Windows 端口探测 | 纯 `bind` 把已占端口判为空闲 | 用 `connect_ex` + `bind` 双检（`_port_free`） |
| Windows 子进程 | `NotImplementedError` | `asyncio.to_thread(subprocess.run, ...)` |
| `alembic.ini` | `UnicodeDecodeError` | 保持纯 ASCII |
| Cookie `Secure` | 本地 http 登录后立刻掉登录 | 本地 `AUTH_COOKIE_SECURE=false` |
| 刷新令牌轮转 | 并发 401 后被踢 | 前端单飞续期；不要绕过 `client.ts` |
| 环境变量遮蔽指纹 | 文件写了但指纹没变 | 检查容器 `FINGERPRINT_*` |
| 内核台账悬空 | 页面版本与启动报错不一致 | `resolve_image` 回退 + `adopt_pulled` |
| seed 写演示数据 | 部署库被污染 | 演示数据只在 `tests/demo_cluster.py` |
| 删实例留卷 | `wv-data-*` 越积越多 | 设计如此；人工确认后清理 |
| HTTPS + noVNC | iframe 被混合内容拦截 | 给 noVNC 单独 TLS 或内网 http |
| Git 推送 | TLS 被代理断连 | 用可用代理：`git -c http.proxy=... -c https.proxy=... push` |

## 10. 术语表

| 术语 | 含义 |
|---|---|
| 实例 / browser | 一台浏览器运行时：容器 + 卷 + 端口 + 资源绑定 |
| 内核 / kernel | 浏览器引擎镜像（CloakBrowser、fingerprint-chromium、ungoogled 等） |
| 指纹 / fingerprint | 一组人格参数；`seed` 是内核生成人格的输入 |
| 出口 / IP | 实例出网用的代理；`direct` 表示直连 |
| 绑定流水 | `browser_*_bindings`，只追加的操作日志 |
| 台账 | `kernels` 表；版本真相在本地镜像 |
| stale | 实例钉在旧内核版本上，未迁移 |
| noVNC | 通过浏览器看实例画面的 Web 客户端 |
| CDP | Chrome DevTools Protocol，Playwright 用它接管实例 |
| 工作区 | 成员与资源的逻辑分组（`workspaces`） |
| 平台账号 | `accounts`，Amazon / TikTok 等业务账号，不是控制台成员 |

## 11. 交付前检查清单

- [ ] 只改了任务要求的范围，没有顺手重构/加功能
- [ ] 没有动已定版页面（除非用户明确要求）
- [ ] 后端 `ruff check` 干净，相关测试通过
- [ ] 前端 `typecheck` + `build` 通过
- [ ] 表结构变更走 Alembic，`alembic check` 无差异
- [ ] 新写接口有权限点与审计
- [ ] 新字段/表有中文注释
- [ ] 接口/配置/行为变化同步更新了 `docs/`
- [ ] 涉及容器/部署时真机验证过（不只是单元测试）
- [ ] 交付说明里写清：改了什么、怎么验证、还有什么风险

## 12. 不要做的事

- 不要执行 `docker compose down -v`、`rm -rf`、清空数据库，除非用户明确要求并确认备份。
- 不要删除 `.workbuddy/`（项目数据与记忆）。
- 不要重置用户的开发库、覆盖未提交改动、强推 Git。
- 不要为了「跑通」而 mock 掉真实校验（权限、审计、端口探测）。
- 不要把演示数据写进 `seed.py`。
- 不要凭记忆改字段名：先读 `schemas` 与 `types/domain.ts`。
