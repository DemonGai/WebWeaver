/** 领域模型：与后端 Pydantic schema 一一对应 */

export type InstanceStatus = 'running' | 'idle' | 'error' | 'stopped' | 'queued'
export type AccountStatus = 'logged_in' | 'in_session' | 'restricted' | 'unbound'
export type IpStatus = 'available' | 'in_use' | 'failed'

export interface InstanceSummary {
  id: string
  name: string
  status: InstanceStatus
  group: string
  account: string
  ip: string
  region: string
  fingerprint: string
  fps: number | null
  latency_ms: number | null
  started_at: string | null
  note: string | null
}

export interface AccountCard {
  id: string
  name: string
  /** 由登录地址推导，不是用户填的 */
  platform: string
  login_url: string | null
  status: AccountStatus
  region: string
  registered_days: number
  bound_instance: string | null
  exit_ip: string | null
  health: number
  action: string
  note: string | null
  email: string | null
  /** 列表只回条数，完整 Cookie 走详情接口 */
  cookie_count: number
}

/** Playwright storage_state.cookies 里的单条 Cookie，字段随平台不同 */
export interface AccountCookie {
  name: string
  value: string
  domain?: string
  path?: string
  expires?: number
  httpOnly?: boolean
  secure?: boolean
  sameSite?: string
  [key: string]: unknown
}

export interface AccountDetail {
  id: string
  platform: string
  login_url: string | null
  username: string
  email: string | null
  region: string
  health: number
  status: AccountStatus
  note: string | null
  cookies: AccountCookie[] | null
}

export interface AccountFormValues {
  /** 只填登录地址，平台由后端推导 */
  login_url: string
  username: string
  email?: string | null
  region: string
  health: number
  note?: string | null
  status?: AccountStatus
  /** 传 null 表示清空登录态；不传表示不动 */
  cookies?: AccountCookie[] | null
}

export interface AccountImportRequest {
  text: string
  overwrite: boolean
}

export interface PlatformDetection {
  login_url: string
  platform: string
  /** false 表示域名没收录，平台是按注册域兜底出来的 */
  known: boolean
}

export interface AccountImportRow {
  line: number
  ok: boolean
  label: string
  message: string
}

export interface AccountImportResult {
  created: number
  updated: number
  skipped: number
  failed: number
  rows: AccountImportRow[]
}

export interface IpResource {
  id: string
  ip: string
  port: number
  protocol: 'http' | 'https' | 'socks5'
  supplier: string
  region: string
  city: string
  type: '住宅' | '机房' | '移动'
  /** 代理认证；机房走 IP 白名单的那种是 null */
  username: string | null
  password: string | null
  latency_ms: number
  health: number
  status: IpStatus
  bound_instance: string | null
}

export interface ClusterEvent {
  id: string
  tone: string
  title: string
  detail: string | null
  time: string
  tag: string
}

export interface TrendPoint {
  labels: string[]
  series: number[]
  companion: number[]
}

export interface HealthPart {
  key: string
  label: string
  score: number
  weight: number
  detail: string
  tone: string
}

export type OverviewRange = '24h' | '7d' | '30d'

export interface OverviewPayload {
  range: OverviewRange
  cluster: {
    total: number
    online: number
    health: number
    updated_seconds: number
    accounts_used: number
    accounts_total: number
    ip_used: number
    ip_total: number
    avg_latency_ms: number
    novnc_fps: number
  }
  health_parts: HealthPart[]
  pool_status: { label: string; value: number; status: InstanceStatus }[]
  cards: {
    key: string
    title: string
    value: number
    unit: string
    hint: string
    progress: number
    tone: string
  }[]
  instances: InstanceSummary[]
  events: ClusterEvent[]
  trend: TrendPoint
  trend_stats: { label: string; value: string; unit: string }[]
}

export interface BrowserPoolPayload {
  totals: { running: number; total: number; delta: number }
  cards: { title: string; value: number; hint: string; tone: string; tag: string }[]
  instances: InstanceSummary[]
  filters: { key: string; label: string; count: number }[]
}

