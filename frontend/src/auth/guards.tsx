/**
 * 路由守卫。
 *
 * 两件事必须分开看：
 *
 * - **未登录不能进业务页**：`RequireAuth` 把访问者挡在 `/login`。
 * - **已登录不必再看登录页**：`PublicOnly` 把访问者送回首页。
 *   少了这一条，用户点浏览器后退键会看到一个已经没用的登录表单。
 *
 * 两者都在 `checking` 时先显示一个极简的启动画面，避免「先闪登录页再跳回来」。
 */

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthProvider'
import { BrandMark } from '@/components/Brand'

function BootScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafafa]">
      <div className="flex flex-col items-center gap-3">
        <div className="animate-pulse">
          <BrandMark />
        </div>
        <span className="text-[11.5px] text-[var(--ink-400)]">正在确认登录状态…</span>
      </div>
    </div>
  )
}

export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'checking') return <BootScreen />
  if (status === 'anonymous') {
    // 记下原本要去的页面，登录后直接送回去
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <Outlet />
}

export function PublicOnly() {
  const { status } = useAuth()

  if (status === 'checking') return <BootScreen />
  if (status === 'authenticated') return <Navigate to="/" replace />
  return <Outlet />
}
