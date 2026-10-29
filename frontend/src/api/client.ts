/**
 * 统一 API 客户端：所有请求走 /api 前缀，开发期由 Vite 代理到 FastAPI。
 * 生产环境可通过 VITE_API_BASE_URL 指向真实后端域名。
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('webweaver_token')

  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  const text = await res.text()
  const data = text ? (JSON.parse(text) as unknown) : null

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
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'DELETE' }),
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  timestamp: string
}

export const fetchHealth = () => api.get<HealthResponse>('/health')
