import { Route, Routes, useLocation } from 'react-router-dom'
import OverviewPage from './pages/OverviewPage'
import BrowserPoolPage from './pages/BrowserPoolPage'
import AccountsPage from './pages/AccountsPage'
import IpPoolPage from './pages/IpPoolPage'
import NoVncConsolePage from './pages/NoVncConsolePage'
import FingerprintsPage from './pages/FingerprintsPage'
import KernelsPage from './pages/KernelsPage'
import KernelDetailPage from './pages/KernelDetailPage'
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage'
import LoginPage from './pages/auth/LoginPage'
import ResetEmailSentPage from './pages/auth/ResetEmailSentPage'
import ResetPasswordPage from './pages/auth/ResetPasswordPage'
import NotFoundPage from './pages/NotFoundPage'
import AuditLogsPage from './pages/AuditLogsPage'
import ProfilePage from './pages/settings/ProfilePage'
import SecurityPage from './pages/settings/SecurityPage'
import SessionsPage from './pages/settings/SessionsPage'
import { ErrorBoundary } from './components/ErrorBoundary'
import { PublicOnly, RequireAuth } from './auth/guards'

export default function App() {
  const location = useLocation()

  return (
    // key 跟着路径变：切页即重建边界，避免一页报错后就一直卡在错误页
    <ErrorBoundary key={location.pathname}>
      <Routes>
        {/* 未登录访问任何业务页都会被送回 /login，并记住原本要去哪 */}
        <Route element={<RequireAuth />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/browsers" element={<BrowserPoolPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/ip-pool" element={<IpPoolPage />} />
          {/* 左右分栏控制台：/novnc 自动落到一台可接管的，/novnc/:id 指定实例 */}
          <Route path="/novnc" element={<NoVncConsolePage />} />
          <Route path="/novnc/:id" element={<NoVncConsolePage />} />
          <Route path="/fingerprints" element={<FingerprintsPage />} />
          <Route path="/kernels" element={<KernelsPage />} />
          <Route path="/kernels/:slug" element={<KernelDetailPage />} />

          {/* 个人中心 */}
          <Route path="/settings/profile" element={<ProfilePage />} />
          <Route path="/settings/security" element={<SecurityPage />} />
          <Route path="/settings/sessions" element={<SessionsPage />} />
          <Route path="/settings/audit-logs" element={<AuditLogsPage />} />
        </Route>

        {/* 账号安全：已登录时不再展示登录页 */}
        <Route element={<PublicOnly />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-email-sent" element={<ResetEmailSentPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ErrorBoundary>
  )
}