/* ── 浏览器池写操作 ───────────────────────────────────── */
export interface BrowserOption {
  id: string
  label: string
  hint: string
  disabled: boolean
}

export interface BrowserOptions {
  groups: BrowserOption[]
  kernels: BrowserOption[]
  /** 内核 id → 磁盘上已下载的版本（新到旧） */
  kernel_versions: Record<string, string[]>
  accounts: BrowserOption[]
  ips: BrowserOption[]
  fingerprints: BrowserOption[]
}

export interface BrowserDetail {
  id: string
  name: string
  status: InstanceStatus
  group_id: string | null
  group: string
  kernel_id: string | null
  kernel: string
  kernel_version: string | null
  account_id: string | null
  account: string
  ip_id: string | null
  ip: string
  ip_mode: 'proxy' | 'direct'
  region: string
  fingerprint_id: string | null
  fingerprint: string
  fingerprint_mode: 'template' | 'default'
  cdp_url: string | null
  vnc_url: string | null
  vnc_port: number | null
  fps: number | null
  latency_ms: number | null
  started_at: string | null
  last_active_at: string | null
  created_at: string
  updated_at: string
  note: string | null
}

export type BrowserActionName = 'start' | 'stop' | 'restart'

export interface BrowserMutationResult {
  ok: boolean
  message: string
}

export interface BrowserActionItem {
  id: string
  name: string
  ok: boolean
  status: string
  message: string
}

export interface BrowserBatchResult {
  ok: boolean
  action: string
  succeeded: number
  failed: number
  items: BrowserActionItem[]
}

export interface BrowserFormValues {
  name?: string
  group_id?: string | null
  kernel_id?: string | null
  kernel_version?: string | null
  account_id?: string | null
  ip_id?: string | null
  fingerprint_id?: string | null
  note?: string | null
}

export interface AccountPoolPayload {
  totals: { total: number; health: number }
  cards: { title: string; value: number; hint: string; tone: string; tag: string }[]
  accounts: AccountCard[]
  filters: { key: string; label: string; count: number }[]
}

export interface IpCheckItem {
  id: string
  ip: string
  port: number
  ok: boolean
  latency_ms: number
  message: string
}

export interface IpCheckResult {
  checked: number
  ok: number
  failed: number
  items: IpCheckItem[]
}

export interface IpImportRequest {
  text: string
  /** 清单里没写类型时用这个兜底 */
  default_kind: 'residential' | 'datacenter' | 'mobile'
  default_supplier: string
  /** 同地址端口已存在时，覆盖还是跳过 */
  overwrite: boolean
}

export interface IpImportRow {
  line: number
  ok: boolean
  label: string
  message: string
}

export interface IpImportResult {
  created: number
  updated: number
  skipped: number
  failed: number
  rows: IpImportRow[]
}

export interface IpPoolPayload {
  totals: { available: number; total: number; online_rate: number }
  cards: { title: string; value: number; hint: string; tone: string; tag: string }[]
  resources: IpResource[]
  region_distribution: { label: string; value: number; unit: string; tone: string }[]
  suppliers: { name: string; count: number; health: number }[]
  trend: TrendPoint
  rotation: {
    enabled: boolean
    items: { label: string; value: string }[]
  }
  filters: { key: string; label: string; count: number }[]
}

export interface NoVncPayload {
  instance: {
    id: string
    name: string
    status: InstanceStatus
    group: string
    connection: string
    url: string
    fps: number
    latency_ms: number
    session_time: string
    quality: string
  }
  state: { started_at: string; kernel: string; memory: string }
  account: { name: string; platform: string; region: string; tags: string[] }
  exit_ip: { ip: string; location: string; type: string; latency_ms: number }
  fingerprint: { user_agent: string; timezone: string; resolution: string; canvas_noise: boolean; score: number }
  logs: { time: string; action: string; kind: string; detail: string; result: string }[]
}

