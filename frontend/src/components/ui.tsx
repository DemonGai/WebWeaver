import type { ReactNode } from 'react'
import { IconArrowUpRight, IconChevronDown, IconSearch } from './icons'

/* ── 基础卡片 ─────────────────────────────────────────── */
export function Card({
  className = '',
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return <section className={`card ${className}`}>{children}</section>
}

export function SectionHeader({
  icon,
  title,
  extra,
  className = '',
}: {
  icon?: ReactNode
  title: string
  extra?: ReactNode
  className?: string
}) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
      <div className="flex items-center gap-2">
        {icon && <span className="text-[var(--ink-400)]">{icon}</span>}
        <h3 className="text-[13.5px] font-semibold text-[var(--ink-900)]">{title}</h3>
      </div>
      {extra}
    </div>
  )
}

/* ── 状态点 + 文案 ────────────────────────────────────── */
export type Tone = 'emerald' | 'blue' | 'rose' | 'amber' | 'violet' | 'zinc' | 'sky'

const toneText: Record<Tone, string> = {
  emerald: 'text-emerald-600',
  blue: 'text-blue-600',
  rose: 'text-rose-500',
  amber: 'text-amber-600',
  violet: 'text-violet-600',
  zinc: 'text-zinc-500',
  sky: 'text-sky-600',
}

const toneBg: Record<Tone, string> = {
  emerald: 'bg-emerald-500',
  blue: 'bg-blue-500',
  rose: 'bg-rose-500',
  amber: 'bg-amber-500',
  violet: 'bg-violet-500',
  zinc: 'bg-zinc-400',
  sky: 'bg-sky-500',
}

const toneSoft: Record<Tone, string> = {
  emerald: 'bg-emerald-50 text-emerald-600',
  blue: 'bg-blue-50 text-blue-600',
  rose: 'bg-rose-50 text-rose-500',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
}

export function StatusDot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${toneText[tone]}`}>
      <span className={`size-[6px] rounded-full ${toneBg[tone]}`} />
      {label}
    </span>
  )
}

export function SoftChip({
  tone = 'zinc',
  children,
}: {
  tone?: Tone
  children: ReactNode
}) {
  return <span className={`chip ${toneSoft[tone]}`}>{children}</span>
}

export function OutlineChip({ children }: { children: ReactNode }) {
  return (
    <span className="chip border border-[var(--line)] bg-white text-[var(--ink-500)]">{children}</span>
  )
}

/* ── 细进度条 ─────────────────────────────────────────── */
export function ProgressBar({
  value,
  tone = 'emerald',
  height = 3,
  className = '',
}: {
  value: number
  tone?: Tone
  height?: number
  className?: string
}) {
  return (
    <div
      className={`w-full overflow-hidden rounded-full bg-[#f0f0f2] ${className}`}
      style={{ height }}
    >
      <div
        className={`h-full rounded-full ${toneBg[tone]}`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

/* ── 指标卡（白底） ───────────────────────────────────── */
export function StatCard({
  icon,
  tone = 'zinc',
  value,
  unit,
  title,
  hint,
  progress,
  progressTone,
  action,
  footer,
}: {
  icon?: ReactNode
  tone?: Tone
  value: ReactNode
  unit?: string
  title: string
  hint?: ReactNode
  progress?: number
  progressTone?: Tone
  action?: ReactNode
  footer?: ReactNode
}) {
  return (
    <Card className="relative flex h-full flex-col justify-between p-5">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          {icon && (
            <span className={`flex size-7 items-center justify-center rounded-lg ${toneSoft[tone]}`}>
              {icon}
            </span>
          )}
          <span className="label-xs">{title}</span>
        </div>
        {action ?? (
          <span className="text-[var(--ink-400)]">
            <IconArrowUpRight size={13} />
          </span>
        )}
      </div>

      <div className="mt-6">
        <div className="flex items-end gap-1.5">
          <span className="tnum text-[30px] leading-none font-semibold tracking-tight text-[var(--ink-900)]">
            {value}
          </span>
          {unit && <span className="pb-0.5 text-[12px] text-[var(--ink-500)]">{unit}</span>}
        </div>
        {hint && <div className="mt-1.5 text-[12px] text-[var(--ink-500)]">{hint}</div>}
        {typeof progress === 'number' && (
          <ProgressBar value={progress} tone={progressTone ?? tone} className="mt-3.5" />
        )}
        {footer}
      </div>
    </Card>
  )
}

/* ── 深色 / 渐变大数字卡 ──────────────────────────────── */
export function HeroCard({
  variant = 'dark',
  eyebrow,
  badge,
  value,
  unit,
  children,
  footer,
  className = '',
}: {
  variant?: 'dark' | 'blue' | 'green'
  eyebrow: string
  badge?: ReactNode
  value: ReactNode
  unit?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  className?: string
}) {
  const bg =
    variant === 'blue'
      ? 'bg-[linear-gradient(115deg,#4171f1_0%,#4f48e6_100%)]'
      : variant === 'green'
        ? 'bg-[linear-gradient(120deg,#0ea186_0%,#12b886_55%,#0fae7d_100%)]'
        : 'bg-[linear-gradient(120deg,#192236_0%,#283448_100%)]'

  return (
    <section className={`relative overflow-hidden rounded-2xl p-5 text-white ${bg} ${className}`}>
      <div className="flex items-start justify-between">
        <span className="text-[11.5px] font-medium text-white/60">{eyebrow}</span>
        {badge}
      </div>

      <div className="mt-4 flex items-end gap-1.5">
        <span className="tnum text-[42px] leading-none font-semibold tracking-tight">{value}</span>
        {unit && <span className="pb-1 text-[12.5px] text-white/60">{unit}</span>}
      </div>

      {children}

      {footer && <div className="mt-4 border-t border-white/10 pt-3.5">{footer}</div>}
    </section>
  )
}

export function HeroBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white/80 ring-1 ring-white/10 ring-inset">
      {children}
    </span>
  )
}

