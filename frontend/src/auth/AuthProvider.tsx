/**
 * 全局登录态。
 *
 * 三件事：
 *
 * 1. **启动检测**：打开页面先问一次 `/auth/session`，结果只有三种——
 *    还在检测（显示骨架）、已登录、未登录。没有这个中间态的话，刷新页面
 *    会先闪一下登录页再跳回来，很难看。
 * 2. **静默续期**：访问令牌只有 30 分钟。剩余时间掉到 5 分钟以下就换一对新的，
 *    用户永远不会看到「登录过期」。续期也失败（刷新令牌到期/被吊销）才踢回登录页。
 * 3. **跨标签同步**：一个标签页退出，其他标签页不该还显示已登录。
 *    这里只往 localStorage 写一个**时间戳**（不是令牌），别的标签监听 storage
 *    事件就知道该跟着退出。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { AUTH_EXPIRED_EVENT, ApiError } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { AuthResponse, AuthUser } from '@/types/domain'

type AuthStatus = 'checking' | 'authenticated' | 'anonymous'

export interface AuthSessionInfo {
  accessExpiresAt: number | null
  refreshExpiresAt: number | null
  absoluteExpiresAt: number | null
  remember: boolean
  otherSessions: number
  sessionId: string | null
  signedInAt: string | null
}

interface AuthContextValue {
  status: AuthStatus
  user: AuthUser | null
  session: AuthSessionInfo | null
  /** 登录成功后调用，把响应里的会话信息装进来 */
  signIn: (result: AuthResponse) => void
  /** 主动退出：吊销服务端会话并清本地状态 */
  signOut: () => Promise<void>
  /** 重新向服务端确认登录态 */
  reload: () => Promise<void>
  /** 立即续期一次；返回是否成功 */
  renew: () => Promise<boolean>
}

/** 访问令牌剩余时间低于这个值就续期：30 分钟的令牌留 5 分钟余量 */
const RENEW_BEFORE_MS = 5 * 60 * 1000
/** 检查间隔。30 秒足够精确，又不会给后端添麻烦 */
const TICK_MS = 30 * 1000
/** 跨标签同步用的键，只存时间戳 */
const LOGOUT_KEY = 'wv_signed_out_at'

const AuthContext = createContext<AuthContextValue | null>(null)

function toMillis(value: string | null | undefined): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

function sessionOf(result: AuthResponse): AuthSessionInfo {
  return {
    accessExpiresAt: toMillis(result.access_expires_at),
    refreshExpiresAt: toMillis(result.refresh_expires_at),
    absoluteExpiresAt: toMillis(result.absolute_expires_at),
    remember: Boolean(result.remember),
    otherSessions: result.other_sessions ?? 0,
    sessionId: result.session_id ?? null,
    signedInAt: result.signed_in_at ?? null,
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [session, setSession] = useState<AuthSessionInfo | null>(null)

  // 续期请求可能被 tick 和 401 同时触发，用 ref 做单飞
  const renewing = useRef<Promise<boolean> | null>(null)

  const adopt = useCallback((result: AuthResponse) => {
    // 只有明确说「未登录」才算未登录。登录/续期响应里这个字段是 null，
    // 用 `!result.authenticated` 会把刚登录成功的用户直接判成登出。
    if (result.authenticated === false) {
      setStatus('anonymous')
      setUser(null)
      setSession(null)
      return
    }
    if (result.user !== undefined) setUser(result.user ?? null)
    setSession(sessionOf(result))
    setStatus('authenticated')
  }, [])

  const renew = useCallback(async () => {
    if (renewing.current) return renewing.current
    const task = endpoints
      .refresh()
      .then((result) => {
        adopt(result)
        return true
      })
      .catch((err: unknown) => {
        // 只有服务端明确说「这个令牌不作数」（401）才把人踢回登录页。
        // 断网、超时也会走到这里，那种情况把人登出纯属添乱。
        if (err instanceof ApiError && err.status === 401) {
          setStatus('anonymous')
          setUser(null)
          setSession(null)
        }
        return false
      })
      .finally(() => {
        renewing.current = null
      })
    renewing.current = task
    return task
  }, [adopt])

  const reload = useCallback(async () => {
    try {
      const result = await endpoints.session()
      if (result.authenticated !== false) {
        adopt(result)
        return
      }
      // 「未登录」有两种情况，不能一概而论：
      //   1. 确实没登录过 —— 手上没有 wv_rt，续期会 401；
      //   2. 只是访问令牌没了 —— wv_at 只有 30 分钟，浏览器到点就把它删了，
      //      而 wv_rt 还有 7 / 30 天。合盖一小时再打开就属于这种。
      // 第 2 种要是直接判未登录，用户就会被莫名要求重新输密码，双令牌等于白做。
      // 所以先拿刷新令牌试一次，成功就静默恢复。
      const renewed = await renew()
      if (!renewed) adopt(result)
    } catch {
      // 网络断了不该把用户当成登出——保持现状，下一个请求会再试
      setStatus((prev) => (prev === 'checking' ? 'anonymous' : prev))
    }
  }, [adopt, renew])

  const signIn = useCallback(
    (result: AuthResponse) => {
      adopt(result)
    },
    [adopt],
  )

  const signOut = useCallback(async () => {
    try {
      await endpoints.logout()
    } catch {
      // 会话可能早就失效了，本地状态照样要清
    }
    setStatus('anonymous')
    setUser(null)
    setSession(null)
    // 广播给其他标签页：值本身没有意义，变化就是信号
    localStorage.setItem(LOGOUT_KEY, String(Date.now()))
  }, [])

  // 启动时检测一次
  useEffect(() => {
    void reload()
  }, [reload])

  // 续期定时器：只有已登录才需要
  useEffect(() => {
    if (status !== 'authenticated') return

    const tick = () => {
      const expiresAt = session?.accessExpiresAt
      const refreshExpiresAt = session?.refreshExpiresAt
      const now = Date.now()

      // 刷新令牌都过期了，续期没有意义，直接登出
      if (refreshExpiresAt && refreshExpiresAt <= now) {
        setStatus('anonymous')
        setUser(null)
        setSession(null)
        return
      }
      // 访问令牌即将过期（或已经过期）才换新的
      if (expiresAt && expiresAt - now <= RENEW_BEFORE_MS) {
        void renew()
      }
    }

    tick()
    const timer = window.setInterval(tick, TICK_MS)
    return () => window.clearInterval(timer)
  }, [status, session?.accessExpiresAt, session?.refreshExpiresAt, renew])

  // 从后台切回来时可能已经过了很久，立刻校准一次
  useEffect(() => {
    if (status !== 'authenticated') return
    const onVisible = () => {
      if (document.visibilityState === 'visible') void renew()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [status, renew])

  // 任意请求确认会话彻底失效时（client.ts 广播），切到未登录
  useEffect(() => {
    const onExpired = () => {
      setStatus('anonymous')
      setUser(null)
      setSession(null)
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [])

  // 其他标签页退出登录
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== LOGOUT_KEY) return
      setStatus('anonymous')
      setUser(null)
      setSession(null)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const value = useMemo(
    () => ({ status, user, session, signIn, signOut, reload, renew }),
    [status, user, session, signIn, signOut, reload, renew],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
