# 08 · 前端

## 1. 技术栈

| 项 | 版本 / 选型 | 说明 |
|---|---|---|
| 框架 | React 19 | 函数组件 + Hooks，无状态管理库 |
| 构建 | Vite 6 | 开发代理 `/api` → `127.0.0.1:8010` |
| 语言 | TypeScript 5.7 | 严格模式，提交前 `tsc --noEmit` |
| 样式 | Tailwind CSS v4 | `@theme` + CSS 变量，无 UI 框架 |
| 路由 | React Router 7 | `BrowserRouter`，路由表在 `App.tsx` |
| 交互 | Headless UI 2 | 只用于少量无样式组件（如菜单） |
| 图标 | 内联 SVG | `components/icons.tsx`，不引图标包 |

没有 Redux / Zustand / React Query：页面级数据用 `useApi`，跨页状态只有登录态
（`AuthProvider`）。

## 2. 命令

```bash
cd frontend
npm ci              # 首次 / 锁文件变更后
npm run dev         # http://localhost:5173
npm run typecheck   # tsc --noEmit
npm run build       # 产物在 dist/
npm run preview     # 预览构建产物
```

仓库里同时存在 `package-lock.json` 与 `bun.lock`。CI 用 npm，Docker 构建也用 npm，
**以 npm 为准**；bun 只作为本地可选加速。

## 3. 目录

```
src/
├── main.tsx              # createRoot + BrowserRouter + AuthProvider
├── App.tsx               # 路由表与守卫分组
├── index.css             # Tailwind、设计令牌、少量全局样式
├── api/
│   ├── client.ts         # fetch 封装、ApiError、401 单飞续期
│   └── endpoints.ts      # 所有接口函数
├── auth/
│   ├── AuthProvider.tsx  # 登录态、静默续期、跨标签同步
│   └── guards.tsx        # RequireAuth / PublicOnly
├── hooks/useApi.ts       # loading / success / error + reload / refresh
├── lib/
│   ├── clipboard.ts      # 复制（带降级）
│   └── format.ts         # 时间、剩余时长格式化
├── components/           # 布局、UI 套件、弹窗、表单、图标
├── pages/                # 业务页 + auth/ + settings/
└── types/domain.ts       # 与后端 schema 对齐的类型
```

## 4. 路由

| 路径 | 页面 | 守卫 | 数据来源 |
|---|---|---|---|
| `/` | 总览 | 登录 | `/api/overview?range=` |
| `/browsers` | 浏览器池 | 登录 | `/api/browsers` + options |
| `/accounts` | 账号管理 | 登录 | `/api/accounts` |
| `/ip-pool` | 代理管理 | 登录 | `/api/ip-pool` |
| `/novnc` | noVNC 控制台（自动选一台） | 登录 | `/api/browsers/novnc` |
| `/novnc/:id` | noVNC 控制台（指定实例） | 登录 | 同上 |
| `/fingerprints` | 指纹管理 | 登录 | `/api/fingerprints` |
| `/kernels` | 内核管理 | 登录 | `/api/kernels` |
| `/kernels/:slug` | 内核详情 | 登录 | `/api/kernels/{slug}` |
| `/settings/profile` | 个人信息 | 登录 | `/api/user/profile` |
| `/settings/security` | 账号安全 | 登录 | `/api/user/security` |
| `/settings/sessions` | 登录设备 | 登录 | `/api/user/sessions` |
| `/settings/audit-logs` | 我的操作日志 | 登录 | `/api/user/audit-logs` |
| `/login` | 登录 | 仅匿名 | `/api/auth` |
| `/forgot-password` | 找回密码 | 仅匿名 | `/api/auth` |
| `/reset-email-sent` | 重置邮件已发送 | 仅匿名 | `/api/auth` |
| `/reset-password` | 设置新密码 | 仅匿名 | `/api/auth` |
| `*` | 404 | — | — |

守卫行为：

- `RequireAuth`：`checking` 显示启动画面；未登录跳 `/login`，把原路径放进 `state.from`，
  登录后送回去。
- `PublicOnly`：已登录访问登录/找回页时送回 `/`，避免后退键看到没用的表单。
- `ErrorBoundary` 以 `location.pathname` 为 key：切页即重建，一页报错不会一直卡在错误页。

## 5. 请求层

### 5.1 `api/client.ts`

- `BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'`；
- 所有请求 `credentials: 'include'`，令牌在 httpOnly Cookie 里；
- 非 2xx 抛 `ApiError(status, message, payload)`，`message` 优先取 `payload.message` /
  `payload.detail` / `detail[0].msg`；
- **401 自动续期一次**：`refreshOnce()` 单飞，成功后重放原请求；失败广播
  `auth:expired`，由 Provider 切匿名态；
- `api.raw()` 不自动续期，认证接口自己用，避免 401 → refresh → 401 递归；
- `api.text()` 取纯文本（CSV 模板），不走 JSON 解析。

