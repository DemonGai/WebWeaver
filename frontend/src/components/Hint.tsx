import type { ReactNode } from 'react'
import { IconAlert, IconCheckCircle } from './icons'

/**
 * 表单里的一条补充说明。
 *
 * 语气分四档：zinc 是中性提示，amber 是「能跑但有边界」，
 * rose 是错误，emerald 是校验通过。图标跟着语气走，
 * 否则满屏都是一个感叹号，用户分不清哪条是真的出错。
 */
export function Hint({
  tone,
  children,
}: {
  tone: 'rose' | 'zinc' | 'amber' | 'emerald'
  children: ReactNode
}) {
  const style =
    tone === 'rose'
      ? 'border-rose-200 bg-rose-50 text-rose-700'
      : tone === 'amber'
        ? 'border-amber-200 bg-amber-50 text-amber-700'
        : tone === 'emerald'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-[var(--line)] bg-[#fcfcfd] text-[var(--ink-500)]'

  return (
    <div className={`flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-[11.5px] ${style}`}>
      <span className="mt-0.5 shrink-0">
        {tone === 'emerald' ? <IconCheckCircle size={12} /> : <IconAlert size={12} />}
      </span>
      <span className="min-w-0">{children}</span>
    </div>
  )
}
