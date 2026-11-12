import type { ReactNode } from 'react'

/** 统计卡 / 卡片图标块的配色，按业务色调取用 */
export const toneTile: Record<string, string> = {
  dark: 'bg-[#18181b] text-white',
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  sky: 'bg-sky-50 text-sky-600',
  zinc: 'bg-zinc-100 text-zinc-500',
}

/**
 * 页头下方的统计卡：左边一个 32px 色调图标块，右边「标签 + 数值/hint 同行」。
 * 内核管理与指纹管理共用同一个，保证两页的统计条长得一模一样。
 */
export function StatTile({
  label,
  value,
  hint,
  tone = 'zinc',
  icon,
}: {
  label: string
  value: string
  hint: string
  tone?: string
  icon: ReactNode
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3.5">
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] ${
          toneTile[tone] ?? toneTile.zinc
        }`}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-[10.5px] text-[var(--ink-400)]">{label}</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="tnum text-[19px] leading-none font-semibold text-[var(--ink-900)]">
            {value}
          </span>
          <span className="truncate text-[10.5px] text-[var(--ink-400)]">{hint}</span>
        </div>
      </div>
    </div>
  )
}
