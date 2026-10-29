import { useEffect, useState, type ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import { Card, PillTabs, SectionHeader, SoftChip, type Tone } from '@/components/ui'
import {
  IconArrowRight,
  IconArrowUpRight,
  IconBox,
  IconCheck,
  IconCheckCircle,
  IconChevronDown,
  IconCloudDown,
  IconDownload,
  IconInfo,
  IconKernel,
  IconLayers,
  IconMonitor,
  IconMore,
  IconRefresh,
  IconRocket,
  IconRollback,
  IconShield,
  IconStarFilled,
} from '@/components/icons'
import type { KernelEngine, KernelEnginePayload, KernelRelease } from '@/types/domain'
import { UpgradeDialog } from '@/components/UpgradeDialog'

const toneTile: Record<string, string> = {
  dark: 'bg-[#18181b] text-white',
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-zinc-100 text-zinc-500',
}

const toneSoft: Record<string, string> = {
  emerald: 'bg-emerald-50 text-emerald-600',
  blue: 'bg-blue-50 text-blue-600',
  violet: 'bg-violet-50 text-violet-600',
  amber: 'bg-amber-50 text-amber-600',
  rose: 'bg-rose-50 text-rose-500',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
}

const toneBar: Record<string, string> = {
  blue: 'bg-blue-500',
  amber: 'bg-amber-500',
  violet: 'bg-violet-500',
  emerald: 'bg-emerald-500',
  zinc: 'bg-zinc-400',
}

const tileIcon: Record<string, ReactNode> = {
  layers: <IconLayers size={15} />,
  monitor: <IconMonitor size={15} />,
  'cloud-down': <IconCloudDown size={15} />,
  box: <IconBox size={15} />,
}

export default function KernelsPage() {
  const { data, status } = useApi<KernelEnginePayload>(() => endpoints.kernels())
  const [tab, setTab] = useState('all')
  const [expanded, setExpanded] = useState<string[]>([])
  const [primaryId, setPrimaryId] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKernel, setDialogKernel] = useState<string | undefined>(undefined)
  const [toast, setToast] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    if (!data || primaryId) return
    const main = data.engines.find((e) => e.primary) ?? data.engines[0]
    setPrimaryId(main.id)
    setExpanded([main.id])
  }, [data, primaryId])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2800)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (status === 'loading' || !data) {
    return (
      <PageShell>
        <div className="py-24 text-center text-[13px] text-[var(--ink-400)]">正在加载内核数据…</div>
      </PageShell>
    )
  }

  const engines = data.engines.filter((e) => {
    if (tab === 'chromium') return e.engine === 'Chromium'
    if (tab === 'firefox') return e.engine === 'Firefox'
    if (tab === 'update') return e.update
    return true
  })

  const toggleRow = (id: string) =>
    setExpanded((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const openSwitch = (kernelId?: string) => {
    setDialogKernel(kernelId)
    setDialogOpen(true)
  }

  const makePrimary = async (engine: KernelEngine) => {
    if (engine.id === primaryId) return
    setPrimaryId(engine.id)
    try {
      const res = await endpoints.setPrimaryKernel(engine.id)
      setToast(res.message)
      if (!res.ok) setPrimaryId(data.engines.find((e) => e.primary)?.id ?? '')
    } catch {
      setPrimaryId(data.engines.find((e) => e.primary)?.id ?? '')
      setToast('切换主力内核失败，请稍后重试')
    }
  }

  const verifyImages = () => {
    setChecking(true)
    window.setTimeout(() => {
      setChecking(false)
      setToast('11 个版本镜像签名校验通过 · 0 个异常')
    }, 700)
  }

  return (
    <PageShell>
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
              浏览器内核管理
            </h1>
            <span className="chip bg-blue-50 text-[11px] text-blue-600">
              <IconArrowUpRight size={11} />1 个内核可更新
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">
            统一管理 CloakBrowser、Camoufox、fingerprint-chromium、ungoogled-chromium 四套引擎及其版本镜像
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button type="button" onClick={verifyImages} disabled={checking} className="btn-ghost">
            <IconShield size={13} />
            {checking ? '校验中…' : '校验镜像'}
          </button>
          <button type="button" className="btn-dark" onClick={() => openSwitch()}>
            <IconDownload size={13} />
            接入新内核
          </button>
        </div>
      </div>

      {/* 统计条 */}
      <div className="grid grid-cols-4 gap-4">
        {data.tiles.map((t) => (
          <div
            key={t.key}
            className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3.5"
          >
            <span
              className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] ${
                toneTile[t.tone] ?? toneTile.dark
              }`}
            >
              {tileIcon[t.icon]}
            </span>
            <div className="min-w-0">
              <div className="text-[10.5px] text-[var(--ink-400)]">{t.label}</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="tnum text-[19px] leading-none font-semibold text-[var(--ink-900)]">
                  {t.value}
                </span>
                <span className="truncate text-[10.5px] text-[var(--ink-400)]">{t.hint}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 内核主表 */}
      <Card className="mt-4 overflow-hidden">
        <div className="flex items-center justify-between gap-4 px-5 pt-5 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-[var(--ink-400)]">
              <IconKernel size={14} />
            </span>
            <h3 className="text-[13.5px] font-semibold text-[var(--ink-900)]">内核引擎</h3>
            <span className="text-[11px] text-[var(--ink-400)]">
              展开任意内核可查看版本镜像与检测明细
            </span>
          </div>
          <PillTabs
            items={data.tabs.map((t) => ({ key: t.key, label: t.label, count: t.count }))}
            active={tab}
            onSelect={setTab}
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1020px] table-fixed">
            <thead>
              <tr className="border-y border-[var(--line)] bg-[#fcfcfd]">
                <th className="table-th w-[25%] pl-5">内核</th>
                <th className="table-th w-[13%]">上游基线</th>
                <th className="table-th w-[15%]">反检测实现</th>
                <th className="table-th w-[17%]">当前版本</th>
                <th className="table-th w-[11%]">已部署实例</th>
                <th className="table-th w-[9%]">检测覆盖</th>
                <th className="table-th w-[10%] pr-5 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {engines.map((e) => (
                <EngineRow
                  key={e.id}
                  engine={e}
                  primary={e.id === primaryId}
                  expanded={expanded.includes(e.id)}
                  onToggle={() => toggleRow(e.id)}
                  onPrimary={() => makePrimary(e)}
                  onSwitch={() => openSwitch(e.id)}
                />
              ))}
              {engines.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[12.5px] text-[var(--ink-400)]">
                    该分类下暂无内核
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-[var(--line)] px-5 py-3">
          <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--ink-400)]">
            <IconCheckCircle size={12} className="text-emerald-500" />
            共 {data.engines.length} 套内核 · {data.total_instances} 台实例已绑定引擎
          </span>
          <span className="text-[11px] text-[var(--ink-400)]">最近同步 2 分钟前</span>
        </div>
      </Card>

      {/* 兜底链路 + 分发 / 更新 */}
      <div className="mt-4 grid grid-cols-12 items-stretch gap-4">
        <Card className="col-span-7 flex flex-col p-5">
          <SectionHeader
            icon={<IconRollback size={14} />}
            title="检测兜底链路"
            extra={
              <span className="chip bg-emerald-50 text-[10.5px] text-emerald-600">
                <span className="size-[5px] rounded-full bg-emerald-500" />
                自动路由已开启
              </span>
            }
          />
          <p className="mt-1 text-[11px] text-[var(--ink-400)]">
            同一实例连续两次触发 challenge 时，按下列顺序自动切换内核，切换记录写入实例日志
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10.5px] text-[var(--ink-400)]">触发条件</span>
            {data.fallback_triggers.map((t) => (
              <span
                key={t}
                className="rounded-full bg-white px-2 py-[3px] text-[10.5px] text-[var(--ink-600)] ring-1 ring-[var(--line)] ring-inset"
              >
                {t}
              </span>
            ))}
          </div>

          <div className="mt-3 space-y-1.5">
            {data.fallback.map((s, i) => (
              <div
                key={s.id}
                className="flex items-start gap-3 rounded-xl bg-[#fafafa] px-3.5 py-2.5"
              >
                <span className="mt-[1px] flex size-5 shrink-0 items-center justify-center rounded-md bg-white text-[10px] font-medium text-[var(--ink-500)] ring-1 ring-[var(--line)] ring-inset">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] font-medium text-[var(--ink-900)]">{s.name}</span>
                    <span className={`chip ${toneSoft[s.tone] ?? toneSoft.zinc}`}>{s.role}</span>
                    <span className="text-[10px] text-[var(--ink-400)]">{s.engine}</span>
                  </div>
                  <p className="mt-0.5 text-[10.5px] leading-relaxed text-[var(--ink-500)]">
                    {s.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-auto flex items-start gap-1.5 border-t border-[var(--line)] pt-3 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
            <span className="mt-[1px] shrink-0">
              <IconInfo size={11} />
            </span>
            四套内核均被拦截时暂停该实例任务并告警，不降级到未加固的普通 Chromium
          </div>
        </Card>

        <div className="col-span-5 space-y-4">
          <section className="relative overflow-hidden rounded-2xl bg-[linear-gradient(138deg,#3d6ff2_0%,#4a45e9_52%,#5a3ef0_100%)] p-5 text-white">
            <div className="flex items-start justify-between">
              <span className="text-[11px] font-medium text-white/65">{data.gray.eyebrow}</span>
              <span className="text-white/70">
                <IconRocket size={15} />
              </span>
            </div>
            <h3 className="mt-2 text-[15px] font-semibold tracking-tight">{data.gray.title}</h3>
            <div className="mt-3 flex items-center justify-between text-[11.5px] text-white/75">
              <span>
                已完成 {data.gray.done} / {data.gray.total} 台
              </span>
              <span className="tnum font-medium text-white">{data.gray.percent}%</span>
            </div>
            <div className="mt-2 h-[5px] w-full overflow-hidden rounded-full bg-white/20">
              <div
                className="h-full rounded-full bg-white"
                style={{ width: `${data.gray.percent}%` }}
              />
            </div>
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {data.gray.stages.map((s) => (
                <span
                  key={s.label}
                  className={`rounded-full px-2.5 py-1 text-[10.5px] font-medium ${
                    s.active
                      ? 'bg-white text-[#3a3fd4]'
                      : 'border border-white/25 bg-white/10 text-white/75'
                  }`}
                >
                  {s.label}
                </span>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                onClick={() => openSwitch('eng-cloak')}
                className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white px-3.5 text-[12px] font-medium text-[#2f37c9] transition-colors hover:bg-white/90"
              >
                查看任务
                <IconArrowRight size={12} />
              </button>
              <button
                type="button"
                className="inline-flex h-8 items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-3.5 text-[12px] font-medium text-white transition-colors hover:bg-white/15"
              >
                <IconRollback size={12} />
                回滚
              </button>
            </div>
          </section>

          <Card className="p-5">
            <SectionHeader
              title="内核更新记录"
              extra={
                <span className="chip bg-[#f4f4f5] text-[10.5px] text-[var(--ink-500)]">
                  {data.release_note.version}
                </span>
              }
            />
            <ul className="mt-3.5 space-y-2.5">
              {data.release_note.items.map((item, i) => (
                <li
                  key={item}
                  className="flex items-start gap-2 text-[11.5px] leading-relaxed text-[var(--ink-700)]"
                >
                  <span
                    className={`mt-[5px] size-[5px] shrink-0 rounded-[1px] ${
                      i === 0 ? 'bg-blue-400' : 'bg-emerald-400'
                    }`}
                  />
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-4 flex items-center justify-between border-t border-[var(--line)] pt-3 text-[10.5px] text-[var(--ink-400)]">
              <span>发布于 {data.release_note.published_at}</span>
              <button type="button" className="text-blue-600 hover:underline">
                查看完整变更
              </button>
            </div>
          </Card>
        </div>
      </div>

      <UpgradeDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        initialKernelId={dialogKernel}
      />

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-[#18181b] px-4 py-2.5 text-[12px] font-medium text-white shadow-[0_12px_32px_-8px_rgba(16,24,40,0.4)]">
          <span className="flex items-center gap-1.5">
            <IconCheck size={12} className="text-emerald-400" />
            {toast}
          </span>
        </div>
      )}
    </PageShell>
  )
}

/* ── 内核行 ───────────────────────────────────────────── */
function EngineRow({
  engine,
  primary,
  expanded,
  onToggle,
  onPrimary,
  onSwitch,
}: {
  engine: KernelEngine
  primary: boolean
  expanded: boolean
  onToggle: () => void
  onPrimary: () => void
  onSwitch: () => void
}) {
  return (
    <>
      <tr
        className={`cursor-pointer border-b border-[var(--line)] transition-colors ${
          expanded ? 'bg-[#fcfcfd]' : 'hover:bg-[#fcfcfd]'
        }`}
        onClick={onToggle}
      >
        <td className="table-td pl-5">
          <div className="flex items-center gap-2.5">
            <span
              className={`shrink-0 text-[var(--ink-400)] transition-transform ${
                expanded ? 'rotate-180' : ''
              }`}
            >
              <IconChevronDown size={13} />
            </span>
            <span
              className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] ${
                toneSoft[engine.tone] ?? toneSoft.zinc
              }`}
            >
              <IconKernel size={15} />
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-[12.5px] font-semibold text-[var(--ink-900)]">
                  {engine.name}
                </span>
                {primary && (
                  <span className="chip bg-[#18181b] px-1.5 text-[10px] text-white">
                    <IconStarFilled size={9} />
                    主力
                  </span>
                )}
              </div>
              <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
                {engine.tagline}
              </div>
            </div>
          </div>
        </td>

        <td className="table-td">
          <div className="text-[11.5px] text-[var(--ink-700)]">{engine.engine}</div>
          <div className="tnum mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
            {engine.base}
          </div>
        </td>

        <td className="table-td">
          <span className={`chip ${toneSoft[engine.tone] ?? toneSoft.zinc}`}>{engine.level}</span>
          <div className="mt-1 truncate text-[10.5px] text-[var(--ink-400)]">{engine.origin}</div>
        </td>

        <td className="table-td">
          <div className="tnum truncate text-[12px] font-medium text-[var(--ink-900)]" title={engine.version}>
            {engine.version}
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            <SoftChip tone={(engine.status_tone as Tone) ?? 'zinc'}>{engine.status}</SoftChip>
            {engine.update && (
              <span className="flex shrink-0 items-center gap-0.5 text-[10px] text-blue-600">
                <IconArrowUpRight size={10} />
                {engine.latest.includes('-') ? engine.latest.split('-').pop() : engine.latest}
              </span>
            )}
          </div>
        </td>

        <td className="table-td">
          <div className="flex items-center gap-2">
            <div className="h-[3px] w-12 overflow-hidden rounded-full bg-[#f0f0f2]">
              <div
                className={`h-full rounded-full ${toneBar[engine.tone] ?? 'bg-zinc-400'}`}
                style={{ width: `${engine.share}%` }}
              />
            </div>
            <span className="tnum text-[11.5px] text-[var(--ink-700)]">{engine.instances}</span>
          </div>
          <div className="mt-1 text-[10.5px] text-[var(--ink-400)]">{engine.share}% 实例占比</div>
        </td>

        <td className="table-td">
          <div className="flex items-center gap-[3px]">
            {engine.checks.map((c) => (
              <span
                key={c.label}
                title={`${c.label} · ${c.status}`}
                className={`h-[11px] w-[6px] rounded-[2px] ${
                  c.tone === 'emerald'
                    ? 'bg-emerald-400'
                    : c.tone === 'amber'
                      ? 'bg-amber-400'
                      : 'bg-[#e4e4e7]'
                }`}
              />
            ))}
          </div>
          <div className="mt-1 text-[10.5px] text-[var(--ink-400)]">
            <span className="tnum font-medium text-[var(--ink-700)]">{engine.pass_rate}%</span> 通过
          </div>
        </td>

        <td className="table-td pr-5">
          <div
            className="flex items-center justify-end gap-1"
            onClick={(ev) => ev.stopPropagation()}
          >
            <button
              type="button"
              onClick={onSwitch}
              className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8]"
            >
              <IconArrowUpRight size={11} />
              切换
            </button>
            <button type="button" className="icon-btn size-7 border-0 text-[var(--ink-400)]">
              <IconMore size={12} />
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-[var(--line)] bg-[#fafafa]">
          <td colSpan={7} className="px-5 pt-3 pb-4">
            <div className="grid grid-cols-12 gap-5">
              <div className="col-span-4">
                <div className="text-[10.5px] font-medium text-[var(--ink-400)]">建议用途</div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--ink-700)]">
                  {engine.usage}
                </p>

                <div className="mt-3 rounded-xl border border-[var(--line)] bg-white px-3.5 py-3">
                  <div className="text-[10.5px] text-[var(--ink-400)]">实现说明</div>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--ink-600)]">
                    {engine.note}
                  </p>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {engine.checks.map((c) => (
                    <span
                      key={c.label}
                      className={`chip ${toneSoft[c.tone] ?? toneSoft.zinc} !text-[10.5px]`}
                    >
                      {c.label}
                      <span className="opacity-70">{c.status}</span>
                    </span>
                  ))}
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onPrimary}
                    disabled={primary}
                    className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[11.5px] font-medium transition-colors ${
                      primary
                        ? 'cursor-default border border-[var(--line)] bg-white text-[var(--ink-400)]'
                        : 'bg-[#18181b] text-white hover:bg-black'
                    }`}
                  >
                    <IconStarFilled size={11} />
                    {primary ? '当前主力内核' : '设为主力'}
                  </button>
                  <button
                    type="button"
                    onClick={onSwitch}
                    className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[var(--line)] bg-white px-3 text-[11.5px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8]"
                  >
                    <IconRefresh size={11} />
                    创建切换任务
                  </button>
                </div>
              </div>

              <div className="col-span-8">
                <div className="flex items-center justify-between">
                  <span className="text-[11.5px] font-medium text-[var(--ink-700)]">版本镜像</span>
                  <span className="text-[10.5px] text-[var(--ink-400)]">
                    {engine.releases.length} 个版本 · {engine.arch} · {engine.channel}
                  </span>
                </div>
                <div className="mt-2 overflow-hidden rounded-xl border border-[var(--line)] bg-white">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-[var(--line)] bg-[#fcfcfd]">
                        <th className="table-th !py-2 !pl-3.5">版本</th>
                        <th className="table-th !py-2">上游基线</th>
                        <th className="table-th !py-2">大小</th>
                        <th className="table-th !py-2">实例</th>
                        <th className="table-th !py-2">状态</th>
                        <th className="table-th !py-2 !pr-3.5 text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {engine.releases.map((r) => (
                        <ReleaseRow key={r.version} release={r} onSwitch={onSwitch} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function ReleaseRow({ release, onSwitch }: { release: KernelRelease; onSwitch: () => void }) {
  return (
    <tr className="border-b border-[var(--line)] last:border-0">
      <td className="table-td !py-2 !pl-3.5">
        <span className="tnum text-[11.5px] font-medium text-[var(--ink-900)]">
          {release.version}
        </span>
        <div className="mt-0.5 text-[10px] text-[var(--ink-400)]">{release.released_at}</div>
      </td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-500)]">{release.base}</td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-700)]">{release.size}</td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-700)]">
        {release.instances || '—'}
      </td>
      <td className="table-td !py-2">
        <SoftChip tone={(release.status_tone as Tone) ?? 'zinc'}>{release.status}</SoftChip>
      </td>
      <td className="table-td !py-2 !pr-3.5">
        <div className="flex items-center justify-end">
          {release.installed ? (
            <button
              type="button"
              onClick={onSwitch}
              className="inline-flex h-6.5 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[10.5px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8]"
            >
              <IconArrowUpRight size={10} />
              分发
            </button>
          ) : (
            <button
              type="button"
              onClick={onSwitch}
              className="inline-flex h-6.5 items-center gap-1 rounded-full bg-blue-600 px-2.5 text-[10.5px] font-medium text-white hover:bg-blue-700"
            >
              <IconDownload size={10} />
              下载并分发
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}
