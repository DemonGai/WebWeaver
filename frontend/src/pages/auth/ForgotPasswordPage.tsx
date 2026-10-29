import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { AuthShell, AuthTitle } from '@/components/AuthShell'
import { CaptchaBox, Field, IconInput, SelectField } from '@/components/fields'
import {
  IconAlert,
  IconArrowLeft,
  IconBuilding,
  IconClock,
  IconMail,
  IconShield,
} from '@/components/icons'
import type { Workspace } from '@/types/domain'

const TIPS = [
  { icon: <IconClock size={12} />, text: '重置链接 30 分钟内有效，仅可使用一次' },
  { icon: <IconShield size={12} />, text: '为保障集群安全，重置成功后强制下线全部会话' },
  { icon: <IconMail size={12} />, text: '若邮箱已无法访问，请联系工作区管理员协助重置' },
]

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspace, setWorkspace] = useState('')
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
      .workspaces()
      .then((res) => {
        setWorkspaces(res.items)
        setWorkspace(res.default_id)
      })
      .catch(() => setWorkspaces([]))
    refreshCaptcha()
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await endpoints.forgotPassword({ workspace, email, captcha: captchaInput })
      if (!res.ok) {
        setError(res.message)
        refreshCaptcha()
        return
      }
      navigate(
        `/reset-email-sent?email=${encodeURIComponent(res.email)}&cooldown=${res.cooldown}`,
      )
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
          title="找回密码"
          subtitle="输入账号绑定的邮箱，我们会向该邮箱发送一封密码重置邮件"
        />
      </div>

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="工作区" htmlFor="workspace">
          <SelectField
            id="workspace"
            icon={<IconBuilding size={14} />}
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          >
            {workspaces.length === 0 && <option value="">加载中…</option>}
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </SelectField>
        </Field>

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
          <IconMail size={14} />
          {submitting ? '发送中…' : '发送重置邮件'}
        </button>
      </form>

      <div className="mt-5 space-y-2.5 rounded-xl bg-[#f8f8f9] p-3.5">
        {TIPS.map((t) => (
          <div key={t.text} className="flex items-start gap-2 text-[11px] text-[var(--ink-500)]">
            <span className="mt-px shrink-0 text-[var(--ink-400)]">{t.icon}</span>
            {t.text}
          </div>
        ))}
      </div>

      <p className="mt-5 text-center text-[11.5px] text-[var(--ink-500)]">
        想起密码了？{' '}
        <Link to="/" className="font-medium text-blue-600 hover:underline">
          使用账号密码登录
        </Link>
      </p>
    </AuthShell>
  )
}
