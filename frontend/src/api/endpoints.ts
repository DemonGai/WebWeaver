import { api } from './client'
import type {
  AccountMenu,
  AccountPoolPayload,
  BrowserPoolPayload,
  Captcha,
  FingerprintPayload,
  ForgotPasswordResponse,
  IpPoolPayload,
  KernelEnginePayload,
  PrimaryResponse,
  NoVncPayload,
  OverviewPayload,
  ResetPasswordResponse,
  ResendResponse,
  UpgradeOptions,
  UpgradeResponse,
  WorkspaceList,
} from '@/types/domain'

export const endpoints = {
  overview: () => api.get<OverviewPayload>('/overview'),
  browsers: () => api.get<BrowserPoolPayload>('/browsers'),
  accounts: () => api.get<AccountPoolPayload>('/accounts'),
  ipPool: () => api.get<IpPoolPayload>('/ip-pool'),
  novnc: (id: string) => api.get<NoVncPayload>(`/novnc/${id}`),
  fingerprints: () => api.get<FingerprintPayload>('/fingerprints'),

  /* 内核管理 */
  kernels: () => api.get<KernelEnginePayload>('/kernels'),
  setPrimaryKernel: (id: string) => api.post<PrimaryResponse>(`/kernels/${id}/primary`, {}),
  upgradeOptions: () => api.get<UpgradeOptions>('/kernels/upgrade-options'),
  createUpgrade: (body: {
    kernel_id: string
    scope: string
    groups: string[]
    batch: string
    interval: string
    auto_rollback: boolean
    pause_queue: boolean
    refresh_ua: boolean
  }) => api.post<UpgradeResponse>('/kernels/upgrade', body),

  /* 账号菜单 */
  accountMenu: () => api.get<AccountMenu>('/account/menu'),

  /* 账号安全 */
  workspaces: () => api.get<WorkspaceList>('/auth/workspaces'),
  captcha: () => api.get<Captcha>('/auth/captcha'),
  forgotPassword: (body: { workspace: string; email: string; captcha: string }) =>
    api.post<ForgotPasswordResponse>('/auth/forgot-password', body),
  resendReset: (body: { email: string }) => api.post<ResendResponse>('/auth/resend-reset', body),
  resetPassword: (body: { password: string; confirm: string; email: string }) =>
    api.post<ResetPasswordResponse>('/auth/reset-password', body),
}
