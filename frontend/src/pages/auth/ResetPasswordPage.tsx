import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { AuthShell, AuthTitle } from '@/components/AuthShell'
import { Field, IconInput } from '@/components/fields'
import {
  IconAlert,
  IconCheck,
  IconEye,
  IconEyeOff,
  IconLock,
  IconShield,
} from '@/components/icons'

interface Check {
  key: string
  label: string
  passed: boolean
}

/** 与服务端 app/services/auth_service.py::password_checks 保持一致 */
function localChecks(password: string, email: string): Check[] {
  const local = email.split('@')[0].toLowerCase()
  const tokens = local.split(/[._-]/).filter((t) => t.length >= 3)
  const lowered = password.toLowerCase()

  return [
    { key: 'length', label: '至少 10 位字符', passed: password.length >= 10 },
    { key: 'digit', label: '包含数字', passed: /[0-9]/.test(password) },
    { key: 'upper', label: '包含大写字母', passed: /[A-Z]/.test(password) },
    { key: 'special', label: '包含特殊符号', passed: /[^A-Za-z0-9\s]/.test(password) },
    { key: 'lower', label: '包含小写字母', passed: /[a-z]/.test(password) },
    {
      key: 'no_account',
      label: '不含账号名',
      passed: password.length > 0 && !tokens.some((t) => lowered.includes(t)),
    },
  ]
}