/* ── 指纹管理 ─────────────────────────────────────────── */
/** 与后端 ``PlatformFamily`` 枚举一一对应，多一个都会在渲染时取不到样式。
 *  「移动」只是筛选分组，不是平台族本身：android / ios 都算移动。 */
export type PlatformFamily = 'windows' | 'macos' | 'linux' | 'android' | 'ios'

export interface FingerprintTemplate {
  id: string
  name: string
  fp_id: string
  platform_family: PlatformFamily
  platform: string
  ua: string
  timezone: string
  language: string
  resolution: string
  dpr: string
  disguises: string[]
  /** null 表示无法评估（例如插件过期），前端显示 "—" */
  uniqueness: number | null
  warning: string | null
  instances: number
  /** 非空时操作列显示修复按钮 */
  action: string | null

  /* ── 下发与采集 ── */
  /** 决定整套人格的输入；别的字段都是它算出来的结果 */
  seed: number | null
  kernel: string | null
  kernel_slug: string | null
  /** 该内核能不能做指纹（ungoogled-chromium / Camoufox 为 false） */
  supported: boolean
  unsupported_reason: string | null
  /** 伪移动：内核人格仍是桌面，只有 UA / 视口 / DPR 换成了移动端 */
  pseudo_mobile: boolean
  /* 以下三项是采集回来的实测值，没采过就是空 */
  gpu: string | null
  canvas_hash: string | null
  probed_at: string | null
  probe_state: ProbeState
}

/** 实测值还能不能信：从没采过 / 与当前参数一致 / 参数改过没重采 / 上次失败 */
export type ProbeState = 'never' | 'fresh' | 'stale' | 'failed'

export interface FingerprintPayload {
  total: number
  kernels: number
  supported_kernels: number
  probed: number
  stale: number
  filters: { key: string; label: string; count: number }[]
  templates: FingerprintTemplate[]
  shown: number
  selected: number
  page: number
  pages: number
}

/** 按内核渲染出的下发物料：三种写法等价，用哪种看场景 */
export interface FingerprintRender {
  /** 写进容器 /data/fingerprint.json 的内容 */
  payload: Record<string, unknown>
  /** 等价的环境变量 */
  env: Record<string, string>
  /** 等价的 chrome 参数 */
  args: string[]
  /** 填了但该内核不认的字段 —— 不列出来就是静默失效 */
  ignored: string[]
}

export interface FingerprintInstanceRef {
  id: string
  name: string
  status: string
}

/** 一个内核认哪些指纹参数。前端据此决定表单里哪些字段能用。 */
export interface KernelFingerprintCaps {
  /** 内核行 ID，新建指纹时直接用它填 kernel_id */
  kernel_id: string
  slug: string
  label: string
  supported: boolean
  seed_range: [number, number] | null
  /** 与后端 fingerprint_caps 的能力名一致：seed / timezone / brand ... */
  features: string[]
  note: string
  reason: string | null
}

export interface FingerprintDetail {
  id: string
  name: string
  fp_id: string

  kernel: string | null
  kernel_slug: string | null
  supported: boolean
  unsupported_reason: string | null
  /** 伪移动：内核人格仍是桌面，只有 UA / 视口 / DPR 换成了移动端 */
  pseudo_mobile: boolean
  /** 伪移动的边界说明，真平台时为 null */
  pseudo_mobile_note: string | null
  /** 该内核指纹机制的一句话说明 */
  note: string | null

  /* 下发参数 */
  seed: number | null
  seed_range: [number, number] | null
  platform_family: PlatformFamily
  platform_version: string | null
  brand: string | null
  brand_version: string | null
  hardware_concurrency: number | null
  timezone: string
  language: string
  accept_lang: string | null
  canvas_noise: boolean
  webgl_noise: boolean
  audio_noise: boolean
  webrtc_protected: boolean

  /* 实测人格 */
  ua: string
  resolution: string
  dpr: string
  gpu: string | null
  canvas_hash: string | null
  languages: string[]
  webdriver: boolean | null
  probed_at: string | null
  probe_state: ProbeState
  probe_error: string | null
  warnings: string[]

  instances: FingerprintInstanceRef[]
  render: FingerprintRender | null
}

