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

export interface OverviewPayload {
  cluster: {
    total: number
    online: number
    health: number
    delta: number
    updated_seconds: number
    accounts_used: number
    accounts_total: number
    ip_used: number
    ip_total: number
    avg_latency_ms: number
    novnc_fps: number
  }
  pool_status: { label: string; value: number; status: InstanceStatus }[]
  load: {
    cpu: number
    memory: number
    bandwidth: number
    disconnect_minutes: number
    reconnects: number
  }
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
  novnc_preview: {
    instance: string
    url: string
    fps: number
    latency_ms: number
  }
}

export interface BrowserPoolPayload {
  totals: { running: number; total: number; delta: number }
  cards: { title: string; value: number; hint: string; tone: string; tag: string }[]
  instances: InstanceSummary[]
  filters: { key: string; label: string; count: number }[]
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
export type PlatformFamily = 'windows' | 'macos' | 'mobile'

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

export interface ForgotPasswordResponse {
  ok: boolean
  email: string
  expires_in: number
  cooldown: number
  message: string
}

export interface ResendResponse {
  ok: boolean
  cooldown: number
  message: string
}

export interface PasswordRule {
  key: string
  label: string
  passed: boolean
}

export interface ResetPasswordResponse {
  ok: boolean
  checks: PasswordRule[]
  strength: number
  revoked_sessions: number
  message: string
}

/* ── 内核管理（引擎维度） ─────────────────────────────── */
export interface KernelCheck {
  label: string
  status: string
  tone: string
}

export interface KernelRelease {
  version: string
  base: string
  arch: string
  size: string
  instances: number
  status: string
  status_tone: string
  installed: boolean
  released_at: string
}

export interface KernelEngine {
  id: string
  name: string
  engine: string
  base: string
  level: string
  tone: string
  tagline: string
  usage: string
  origin: string
  version: string
  latest: string
  update: boolean
  channel: string
  size: string
  arch: string
  instances: number
  share: number
  status: string
  status_tone: string
  primary: boolean
  pass_rate: number
  checks: KernelCheck[]
  releases: KernelRelease[]
  note: string
}

export interface KernelSummaryTile {
  key: string
  label: string
  value: string
  hint: string
  icon: string
  tone: string
}

export interface KernelTab {
  key: string
  label: string
  count: number
}

export interface FallbackStep {
  id: string
  name: string
  engine: string
  role: string
  detail: string
  tone: string
}

export interface ChangelogBlock {
  version: string
  items: string[]
  published_at: string
}

export interface GrayRelease {
  eyebrow: string
  title: string
  done: number
  total: number
  percent: number
  stages: { label: string; active: boolean }[]
}

export interface KernelEnginePayload {
  tiles: KernelSummaryTile[]
  tabs: KernelTab[]
  engines: KernelEngine[]
  fallback: FallbackStep[]
  fallback_triggers: string[]
  release_note: ChangelogBlock
  gray: GrayRelease
  total_instances: number
  check_labels: string[]
}

export interface PrimaryResponse {
  ok: boolean
  primary_id: string
  message: string
}

export interface KernelOption {
  id: string
  name: string
  channel: string
  size: string
  note: string
  recommended: boolean
  disabled: boolean
}

export interface UpgradeOptions {
  kernels: KernelOption[]
  groups: { id: string; name: string; count: number }[]
  scope_tabs: string[]
  batches: string[]
  intervals: string[]
  toggles: { key: string; label: string; description: string; default: boolean }[]
  notice: string
  eta: string
}

export interface UpgradeResponse {
  ok: boolean
  task_id: string
  kernel: string
  targets: number
  batch: string
  interval: string
  eta: string
  message: string
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

export interface AccountMenu {
  name: string
  initial: string
  email: string
  role: string
  workspace: string
  workspace_note: string
  groups: MenuRow[][]
  last_login: string
  version: string
}