单飞续期不是优化，是正确性要求：刷新令牌轮转，如果 6 个并发请求各发一次 refresh，
后 5 个会被判定为重放，整场会话被吊销。

### 5.2 `endpoints.ts`

所有接口集中在这里，页面不直接 `fetch`。新增接口时：

1. 在 `types/domain.ts` 加类型（与后端 schema 同名同形）；
2. 在 `endpoints` 里加一个函数；
3. 页面通过 `useApi(() => endpoints.xxx(), deps)` 使用。

### 5.3 `useApi`

```ts
const { data, status, error, reload, refresh } = useApi(() => endpoints.browsers(), [])
```

- `reload`：回到 `loading`，用于首屏、切筛选、失败重试；
- `refresh`：保留旧数据，成功才替换；用于轮询（总览 30 秒一次），避免每半分钟闪骨架屏；
- 组件卸载后不再 setState（内部 `cancelled` 标记）。

## 6. 登录态

`AuthProvider` 维护 `status: 'checking' | 'authenticated' | 'anonymous'`：

1. 启动调 `GET /api/auth/session`（未登录是 200 + `authenticated:false`，不触发续期）；
2. 访问令牌剩余 < 5 分钟时调 `/auth/refresh`，每 30 秒检查一次；
3. 监听 `auth:expired` 事件切匿名；
4. 退出时往 `localStorage` 写 `wv_signed_out_at` 时间戳，其他标签监听 `storage` 事件同步退出。

`useAuth()` 暴露 `status` / `user` / `session` / `signIn` / `signOut` / `reload` / `renew`。
页面需要权限判断时读 `user.permissions`，但只用于隐藏按钮，不当作安全边界。

## 7. 页面

### 7.1 总览 `/`

四层信息结构，刻意做出主次：

1. **深色主卡**：健康分、在线 / 未运行、平均延迟、帧率、分段容量条；右栏「需要处理」
   取 `health_parts` 中 score < 90 的项，点击跳对应页面；
2. **资源水位**：一张卡 6 格（实例 / 账号 / 出口 / 指纹等），不抢主卡视觉；
3. **活跃实例表 + 最近操作**：两栏等高，展示当前实例与审计事件；
4. **趋势图**：置底，按 `24h / 7d / 30d` 切换，数据来自审计活跃度。

30 秒静默刷新一次（`refresh`，不闪骨架）。页头没有「新建实例」按钮——总览是查看面，
入口在浏览器池。延迟与帧率目前是占位读数（见 05），不要把它们当作真实监控指标。

### 7.2 浏览器池 `/browsers`

- 卡片 / 列表两种视图；卡片主按钮只做电源（启动 / 停止），noVNC 是独立常驻按钮；
- 勾选后出现批量操作条（启动 / 停止 / 重启），最多 200 台；
- 「新建 / 编辑」用 `BrowserDialog`：内核选择会带出「是否支持指纹」，不支持时隐藏指纹栏；
- 「复制」沿用内核与备注，不复制账号 / 出口 / 指纹（避免两台实例抢同一账号）；
- 复制 CDP 地址、跳 noVNC、删除（运行中会提示先停止）。

### 7.3 noVNC `/novnc/:id`

左右分栏：左侧 318px 实例列表（搜索 + 状态分段筛选，选中行有墨色竖条），右侧 iframe。
切换实例只换右侧地址，不离开页面。

- 顶部：名称 / ID / 状态 chip / 端口 / 重载 / 新窗口；
- 底部：内核 / 版本 / 账号 / 出口 / 分组 / 镜像；
- 不可接管时按 `availability` 原地说明，并提供「启动实例」；
- 高度 `lg:h-[calc(100vh-156px)]`，小屏退化为纵向。

### 7.4 账号 `/accounts`

统计条 + 平台筛选 + 搜索；账号卡片展示状态、健康度、绑定实例、登录地址。
`AccountDialog` 新建/编辑，`AccountImportDialog` 粘贴导入并展示逐行结果。
详情里可查看 Cookie（明文只在单条详情接口返回）。

### 7.5 代理 `/ip-pool`

按地区 / 供应商聚合；表格展示地址、协议、类型、延迟、健康度、绑定实例。
`IpImportDialog` 支持 CSV / URL / 冒号格式；「检测」逐条 TCP 探测并回写状态；
密码默认隐藏，可切换显示与复制。

### 7.6 指纹 `/fingerprints`

列表 + 能力筛选；`FingerprintDialog` 按 `GET /capabilities` 动态显示字段（不是所有内核
都支持 `platform_version` / `brand` / `hardware_concurrency`）；`FingerprintDrawer`
展示下发参数、实测人格、「采集」与「下发到实例」。

### 7.7 内核 `/kernels` 与 `/kernels/:slug`

- 列表：四张引擎卡片，显示本地版本、当前版本、实例数、stale 数、镜像体积；
  「拉取镜像」弹窗轮询任务进度；「批量迁移」只对已安装版本开放；
