# WebWeaver · 浏览器集群控制台

前后端分离的浏览器集群管理控制台。前端 **React + Vite + TypeScript + Tailwind CSS v4**，后端 **Python 3.12+ / FastAPI**，包管理使用 **uv**。

页面按 Calicat 设计稿还原（设计文件 `2115610777576079360`），共 10 个页面：控制台 5 页 + 指纹库列表 + 内核管理 + 账号安全 3 页。导航为 6 项（总览 / 浏览器池 / 账号池 / IP 池 / 指纹库 / 内核管理）。

## 目录结构

```
WebWeaver/
├── frontend/                     # 前端工程（独立 npm 项目）
│   ├── index.html
│   ├── package.json
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
│       ├── pages/                # 控制台 5 页 + 指纹库 + auth/ 三页 + 占位页 + 404
│       └── types/domain.ts       # 与后端 schema 对应的类型
└── backend/                      # 后端工程（uv 管理）
    ├── pyproject.toml            # 依赖 + 清华源 + ruff/pytest 配置
    ├── uv.lock
    ├── .env.example
    ├── app/
    │   ├── main.py               # 应用工厂 + CORS + 路由挂载
    │   ├── core/config.py        # pydantic-settings 配置
    │   ├── api/router.py         # 路由汇总
    │   ├── api/routes/           # health / overview / browsers / accounts / ip_pool / novnc / fingerprints / kernels / account
    │   ├── schemas/domain.py     # Pydantic 模型
    │   └── services/mock_data.py # 演示数据（接真实集群时替换此处）
    └── tests/test_api.py
```

## 启动

### 后端（端口 8010）

> 端口用 8010 而非 8000：本机 Docker Desktop 的 `com.docker.backend.exe` 已占用 8000/8080。

```bash
cd backend
uv sync                                  # 首次：创建 .venv 并安装依赖
uv run uvicorn app.main:app --reload --port 8010
```

- 接口文档（Swagger UI）：http://127.0.0.1:8010/docs
- 备用文档（ReDoc）：http://127.0.0.1:8010/redoc
- OpenAPI 描述：http://127.0.0.1:8010/openapi.json
- 新增依赖：`uv add <pkg>`；同步环境：`uv sync`

### 前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

其他脚本：`npm run build`（生产构建）、`npm run typecheck`（类型检查）。

### 后端测试

```bash
cd backend
uv run pytest
```

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/overview` | 集群总览（集群指标、负载、活跃实例、实时事件、趋势） |
| GET | `/api/browsers` | 浏览器池（统计、实例卡片、筛选项） |
| GET | `/api/accounts` | 账号池（统计、账号卡片、平台筛选） |
| GET | `/api/ip-pool` | IP 池（资源明细、区域分布、供应商健康、轮换策略） |
| GET | `/api/novnc/{instance_id}` | noVNC 会话详情（状态、账号、出口 IP、指纹、操作日志） |
| GET | `/api/fingerprints` | 指纹模板列表（筛选计数、伪装项、唯一性、使用实例） |
| GET | `/api/kernels` | 内核管理页数据（4 套内核引擎、检测覆盖、版本镜像、兜底链路、分发进度、更新记录） |
| POST | `/api/kernels/{kernel_id}/primary` | 将某套内核设为主力（进程内状态，返回最新主力） |
| GET | `/api/kernels/upgrade-options` | 内核切换弹窗选项（目标内核、实例分组、分批策略、开关默认值） |
| POST | `/api/kernels/upgrade` | 创建内核切换任务，校验内核可用性与分组必选 |
| GET | `/api/account/menu` | 头像浮层的用户信息与菜单分组 |
| GET | `/api/auth/workspaces` | 找回密码页的工作区下拉 |
| GET | `/api/auth/captcha` | 下发图形验证码（进程内保存，120 秒有效） |
| POST | `/api/auth/forgot-password` | 校验邮箱与验证码并"发送"重置邮件，返回有效期 |
| POST | `/api/auth/resend-reset` | 重新发送，返回新的倒计时 |
| POST | `/api/auth/reset-password` | 校验密码规则与两次输入一致性，返回强度与下线会话数 |

## 前后端联调约定

- 前端请求统一走 `/api` 前缀，开发期由 Vite 代理到 `http://127.0.0.1:8010`，不产生跨域问题。
- 后端路由统一挂在 `settings.api_prefix`（默认 `/api`）下；新增业务在 `backend/app/api/routes/` 建模块，再于 `api/router.py` 注册。
- 生产环境用 `VITE_API_BASE_URL` 指向真实后端域名，同时配置后端 `CORS_ORIGINS`。
- 字段命名：后端 snake_case，前端类型同名对应（`types/domain.ts` ↔ `schemas/domain.py`），不做自动转换，保持两侧一眼可对。

## 页面

| 路由 | 页面 | 数据来源 |
|---|---|---|
| `/` | 集群总览 | `/api/overview` |
| `/browsers` | 浏览器池 | `/api/browsers` |
| `/accounts` | 账号池 | `/api/accounts` |
| `/ip-pool` | IP 池 | `/api/ip-pool` |
| `/novnc/:id` | noVNC 实时视图 | `/api/novnc/{id}` |
| `/fingerprints` | 指纹库列表视图（筛选、搜索、唯一性、分页） | `/api/fingerprints` |
| `/kernels` | 内核管理（CloakBrowser / Camoufox / fingerprint-chromium / ungoogled-chromium 四套引擎，表格 + 展开版本镜像） | `/api/kernels` |
| `/forgot-password` | 找回密码（工作区 + 邮箱 + 图形验证码） | `/api/auth/*` |
| `/reset-email-sent` | 重置邮件已发送（倒计时、重发） | `/api/auth/*` |
| `/reset-password` | 设置新密码（强度条 + 规则校验） | `/api/auth/*` |

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

- [ ] 把 `services/mock_data.py` 换成真实调度系统的查询
- [ ] 内核镜像的实际上传/校验、分批执行器尚未接入，目前为演示数据
- [ ] 内核与实例的绑定关系仍为静态演示值，未与浏览器池数据打通
- [ ] 账号安全三页目前接的是演示接口，真实的邮件投递与令牌校验待接入
- [ ] 实例操作（新建/接管/重连）接入真实接口