/** 新建 / 编辑共用：只传要改的字段 */
export interface FingerprintFormValues {
  name?: string
  kernel_id?: string | null
  platform_family?: PlatformFamily
  seed?: number | null
  platform_version?: string | null
  brand?: string | null
  brand_version?: string | null
  hardware_concurrency?: number | null
  timezone?: string
  language?: string
  accept_lang?: string | null
  canvas_noise?: boolean
  webgl_noise?: boolean
  audio_noise?: boolean
  webrtc_protected?: boolean
  code?: string | null
}

export interface FingerprintApplyItem {
  instance_id: string
  instance_name: string
  container: string
  ok: boolean
  message: string
  restarted: boolean
  ignored: string[]
}

export interface FingerprintApplyResult {
  ok: boolean
  succeeded: number
  failed: number
  items: FingerprintApplyItem[]
}

/* ── 账号安全 ─────────────────────────────────────────── */
export interface Workspace {
  id: string
  name: string
  members: number
}

export interface WorkspaceList {
  items: Workspace[]
  default_id: string
}

export interface Captcha {
  code: string
  expires_in: number
}

export interface PasswordRule {
  key: string
  label: string
  passed: boolean
}

/**
 * 认证统一响应（对应后端 schemas/auth.py::AuthResponse）。
 * 单入口一个信封，所以除了 ok/action/message 之外都是按动作可选的字段：
 * 登录 / 注册读 user 与各到期时间，找回密码读 email / cooldown，
 * 重置密码读 checks / strength / revoked_sessions。
 *
 * **令牌不在响应体里**：两个令牌都走 httpOnly Cookie，前端读不到也不需要读，
 * 只需要知道「还剩多久」来安排续期。
 */
export interface AuthResponse {
  ok: boolean
  action: string
  message: string
  /** 仅 `/auth/session` 会给出明确的是/否 */
  authenticated?: boolean | null

  user?: AuthUser | null

  /** 令牌时长（秒）：访问令牌用于安排静默续期，刷新令牌用于展示会话有效期 */
  access_expires_at?: string | null
  refresh_expires_at?: string | null
  absolute_expires_at?: string | null
  access_ttl?: number | null
  refresh_ttl?: number | null
  absolute_ttl?: number | null
  remember?: boolean | null

  /** 会话状态 */
  session_id?: string | null
  signed_in_at?: string | null
  last_seen_at?: string | null
  other_sessions?: number | null

  email?: string | null
  cooldown?: number | null
  expires_in?: number | null
  /** 仅本地联调时后端返回（AUTH_EXPOSE_RESET_TOKEN=true） */
  reset_token?: string | null

  checks?: PasswordRule[] | null
  strength?: number | null
  revoked_sessions?: number | null
}

export interface AuthUser {
  id: string
  username: string
  email: string
  display_name: string
  status: string
  is_superuser: boolean
  roles: string[]
  permissions: string[]
  last_login_at: string | null
}

/* ── 内核管理（镜像维度） ─────────────────────────────── */

/** 本地的一个版本：同一个镜像的多个 tag 会被后端合并成一条 */
export interface KernelVersion {
  version: string
  /** 首选引用用的 tag：固定 tag 优先，没有才用滚动 tag */
  tag: string
  /** 完整镜像名，如 demon1315132284/browser_engine:cloakbrowser */
  image_ref: string
  image_id: string | null
  digest: string | null
  size: string | null
  size_bytes: number
  /** 镜像构建时间（本地时区） */
  created_at: string | null
  /** 有滚动 tag 指向这个镜像，下次构建会被覆盖 */
  rolling: boolean
  /** 有固定版本 tag，可以钉住 */
  pinned: boolean
  tags: string[]
  arch: string | null
  current: boolean
  instances: number
}

export interface KernelCard {
  id: string
  slug: string
  name: string
  engine: string
  channel: string
  arch: string
  tone: string
  tagline: string
  detection_level: string | null
  repo_url: string | null
  mirror_url: string | null

