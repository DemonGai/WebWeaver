# 02 · 后端

## 1. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| Web | FastAPI ≥ 0.115 | 同步风格的 `async def` 路由，OpenAPI 自动生成 |
| 运行时 | Python 3.12+ / uvicorn | `uvicorn[standard]`，容器内 `--proxy-headers` |
| ORM | SQLAlchemy 2.0 async + asyncpg | 会话由 `get_session` 依赖提供 |
| 模型 | SQLModel | 表定义与 Pydantic 共用一套字段声明 |
| 迁移 | Alembic（异步模板） | 元数据来自 `SQLModel.metadata` |
| 配置 | pydantic-settings | `.env` + 环境变量，字段即文档 |
| 日志 | loguru | 控制台 + 文件 + ELK JSON，统一带 `request_id` |
| 包管理 | uv | `uv sync` / `uv add` / `uv run` |

后端**没有**：Celery、Redis、任务队列、缓存层、ORM 二级缓存。当前规模用不上，引入后
每个部署都多一个必须维护的组件。

## 2. 启动过程

`app/main.py` 的 `create_app()` 做四件事：

1. 创建 `FastAPI`（`docs_url="/docs"`、`redoc_url="/redoc"`）；
2. 挂 CORS（`settings.cors_origins`）与 `RequestLogMiddleware`；
3. `include_router(api_router, prefix=settings.api_prefix)`；
4. 如果配了 `FRONTEND_DIST` 且目录里有 `index.html`：挂 `/assets` 静态目录，其余路径
   回落到 `index.html`（SPA 路由刷新不 404）；没配则只提供 API，`/` 返回服务信息。

`lifespan` 在启动时探测 PostgreSQL：

- 连上：打印 `server_version`；`DB_AUTO_CREATE=true` 时按模型建表，否则读
  `alembic_version` 并提示当前版本；
- 连不上：只打印 warning，**服务照常启动**。这样数据库晚于应用启动时，健康检查与
  静态页面仍然可用，运维能看到真实原因而不是一个起不来的容器。

关闭时 `engine.dispose()`。单容器模式下由 `entrypoint.sh` 先停 uvicorn 再停 PostgreSQL。

## 3. 分层与文件

```
app/
├── main.py                 应用工厂、lifespan、SPA 托管
├── api/
│   ├── deps.py             SessionDep / CurrentUser / require_permission / bearer_token
│   ├── router.py           汇总 12 个路由模块
│   └── routes/             health overview browsers accounts ip_pool novnc
│                           fingerprints kernels auth audit rbac user
├── core/
│   ├── config.py           Settings（全部环境变量）
│   ├── db.py               异步引擎、会话工厂、ping / revision / create_all
│   ├── security.py         scrypt 密码、JWT 签发与校验、令牌摘要
│   ├── cookies.py          wv_at / wv_rt 的读写与清除
│   ├── logging_config.py   loguru 配置、request_id contextvar
│   └── middleware.py       请求日志
├── models/                 18 张表 + 枚举（见 03）
├── schemas/                请求 / 响应 / 展示模型
└── services/               业务实现（见下表）
```

| 服务 | 职责 |
|---|---|
| `cluster.py` | 读快照 + 总览 / 浏览器池 / 账号 / IP / 指纹的展示拼装 |
| `browser_pool.py` | 实例新建、编辑、复制、删除、启停、批量、绑定校验、审计 |
| `browser_runtime.py` | Docker 容器生命周期、端口发布、镜像解析、代理参数 |
| `browser_novnc.py` | 镜像 noVNC 能力检测、可接管清单、画面地址 |
| `kernel_pool.py` | 内核台账 + 本地镜像 → 卡片 / 详情、切版本、迁移 |
| `kernel_scan.py` | 镜像 tag 解析、按 `image_id` 合并版本、README 读取 |
| `kernel_image.py` | `docker` 命令封装、镜像列表 / 检查 / 拉取 |
| `kernel_install.py` | 拉取任务（内存态、并发 1、进度估算） |
| `fingerprint_caps.py` | 三个内核的指纹能力矩阵与参数渲染 |
| `fingerprint_apply.py` | 写 `/data/fingerprint.json` + 重启容器 |
| `fingerprint_probe.py` | 起临时容器采集真实人格（CDP） |
| `fingerprint_pool.py` | 指纹模板 CRUD、能力查询、下发编排 |
| `account_pool.py` | 账号 CRUD、CSV 解析与导入、平台识别、Cookie 规范化 |
| `ip_pool.py` | 代理 CRUD、CSV 解析与导入、TCP 可达性检测 |
| `auth_service.py` | 登录 / 注册 / 注销 / 改密 / 找回密码 / 会话轮转 |
| `rbac.py` | 权限判断、角色与权限目录查询 |
| `user.py` | 个人中心：资料、设备、安全概览、我的审计 |
| `audit.py` | 审计写入、列表查询、活跃度分桶 |
| `browser_novnc.py` | 同上 |
| `seed.py` | 初始化：工作区、35 个权限点、4 个角色、超管、4 条内核登记 |

