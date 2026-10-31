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
  platform: string
  status: AccountStatus
  region: string
  registered_days: number
  bound_instance: string | null
  exit_ip: string | null
  health: number
  action: string
  note: string | null
}

export interface IpResource {
  id: string
  ip: string
  supplier: string
  region: string
  city: string
  type: '住宅' | '机房' | '移动'
  latency_ms: number
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

/* ── 指纹库 ───────────────────────────────────────────── */
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
}

export interface FingerprintPayload {
  total: number
  kernels: number
  filters: { key: string; label: string; count: number }[]
  templates: FingerprintTemplate[]
  shown: number
  selected: number
  page: number
  pages: number
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
 * 登录 / 注册读 token 与 user，找回密码读 email / cooldown，
 * 重置密码读 checks / strength / revoked_sessions。
 */
export interface AuthResponse {
  ok: boolean
  action: string
  message: string

  user?: AuthUser | null
  token?: string | null
  expires_at?: string | null

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

/* ── 内核管理（引擎维度） ─────────────────────────────── */
export interface KernelVersion {
  version: string
  base: string | null
  arch: string | null
  channel: string | null
  size: string | null
  released_at: string | null
  packaged_at: string | null
  source: string | null
  /** 版本目录的绝对路径，排障时直接复制 */
  path: string
  /** 目录里有 meta.json 标记，才算下载完成 */
  ready: boolean
  current: boolean
  instances: number
  warning: string | null
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
  is_primary: boolean
  current_version: string | null
  latest_version: string | null
  update_available: boolean
  downloaded: boolean
  version_count: number
  instance_count: number
  stale_count: number
  disk_path: string
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
  root: string
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

export interface PrimaryResponse {
  ok: boolean
  primary_id: string
  message: string
}

/* ── 引擎档案（browser_engine/<slug>/engine.json，人工维护） ── */
export type AcquireKind = 'pip' | 'archive' | 'manual'

export interface EngineLink {
  label: string
  url: string
  kind: 'release' | 'docs' | 'bucket' | 'mirror'
}

export interface EnginePackage {
  kind: AcquireKind
  os: string
  arch: string
  size: string | null
  url: string | null
  /** 上游没公示就留空，页面上标「未校验」，不要伪造 */
  sha256: string | null
  installer: string | null
  pin: string | null
  note: string | null
}

export interface EngineVersionSpec {
  version: string
  base: string | null
  channel: string | null
  released_at: string | null
  notes: string | null
  packages: EnginePackage[]
}

export interface AcquireSpec {
  kind: AcquireKind
  installer: string | null
  pin: string | null
  fetch: string[]
  cache_dirs: string[]
  executable: string | null
  note: string | null
}

export interface EngineProfile {
  schema: number
  name: string
  engine: string
  tone: string | null
  tagline: string | null
  best_for: string | null
  detection_level: string | null
  pros: string[]
  cons: string[]
  install_notes: string[]
  links: EngineLink[]
  acquire: AcquireSpec | null
  versions: EngineVersionSpec[]
}

export interface EngineVersionView extends EngineVersionSpec {
  installed: boolean
  installed_size: string | null
  is_current: boolean
  /** 磁盘上有、档案没登记（手工放进去的旧版本） */
  on_disk_only: boolean
}

export interface KernelDetailPayload {
  slug: string
  card: KernelCard
  profile: EngineProfile | null
  profile_ok: boolean
  profile_error: string | null
  versions: EngineVersionView[]
  docs: string | null
  docs_path: string
  install_hint: string | null
}

export interface InstallJob {
  id: string
  slug: string
  version: string
  kind: AcquireKind
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
