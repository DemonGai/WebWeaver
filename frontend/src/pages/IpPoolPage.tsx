import { useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import {
  AreaChart,
  BarDistribution,
  Card,
  HeroBadge,
  HeroCard,
  PillTabs,
  ProgressBar,
  SearchInput,
  SectionHeader,
  SelectBox,
  StatusDot,
  type Tone,
} from '@/components/ui'
import {
  IconActivity,
  IconBolt,
  IconCheck,
  IconDownload,
  IconGlobe,
  IconLink,
  IconPower,
  IconRefresh,
  IconShield,
  IconSliders,
  IconTag,
  IconUpload,
  IconWifi,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { IpStatus } from '@/types/domain'

const meta: Record<IpStatus, { label: string; tone: Tone }> = {
  available: { label: '可用', tone: 'emerald' },
  in_use: { label: '占用', tone: 'blue' },
  failed: { label: '失败', tone: 'rose' },
}

const typeChip: Record<string, string> = {
  住宅: 'bg-emerald-50 text-emerald-600',
  机房: 'bg-blue-50 text-blue-600',
  移动: 'bg-violet-50 text-violet-600',
}

export default function IpPoolPage() {
  const { data, status, error, reload } = useApi(endpoints.ipPool, [])
  const [tab, setTab] = useState('all')

  if (status === 'loading') return <PageShell><Loading /></PageShell>
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const { totals, cards, resources, region_distribution, suppliers, trend, rotation, filters } = data
  const maxRegion = Math.max(...region_distribution.map((r) => r.value))

  return (
    <PageShell>
      <PageHeader
        title="IP 池"
        subtitle="住宅 / 机房 / 移动代理统一调度，支持自动轮换、健康检测与实例级绑定"
        actions={
          <>
            <button type="button" className="btn-ghost">
              <IconActivity size={14} />
              一键检测
            </button>
            <button type="button" className="btn-dark">
              <IconUpload size={14} />
              导入 IP 资源
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-4">
        <HeroCard
          variant="green"
          className="col-span-4"
          eyebrow="可用 IP 资源"
          badge={
            <HeroBadge>
              <IconWifi size={10} />
              在线率 {totals.online_rate}%
            </HeroBadge>
          }
          value={totals.available}
          unit={`/ ${totals.total} 总数`}
        >
          <div className="mt-6 flex items-center gap-1.5">
            <ProgressBar value={64} tone="zinc" height={4} className="!bg-white/25 [&>div]:!bg-white" />
            <ProgressBar value={22} tone="zinc" height={4} className="!bg-white/25 [&>div]:!bg-white/60" />
            <ProgressBar value={14} tone="zinc" height={4} className="!bg-white/25 [&>div]:!bg-white/35" />
          </div>
        </HeroCard>

        <div className="col-span-8 grid grid-cols-3 gap-4">
          {cards.map((c) => (
            <Card key={c.title} className="flex flex-col justify-between p-5">
              <div className="flex items-start justify-between">
                <span className={`flex size-7 items-center justify-center rounded-lg ${iconTone[c.tone]}`}>
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

      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 p-3.5">
        <div className="flex items-center gap-3">
          <SearchInput placeholder="搜索 IP / 供应商 / 区域" width="w-[240px]" />
          <PillTabs
            items={filters.map((f) => ({
              key: f.key,
              label: f.label,
              count: f.count,
              tone: f.key === 'residential' ? 'emerald' : f.key === 'datacenter' ? 'blue' : 'violet',
            }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectBox label="全部区域" />
          <div className="flex items-center gap-2 rounded-full border border-[var(--line)] bg-white px-3 py-1.5">
            <span className="text-[11.5px] text-[var(--ink-500)]">自动轮换</span>
            <span className="text-[11.5px] font-medium text-emerald-600">开</span>
            <Toggle on />
          </div>
        </div>
      </Card>

      {/* IP 资源明细 */}
      <Card className="mt-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <SectionHeader icon={<IconGlobe size={15} />} title="IP 资源明细" />
          <div className="flex items-center gap-2">
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]">
              <IconLink size={11} />
              批量绑定
            </button>
            <button type="button" className="icon-btn size-7">
              <IconDownload size={12} />
            </button>
          </div>
        </div>

        <table className="w-full">
          <thead>
            <tr className="border-y border-[var(--line)] bg-[#fcfcfd]">
              <th className="table-th w-[22%]">IP 地址</th>
              <th className="table-th w-[16%]">区域</th>
              <th className="table-th w-[12%]">类型</th>
              <th className="table-th w-[10%]">延迟</th>
              <th className="table-th w-[12%]">状态</th>
              <th className="table-th w-[18%]">绑定实例</th>
              <th className="table-th w-[10%] text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {resources.map((r) => {
              const s = meta[r.status]
              return (
                <tr key={r.id} className="border-b border-[var(--line)] last:border-0">
                  <td className="table-td">
                    <div className="tnum font-medium text-[var(--ink-900)]">{r.ip}</div>
                    <div className="text-[10.5px] text-[var(--ink-400)]">{r.supplier}</div>
                  </td>
                  <td className="table-td">
                    {r.region} · {r.city}
                  </td>
                  <td className="table-td">
                    <span className={`chip ${typeChip[r.type]}`}>{r.type}</span>
                  </td>
                  <td className="table-td tnum">{r.latency_ms} ms</td>
                  <td className="table-td">
                    <StatusDot tone={s.tone} label={s.label} />
                  </td>
                  <td className="table-td">
                    {r.bound_instance ? (
                      <span className="tnum text-[var(--ink-700)]">{r.bound_instance}</span>
                    ) : (
                      <span className="text-[var(--ink-400)]">未绑定</span>
                    )}
                  </td>
                  <td className="table-td">
                    <div className="flex items-center justify-end gap-1.5">
                      <button type="button" className="btn-dark !h-7 !px-2.5 !text-[11.5px]">
                        <IconRefresh size={11} />
                        换 IP
                      </button>
                      <button type="button" className="icon-btn size-7">
                        <IconPower size={11} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <div className="border-t border-[var(--line)] px-5 py-3 text-[11px] text-[var(--ink-400)]">
          共 {totals.total} 条资源，当前显示 {resources.length} 条
        </div>
      </Card>

      {/* 区域分布 + 供应商健康 + 规则 */}
      <div className="mt-4 grid grid-cols-12 gap-4">
        <Card className="col-span-7 p-5">
          <SectionHeader icon={<IconGlobe size={15} />} title="区域分布" />
          <div className="mt-5">
            <BarDistribution
              items={region_distribution.map((r) => ({
                label: r.label,
                value: r.value,
                total: maxRegion,
                tone: toneOf(r.tone),
                unit: r.unit,
              }))}
            />
          </div>
        </Card>

        <Card className="col-span-5 flex flex-col p-5">
          <SectionHeader
            icon={<IconShield size={15} />}
            title="供应商健康"
            extra={
              <span className="chip bg-emerald-50 text-emerald-600">
                <IconCheck size={9} />
                全部正常
              </span>
            }
          />
          <div className="mt-4 flex-1 space-y-3">
            {suppliers.map((s) => (
              <div key={s.name} className="flex items-center gap-3">
                <span className={`size-[5px] rounded-full ${healthDot(s.health)}`} />
                <span className="w-[86px] shrink-0 text-[12px] font-medium text-[var(--ink-700)]">
                  {s.name}
                </span>
                <div className="h-[4px] flex-1 overflow-hidden rounded-full bg-[#f2f2f4]">
                  <div
                    className={`h-full rounded-full ${healthBar(s.health)}`}
                    style={{ width: `${s.health}%` }}
                  />
                </div>
                <span className="tnum w-10 text-right text-[11.5px] font-medium">{s.health}%</span>
              </div>
            ))}
          </div>

          <div className="mt-3 rounded-xl bg-[#fafafa] px-3 py-2 text-[10.5px] text-[var(--ink-400)]">
            健康度按最近 10 分钟探测成功率计算
          </div>
        </Card>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl bg-[linear-gradient(120deg,#192236_0%,#283448_100%)] p-5 text-white">
        <div className="flex items-start justify-between">
          <div className="text-[13px] font-semibold">IP 与实例绑定规则</div>
          <span className="text-white/40">
            <IconShield size={15} />
          </span>
        </div>
        <ul className="mt-3 space-y-2">
          {[
            '同一账号切换 IP 时自动清理 Cookie',
            '住宅 IP 单实例最长绑定 12 小时',
            '失效 IP 自动替换同区域可用资源',
          ].map((t) => (
            <li key={t} className="flex items-center gap-2 text-[11.5px] text-white/75">
              <IconCheck size={11} className="text-emerald-400" />
              {t}
            </li>
          ))}
        </ul>
      </div>

      {/* 趋势 + 轮换策略 */}
      <div className="mt-4 grid grid-cols-12 gap-4">
        <Card className="col-span-7 p-5">
          <SectionHeader
            icon={<IconActivity size={15} />}
            title="IP 池健康趋势"
            extra={<span className="text-[10.5px] text-[var(--ink-400)]">最近 24 小时 · 5 分钟粒度</span>}
          />
          <div className="mt-3">
            <AreaChart
              primary={trend.series}
              secondary={trend.companion}
              labels={trend.labels}
              height={128}
              primaryLabel="可用率"
              secondaryLabel="轮换次数"
            />
          </div>
        </Card>

        <Card className="col-span-5 p-5">
          <SectionHeader
            icon={<IconSliders size={15} />}
            title="轮换与调度策略"
            extra={
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-emerald-600">已启用</span>
                <Toggle on={rotation.enabled} />
              </div>
            }
          />
          <div className="mt-3 divide-y divide-[var(--line)]">
            {rotation.items.map((it) => (
              <div key={it.label} className="flex items-center justify-between py-2.5">
                <span className="flex items-center gap-2 text-[11.5px] text-[var(--ink-500)]">
                  <span className="text-[var(--ink-400)]">
                    <IconTag size={11} />
                  </span>
                  {it.label}
                </span>
                <span className="text-[11.5px] font-medium text-[var(--ink-700)]">{it.value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </PageShell>
  )
}

function Toggle({ on }: { on: boolean }) {
  return (
    <span
      className={`relative inline-flex h-[16px] w-[28px] items-center rounded-full transition-colors ${
        on ? 'bg-emerald-500' : 'bg-zinc-300'
      }`}
    >
      <span
        className={`absolute size-[12px] rounded-full bg-white transition-all ${
          on ? 'left-[14px]' : 'left-[2px]'
        }`}
      />
    </span>
  )
}

const toneOf = (t: string): Tone =>
  t === 'emerald' ? 'emerald' : t === 'blue' ? 'blue' : t === 'violet' ? 'violet' : 'amber'

const healthDot = (v: number) => (v >= 98 ? 'bg-emerald-500' : v >= 95 ? 'bg-emerald-400' : 'bg-amber-400')
const healthBar = (v: number) => (v >= 98 ? 'bg-emerald-500' : v >= 95 ? 'bg-emerald-400' : 'bg-amber-400')

const iconTone: Record<string, string> = {
  emerald: 'bg-emerald-50 text-emerald-500',
  blue: 'bg-blue-50 text-blue-500',
  amber: 'bg-amber-50 text-amber-500',
  rose: 'bg-rose-50 text-rose-500',
  violet: 'bg-violet-50 text-violet-500',
  zinc: 'bg-zinc-100 text-zinc-500',
}

function cardIcon(title: string) {
  if (title.includes('住宅')) return <IconGlobe size={13} />
  if (title.includes('机房')) return <IconBolt size={13} />
  return <IconShield size={13} />
}
