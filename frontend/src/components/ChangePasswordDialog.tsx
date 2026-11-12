/**
 * 修改密码（已登录状态）。
 *
 * 和「忘记密码」的区别是这里必须先给出原密码——否则一台没锁屏的电脑
 * 就能被顺手改掉密码，把真正的主人关在门外。
 *
 * 提交成功后后端会：踢掉其他所有设备的会话、轮转当前会话的令牌，
 * 所以这边拿到响应要顺手把全局登录态刷新一次（到期时间变了）。
 */

import { useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useAuth } from '@/auth/AuthProvider'
import { Field, IconInput } from '@/components/fields'
import { IconAlert, IconCheckCircle, IconLock } from '@/components/icons'
import { Modal } from '@/components/Modal'
import type { PasswordRule } from '@/types/domain'

const RULE_TONE = (passed: boolean) =>
  passed ? 'text-emerald-600' : 'text-[var(--ink-400)]'

export function ChangePasswordDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { reload } = useAuth()
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [checks, setChecks] = useState<PasswordRule[]>([])
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setCurrent('')
    setPassword('')
    setConfirm('')
    setChecks([])
    setError(null)
    setDone(null)
    setBusy(false)
  }

  const close = () => {
    reset()
    onClose()
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    setError(null)
    setBusy(true)
    try {
      const res = await endpoints.changePassword({
        current_password: current,
        password,
        confirm,
      })
      if (res.checks) setChecks(res.checks)
      if (!res.ok) {
        setError(res.message)
        return
      }
      setDone(res.message)
      // 令牌刚被轮转，重新拉一次会话状态，让倒计时与设备数保持准确
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : '修改失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="修改登录密码"
      subtitle="修改后其他设备会被强制下线，当前设备保持登录"
      icon={<IconLock size={15} />}
      width="max-w-[440px]"
      footer={
        done ? (
          <button type="button" onClick={close} className="btn-dark">
            我知道了
          </button>
        ) : (
          <>
            <button type="button" onClick={close} className="btn-ghost">
              取消
            </button>
            <button type="submit" form="change-password-form" disabled={busy} className="btn-dark">
              {busy ? '提交中…' : '确认修改'}
            </button>
          </>
        )
      }
    >
      {done ? (
        <div className="px-6 pb-2">
          <div className="flex items-start gap-2 rounded-xl bg-emerald-50 px-3 py-3 text-[12px] text-emerald-700">
            <span className="mt-px shrink-0">
              <IconCheckCircle size={13} />
            </span>
            {done}
          </div>
        </div>
      ) : (
        <form id="change-password-form" onSubmit={submit} className="space-y-3 px-6 pb-2">
          <Field label="当前密码" htmlFor="current-password">
            <IconInput
              id="current-password"
              type="password"
              icon={<IconLock size={14} />}
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              placeholder="用于确认是本人操作"
            />
          </Field>

          <Field label="新密码" htmlFor="new-password">
            <IconInput
              id="new-password"
              type="password"
              icon={<IconLock size={14} />}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 10 位，含大小写、数字与符号"
            />
          </Field>

          <Field label="确认新密码" htmlFor="confirm-password">
            <IconInput
              id="confirm-password"
              type="password"
              icon={<IconLock size={14} />}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="再输入一次"
            />
          </Field>

          {checks.length > 0 && (
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1 rounded-xl bg-[#fafafa] px-3 py-2.5">
              {checks.map((rule) => (
                <li key={rule.key} className={`text-[11px] ${RULE_TONE(rule.passed)}`}>
                  {rule.passed ? '✓' : '·'} {rule.label}
                </li>
              ))}
            </ul>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2.5 text-[11.5px] text-rose-500">
              <span className="mt-px shrink-0">
                <IconAlert size={12} />
              </span>
              {error}
            </div>
          )}
        </form>
      )}
    </Modal>
  )
}