  registry: string
  /** Camoufox 这类还没做镜像的为 false */
  supported: boolean
  unsupported_reason: string | null

  current_version: string | null
  current_ref: string | null
  latest_version: string | null
  update_available: boolean
  /** 本地至少有一个镜像 */
  installed: boolean
  version_count: number
  total_size: string | null
  instance_count: number
  stale_count: number
  scanned_at: string
  versions: KernelVersion[]
  note: string | null
}

export interface KernelStat {
  key: string
  label: string
  value: string
  hint: string
  tone: string
  icon: string
}

export interface KernelPayload {
  stats: KernelStat[]
  cards: KernelCard[]
  /** 镜像仓库，如 demon1315132284/browser_engine */
  registry: string
  docker_ok: boolean
  docker_error: string | null
  scanned_at: string
  total_instances: number
  total_versions: number
}

export interface KernelInstance {
  id: string
  name: string
  version: string | null
  group: string
  status: string
}

export interface KernelMigrationResult {
  ok: boolean
  version: string
  migrated: number
  message: string
}

export interface KernelDetailPayload {
  slug: string
  card: KernelCard
  versions: KernelVersion[]
  docs: string | null
  docs_path: string
  hint: string | null
  /** 可以直接复制去跑的 docker run */
  run_command: string | null
  docker_ok: boolean
  docker_error: string | null
}

export interface InstallJob {
  id: string
  slug: string
  version: string
  tag: string
  image_ref: string
  kind: string
  status: 'running' | 'success' | 'failed'
  progress: number
  message: string
  error: string | null
  started_at: string
  finished_at: string | null
}

/* ── 账号菜单 ─────────────────────────────────────────── */
export interface MenuRow {
  key: string
  label: string
  icon: string
  badge: string | null
  badge_tone: string | null
  danger: boolean
}

export interface UserMenuPayload {
  name: string
  initial: string
  email: string
  role: string
  workspace: string
  workspace_code: string
  workspace_note: string
  groups: MenuRow[][]
  last_login: string
  version: string
}

/* ── 个人中心 ─────────────────────────────────────────── */
export interface WorkspaceBrief {
  id: string
  code: string
  name: string
  note: string | null
}

export interface ProfilePayload {
  id: string
  username: string
  display_name: string
  email: string
  initial: string
  role: string
  role_code: string
  status: string
  is_superuser: boolean
  workspace: WorkspaceBrief | null
  created_at: string
  last_login_at: string | null
  password_updated_at: string | null
  active_sessions: number
  mfa_enabled: boolean
}

export interface ProfileUpdateResponse {
  ok: boolean
  message: string
  profile: ProfilePayload
}

export interface SessionItem {
  id: string
  current: boolean
  ip_address: string | null
  browser: string
  os: string
  device: string
  issued_at: string
  last_seen_at: string | null
  expires_at: string
  revoked: boolean
  revoked_reason: string | null
}

export interface SessionList {
  items: SessionItem[]
  total: number
  active_total: number
}

export interface SessionRevokeResponse {
  ok: boolean
  message: string
  revoked: number
  signed_out: boolean
}

export interface SecurityEvent {
  id: string
  action: string
  action_label: string
  result: string
  detail: string | null
  ip_address: string | null
  occurred_at: string
}

export interface SecurityPayload {
  password_updated_at: string | null
  failed_login_count: number
  locked_until: string | null
  lock_remaining_minutes: number
  active_sessions: number
  mfa_enabled: boolean
  mfa_note: string
  last_login_at: string | null
  recent_events: SecurityEvent[]
}

/* ── 账号操作日志 ─────────────────────────────────────── */
export interface AuditLogItem {
  id: string
  occurred_at: string
  operator: string
  source: string
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  result: string
  detail: string | null
  changes: Record<string, { before: unknown; after: unknown }> | null
  error_message: string | null
  duration_ms: number | null
  request_id: string | null
  ip_address: string | null
  user_agent: string | null
}

export interface AuditLogList {
  items: AuditLogItem[]
  total: number
  limit: number
  offset: number
}