- 详情：版本清单、平台选择、`docker run` 示例、镜像信息、`browser_engine/<slug>/README.md`
  正文（`Markdown` 组件渲染，支持表格）。

### 7.8 个人中心 `/settings/*`

- 个人信息：只能改显示名；登录名与邮箱不开放自助修改；
- 账号安全：改密入口、失败次数与锁定、在线设备数、最近认证事件；
- 登录设备：标记本机、踢设备（踢当前等于退出）、显示下线原因；
- 我的操作日志：按动作 / 结果筛选、分页。

### 7.9 账号安全页 `/login` 等

登录、找回密码、邮件已发送、设置新密码。图形验证码走 `/api/auth/captcha`；
密码强度条与规则来自后端 `checks`，不在前端硬编码。

## 8. 组件

| 组件 | 用途 |
|---|---|
| `Layout.tsx` | `Header`（Logo / 导航 / 搜索 / 通知 / 用户菜单）、`PageHeader`、`PageShell` |
| `ui.tsx` | `Card` / `SectionHeader` / `StatusDot` / `SoftChip` / `OutlineChip` / `ProgressBar` / `StatCard` / `HeroCard` / `Checkbox` / `SearchInput` / `PillTabs` / `AreaChart` / `BarDistribution` |
| `StatTile.tsx` | 页头下的统计卡（内核管理、指纹管理共用） |
| `Modal.tsx` | 弹窗外壳：遮罩、Esc、锁滚动、页脚插槽 |
| `Toast.tsx` | 右下角悬浮通知（4 秒消失） |
| `Select.tsx` / `SelectMenu.tsx` | 下拉选择 |
| `fields.tsx` | `Field` / `IconInput` / `SelectField` / `CaptchaBox` |
| `BrowserDialog` / `AccountDialog` / `FingerprintDialog` / `KernelMigrateDialog` 等 | 业务弹窗 |
| `FingerprintDrawer.tsx` | 指纹详情抽屉 |
| `Markdown.tsx` | 极简 Markdown（标题 / 列表 / 代码 / 引用 / 表格），纯 React 元素，无 XSS |
| `IdBadge.tsx` | 短 ID 展示，点击复制完整 UUID |
| `ErrorBoundary.tsx` | 页面级错误边界 |

## 9. 设计令牌

定义在 `src/index.css`：

| 用途 | 值 |
|---|---|
| 页面背景 | `--color-canvas: #fafafa` |
| 主文字 / 次文字 / 弱文字 | `--ink-900: #18181b` / `--ink-500: #71717a` / `--ink-400: #a1a1aa` |
| 分隔线 | `--line: #ececf0` |
| 深色主卡渐变 | `#192236 → #283448` |
| 导航激活 | `#18181b` |
| 语义色 | emerald `#10b981`、blue `#3b82f6`、violet `#8b5cf6`、amber `#f59e0b`、rose `#f43f5e` |

约定：

- 优先用 `var(--ink-*)` / `var(--line)`，不要新造近似灰；
- 数字统一加 `.tnum`（等宽字形），避免刷新时跳动；
- 卡片圆角 16px（`--radius-card`），内边距与字号按现有页面取，不另起一套；
- 状态色与文案集中在各页的 `meta` 映射里，新增状态先补映射再渲染。

## 10. 新增一个页面

1. `src/pages/XxxPage.tsx`，用 `PageShell` + `PageHeader`，数据用 `useApi`；
2. `App.tsx` 在 `RequireAuth` 分组里加 `<Route path="/xxx" element={<XxxPage />} />`；
3. `components/Layout.tsx` 的 `NAV` 加导航项（图标从 `icons.tsx` 取），并在
   `SEARCH_HINT` 补搜索占位文案；
4. `types/domain.ts` 补类型，`api/endpoints.ts` 补接口函数；
5. 跑 `npm run typecheck` 与 `npm run build`，用 1500 / 1280 两档宽度看布局。

## 11. 构建与环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | 生产环境指向真实后端；同源部署留空即可 |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8010` | 开发期 Vite 代理目标 |

构建产物 `dist/` 由三种方式提供：

- 单容器：`FRONTEND_DIST=/app/frontend/dist`，FastAPI 托管；
- 静态服务器 + 反代 `/api`；
- 本地 `npm run preview`。

单容器模式下 SPA 兜底由 `main.py` 处理：非 `/api`、非静态文件的路径都返回 `index.html`。

## 12. 已知边界

- 页头搜索框与通知按钮目前是**占位**，没有接查询与通知数据；各页面用自己的 `SearchInput`。
- 没有全局状态管理，跨页共享只靠 `AuthProvider`；页面切换会重新拉数据。
- 没有虚拟列表，实例 / 账号数量在千级以内表现正常；再大需要分页或虚拟滚动。
- 没有 i18n，文案直接写在组件里。
- 前端隐藏按钮不等于权限控制，服务端仍然校验写接口。
- noVNC 用 `http://` iframe；控制台上 HTTPS 时会被混合内容策略拦截（见 05 / 09）。
