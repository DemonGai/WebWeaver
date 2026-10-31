import { api } from './client'
import type {
  UserMenuPayload,
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
  FingerprintPayload,
  InstallJob,
  IpPoolPayload,
  KernelDetailPayload,
  KernelInstance,
  KernelMigrationResult,
  KernelPayload,
  PrimaryResponse,
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
  ipPool: () => api.get<IpPoolPayload>('/ip-pool'),
  novnc: (id: string) => api.get<NoVncPayload>(`/novnc/${id}`),
  fingerprints: () => api.get<FingerprintPayload>('/fingerprints'),

  /* 内核管理 */
  kernels: () => api.get<KernelPayload>('/kernels'),
  rescanKernels: () => api.post<KernelPayload>('/kernels/rescan', {}),
  setPrimaryKernel: (id: string) => api.post<PrimaryResponse>(`/kernels/${id}/primary`, {}),
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

  /* 引擎详情 + 按档案里的下载源获取版本 */
  kernelDetail: (slug: string) => api.get<KernelDetailPayload>(`/kernels/${slug}`),
  installKernel: (slug: string, body: { version: string; os?: string; arch?: string }) =>
    api.post<InstallJob>(`/kernels/${slug}/install`, body),
  installJobs: () => api.get<InstallJob[]>('/kernels/jobs'),
  installJob: (id: string) => api.get<InstallJob>(`/kernels/jobs/${id}`),

  /* 头像菜单 + 个人中心（当前登录成员，非浏览器账号池） */
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

  logout: () => api.post<AuthResponse>('/auth', { action: 'logout' }),

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
