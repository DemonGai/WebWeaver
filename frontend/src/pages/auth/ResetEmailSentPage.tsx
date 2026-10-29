import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { AuthShell } from '@/components/AuthShell'
import {
  IconAlert,
  IconArrowLeft,
  IconCheck,
  IconClock,
  IconMail,
  IconRefresh,
  IconShare,
} from '@/components/icons'

const formatClock = (total: number) => {
  const s = Math.max(0, total)
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export default function ResetEmailSentPage() {
  const [params] = useSearchParams()
  const email = params.get('email') ?? 'lin.zhiyuan@webweaver.io'
  const initial = Number(params.get('cooldown') ?? 1752)

  const [remaining, setRemaining] = useState(Number.isFinite(initial) ? initial : 1752)
  const [resending, setResending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRemaining((v) => (v > 0 ? v - 1 : 0))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  const resend = useCallback(async () => {
    if (resending) return
    setResending(true)
    setNotice(null)
    try {
      const res = await endpoints.resendReset({ email })
      setNotice(res.message)
      setRemaining(res.cooldown)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '重发失败，请稍后重试')
    } finally {
      setResending(false)
    }
  }, [email, resending])

  return (
    <AuthShell brand={false} bottom="WebWeaver 浏览器集群 · 账号安全中心">
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <div className="flex size-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <IconMail size={27} />
          </div>
          <span className="absolute -top-0.5 -right-0.5 flex size-5 items-center justify-center rounded-full bg-emerald-500 text-white ring-2 ring-white">
            <IconCheck size={10} />
          </span>
        </div>

        <h1 className="mt-5 text-[21px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
          重置邮件已发送
        </h1>
        <p className="mt-2 text-[12.5px] text-[var(--ink-500)]">
          我们已向以下邮箱发送密码重置链接
        </p>
        <p className="mt-2.5 text-[13px] font-semibold text-[var(--ink-900)]">{email}</p>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3 rounded-xl border border-[var(--line)] px-3.5 py-2.5">
        <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--ink-500)]">
          <IconClock size={12} />
          链接有效期剩余 <span className="tnum font-medium text-[var(--ink-700)]">{formatClock(remaining)}</span>
        </span>
        <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--ink-400)]">
          未收到？
          <button
            type="button"
            onClick={resend}
            disabled={resending}
            className="font-medium text-blue-600 transition-colors hover:text-blue-700 disabled:opacity-60"
          >
            {resending ? '发送中…' : '重新发送'}
          </button>
        </span>
      </div>

      {notice && <p className="mt-2 text-center text-[11px] text-emerald-600">{notice}</p>}

      <a href="mailto:" className="btn-dark mt-4 !h-11 w-full !text-[13px]">
        <IconShare size={14} />
        打开邮箱查看
      </a>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <Link to="/" className="btn-ghost !h-11 w-full !text-[12.5px]">
          <IconArrowLeft size={13} />
          返回登录
        </Link>
        <button type="button" className="btn-ghost !h-11 w-full !text-[12.5px]">
          <IconRefresh size={13} />
          联系管理员
        </button>
      </div>

      <div className="mt-4 flex items-start gap-2 rounded-xl bg-[#fdf6e3] px-3.5 py-2.5 text-[11px] leading-relaxed text-amber-700">
        <span className="mt-px shrink-0">
          <IconAlert size={12} />
        </span>
        若 5 分钟内仍未收到邮件，请检查垃圾邮件目录或确认邮箱是否输入正确
      </div>
    </AuthShell>
  )
}
