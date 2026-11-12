/**
 * 统一 API 客户端：所有请求走 /api 前缀，开发期由 Vite 代理到 FastAPI。
 * 生产环境可通过 VITE_API_BASE_URL 指向真实后端域名。
 *
 * **认证靠 Cookie，不靠 localStorage**。访问令牌和刷新令牌都是 httpOnly 的，
 * 页面脚本读不到它们（XSS 也就偷不走），每次请求由浏览器自动带上。
 * 因此这里只做三件事：
 *
 * 1. `credentials: 'include'` —— 跨源请求也要带上 Cookie；
 * 2. 收到 401 时自动续期一次再重放原请求（用户看不到这次失败）；
 * 3. 续期也失败时广播 `auth:expired`，由 AuthProvider 把用户请回登录页。
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export interface ApiErrorPayload {
  detail?: string | { msg?: string }[]
  message?: string
}

export class ApiError extends Error {
  status: number
  payload: ApiErrorPayload | null

  constructor(status: number, message: string, payload: ApiErrorPayload | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function extractMessage(payload: ApiErrorPayload | null, fallback: string): string {
  if (!payload) return fallback
  if (typeof payload.message === 'string') return payload.message
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail) && payload.detail[0]?.msg) return payload.detail[0].msg
  return fallback
}

/** 会话彻底失效时广播：AuthProvider 监听它切到未登录态。 */
export const AUTH_EXPIRED_EVENT = 'auth:expired'

function broadcastExpired() {
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
}

/**
 * 单飞续期：并发请求同时收到 401 时只发一次 /auth/refresh。
 *
 * 不做这件事的话，一个页面同时发 6 个请求，就会有 6 个刷新请求打过去——
 * 而刷新令牌是**轮转**的：第一个请求用旧令牌换到了新的，后面 5 个拿着的
 * 旧令牌会被判定成重放，整场会话反而被吊销。这个 bug 很难在生产环境里复现，
 * 但用户会莫名其妙被踢下线。
 */
let refreshing: Promise<boolean> | null = null

function refreshOnce(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

export interface RequestOptions {
  /** 不要自动续期（认证类接口自己处理，避免递归） */
  skipAuthRefresh?: boolean
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const { skipAuthRefresh = false } = options

  const send = () =>
    fetch(`${BASE_URL}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...init.headers,
      },
    })

  let res = await send()

  // 访问令牌过期（30 分钟）是最常见的一种 401，先试着换一个再重放
  if (res.status === 401 && !skipAuthRefresh) {
    const renewed = await refreshOnce()
    if (renewed) {
      res = await send()
    }
    if (!renewed || res.status === 401) {
      broadcastExpired()
    }
  }

  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }

  if (!res.ok) {
    throw new ApiError(
      res.status,
      extractMessage(data as ApiErrorPayload, `请求失败（HTTP ${res.status}）`),
      data as ApiErrorPayload,
    )
  }

  return data as T
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'GET' }),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'DELETE' }),
  /** 不带自动续期的请求：认证接口自己用，防止 401 → 刷新 → 401 的递归 */
  raw: <T>(path: string, init: RequestInit = {}) =>
    request<T>(path, init, { skipAuthRefresh: true }),
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  timestamp: string
}

export const fetchHealth = () => api.get<HealthResponse>('/health')