const STRENGTH: Record<number, { label: string; bar: string; text: string }> = {
  0: { label: '很弱', bar: 'bg-rose-400', text: 'text-rose-500' },
  1: { label: '很弱', bar: 'bg-rose-400', text: 'text-rose-500' },
  2: { label: '一般', bar: 'bg-amber-400', text: 'text-amber-600' },
  3: { label: '强', bar: 'bg-blue-500', text: 'text-blue-600' },
  4: { label: '很强', bar: 'bg-emerald-500', text: 'text-emerald-600' },
}

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  // 邮件里的链接会带上 ?email=...；没有就留空，别拿一个假账号顶上——
  // 那会让用户以为自己正在改别人的密码
  const email = params.get('email') ?? ''
  // 令牌是重置的唯一凭据：没有它服务端会直接拒绝，前端先把话说清楚
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [visible, setVisible] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState<{ revoked: number } | null>(null)

  const checks = useMemo(() => localChecks(password, email), [password, email])
  const passedBase = checks.filter((c) => c.key !== 'no_account' && c.passed).length
  const strength = checks.every((c) => c.passed) ? 4 : passedBase
  const matched = confirm.length > 0 && confirm === password
  const tone = STRENGTH[strength]

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)

    setSubmitting(true)
    try {
      const res = await endpoints.resetPassword({ token, password, confirm, email })
      if (!res.ok) {
        setError(res.message)
        return
      }
      setDone({ revoked: res.revoked_sessions ?? 0 })
    } catch (err) {
      setError(err instanceof Error ? err.message : '重置失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <IconCheck size={28} />
          </div>
          <h1 className="mt-5 text-[21px] font-semibold tracking-tight">密码已重置</h1>
          <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--ink-500)]">
            已强制下线 {done.revoked} 个登录会话
            <br />
            请使用新密码重新登录
          </p>
          <Link to="/" className="btn-dark mt-6 !h-11 w-full !text-[13px]">
            前往登录
          </Link>
        </div>
      </AuthShell>
    )
  }

  // 没有令牌（链接被截断、复制漏了一段）就别摆出一个能填的表单，
  // 直接说清楚并给一条重发的路
  if (!token) {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-rose-50 text-rose-500">
            <IconAlert size={26} />
          </div>
          <h1 className="mt-5 text-[21px] font-semibold tracking-tight">链接无效或已过期</h1>
          <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--ink-500)]">
            重置链接只能使用一次，有效期 30 分钟
            <br />
            请重新申请一封重置邮件
          </p>
          <Link to="/forgot-password" className="btn-dark mt-6 !h-11 w-full !text-[13px]">
            重新发送重置邮件
          </Link>
          <Link
            to="/login"
            className="mt-3 text-[11.5px] font-medium text-blue-600 hover:underline"
          >
            返回登录
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell>
      <AuthTitle
        title="设置新密码"
        subtitle={
          email ? (
            <>
              为账号 <span className="font-medium text-[var(--ink-700)]">{email}</span>{' '}
              设置一个新的登录密码
            </>
          ) : (
            '设置一个新的登录密码'
          )
        }
      />

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="新密码" htmlFor="password">
          <IconInput
            id="password"
            type={visible ? 'text' : 'password'}
            icon={<IconLock size={14} />}
            placeholder="请输入新密码"
            value={password}
            autoComplete="new-password"
            onChange={(e) => setPassword(e.target.value)}
            trailing={
              <button
                type="button"
                onClick={() => setVisible((v) => !v)}
                className="text-[var(--ink-400)] transition-colors hover:text-[var(--ink-700)]"
                aria-label={visible ? '隐藏密码' : '显示密码'}
              >
                {visible ? <IconEyeOff size={15} /> : <IconEye size={15} />}
              </button>
            }
          />
          {password.length > 0 && (
            <div className="!mt-2.5 flex items-center gap-2">
              <div className="flex flex-1 gap-1.5">
                {[0, 1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className={`h-[3px] flex-1 rounded-full ${
                      i < strength ? tone.bar : 'bg-[#ececf0]'
                    }`}
                  />
                ))}
              </div>
              <span className={`shrink-0 text-[11px] font-medium ${tone.text}`}>
                强度：{tone.label}
              </span>
            </div>
          )}
        </Field>

        <Field label="确认新密码" htmlFor="confirm">
          <IconInput
            id="confirm"
            type={visible ? 'text' : 'password'}
            icon={<IconLock size={14} />}
            placeholder="再次输入新密码"
            value={confirm}
            autoComplete="new-password"
            onChange={(e) => setConfirm(e.target.value)}
            invalid={confirm.length > 0 && !matched}
            trailing={
              matched ? (
                <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                  <IconCheck size={11} />
                  一致
                </span>
              ) : undefined
            }
          />
        </Field>

        <div className="rounded-xl bg-[#f8f8f9] p-3.5">
          <div className="text-[11.5px] text-[var(--ink-500)]">密码需满足以下条件</div>
          <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-2">
            {checks.map((c) => (
              <div key={c.key} className="flex items-center gap-1.5">
                <span
                  className={`flex size-[13px] shrink-0 items-center justify-center rounded-full ${
                    c.passed
                      ? 'bg-emerald-500 text-white'
                      : 'border border-[#d8d8de] bg-white text-transparent'
                  }`}
                >
                  <IconCheck size={8} />
                </span>
                <span
                  className={`text-[11px] ${
                    c.passed ? 'text-emerald-600' : 'text-[var(--ink-400)]'
                  }`}
                >
                  {c.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-500">
            <span className="mt-px shrink-0">
              <IconAlert size={12} />
            </span>
            {error}
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-dark !h-11 w-full !text-[13px]">
          <IconCheck size={14} />
          {submitting ? '提交中…' : '确认重置密码'}
        </button>
      </form>

      <div className="mt-4 flex items-start gap-2 rounded-xl bg-rose-50 px-3.5 py-2.5 text-[11px] leading-relaxed text-rose-500">
        <span className="mt-px shrink-0">
          <IconShield size={12} />
        </span>
        重置成功后，全部设备上的登录会话将失效，需要使用新密码重新登录
      </div>

      <p className="mt-5 text-center text-[11.5px] text-[var(--ink-500)]">
        不想修改了？{' '}
        <Link to="/" className="font-medium text-blue-600 hover:underline">
          返回登录
        </Link>
      </p>
    </AuthShell>
  )
}
