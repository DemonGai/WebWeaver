# 10 · 开发

## 1. 环境要求

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | 3.12+ | 后端 |
| [uv](https://docs.astral.sh/uv/) | 最新 | 依赖与虚拟环境 |
| Node.js | 20+ / npm 10+ | 前端 |
| Docker | 24+，compose v2 | 数据库、实例容器、部署 |
| Git | 2.40+ | 版本控制 |

可选：`bun`（本地更快的包管理）、Edge / Chrome（`scripts/ui-check.mjs` 截图）。

## 2. 首次启动

```bash
# 1) 数据库
docker compose --profile dev up -d postgres
docker compose ps                       # webweaver-postgres 应为 Up (healthy)

# 2) 后端
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.services.seed
uv run uvicorn app.main:app --reload --port 8010

# 3) 前端（新终端）
cd frontend
npm ci
npm run dev                             # http://127.0.0.1:5173
```

默认账号 `admin / admin`。开发库连接串
`postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver`。

一键启动（Git Bash）：

```bash
bash scripts/dev.sh                     # [api] 8010 + [web] 5173，Ctrl+C 一起停
API_PORT=8020 WEB_PORT=5180 bash scripts/dev.sh
```

`scripts/dev.mjs` 是等价的 Node 版本，需要 `bun scripts/dev.mjs` 或 `node scripts/dev.mjs`。

## 3. 命令速查

| 目的 | 命令 |
|---|---|
| 装依赖 | `uv sync` / `npm ci` |
| 加后端依赖 | `uv add <pkg>` |
| 迁移到最新 | `uv run alembic upgrade head` |
| 生成迁移 | `uv run alembic revision --autogenerate -m "说明"` |
| 检查模型与库 | `uv run alembic check` |
| 初始化数据 | `uv run python -m app.services.seed` |
| 跑 API | `uv run uvicorn app.main:app --reload --port 8010` |
| 后端 lint | `uv run ruff check .` |
| 后端格式 | `uv run ruff format .` |
| 后端测试 | `uv run pytest` |
| 前端类型检查 | `npm run typecheck` |
| 前端构建 | `npm run build` |
| 一键开发 | `bash scripts/dev.sh` |

## 4. 测试

### 4.1 结构

| 文件 | 覆盖 |
|---|---|
| `tests/test_models.py` | 表结构、注释、约束、枚举 |
| `tests/test_auth.py` / `test_tokens.py` | 登录、注册、锁定、令牌轮转、重放 |
| `tests/test_api.py` | 总览、浏览器池、账号、IP、指纹、noVNC 的读接口 |
| `tests/test_browser_pool.py` | 实例增删改、启停、端口、绑定、批量 |
| `tests/test_accounts*.py` / `test_ip_import.py` | 导入解析、平台识别、检测 |
| `tests/test_fingerprints_api.py` / `test_fingerprint_caps.py` | 指纹能力矩阵、下发参数 |
| `tests/test_kernels_api.py` / `test_kernel_scan.py` | 镜像 tag 解析、版本合并、迁移 |
| `tests/test_rbac.py` / `test_audit.py` / `test_user.py` | 权限、审计、个人中心 |

### 4.2 数据库依赖

- `conftest.py` 在导入 `app` **之前**设置 `DB_POOL_DISABLED=true`。原因：`TestClient`
  不进入上下文管理器时每个请求都会新建事件循环，池化连接跨循环会抛
  `Event loop is closed`。
- `seeded_database` 夹具先跑 `seed()`，再跑 `tests/demo_cluster.py` 写入演示集群；
  每张表已有数据就跳过，所以重复跑不会叠加。
- 数据库连不上时，依赖它的用例 `pytest.skip`；认证、内核扫描等纯内存用例照常跑。
- 测试结束会删除 `ip_address = 'testclient'` 的审计记录，避免开发库越堆越多。

### 4.3 用临时库跑全量（推荐）

直接对开发库跑测试会写入演示数据。更干净的做法是建一个临时库：

```bash
docker exec webweaver-postgres psql -U webweaver -d postgres \
  -c "DROP DATABASE IF EXISTS webweaver_probe" \
  -c "CREATE DATABASE webweaver_probe"

cd backend
export DATABASE_URL="postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver_probe"
uv run alembic upgrade head
uv run pytest -q
unset DATABASE_URL

docker exec webweaver-postgres psql -U webweaver -d postgres \
  -c "DROP DATABASE IF EXISTS webweaver_probe"
```

当前全量 200 余条用例。CI 里没有 PostgreSQL 服务，数据库类用例会自动 skip，因此
**CI 绿不等于全量绿**；合并前建议本地用临时库跑一遍。

## 5. 静态检查与 CI

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest -q

cd ../frontend
npm run typecheck
npm run build
```

`.github/workflows/ci.yml`：

- **backend**：`uv sync --frozen --group dev` → `ruff check` → `ruff format --check` → `pytest`；
- **frontend**：`npm ci` → `typecheck` → `build`，产物作为 artifact 留存 7 天；
- **ci**：汇总任务 `CI Success`，分支保护只勾这一项。

路径过滤：`**/*.md`、`docs/**`、`.gitignore`、`LICENSE` 的改动不触发 CI。

## 6. 提交规范

Conventional Commits，scope 用模块名：

```
feat(browser): 实例容器名改用实例 ID
fix(kernel): 拉取后校正悬空版本
refactor(overview): 重做主卡信息层级
docs: 补部署与 AI 操作手册
chore(git): Dockerfile 与 docker/ 脚本钉 LF
```

约定：

- 一个提交只做一件事；格式化与逻辑改动分开；
- 提交前跑 lint / typecheck（至少改到哪边跑哪边）；
- 迁移脚本与模型改动必须同一个提交；
- 不提交 `.env`、dump、日志、`browser_engine/*/` 下的二进制。

## 7. 换行符与文件编码

`.gitattributes` 把 `Dockerfile`、`docker/**` 钉成 LF：

```
Dockerfile text eol=lf
docker/** text eol=lf
*.sh text eol=lf
```

原因：Windows 检出后 CRLF 会让容器里的 `sh` 报 `\r: not found`。Python / TypeScript 源码
不强制，Git 默认处理即可。

`alembic.ini` 必须是纯 ASCII：Windows 下 alembic 按 GBK 读 ini，中文注释会直接
`UnicodeDecodeError`。

## 8. Windows 注意事项

| 问题 | 处理 |
|---|---|
| 控制台中文乱码 | `scripts/dev.sh` 已设 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`；手工跑时也设 |
| `uv` 不在 PATH | 用绝对路径，或在 `scripts/dev.sh` 里改 `UV` |
| 端口被 Docker Desktop 占用 | 8000/8080 常被 `com.docker.backend.exe` 占；开发用 8010 |
| 端口探测误判空闲 | docker-proxy 用 `SO_REUSEADDR`，纯 `bind` 不可靠；代码用 `connect_ex` + `bind` 双检 |
| `asyncio.create_subprocess_exec` 报 `NotImplementedError` | Windows 的 SelectorEventLoop 不支持；统一 `asyncio.to_thread(subprocess.run, ...)` |
| Git 推送走代理失败 | 用 `git -c http.proxy=... -c https.proxy=... push`；Git 的 TLS 与某些代理不兼容 |
| 文件路径含中文 | 尽量用绝对路径 + 引号；Python 侧统一 `Path` |

## 9. 开发流程建议

1. **先读**：改哪个模块先读 `docs/` 对应一篇，尤其是「设计取舍」和「常见故障」；
2. **先复现**：界面问题用 `scripts/ui-check.mjs` 或浏览器截图；接口问题用 `curl` + Cookie；
3. **小步改**：后端先改 schema/service，再改路由；前端先改类型与接口，再改页面；
4. **验证**：后端 `ruff` + 目标测试；前端 `typecheck` + `build`；涉及容器/迁移时跑真机；
5. **写文档**：行为、接口、配置有变化时同步更新 `docs/`。

## 10. 文档维护

- 新增模块：在 `docs/` 补一篇，并在 `docs/README.md` 的文档地图登记；
- 修改接口：更新 `docs/07-api-reference.md`；
- 修改部署方式 / 环境变量：更新 `docs/09-deployment.md`；
- 修改不变量 / 验证方式：更新 `docs/11-ai-guide.md`；
- 文档里的路径、命令必须能直接执行；不要写「示例域名」这类不可复现的内容。

## 11. 常见开发故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `uv run alembic` 报连不上库 | 开发库没起 / `.env` 连接串错 | `docker compose --profile dev up -d postgres` |
| 迁移报 `Target database is not up to date` | 本地库落后 | `alembic upgrade head` 后再生成 |
| 前端 401 循环 | Cookie 没带上 / `VITE_API_BASE_URL` 指向错 | 用 Vite 代理；检查 Network 里的 `wv_at` |
| `npm ci` 报 rollup 平台包缺失 | 锁文件在别的平台生成 | 本地 `npm install` 重新生成锁文件，或删 `node_modules` 重装 |
| 测试写脏开发库 | 直接对开发库跑了 pytest | 用临时库（见 4.3），或接受演示数据 |
| Docker 构建极慢 | apt / npm / pip 走外网 | 用默认清华源；npm 配国内 registry |
