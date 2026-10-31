import { Route, Routes, useLocation } from 'react-router-dom'
import OverviewPage from './pages/OverviewPage'
import BrowserPoolPage from './pages/BrowserPoolPage'
import AccountsPage from './pages/AccountsPage'
import IpPoolPage from './pages/IpPoolPage'
import NoVncPage from './pages/NoVncPage'
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

export default function App() {
  const location = useLocation()

  return (
    // key 跟着路径变：切页即重建边界，避免一页报错后就一直卡在错误页
    <ErrorBoundary key={location.pathname}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/browsers" element={<BrowserPoolPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/ip-pool" element={<IpPoolPage />} />
        <Route path="/novnc/:id" element={<NoVncPage />} />
        <Route path="/fingerprints" element={<FingerprintsPage />} />
        <Route path="/kernels" element={<KernelsPage />} />
        <Route path="/kernels/:slug" element={<KernelDetailPage />} />

        {/* 个人中心 */}
        <Route path="/settings/profile" element={<ProfilePage />} />
        <Route path="/settings/security" element={<SecurityPage />} />
        <Route path="/settings/sessions" element={<SessionsPage />} />
        <Route path="/settings/audit-logs" element={<AuditLogsPage />} />

        {/* 账号安全 */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-email-sent" element={<ResetEmailSentPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ErrorBoundary>
  )
}
