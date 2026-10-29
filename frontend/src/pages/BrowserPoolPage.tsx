import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import {
  Card,
  HeroBadge,
  HeroCard,
  PillTabs,
  SearchInput,
  SelectBox,
  type Tone,
} from '@/components/ui'
import {
  IconArrowRight,
  IconBolt,
  IconBrowser,
  IconClock,
  IconExpand,
  IconFingerprint,
  IconGlobe,
  IconGrid,
  IconList,
  IconMonitor,
  IconMore,
  IconPlus,
  IconPower,
  IconRefresh,
  IconShare,
  IconSliders,
  IconUser,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstanceStatus, InstanceSummary } from '@/types/domain'

const meta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空间', tone: 'blue' },
  error: { label: '异常', tone: 'rose' },
  stopped: { label: '已停止', tone: 'zinc' },
  queued: { label: '排队中', tone: 'amber' },
}

const statusChip: Record<InstanceStatus, string> = {
  running: 'bg-emerald-50 text-emerald-600',
  idle: 'bg-blue-50 text-blue-600',
  error: 'bg-rose-50 text-rose-500',
  stopped: 'bg-zinc-100 text-zinc-500',
  queued: 'bg-amber-50 text-amber-600',
}

export default function BrowserPoolPage() {
  const navigate = useNavigate()
  const { data, status, error, reload } = useApi(endpoints.browsers, [])
  const [tab, setTab] = useState('all')

  if (status === 'loading') return <PageShell><Loading /></PageShell>
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const { totals, cards, instances, filters } = data
  const visible =
    tab === 'all'
      ? instances
      : instances.filter((i) =>
          tab === 'running' ? i.status === 'running' : tab === 'idle' ? i.status === 'idle' : i.status === 'error',
        )

  return (
    <PageShell>
      <PageHeader
        title="浏览器池"
        subtitle="每个实例可独立绑定账号、出口 IP 与浏览器指纹，并通过 noVNC 实时接管"
        actions={
          <>
            <button type="button" className="btn-ghost">
              <IconPower size={14} />
              批量启动
            </button>
            <button type="button" className="btn-dark">
              <IconPlus size={14} />
              新建浏览器实例
            </button>
          </>
        }
      />

      {/* 顶部统计 */}
      <div className="grid grid-cols-12 gap-4">
        <HeroCard
          className="col-span-4"
          eyebrow="运行中实例"
          badge={
            <HeroBadge>
              <IconBolt size={10} />
              +{totals.delta} 较昨日
            </HeroBadge>
          }
          value={totals.running}
          unit={`/ ${totals.total} 台`}
        >
          <div className="mt-5 flex items-center gap-[7px]">
            {Array.from({ length: 10 }).map((_, i) => {
              const hi = [2, 4, 7].includes(i)
              return (
                <span
                  key={i}
                  className={`h-[20px] flex-1 rounded-full ${hi ? 'bg-blue-400' : 'bg-white/15'}`}
                />
              )
            })}
          </div>
        </HeroCard>

        <div className="col-span-8 grid grid-cols-3 gap-4">
          {cards.map((c) => (
            <Card key={c.title} className="flex flex-col justify-between p-5">
              <div className="flex items-start justify-between">
                <span
                  className={`flex size-7 items-center justify-center rounded-lg ${iconTone[c.tone]}`}
                >
                  {cardIcon(c.title)}
                </span>
                <span className="text-[11px] text-[var(--ink-400)]">{c.tag}</span>
              </div>
              <div>
                <div className="tnum text-[30px] leading-none font-semibold tracking-tight">
                  {c.value}
                </div>
                <div className="mt-1.5 text-[12px] text-[var(--ink-500)]">{c.hint}</div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* 筛选栏 */}
      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 p-3.5">
        <div className="flex items-center gap-3">
          <SearchInput placeholder="按实例名、账号或 IP 搜索" width="w-[260px]" />
          <PillTabs
            items={filters.map((f) => ({
              key: f.key,
              label: f.label,
              count: f.count,
              tone: f.key === 'running' ? 'emerald' : f.key === 'idle' ? 'blue' : 'rose',
            }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectBox label="全部分组" />
          <SelectBox label="指纹模板" />
          <div className="flex items-center gap-1 rounded-full border border-[var(--line)] p-0.5">
            <button type="button" className="flex size-7 items-center justify-center rounded-full bg-[#18181b] text-white">
              <IconGrid size={13} />
            </button>
            <button type="button" className="flex size-7 items-center justify-center rounded-full text-[var(--ink-400)]">
              <IconList size={13} />
            </button>
          </div>
        </div>
      </Card>

      {/* 实例卡片网格 */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        {visible.map((it, idx) => (
          <InstanceCard key={it.id} item={it} index={idx} onOpen={() => navigate('/novnc/' + it.id)} />
        ))}

        {/* 新建入口 */}
        <button
          type="button"
          className="flex items-center justify-center gap-3 rounded-2xl border border-dashed border-[#dcdce2] bg-white/60 py-6 transition-colors hover:bg-white"
        >
          <span className="flex size-8 items-center justify-center rounded-lg bg-[#f4f4f5] text-[var(--ink-500)]">
            <IconPlus size={15} />
          </span>
          <span className="text-left">
            <span className="block text-[13px] font-medium text-[var(--ink-900)]">新建浏览器实例</span>
            <span className="mt-0.5 block text-[11.5px] text-[var(--ink-400)]">
              批量创建 10 / 50 / 100 台并自动分配账号与 IP
            </span>
          </span>
        </button>

        {/* 批量绑定向导 */}
        <div className="relative overflow-hidden rounded-2xl bg-[linear-gradient(115deg,#4171f1_0%,#4f48e6_100%)] p-5 text-white">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[13px] font-semibold">批量绑定向导</div>
              <div className="mt-1 text-[11.5px] text-white/70">
                按规则为实例批量分配账号、IP 与指纹模板
              </div>
            </div>
            <span className="text-white/60">
              <IconShare size={15} />
            </span>
          </div>
          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white px-3.5 text-[12px] font-medium text-[#3f4bd8]"
            >
              开始配置
              <IconArrowRight size={12} />
            </button>
            <span className="text-[11px] text-white/70">剩余 24 台实例待绑定</span>
          </div>
        </div>
      </div>
    </PageShell>
  )
}

function InstanceCard({
  item,
  index,
  onOpen,
}: {
  item: InstanceSummary
  index: number
  onOpen: () => void
}) {
  const badge = meta[item.status]
  const primary =
    item.status === 'error'
      ? { label: '立即重连', icon: <IconRefresh size={11} /> }
      : item.status === 'idle'
        ? { label: '接管会话', icon: <IconMonitor size={11} /> }
        : { label: '打开 noVNC', icon: <IconMonitor size={11} /> }
  const secondary = item.status === 'error' ? '更换 IP' : '绑定配置'

  return (
    <Card className="flex gap-4 p-4">
      <div
        className={`size-[104px] shrink-0 rounded-xl ${thumbs[index % thumbs.length]}`}
        aria-hidden
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[13.5px] font-semibold tracking-tight text-[var(--ink-900)]">
              {item.name}
            </div>
            <div className="mt-1 text-[11px] text-[var(--ink-400)]">
              分组：{item.group} · {item.note ?? `启动于 ${item.started_at}`}
            </div>
          </div>
          <span className={`chip ${statusChip[item.status]} gap-1`}>
            <span className="size-[4px] rounded-full bg-current" />
            {badge.label}
          </span>
        </div>

        <div className="mt-2.5 flex items-center gap-4 text-[11.5px] text-[var(--ink-600)]">
          <span className="flex items-center gap-1">
            <span className="text-[var(--ink-400)]">
              <IconUser size={11} />
            </span>
            {item.account}
          </span>
          <span className="flex items-center gap-1">
            <span className="text-[var(--ink-400)]">
              <IconGlobe size={11} />
            </span>
            <span className="tnum">{item.ip}</span>
            <span className="text-[var(--ink-400)]">· {item.region}</span>
          </span>
        </div>

        <div className="mt-2 flex items-center gap-3">
          <span className="chip bg-amber-50 text-amber-600">
            <IconFingerprint size={10} />
            {item.fingerprint}
          </span>
          {item.status === 'error' ? (
            <span className="chip bg-rose-50 text-rose-500">{item.note}</span>
          ) : item.fps != null ? (
            <>
              <span className="flex items-center gap-1 text-[11px] text-[var(--ink-500)]">
                <IconMonitor size={10} />
                {item.fps} fps
              </span>
              <span className="flex items-center gap-1 text-[11px] text-[var(--ink-500)]">
                <IconClock size={10} />
                {item.latency_ms} ms
              </span>
            </>
          ) : null}
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button type="button" onClick={onOpen} className="btn-dark !h-7 !px-3 !text-[11.5px]">
              {primary.icon}
              {primary.label}
            </button>
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]">
              {secondary}
            </button>
          </div>
          <div className="flex items-center gap-1">
            <button type="button" className="icon-btn size-7 !border-transparent !bg-transparent">
              <IconPower size={12} />
            </button>
            <button type="button" className="icon-btn size-7 !border-transparent !bg-transparent">
              <IconMore size={13} />
            </button>
          </div>
        </div>
      </div>
    </Card>
  )
}

const thumbs = [
  'bg-[linear-gradient(140deg,#8b7355_0%,#c4b7a4_45%,#6f5f4c_100%)]',
  'bg-[linear-gradient(140deg,#7d8a63_0%,#d4c98f_50%,#8e7f52_100%)]',
  'bg-[linear-gradient(140deg,#9a8a7a_0%,#cfc6ba_45%,#7c6a58_100%)]',
  'bg-[linear-gradient(140deg,#86795f_0%,#b8ab92_50%,#6b5c47_100%)]',
  'bg-[linear-gradient(140deg,#7f7a70_0%,#c2bcae_45%,#726a5f_100%)]',
  'bg-[linear-gradient(140deg,#8a7f72_0%,#c9c0b4_50%,#75695c_100%)]',
]

const iconTone: Record<string, string> = {
  emerald: 'bg-emerald-50 text-emerald-500',
  blue: 'bg-blue-50 text-blue-500',
  amber: 'bg-amber-50 text-amber-500',
  rose: 'bg-rose-50 text-rose-500',
  violet: 'bg-violet-50 text-violet-500',
  zinc: 'bg-zinc-100 text-zinc-500',
}

function cardIcon(title: string) {
  if (title.includes('可调度')) return <IconSliders size={13} />
  if (title.includes('需处理')) return <IconBolt size={13} />
  if (title.includes('队列')) return <IconBrowser size={13} />
  return <IconExpand size={13} />
}
