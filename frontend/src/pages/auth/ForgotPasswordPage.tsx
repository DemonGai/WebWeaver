import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { AuthShell, AuthTitle } from '@/components/AuthShell'
import { CaptchaBox, Field, IconInput } from '@/components/fields'
import {
  IconAlert,
  IconArrowLeft,
  IconMail,
  IconShield,
} from '@/components/icons'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('lin.zhiyuan@webweaver.io')
  const [captchaCode, setCaptchaCode] = useState('')
  const [captchaInput, setCaptchaInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const refreshCaptcha = () => {
    setCaptchaInput('')
    endpoints
      .captcha()
      .then((c) => setCaptchaCode(c.code))
      .catch(() => setCaptchaCode(''))
  }

  useEffect(() => {
    endpoints
    refreshCaptcha()
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await endpoints.forgotPassword({ email, captcha: captchaInput })
      if (!res.ok) {
        setError(res.message)
        refreshCaptcha()
        return
      }
      const query = new URLSearchParams({
        email: res.email ?? email,
        cooldown: String(res.cooldown ?? 0),
      })
      // 本地没有邮件服务时后端会把令牌直接返回，带上它才能把重置流程点通
      if (res.reset_token) query.set('token', res.reset_token)
      navigate(`/reset-email-sent?${query.toString()}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送失败，请稍后重试')
      refreshCaptcha()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--ink-500)] transition-colors hover:text-[var(--ink-900)]"
      >
        <IconArrowLeft size={13} />
        返回登录
      </Link>

      <div className="mt-5">
        <AuthTitle
          title="重置密码"
          subtitle="输入账号绑定的邮箱，我们会向该邮箱发送一封密码重置邮件"
        />
      </div>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="登录邮箱" htmlFor="email">
          <IconInput
            id="email"
            type="email"
            autoComplete="email"
            icon={<IconMail size={14} />}
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="图形验证码" htmlFor="captcha">
          <div className="flex items-center gap-2.5">
            <IconInput
              id="captcha"
              className="flex-1"
              icon={<IconShield size={14} />}
              placeholder="输入 4 位字符"
              maxLength={4}
              value={captchaInput}
              onChange={(e) => setCaptchaInput(e.target.value)}
            />
            <CaptchaBox code={captchaCode || '····'} onRefresh={refreshCaptcha} />
          </div>
        </Field>

        {error && (
          <div className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-500">
            <span className="mt-px shrink-0">
              <IconAlert size={12} />
            </span>
            {error}
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-dark !h-11 w-full !text-[13px]">
          {submitting ? '发送中…' : '重置密码'}
        </button>
      </form>
      <p className="mt-5 text-center text-[11.5px] text-[var(--ink-500)]">
        想起密码了？{' '}
        <Link to="/" className="font-medium text-blue-600 hover:underline">
          使用账号密码登录
        </Link>
      </p>
    </AuthShell>
  )
}
