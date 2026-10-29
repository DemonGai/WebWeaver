import { Route, Routes } from 'react-router-dom'
import OverviewPage from './pages/OverviewPage'
import BrowserPoolPage from './pages/BrowserPoolPage'
import AccountsPage from './pages/AccountsPage'
import IpPoolPage from './pages/IpPoolPage'
import NoVncPage from './pages/NoVncPage'
import FingerprintsPage from './pages/FingerprintsPage'
import KernelsPage from './pages/KernelsPage'
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage'
import ResetEmailSentPage from './pages/auth/ResetEmailSentPage'
import ResetPasswordPage from './pages/auth/ResetPasswordPage'
import NotFoundPage from './pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/browsers" element={<BrowserPoolPage />} />
      <Route path="/accounts" element={<AccountsPage />} />
      <Route path="/ip-pool" element={<IpPoolPage />} />
      <Route path="/novnc/:id" element={<NoVncPage />} />
      <Route path="/fingerprints" element={<FingerprintsPage />} />
      <Route path="/kernels" element={<KernelsPage />} />

      {/* 账号安全 */}
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-email-sent" element={<ResetEmailSentPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