## 4. 路由与依赖

### 4.1 新增路由模块

```python
# app/api/routes/widgets.py（示例模块，实际不存在的表用 xxx 代替）
from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.schemas.widget import WidgetList

router = APIRouter(tags=["widgets"])          # 路径里写全，不设 prefix


@router.get("/widgets", response_model=WidgetList, summary="控件列表")
async def list_widgets(session: SessionDep, _: CurrentUser) -> WidgetList:
    ...
    return WidgetList(items=[])


# 写接口挂权限点。新模块要先在 seed.py 的 PERMISSIONS 里登记「模块 × 动作」，
# 否则只有超管能通过；这里示例复用已有权限点。
@router.post(
    "/widgets",
    response_model=WidgetList,
    summary="新建控件",
    dependencies=[Depends(require_permission("browser:create"))],
)
async def create_widget(...):
    ...
```

然后在 `app/api/router.py` 里 `api_router.include_router(widgets.router)`。
路径最终是 `/api/widgets`（`settings.api_prefix` 默认 `/api`）。

### 4.2 依赖

| 依赖 | 作用 |
|---|---|
| `SessionDep` | 每请求一个 `AsyncSession`，退出时自动关闭 |
| `CurrentUser` | 必须登录，返回 `User`；未登录 401 |
| `CurrentContext` | 登录 + 当前 `AuthSession` 行（设备管理用） |
| `OptionalUser` | 可选登录，匿名返回 `None` |
| `require_permission("browser:create")` | 先登录再查权限；超管直接放行 |
| `get_snapshot` | 一次读 6 张业务表，供读接口拼装 |

**令牌来源**：`Authorization: Bearer` 优先，其次 `wv_at` Cookie。显式 header 覆盖 Cookie，
避免「带了 header 却用了另一个身份」这种难查的问题。

