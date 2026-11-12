import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useAuth } from '@/auth/AuthProvider'
import { AuthShell, AuthTitle } from '@/components/AuthShell'
import { Field, IconInput, PasswordInput } from '@/components/fields'
import { IconAlert, IconLock, IconUser } from '@/components/icons'
import { Checkbox } from '@/components/ui'

/**
 * 登录页。
 *
 * 认证后端只有一个写入口 `POST /api/auth`，这里传 `action: 'login'`。
 * 令牌由后端写进 httpOnly Cookie，页面拿不到也不需要拿——`signIn` 只需
 * 把响应里的会话信息（用户、各到期时间）装进全局状态。
 *
 * 进来时如果带着 `state.from`（守卫记下的原页面），登录后直接送回去，
 * 而不是一律跳首页。
 */
export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn } = useAuth()
  const [account, setAccount] = useState('admin')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await endpoints.login({ account, password, remember })
      if (!res.ok) {
        setError(res.message)
        return
      }
      signIn(res)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : '/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell bottom="WebWeaver 浏览器集群 · 账号安全中心">
      <AuthTitle title="登录" subtitle="使用成员账号进入浏览器集群控制台" />
      <form onSubmit={submit} className="mt-6">
        <Field label="账号" htmlFor="account">
          <IconInput
            id="account"
            autoComplete="username"
            icon={<IconUser size={14} />}
            placeholder="用户名或邮箱"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          />
        </Field>

        <Field label="密码" htmlFor="password" className="mt-4">
          <PasswordInput
            id="password"
            autoComplete="current-password"
            icon={<IconLock size={14} />}
            placeholder="请输入密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>

        {/* 这一行不是表单项，是「密码」的附属选项：跟紧上面，离按钮远一点，
            否则三块等距排下来会被读成第三个字段。 */}
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="remember"
              checked={remember}
              onChange={setRemember}
              label="记住我（30 天内免登）"
            />
            <label
              htmlFor="remember"
              className="cursor-pointer text-[11.5px] text-[var(--ink-500)]"
            >
              记住我（30 天内免登）
            </label>
          </div>
          <Link
            to="/forgot-password"
            className="text-[11.5px] font-medium text-blue-600 hover:underline"
          >
            忘记密码？
          </Link>
        </div>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-500">
            <span className="mt-px shrink-0">
              <IconAlert size={12} />
            </span>
            {error}
          </div>
        )}
        <button type="submit" disabled={submitting} className="btn-dark mt-5 !h-11 w-full !text-[13px]">
          {submitting ? '登录中…' : '登录'}
        </button>
      </form>
    </AuthShell>
  )
}
