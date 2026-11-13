import { api } from './client'
import type {
  UserMenuPayload,
  AccountDetail,
  AccountFormValues,
  AccountImportRequest,
  AccountImportResult,
  AccountPoolPayload,
  AuditLogList,
  AuthResponse,
  BrowserPoolPayload,
  BrowserActionName,
  BrowserBatchResult,
  BrowserDetail,
  BrowserFormValues,
  BrowserMutationResult,
  BrowserOptions,
  Captcha,
  FingerprintApplyResult,
  FingerprintDetail,
  FingerprintFormValues,
  FingerprintInstanceRef,
  FingerprintPayload,
  KernelFingerprintCaps,
  InstallJob,
  IpCheckResult,
  IpImportRequest,
  IpImportResult,
  IpPoolPayload,
  KernelDetailPayload,
  KernelInstance,
  KernelMigrationResult,
  KernelPayload,
  NoVncPayload,
  OverviewPayload,
  OverviewRange,
  ProfilePayload,
  ProfileUpdateResponse,
  SecurityPayload,
  SessionList,
  SessionRevokeResponse,
  WorkspaceList,
} from '@/types/domain'

export const endpoints = {
  overview: (range: OverviewRange = '7d') =>
    api.get<OverviewPayload>(`/overview?range=${range}`),
  browsers: () => api.get<BrowserPoolPayload>('/browsers'),
  /* 浏览器池写操作 */
  browserOptions: () => api.get<BrowserOptions>('/browsers/options'),
  browserDetail: (id: string) => api.get<BrowserDetail>(`/browsers/${id}`),
  createBrowser: (body: BrowserFormValues & { name: string }) =>
    api.post<BrowserDetail>('/browsers', body),
  updateBrowser: (id: string, body: BrowserFormValues) =>
    api.patch<BrowserDetail>(`/browsers/${id}`, body),
  deleteBrowser: (id: string) => api.delete<BrowserMutationResult>(`/browsers/${id}`),
  browserAction: (id: string, action: BrowserActionName) =>
    api.post<BrowserMutationResult>(`/browsers/${id}/actions`, { action }),
  browserBatch: (ids: string[], action: BrowserActionName) =>
    api.post<BrowserBatchResult>('/browsers/batch', { ids, action }),
  accounts: () => api.get<AccountPoolPayload>('/accounts'),
  /* 账号管理写操作 */
  accountDetail: (id: string) => api.get<AccountDetail>(`/accounts/${id}`),
  createAccount: (body: AccountFormValues) => api.post<AccountDetail>('/accounts', body),
  updateAccount: (id: string, body: Partial<AccountFormValues>) =>
    api.patch<void>(`/accounts/${id}`, body),
  importAccounts: (body: AccountImportRequest) =>
    api.post<AccountImportResult>('/accounts/import', body),
  accountTemplate: () => api.text('/accounts/template'),
  ipPool: () => api.get<IpPoolPayload>('/ip-pool'),
  /* 代理管理写操作 */
  importIps: (body: IpImportRequest) => api.post<IpImportResult>('/ip-pool/import', body),
  checkIps: () => api.post<IpCheckResult>('/ip-pool/check', {}),
  // 模板是 CSV，不能走 JSON 解析
  ipTemplate: () => api.text('/ip-pool/template'),
  novnc: (id: string) => api.get<NoVncPayload>(`/novnc/${id}`),
  fingerprints: () => api.get<FingerprintPayload>('/fingerprints'),

  /* 内核管理 */
  kernels: () => api.get<KernelPayload>('/kernels'),
  rescanKernels: () => api.post<KernelPayload>('/kernels/rescan', {}),
  // 切当前版本：旧版本目录保留，老实例仍留在旧版本上
  switchKernelVersion: (id: string, version: string) =>
    api.post<KernelPayload>(`/kernels/${id}/version`, { version }),
  kernelInstances: (id: string, params: { stale?: boolean; version?: string } = {}) => {
    const search = new URLSearchParams()
    if (params.stale) search.set('stale', 'true')
    if (params.version) search.set('version', params.version)
    const query = search.toString()
    return api.get<KernelInstance[]>(`/kernels/${id}/instances${query ? `?${query}` : ''}`)
  },
  migrateKernelVersion: (id: string, version: string, browserIds: string[] = []) =>
    api.post<KernelMigrationResult>(`/kernels/${id}/migrate`, {
      version,
      browser_ids: browserIds,
    }),

  /* 内核详情 + 拉取镜像 */
  kernelDetail: (slug: string) => api.get<KernelDetailPayload>(`/kernels/${slug}`),
  // tag 留空表示拉滚动 tag（该内核最近一次构建）
  installKernel: (slug: string, body: { tag?: string; version?: string } = {}) =>
    api.post<InstallJob>(`/kernels/${slug}/install`, body),
  installJobs: () => api.get<InstallJob[]>('/kernels/jobs'),

  /* 指纹管理写操作 */
  fingerprintCapabilities: () =>
    api.get<KernelFingerprintCaps[]>('/fingerprints/capabilities'),
  fingerprintOptions: () =>
    api.get<FingerprintInstanceRef[]>('/fingerprints/options'),
  fingerprintDetail: (id: string) =>
    api.get<FingerprintDetail>(`/fingerprints/${id}`),
  createFingerprint: (body: FingerprintFormValues & { name: string }) =>
    api.post<FingerprintDetail>('/fingerprints', body),
  updateFingerprint: (id: string, body: FingerprintFormValues) =>
    api.patch<FingerprintDetail>(`/fingerprints/${id}`, body),
  deleteFingerprint: (id: string) => api.delete<void>(`/fingerprints/${id}`),
  // 起一个临时容器按当前参数装配一次人格，把 UA / GPU 这些读回来
  probeFingerprint: (id: string) =>
    api.post<FingerprintDetail>(`/fingerprints/${id}/probe`, {}),
  // 写进实例容器的 /data/fingerprint.json 并重启容器
  applyFingerprint: (id: string, instanceIds: string[]) =>
    api.post<FingerprintApplyResult>(`/fingerprints/${id}/apply`, {
      instance_ids: instanceIds,
    }),
  installJob: (id: string) => api.get<InstallJob>(`/kernels/jobs/${id}`),

  /* 头像菜单 + 个人中心（当前登录成员，非浏览器账号管理） */
  userMenu: () => api.get<UserMenuPayload>('/user/menu'),
  profile: () => api.get<ProfilePayload>('/user/profile'),
  updateProfile: (body: { display_name: string }) =>
    api.patch<ProfileUpdateResponse>('/user/profile', body),
  sessions: () => api.get<SessionList>('/user/sessions'),
  revokeSession: (id: string) =>
    api.delete<SessionRevokeResponse>(`/user/sessions/${id}`),
  security: () => api.get<SecurityPayload>('/user/security'),
  myAuditLogs: (params: { action?: string; result?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams()
    if (params.action) search.set('action', params.action)
    if (params.result) search.set('result', params.result)
    if (params.limit) search.set('limit', String(params.limit))
    if (params.offset) search.set('offset', String(params.offset))
    const query = search.toString()
    return api.get<AuditLogList>(`/user/audit-logs${query ? `?${query}` : ''}`)
  },

  /* 认证：所有写操作都打同一个入口，用 action 区分 */
  auth: (body: Record<string, unknown> & { action: string }) =>
    api.post<AuthResponse>('/auth', body),

  login: (body: { account: string; password: string; remember?: boolean }) =>
    api.post<AuthResponse>('/auth', { action: 'login', ...body }),

  register: (body: {
    username: string
    email: string
    password: string
    confirm?: string
    display_name?: string
  }) => api.post<AuthResponse>('/auth', { action: 'register', ...body }),

  logout: () => api.raw<AuthResponse>('/auth', { method: 'POST', body: JSON.stringify({ action: 'logout' }) }),

  /** 下线所有其他设备（keep_current 决定是否保留当前这台） */
  logoutAll: (keepCurrent = true) =>
    api.post<AuthResponse>('/auth', { action: 'logout_all', keep_current: keepCurrent }),

  /** 已登录改密码：必须给出原密码 */
  changePassword: (body: { current_password: string; password: string; confirm: string }) =>
    api.post<AuthResponse>('/auth', { action: 'change_password', ...body }),

  /**
   * 用刷新令牌换一对新令牌。一般由 client.ts 自动调用；
   * 页面里只在「手动立即续期」这种场景才直接调。
   */
  refresh: () => api.raw<AuthResponse>('/auth/refresh', { method: 'POST' }),

  /** 登录状态检测：未登录返回 200 + authenticated: false，不会触发续期 */
  session: () => api.raw<AuthResponse>('/auth/session'),

  me: () => api.get<AuthResponse>('/auth/me'),

  /* 账号安全 */
  workspaces: () => api.get<WorkspaceList>('/auth/workspaces'),
  captcha: () => api.get<Captcha>('/auth/captcha'),
  forgotPassword: (body: { workspace?: string; email: string; captcha: string }) =>
    api.post<AuthResponse>('/auth', { action: 'forgot_password', ...body }),
  resendReset: (body: { email: string }) =>
    api.post<AuthResponse>('/auth', { action: 'resend_reset', ...body }),
  resetPassword: (body: { token: string; password: string; confirm: string; email?: string }) =>
    api.post<AuthResponse>('/auth', { action: 'reset_password', ...body }),
}
