import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { authToken } from '@/api/client'
import { AuthShell, AuthTitle } from '@/components/AuthShell'
import { Field, IconInput } from '@/components/fields'
import { IconAlert, IconArrowRight, IconEye, IconEyeOff, IconLock, IconUser } from '@/components/icons'

/**
 * 登录页。
 *
 * 认证后端只有一个写入口 `POST /api/auth`，这里传 `action: 'login'`。
 * 拿到令牌后写进 localStorage（见 api/client.ts），后续请求自动带 Bearer 头。
 */
export default function LoginPage() {
  const navigate = useNavigate()
  const [account, setAccount] = useState('admin_chen')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await endpoints.login({ account, password, remember })
      if (!res.ok || !res.token) {
        setError(res.message)
        return
      }
      authToken.set(res.token)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell bottom="WebWeaver 浏览器集群 · 账号安全中心">
      <AuthTitle title="登录 WebWeaver" subtitle="使用成员账号进入浏览器集群控制台" />

      <form onSubmit={submit} className="mt-6 space-y-4">
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

        <Field label="密码" htmlFor="password">
          <div className="relative">
            <IconInput
              id="password"
              type={visible ? 'text' : 'password'}
              autoComplete="current-password"
              icon={<IconLock size={14} />}
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              aria-label={visible ? '隐藏密码' : '显示密码'}
              onClick={() => setVisible((v) => !v)}
              className="absolute top-1/2 right-3 -translate-y-1/2 text-[var(--ink-400)] transition-colors hover:text-[var(--ink-600)]"
            >
              {visible ? <IconEyeOff size={14} /> : <IconEye size={14} />}
            </button>
          </div>
        </Field>

        <label className="flex items-center gap-2 text-[11.5px] text-[var(--ink-500)]">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="size-3.5 rounded border-[var(--line)]"
          />
          记住我（30 天内免登录）
        </label>

        {error && (
          <div className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-500">
            <span className="mt-px shrink-0">
              <IconAlert size={12} />
            </span>
            {error}
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-dark !h-11 w-full !text-[13px]">
          {submitting ? '登录中…' : '登录'}
          {!submitting && <IconArrowRight size={14} />}
        </button>
      </form>

      <div className="mt-4 flex items-center justify-between text-[11.5px]">
        <Link to="/forgot-password" className="font-medium text-blue-600 hover:underline">
          忘记密码？
        </Link>
        <span className="text-[var(--ink-400)]">需要账号请联系工作区管理员</span>
      </div>
    </AuthShell>
  )
}