**读接口不挂权限依赖**：当前写接口按模块挂 `*:create` / `*:update` / `*:delete` /
`*:execute`。**读接口的情况要特别注意**：只有 `/api/user/*` 与 `/api/auth/me` 挂了
`CurrentUser`，其余 GET（浏览器池、账号、代理、指纹、内核、审计、RBAC）目前没有登录依赖，
匿名请求也能拿到数据。这是已知安全缺口，不是设计意图；部署时不要直接暴露到公网，
修复与影响见 [04 认证](04-auth-rbac.md#84-接口侧的实际用法)。要收紧读权限，在路由上加
`CurrentUser` 与（可选的）`require_permission("xxx:read")` 即可。

### 4.3 错误处理

统一用 `HTTPException(status_code=..., detail="中文一句话")`，`detail` 直接给用户看。

| 状态码 | 场景 |
|---|---|
| 400 | 参数能解析但语义不合法（如内核版本不存在） |
| 401 | 未登录 / 过期 / 会话已吊销，带 `WWW-Authenticate: Bearer` |
| 403 | 缺少权限点 |
| 404 | 资源不存在 |
| 409 | 状态冲突（运行中删除、账号已被占用、端口分配失败） |
| 422 | Pydantic 校验失败（字段缺失 / 类型错 / 正则不匹配） |
| 503 | Docker 不可用等环境问题 |

不要返回 200 + `{"ok": false}`：前端 `api/client.ts` 只在 `res.ok` 时解析成功，会把业务
失败当成成功。

## 5. 配置

`app/core/config.py` 用 pydantic-settings，字段名即环境变量名（大小写不敏感）。完整清单见
[09 部署](09-deployment.md#4-环境变量)，这里只列分组：

| 分组 | 关键项 |
|---|---|
| 应用 | `APP_NAME` `APP_VERSION` `API_PREFIX` `DEBUG` `CORS_ORIGINS` |
| 数据库 | `DATABASE_URL` `DB_ECHO` `DB_AUTO_CREATE` `DB_POOL_DISABLED` |
| 认证 | `AUTH_*`（令牌时长、密钥、Cookie、锁定、注册开关、重置） |
| 日志 | `LOG_DIR` `LOG_LEVEL` `LOG_DIAGNOSE` |
| 内核 | `KERNEL_IMAGE_REGISTRY` `KERNEL_DOCKER_BIN` `KERNEL_IMAGE_PULL_TIMEOUT` |
| 页面 | `NOVNC_HOST` `FRONTEND_DIST` |

约定：

- 相对路径以 `backend/` 为基准（`BACKEND_ROOT`），部署时工作目录变了也不会写错地方。
- 新增配置必须给默认值，否则测试与容器启动都会因为缺环境变量失败。
- **不要**把密钥写进代码默认值后当作「生产可用」，默认值只服务本地开发。

## 6. 日志

```python
from app.core.logging_config import logger

logger.info("实例 {} 已接管", instance_id)      # 自动带 request_id
logger.opt(exception=exc).error("调度失败")      # 带堆栈
```

- 输出：控制台（彩色）、`backend/logs/app_<日期>.log`（100MB / 30 天）、
  `logs/error.log`（50MB / 90 天）、`logs/elk_<日期>.json`（100MB / 30 天）。
- `request_id` 由中间件生成（优先取 `X-Request-ID`），通过 `ContextVar` 注入，响应头回写。
- `LOG_DIAGNOSE=false` 时异常日志不含局部变量快照，避免密码 / 令牌落盘。
- uvicorn 自带访问日志已关闭，请求日志统一由中间件输出（4xx/5xx 记 WARNING）。

## 7. 代码约定

- 行宽 100（`pyproject.toml` 的 ruff 配置），`ruff check .` 与 `ruff format --check .` 必须干净。
- 全量类型标注；公共函数写 docstring，重点写**为什么**，不是复述函数名。
- 枚举用 `StrEnum`，落库用 `enum_type()`（VARCHAR + CHECK）。
- 金额、时间等跨时区数据统一存 UTC（`utcnow()`），展示时再转本地。
- 中文注释与中文错误文案是这个项目的既定风格，不要为了「国际化」改成英文。
- 不要用 `asyncio.create_subprocess_exec`：Windows 上 uvicorn 的 SelectorEventLoop 会抛
  `NotImplementedError`。统一 `asyncio.to_thread(subprocess.run, ...)`（见 `kernel_image.py`）。

## 8. 开发配方

### 8.1 给现有接口加字段

1. 改 `app/schemas/` 里的响应模型；
2. 改 `services/` 里拼装该模型的地方；
3. 改 `frontend/src/types/domain.ts` 对应类型；
4. 跑 `pytest`、`npm run typecheck`。

只加可选字段一般不影响旧客户端；删除或改名字段要先搜前端引用。

### 8.2 加一张表

1. 在 `app/models/` 新建模块，继承 `IdMixin` / `TimestampMixin`，字段写
   `sa_column_kwargs={"comment": "中文说明"}`；
2. 在 `app/models/__init__.py` 导入并加入 `__all__`；
3. `uv run alembic revision --autogenerate -m "add_xxx"`，**人工 review** 生成的脚本；
4. `uv run alembic upgrade head`，再 `uv run alembic check` 确认无差异；
5. 在 `tests/test_models.py` 补注释与约束校验（如果该测试按表遍历，会自动覆盖）。

### 8.3 加一个后台任务

当前没有任务框架。内核拉取用「内存任务表 + `asyncio.create_task` + 信号量」实现，可作为
模板：任务状态放模块级字典，接口返回 202 + job id，前端轮询。注意进程重启任务即丢，
长任务要能重入（镜像拉取本身是幂等的，重新点一次即可）。

### 8.4 调试

```bash
# 直接问接口（带 Cookie）
curl -c /tmp/wv.jar -H 'Content-Type: application/json' \
  -d '{"action":"login","account":"admin","password":"admin"}' \
  http://127.0.0.1:8010/api/auth
curl -b /tmp/wv.jar http://127.0.0.1:8010/api/browsers | python -m json.tool

# 看 SQL
DB_ECHO=true uv run uvicorn app.main:app --reload --port 8010

# 看容器
docker ps -a --filter label=webweaver.instance
docker logs <实例 ID> --tail 50
```

## 9. 测试

```bash
cd backend
uv run pytest                 # 全量
uv run pytest tests/test_auth.py -q
uv run pytest -k browsers -q
```

- `tests/conftest.py` 在导入 `app` **之前**设 `DB_POOL_DISABLED=true`：`TestClient` 不进入
  上下文管理器时每个请求新建事件循环，池化连接跨循环会抛 `Event loop is closed`。
- 数据类用例依赖 `seeded_database` 夹具：先跑 `seed()`，再跑 `tests/demo_cluster.py` 的
  演示集群；数据库连不上时 `pytest.skip`，认证 / 内核等纯内存用例照常跑。
- 演示数据只在测试里写，**不要**把它挪回 `app/services/seed.py`。

没有独立测试库时，建议建临时库跑全量，跑完删掉：

```bash
docker exec webweaver-postgres psql -U webweaver -d postgres \
  -c "DROP DATABASE IF EXISTS webweaver_probe" -c "CREATE DATABASE webweaver_probe"

cd backend
DATABASE_URL="postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver_probe" \
  uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver_probe" \
  uv run pytest -q
```

## 10. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动日志 `未检测到迁移版本` | 新库没跑迁移 | `uv run alembic upgrade head` |
| 接口 500 且日志 `Event loop is closed` | 测试里没关连接池 | 确认 `DB_POOL_DISABLED=true` 在导入 app 前设置 |
| `alembic.ini` 读取报 `UnicodeDecodeError` | ini 里有非 ASCII 字符（Windows GBK） | ini 保持纯 ASCII，中文说明放注释之外 |
| 新增字段后 `alembic check` 仍报差异 | 注释 / 默认值未纳入迁移 | 重新 autogenerate 并 review，或手工补 `COMMENT ON` |
| 写接口 403 但用户是管理员 | 权限点编码写错 | 权限编码格式 `模块:动作`，查 `seed.py` 的 `PERMISSIONS` |