/* ── 搜索框 / 下拉 / 分段 ─────────────────────────────── */
export function SearchInput({
  placeholder,
  width = 'w-64',
  value,
  onChange,
}: {
  placeholder: string
  width?: string
  value?: string
  onChange?: (v: string) => void
}) {
  return (
    <div
      className={`flex h-9 items-center gap-2 rounded-full border border-[var(--line)] bg-white px-3.5 ${width}`}
    >
      <span className="text-[var(--ink-400)]">
        <IconSearch size={14} />
      </span>
      <input
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-[12.5px] text-[var(--ink-900)] outline-none placeholder:text-[var(--ink-400)]"
      />
    </div>
  )
}

export function SelectBox({ label }: { label: string }) {
  return (
    <button
      type="button"
      className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[var(--line)] bg-white px-3 text-[12px] font-medium text-[var(--ink-700)] transition-colors hover:bg-[#f7f7f8]"
    >
      {label}
      <IconChevronDown size={13} />
    </button>
  )
}

export function PillTabs({
  items,
  active,
  onSelect,
}: {
  items: { key: string; label: string; count?: number; tone?: Tone }[]
  active: string
  onSelect?: (key: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {items.map((it) => {
        const isActive = it.key === active
        return (
          <button
            key={it.key}
            type="button"
            onClick={() => onSelect?.(it.key)}
            className={`filter-pill ${isActive ? 'filter-pill-active' : ''}`}
          >
            {it.tone && !isActive && it.key !== 'all' && (
              <span className={`size-[5px] rounded-full ${toneBg[it.tone]}`} />
            )}
            {it.label}
            {typeof it.count === 'number' && (
              <span
                className={
                  isActive
                    ? 'ml-0.5 text-[11px] text-white/70'
                    : 'ml-0.5 text-[11px] text-[var(--ink-400)]'
                }
              >
                {it.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ── 双折线面积图（纯 SVG，无第三方图表库） ───────────── */
export function AreaChart({
  primary,
  secondary,
  labels,
  height = 150,
  primaryLabel,
  secondaryLabel,
}: {
  primary: number[]
  secondary?: number[]
  labels: string[]
  height?: number
  primaryLabel?: string
  secondaryLabel?: string
}) {
  const W = 640
  const H = height
  const paddingX = 8
  const paddingY = 14

  const all = secondary ? [...primary, ...secondary] : primary
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1

  const toPoints = (data: number[]) =>
    data.map((v, i) => {
      const x = paddingX + (i * (W - paddingX * 2)) / (data.length - 1)
      const y = paddingY + (1 - (v - min) / span) * (H - paddingY * 2)
      return [x, y] as const
    })

  // Catmull-Rom → 三次贝塞尔，得到平滑曲线
  const smooth = (pts: readonly (readonly [number, number])[]) => {
    if (pts.length < 2) return ''
    let d = `M ${pts[0][0]},${pts[0][1]}`
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] ?? pts[i]
      const p1 = pts[i]
      const p2 = pts[i + 1]
      const p3 = pts[i + 2] ?? p2
      const c1x = p1[0] + (p2[0] - p0[0]) / 6
      const c1y = p1[1] + (p2[1] - p0[1]) / 6
      const c2x = p2[0] - (p3[0] - p1[0]) / 6
      const c2y = p2[1] - (p3[1] - p1[1]) / 6
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`
    }
    return d
  }

  const p1 = toPoints(primary)
  const p2 = secondary ? toPoints(secondary) : null
  const line1 = smooth(p1)
  const area1 = `${line1} L ${p1[p1.length - 1][0]},${H} L ${p1[0][0]},${H} Z`
  const line2 = p2 ? smooth(p2) : ''

  return (
    <div>
      {(primaryLabel || secondaryLabel) && (
        <div className="mb-2 flex items-center justify-end gap-4">
          {primaryLabel && (
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--ink-500)]">
              <span className="h-[2px] w-3.5 rounded bg-blue-500" />
              {primaryLabel}
            </span>
          )}
          {secondaryLabel && (
            <span className="flex items-center gap-1.5 text-[11px] text-[var(--ink-500)]">
              <span className="h-[2px] w-3.5 rounded border-t border-dashed border-emerald-500" />
              {secondaryLabel}
            </span>
          )}
        </div>
      )}

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} preserveAspectRatio="none">
        <defs>
          <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {[0.25, 0.5, 0.75].map((r) => (
          <line
            key={r}
            x1={0}
            x2={W}
            y1={H * r}
            y2={H * r}
            stroke="#f0f0f2"
            strokeWidth={1}
            strokeDasharray="3 4"
          />
        ))}

        <path d={area1} fill="url(#areaFill)" />
        <path d={line1} fill="none" stroke="#3b82f6" strokeWidth={1.8} strokeLinecap="round" />

        {line2 && (
          <path
            d={line2}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            strokeLinecap="round"
          />
        )}

        {p1.map(([x, y], i) =>
          i === p1.length - 3 ? (
            <circle key={i} cx={x} cy={y} r={3} fill="#fff" stroke="#3b82f6" strokeWidth={1.6} />
          ) : null,
        )}
        {p2 &&
          p2.map(([x, y], i) =>
            i === p2.length - 3 ? (
              <circle key={i} cx={x} cy={y} r={2.6} fill="#fff" stroke="#10b981" strokeWidth={1.5} />
            ) : null,
          )}
      </svg>

      <div className="mt-2 flex justify-between px-1">
        {labels.map((l) => (
          <span key={l} className="text-[10.5px] text-[var(--ink-400)]">
            {l}
          </span>
        ))}
      </div>
    </div>
  )
}

/* ── 水平条形分布 ─────────────────────────────────────── */
export function BarDistribution({
  items,
}: {
  items: { label: string; value: number; total: number; tone: Tone; unit?: string }[]
}) {
  return (
    <div className="space-y-4">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-4">
          <span className="w-14 shrink-0 text-[12px] text-[var(--ink-700)]">{it.label}</span>
          <div className="h-[6px] flex-1 overflow-hidden rounded-full bg-[#f2f2f4]">
            <div
              className={`h-full rounded-full ${toneBg[it.tone]}`}
              style={{ width: `${(it.value / it.total) * 100}%` }}
            />
          </div>
          <span className="tnum w-12 shrink-0 text-right text-[12px] font-medium text-[var(--ink-700)]">
            {it.value} {it.unit ?? '个'}
          </span>
        </div>
      ))}
    </div>
  )
}
