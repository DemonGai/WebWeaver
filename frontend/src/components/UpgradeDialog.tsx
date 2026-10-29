import { useEffect, useState, type ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import type { UpgradeOptions, UpgradeResponse } from '@/types/domain'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconCloud,
  IconKernel,
  IconRefresh,
  IconRollback,
  IconShield,
  IconX,
} from '@/components/icons'

const kernelIcon = (index: number) => {
  if (index === 1) return <IconShield size={14} className="text-amber-500" />
  if (index === 2) return <IconCloud size={14} className="text-violet-500" />
  return <IconKernel size={14} className="text-blue-500" />
}

export function UpgradeDialog({
  open,
  onClose,
  initialKernelId,
}: {
  open: boolean
  onClose: () => void
  initialKernelId?: string
}) {
  const [options, setOptions] = useState<UpgradeOptions | null>(null)
  const [kernelId, setKernelId] = useState('eng-cloak')
  const [scope, setScope] = useState('group')
  const [groups, setGroups] = useState<string[]>(['g-na'])
  const [batch, setBatch] = useState('3 批 (8/8/8)')
  const [interval, setIntervalValue] = useState('10 分钟')
  const [toggles, setToggles] = useState<Record<string, boolean>>({
    auto_rollback: true,
    pause_queue: true,
    refresh_ua: true,
  })
  const [result, setResult] = useState<UpgradeResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open || options) return
    endpoints.upgradeOptions().then((d) => {
      setOptions(d)
      setBatch(d.batches[0])
      setIntervalValue(d.intervals[1] ?? d.intervals[0])
    })
  }, [open, options])

  useEffect(() => {
    if (!open || !initialKernelId) return
    setKernelId(initialKernelId)
  }, [open, initialKernelId])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  useEffect(() => {
    if (!open) {
      setResult(null)
      setSubmitting(false)
    }
  }, [open])

  if (!open || !options) return null

  const selectedCount = options.groups
    .filter((g) => groups.includes(g.id))
    .reduce((sum, g) => sum + g.count, 0)

  const toggleGroup = (id: string) =>
    setGroups((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const submit = async () => {
    setSubmitting(true)
    try {
      const res = await endpoints.createUpgrade({
        kernel_id: kernelId,
        scope,
        groups,
        batch,
        interval,
        auto_rollback: toggles.auto_rollback,
        pause_queue: toggles.pause_queue,
        refresh_ua: toggles.refresh_ua,
      })
      setResult(res)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/35 px-4 py-10 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[calc(100vh-56px)] w-full max-w-[560px] flex-col rounded-2xl bg-white shadow-[0_24px_64px_-12px_rgba(16,24,40,0.28)]"
      >
        {/* 头部 */}
        <div className="flex items-start justify-between gap-4 px-6 pt-6">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#18181b] text-white">
              <IconArrowRight size={15} />
            </span>
            <div>
              <h2 className="text-[15.5px] font-semibold tracking-tight text-[var(--ink-900)]">
                内核升级任务
              </h2>
              <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--ink-500)]">
                将指定实例的内核切换至新版本，支持灰度分批与失败回滚
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="icon-btn size-7 shrink-0 border-0">
            <IconX size={14} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-2">
          {/* 目标内核 */}
          <Block title="目标内核版本">
            <div className="space-y-2">
              {options.kernels.map((k, i) => {
                const active = kernelId === k.id
                return (
                  <button
                    key={k.id}
                    type="button"
                    disabled={k.disabled}
                    onClick={() => setKernelId(k.id)}
                    className={`flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition-colors ${
                      k.disabled
                        ? 'cursor-not-allowed border-[var(--line)] bg-[#fafafa] opacity-60'
                        : active
                          ? 'border-blue-300 bg-blue-50/60'
                          : 'border-[var(--line)] bg-white hover:bg-[#fafafa]'
                    }`}
                  >
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-white ring-1 ring-[var(--line)] ring-inset">
                      {kernelIcon(i)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-[var(--ink-900)]">
                        {k.name}
                      </span>
                      <span className="mt-0.5 block text-[10.5px] text-[var(--ink-400)]">
                        {k.channel} · {k.size}
                        {k.note ? ` · ${k.note}` : ''}
                      </span>
                    </span>
                    <span
                      className={`flex size-[15px] shrink-0 items-center justify-center rounded-full border ${
                        active ? 'border-blue-600 bg-blue-600 text-white' : 'border-[#d4d4d8]'
                      }`}
                    >
                      {active && <IconCheck size={9} />}
                    </span>
                  </button>
                )
              })}
            </div>
          </Block>

          {/* 升级范围 */}
          <Block
            title="升级范围"
            extra={
              <span className="text-[10.5px] text-[var(--ink-400)]">
                已选 {selectedCount} 台实例
              </span>
            }
          >
            <div className="flex items-center gap-1">
              {options.scope_tabs.map((t) => {
                const key = t === '按分组' ? 'group' : t === '按当前版本' ? 'version' : 'manual'
                const active = scope === key
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setScope(key)}
                    className={`h-7 rounded-full px-3 text-[11.5px] font-medium transition-colors ${
                      active
                        ? 'bg-[#18181b] text-white'
                        : 'text-[var(--ink-500)] hover:bg-[#f4f4f5]'
                    }`}
                  >
                    {t}
                  </button>
                )
              })}
            </div>

            <div className="mt-3 space-y-2">
              {options.groups.map((g) => {
                const active = groups.includes(g.id)
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => toggleGroup(g.id)}
                    className={`flex w-full items-center justify-between rounded-xl border px-3.5 py-3 text-left transition-colors ${
                      active
                        ? 'border-[#d9d9de] bg-[#fafafa]'
                        : 'border-[var(--line)] bg-white hover:bg-[#fafafa]'
                    }`}
                  >
                    <span className="flex items-center gap-2.5">
                      <span
                        className={`flex size-[17px] items-center justify-center rounded-full ${
                          active ? 'bg-[#18181b] text-white' : 'border border-[#d4d4d8]'
                        }`}
                      >
                        {active && <IconCheck size={10} />}
                      </span>
                      <span className="text-[12.5px] text-[var(--ink-900)]">{g.name}</span>
                    </span>
                    <span className="tnum text-[11.5px] text-[var(--ink-400)]">{g.count} 台</span>
                  </button>
                )
              })}
            </div>
          </Block>

          {/* 灰度策略 */}
          <Block title="灰度发布策略">
            <div className="grid grid-cols-2 gap-2.5">
              <label className="block">
                <span className="label-xs">分批批次</span>
                <select
                  value={batch}
                  onChange={(e) => setBatch(e.target.value)}
                  className="mt-1.5 h-9 w-full rounded-xl border border-[var(--line)] bg-white px-3 text-[12px] text-[var(--ink-900)] outline-none focus:border-[#d4d4d8]"
                >
                  {options.batches.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label-xs">批次间隔</span>
                <select
                  value={interval}
                  onChange={(e) => setIntervalValue(e.target.value)}
                  className="mt-1.5 h-9 w-full rounded-xl border border-[var(--line)] bg-white px-3 text-[12px] text-[var(--ink-900)] outline-none focus:border-[#d4d4d8]"
                >
                  {options.intervals.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mt-2.5 space-y-2">
              {options.toggles.map((t) => {
                const on = toggles[t.key] ?? t.default
                const Icon =
                  t.key === 'auto_rollback'
                    ? IconRollback
                    : t.key === 'pause_queue'
                      ? IconKernel
                      : IconRefresh
                return (
                  <div
                    key={t.key}
                    className="flex items-center justify-between gap-3 rounded-xl border border-[var(--line)] bg-white px-3.5 py-2.5"
                  >
                    <span className="flex min-w-0 items-center gap-2 text-[12px] text-[var(--ink-700)]">
                      <span className="shrink-0 text-[var(--ink-400)]">
                        <Icon size={12} />
                      </span>
                      <span className="truncate">{t.label}</span>
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={on}
                      aria-label={t.label}
                      onClick={() => setToggles((p) => ({ ...p, [t.key]: !on }))}
                      className={`relative h-[18px] w-[32px] shrink-0 rounded-full transition-colors ${
                        on ? 'bg-emerald-500' : 'bg-[#e4e4e7]'
                      }`}
                    >
                      <span
                        className={`absolute top-[2px] size-[14px] rounded-full bg-white shadow-sm transition-all ${
                          on ? 'left-[16px]' : 'left-[2px]'
                        }`}
                      />
                    </button>
                  </div>
                )
              })}
            </div>

            <div className="mt-2.5 flex items-start gap-2 rounded-xl bg-amber-50 px-3.5 py-3">
              <span className="mt-[1px] shrink-0 text-amber-500">
                <IconAlert size={12} />
              </span>
              <div className="text-[11px] leading-relaxed text-amber-700">
                <span className="font-medium">升级影响提示</span>
                <p className="mt-0.5 text-amber-600">{options.notice}</p>
              </div>
            </div>
          </Block>

        </div>

        {result && (
          <div className="px-6 pt-3">
            <div
              className={`flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-[11.5px] ${
                result.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
              }`}
            >
              <span className="mt-[1px] shrink-0">
                {result.ok ? <IconCheck size={12} /> : <IconAlert size={12} />}
              </span>
              <span>{result.message}</span>
            </div>
          </div>
        )}

        {/* 底部 */}
        <div className="flex shrink-0 items-center justify-between gap-4 border-t border-[var(--line)] px-6 py-4">
          <span className="flex items-center gap-1.5 text-[11px] text-[var(--ink-400)]">
            <IconRefresh size={11} />
            预计耗时 {options.eta}
          </span>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="btn-ghost !h-9">
              取消
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="btn-dark !h-9 disabled:opacity-60"
            >
              {submitting ? '创建中…' : '创建升级任务'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Block({
  title,
  extra,
  children,
}: {
  title: string
  extra?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="mt-5">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-3 w-[2px] rounded-full bg-[#18181b]" />
          <h3 className="text-[12px] font-semibold text-[var(--ink-900)]">{title}</h3>
        </div>
        {extra}
      </div>
      {children}
    </div>
  )
}
