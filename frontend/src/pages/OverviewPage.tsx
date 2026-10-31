import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import {
  AreaChart,
  Card,
  HeroBadge,
  HeroCard,
  OutlineChip,
  PillTabs,
  ProgressBar,
  SectionHeader,
  StatCard,
  StatusDot,
  type Tone,
} from '@/components/ui'
import {
  IconActivity,
  IconArrowRight,
  IconArrowUpRight,
  IconBolt,
  IconBrowser,
  IconDownload,
  IconExpand,
  IconFingerprint,
  IconGlobe,
  IconMonitor,
  IconPause,
  IconPlus,
  IconRefresh,
  IconShield,
  IconTrend,
  IconUser,
} from '@/components/icons'
import type { HealthPart, InstanceStatus, OverviewPayload, OverviewRange } from '@/types/domain'

const statusMeta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空闲', tone: 'blue' },
  error: { label: '异常', tone: 'rose' },
  stopped: { label: '已停止', tone: 'zinc' },
  queued: { label: '排队中', tone: 'amber' },
}

/** 深色主卡里的槽位条：一眼看出「哪几台在跑、哪几台占着位置」。 */
const laneBg: Record<InstanceStatus, string> = {
  running: 'bg-blue-400',
  idle: 'bg-white/30',
  error: 'bg-rose-400',
  stopped: 'bg-white/10',
  queued: 'bg-amber-400',
}

const TONES: Tone[] = ['emerald', 'blue', 'rose', 'amber', 'violet', 'zinc', 'sky']

const asTone = (value: string | undefined, fallback: Tone = 'zinc'): Tone =>
  TONES.includes(value as Tone) ? (value as Tone) : fallback

/** 健康分越高越绿，掉到 60 以下必须是红色的——徽标不能永远绿着。 */
const healthTone = (score: number): Tone =>
  score >= 90 ? 'emerald' : score >= 75 ? 'blue' : score >= 60 ? 'amber' : 'rose'

// 深色主卡上的文字色，比常规 tone 亮一档才看得清
const healthText: Record<Tone, string> = {
  emerald: 'text-emerald-300',
  blue: 'text-sky-300',
  amber: 'text-amber-300',
  rose: 'text-rose-300',
  violet: 'text-violet-300',
  zinc: 'text-white/70',
  sky: 'text-sky-300',
}

const RANGE_LABEL: Record<OverviewRange, string> = {
  '24h': '最近 24 小时',
  '7d': '最近 7 天',
  '30d': '最近 30 天',
}

// 每张配额卡直达对应的维护页——首页只做导航，维护动作都在各自列表页完成
const CARD_HREF: Record<string, string> = {
  accounts: '/accounts',
  ip: '/ip-pool',
  fingerprints: '/fingerprints',
}

const REFRESH_MS = 30_000

export default function OverviewPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState<OverviewRange>('7d')
  const [auto, setAuto] = useState(true)
  const [statusFilter, setStatusFilter] = useState('all')

  const { data, status, error, reload, refresh } = useApi(
    () => endpoints.overview(range),
    [range],
  )

  // 轮询用静默刷新：整页每 30 秒闪一次骨架屏比不刷新更糟
  useEffect(() => {
    if (!auto) return
    const timer = window.setInterval(refresh, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [auto, refresh])

  const exportCsv = useCallback((payload: OverviewPayload) => {
    const header = [
      '实例名称',
      '状态',
      '分组',
      '绑定账号',
      '出口 IP',
      '地区',
      '指纹模板',
      '延迟(ms)',
      '帧率(fps)',
      '启动时间',
      '备注',
    ]
    const rows = payload.instances.map((it) => [
      it.name,
      statusMeta[it.status].label,
      it.group,
      it.account,
      it.ip,
      it.region,
      it.fingerprint,
      it.latency_ms ?? '',
      it.fps ?? '',
      it.started_at ?? '',
      it.note ?? '',
    ])
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\r\n')
    // 带 BOM，Excel 打开 UTF-8 中文才不乱码
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const stamp = new Date().toISOString().slice(0, 16).replace(/[:T-]/g, '')
    link.href = url
    link.download = `webweaver-overview-${stamp}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }, [])

  if (status === 'loading')
    return (
      <PageShell>
        <Loading />
      </PageShell>
    )
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const { cluster, pool_status, health_parts, cards, instances, events, trend, trend_stats } = data

  const filtered =
    statusFilter === 'all' ? instances : instances.filter((i) => i.status === statusFilter)
  const visible = filtered.slice(0, 6)
  const emptyHint =
    statusFilter === 'all'
      ? '当前还没有任何实例'
      : `当前没有「${statusMeta[statusFilter as InstanceStatus]?.label ?? '该'}」状态的实例`
  const counts = instances.reduce<Record<string, number>>((acc, it) => {
    acc[it.status] = (acc[it.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <PageShell>
      {/* ── 页头：标题 + 时间窗 + 动作 ────────────────────── */}
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-[26px] leading-tight font-semibold tracking-tight">集群总览</h1>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                auto ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'
              }`}
            >
              <span
                className={`size-[5px] rounded-full ${auto ? 'animate-pulse bg-emerald-500' : 'bg-zinc-400'}`}
              />
              {auto ? '实时同步 · 每 30 秒' : '自动同步已暂停'}
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">
            管理 {cluster.total} 台浏览器实例 · {cluster.accounts_total} 个账号 ·{' '}
            {cluster.ip_total} 个出口 IP
          </p>
        </div>

        <div className="flex items-center gap-2">
          <PillTabs
            items={[
              { key: '24h', label: '24 小时' },
              { key: '7d', label: '7 天' },
              { key: '30d', label: '30 天' },
            ]}
            active={range}
            onSelect={(key) => setRange(key as OverviewRange)}
          />
          <button
            type="button"
            onClick={() => setAuto((v) => !v)}
            className="btn-ghost"
            title={auto ? '每 30 秒自动刷新，点击暂停' : '已暂停自动刷新，点击恢复'}
          >
            {auto ? <IconPause size={13} /> : <IconRefresh size={13} />}
            {auto ? '自动刷新' : '已暂停'}
          </button>
          <button type="button" className="btn-ghost" onClick={() => exportCsv(data)}>
            <IconDownload size={14} />
            导出报表
          </button>
          <button type="button" className="btn-dark" onClick={() => navigate('/browsers')}>
            <IconPlus size={14} />
            新建实例
          </button>
        </div>
      </div>

      {/* ── 主视觉：集群态势（大卡）+ 池状态 + 健康构成 ──── */}
      <div className="grid grid-cols-12 gap-4">
        <HeroCard
          className="col-span-6"
          eyebrow="浏览器集群运行总览"
          badge={
            <HeroBadge>
              <IconShield size={11} />
              集群健康
              <span className={`ml-0.5 font-semibold ${healthText[healthTone(cluster.health)]}`}>
                {cluster.health}%
              </span>
            </HeroBadge>
          }
          value={cluster.online}
          unit={`/ ${cluster.total} 台在线`}
          footer={
            <div className="grid grid-cols-4 divide-x divide-white/10">
              {[
                { k: '账号在线', v: `${cluster.accounts_used} / ${cluster.accounts_total}` },
                { k: '出口占用', v: `${cluster.ip_used} / ${cluster.ip_total}` },
                { k: '平均响应', v: `${cluster.avg_latency_ms} ms` },
                { k: 'noVNC 帧率', v: `${cluster.novnc_fps} fps` },
              ].map((m) => (
                <div key={m.k} className="px-3 first:pl-0">
                  <div className="text-[10.5px] text-white/45">{m.k}</div>
                  <div className="tnum mt-1 text-[14px] font-semibold">{m.v}</div>
                </div>
              ))}
            </div>
          }
        >
          <div className="mt-5">
            <div className="flex items-center gap-[7px]">
              {instances.map((it) => (
                <span
                  key={it.id}
                  title={`${it.name} · ${statusMeta[it.status].label}`}
                  className={`h-[22px] flex-1 rounded-full transition-opacity hover:opacity-70 ${laneBg[it.status]}`}
                />
              ))}
              {/* 槽位不足 16 时补空位，让「容量」这件事有视觉上的固定尺寸 */}
              {Array.from({ length: Math.max(16 - instances.length, 0) }).map((_, i) => (
                <span key={`slot-${i}`} className="h-[22px] flex-1 rounded-full bg-white/[0.07]" />
              ))}
            </div>
            <div className="mt-2.5 flex items-center gap-4 text-[10px] text-white/45">
              {(['running', 'idle', 'queued', 'error', 'stopped'] as InstanceStatus[])
                .filter((s) => counts[s])
                .map((s) => (
                  <span key={s} className="flex items-center gap-1.5">
                    <span className={`size-[5px] rounded-full ${laneBg[s]}`} />
                    {statusMeta[s].label} {counts[s]}
                  </span>
                ))}
            </div>
          </div>
        </HeroCard>

        <Card className="col-span-3 p-5">
          <SectionHeader
            icon={<IconBrowser size={15} />}
            title="实例池状态"
            extra={
              <Link
                to="/browsers"
                className="flex items-center gap-1 text-[11px] text-[var(--ink-400)] hover:text-[var(--ink-900)]"
              >
                详情
                <IconArrowUpRight size={12} />
              </Link>
            }
          />
          <div className="mt-4 space-y-3.5">
            {pool_status.map((p) => {
              const tone = statusMeta[p.status].tone
              return (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => {
                    setStatusFilter(p.status)
                    document.getElementById('instance-board')?.scrollIntoView({ behavior: 'smooth' })
                  }}
                  className="block w-full text-left"
                >
                  <div className="flex items-center justify-between">
                    <StatusDot tone={tone} label={p.label} />
                    <span className="tnum text-[13px] font-semibold">{p.value}</span>
                  </div>
                  <ProgressBar
                    value={cluster.total ? (p.value / cluster.total) * 100 : 0}
                    tone={tone}
                    className="mt-2"
                  />
                </button>
              )
            })}
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <SectionHeader
            icon={<IconShield size={15} />}
            title="健康分构成"
            extra={<span className="text-[11px] text-[var(--ink-400)]">加权总分</span>}
          />
          <div className="mt-4 space-y-3">
            {health_parts.map((p) => (
              <HealthRow key={p.key} part={p} />
            ))}
          </div>
          <div className="mt-3.5 rounded-xl bg-[#fafafa] px-3 py-2 text-[10.5px] leading-relaxed text-[var(--ink-500)]">
            总分 = 实例 45% + 出口 25% + 账号 20% + 指纹 10%，任一项掉分都会拉低集群健康度。
          </div>
        </Card>
      </div>

      {/* ── 次一级：基础设施配额（每张卡右上角直达对应维护页） ── */}
      <Divider label="资源与配额" />
      <div className="grid grid-cols-3 gap-4">
        {cards.map((c) => {
          const href = CARD_HREF[c.key] ?? '/browsers'
          return (
            <StatCard
              key={c.key}
              icon={cardIcon(c.key)}
              tone={asTone(c.tone)}
              title={c.title}
              value={c.value}
              unit={c.unit}
              hint={c.hint}
              progress={c.progress}
              action={
                <Link
                  to={href}
                  className="flex items-center gap-1 text-[11px] text-[var(--ink-400)] transition-colors hover:text-[var(--ink-900)]"
                >
                  详情
                  <IconArrowUpRight size={12} />
                </Link>
              }
            />
          )
        })}
      </div>

      {/* ── 明细：活跃实例 + 审计事件流 ───────────────────── */}
      <Divider label="运行明细" />
      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-8 overflow-hidden">
          <div id="instance-board" className="flex items-center justify-between px-5 pt-5 pb-3">
            <SectionHeader icon={<IconMonitor size={15} />} title="活跃实例" />
            <PillTabs
              items={[
                { key: 'all', label: '全部', count: instances.length },
                { key: 'running', label: '运行中', count: counts.running ?? 0, tone: 'emerald' },
                { key: 'idle', label: '空闲', count: counts.idle ?? 0, tone: 'blue' },
                { key: 'error', label: '异常', count: counts.error ?? 0, tone: 'rose' },
                { key: 'stopped', label: '已停止', count: counts.stopped ?? 0 },
              ]}
              active={statusFilter}
              onSelect={setStatusFilter}
            />
          </div>

          <table className="w-full">
            <thead>
              <tr className="border-y border-[var(--line)] bg-[#fcfcfd]">
                <th className="table-th w-[26%]">实例名称</th>
                <th className="table-th w-[12%]">状态</th>
                <th className="table-th w-[18%]">绑定账号</th>
                <th className="table-th w-[17%]">出口 IP</th>
                <th className="table-th w-[15%]">指纹模板</th>
                <th className="table-th w-[12%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((it) => {
                const meta = statusMeta[it.status]
                return (
                  <tr key={it.id} className="border-b border-[var(--line)] last:border-0">
                    <td className="table-td">
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--ink-400)]">
                          <IconBrowser size={13} />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate font-medium text-[var(--ink-900)]">{it.name}</div>
                          <div className="text-[10.5px] text-[var(--ink-400)]">{it.group}</div>
                        </div>
                      </div>
                    </td>
                    <td className="table-td">
                      <StatusDot tone={meta.tone} label={meta.label} />
                    </td>
                    <td className="table-td">
                      <div className="flex items-center gap-1.5">
                        <span className="flex size-4 items-center justify-center rounded bg-blue-50 text-[9px] font-semibold text-blue-500">
                          {it.account.slice(0, 1).toUpperCase()}
                        </span>
                        <span className="truncate">{it.account}</span>
                      </div>
                    </td>
                    <td className="table-td">
                      <div className="tnum text-[var(--ink-900)]">{it.ip}</div>
                      <div className="text-[10.5px] text-[var(--ink-400)]">{it.region}</div>
                    </td>
                    <td className="table-td">
                      <OutlineChip>{it.fingerprint}</OutlineChip>
                    </td>
                    <td className="table-td">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => navigate(`/novnc/${it.id}`)}
                          className="btn-dark !h-7 !px-2.5 !text-[11.5px]"
                          title={`查看 ${it.name} 的实时画面`}
                        >
                          <IconMonitor size={11} />
                          noVNC
                        </button>
                        <button
                          type="button"
                          onClick={() => navigate('/browsers')}
                          className="icon-btn size-7"
                          title="在浏览器池中查看"
                        >
                          <IconExpand size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-[12px] text-[var(--ink-400)]">
                    {emptyHint}
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <div className="flex items-center justify-between px-5 py-3">
            <span className="text-[11.5px] text-[var(--ink-400)]">
              显示 {visible.length} / {filtered.length} 台
              {statusFilter !== 'all' && `（共 ${instances.length} 台实例）`}
            </span>
            <Link
              to="/browsers"
              className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-700)] hover:text-[var(--ink-900)]"
            >
              进入浏览器池
              <IconArrowRight size={12} />
            </Link>
          </div>
        </Card>

        <Card className="col-span-4 flex flex-col p-5">
          <SectionHeader
            icon={<IconBolt size={15} />}
            title="最新操作"
            extra={
              <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-[3px] text-[10px] font-semibold text-rose-500">
                <span className="size-[4px] rounded-full bg-rose-500" />
                LIVE
              </span>
            }
          />

          <div className="mt-4 flex-1 space-y-4">
            {events.map((e) => (
              <div key={e.id} className="flex gap-2.5">
                <span
                  className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full ${dotBg[asTone(e.tone)]}`}
                >
                  <span className="size-[5px] rounded-full bg-current opacity-70" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] leading-snug font-medium text-[var(--ink-900)]">
                    {e.title}
                  </div>
                  {e.detail && (
                    <div className="mt-0.5 line-clamp-2 text-[11px] text-[var(--ink-500)]">
                      {e.detail}
                    </div>
                  )}
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className={`chip ${badgeTone[asTone(e.tone)]}`}>{e.tag}</span>
                    <span className="text-[10.5px] text-[var(--ink-400)]">{e.time}</span>
                  </div>
                </div>
              </div>
            ))}
            {events.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-2 py-8 text-center">
                <span className="text-[var(--ink-400)]">
                  <IconActivity size={20} />
                </span>
                <p className="text-[12px] text-[var(--ink-400)]">暂无操作记录</p>
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-[var(--line)] pt-3">
            <span className="text-[11px] text-[var(--ink-400)]">来自审计日志 · 最近 5 条</span>
            <Link
              to="/settings/audit-logs"
              className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-700)] hover:text-[var(--ink-900)]"
            >
              全部日志
              <IconArrowRight size={12} />
            </Link>
          </div>
        </Card>
      </div>

      {/* ── 底部：操作趋势（整行，图 9 列 + 统计 3 列） ────── */}
      <div className="mt-4">
        <Card className="p-5">
          <SectionHeader
            icon={<IconTrend size={15} />}
            title="集群操作趋势"
            extra={
              <span className="text-[10.5px] text-[var(--ink-400)]">
                {RANGE_LABEL[range]} · 按审计日志统计
              </span>
            }
          />
          <div className="mt-3 grid grid-cols-12 items-center gap-6">
            <div className="col-span-9">
              <AreaChart
                primary={trend.series}
                secondary={trend.companion}
                labels={trend.labels}
                height={150}
                primaryLabel="操作数"
                secondaryLabel="失败数"
              />
            </div>
            <div className="col-span-3 space-y-2.5">
              {trend_stats.map((s) => (
                <div key={s.label} className="rounded-xl bg-[#fafafa] px-3.5 py-3">
                  <div className="text-[10.5px] text-[var(--ink-500)]">{s.label}</div>
                  <div className="tnum mt-1 text-[17px] font-semibold">
                    {s.value}
                    <span className="ml-0.5 text-[10.5px] font-normal text-[var(--ink-400)]">
                      {s.unit}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </PageShell>
  )
}

/* ── 局部组件 ─────────────────────────────────────────── */
const dotBg: Record<Tone, string> = {
  emerald: 'bg-emerald-50 text-emerald-500',
  blue: 'bg-blue-50 text-blue-500',
  rose: 'bg-rose-50 text-rose-500',
  amber: 'bg-amber-50 text-amber-500',
  violet: 'bg-violet-50 text-violet-500',
  zinc: 'bg-zinc-100 text-zinc-400',
  sky: 'bg-sky-50 text-sky-500',
}

const badgeTone: Record<Tone, string> = {
  emerald: 'bg-emerald-50 text-emerald-600',
  blue: 'bg-blue-50 text-blue-600',
  rose: 'bg-rose-50 text-rose-500',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
}

function HealthRow({ part }: { part: HealthPart }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11.5px]">
        <span className="text-[var(--ink-500)]">
          {part.label}
          <span className="ml-1 text-[10px] text-[var(--ink-400)]">{part.weight}%</span>
        </span>
        <span className="tnum font-semibold">{part.score}%</span>
      </div>
      <ProgressBar value={part.score} tone={asTone(part.tone)} className="mt-1.5" height={4} />
    </div>
  )
}

function Divider({ label }: { label: string }) {
  return (
    <div className="mt-6 mb-3 flex items-center gap-3">
      <span className="text-[11px] font-medium tracking-wide text-[var(--ink-400)]">{label}</span>
      <span className="h-px flex-1 bg-[var(--line)]" />
    </div>
  )
}

function cardIcon(key: string) {
  const map: Record<string, React.ReactNode> = {
    accounts: <IconUser size={13} />,
    ip: <IconGlobe size={13} />,
    fingerprints: <IconFingerprint size={13} />,
  }
  return map[key] ?? <IconUser size={13} />
}

export function Loading() {
  return (
    <div className="flex h-[60vh] items-center justify-center">
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--ink-400)]">
        <span className="size-3 animate-spin rounded-full border-2 border-[var(--line)] border-t-blue-500" />
        加载中…
      </div>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex h-[60vh] flex-col items-center justify-center gap-3">
      <p className="text-[13px] text-rose-500">{message}</p>
      <p className="text-[12px] text-[var(--ink-400)]">
        请确认后端已启动：<code className="rounded bg-zinc-100 px-1.5 py-0.5">uv run uvicorn app.main:app --reload</code>
      </p>
      <button type="button" onClick={onRetry} className="btn-dark">
        重试
      </button>
    </div>
  )
}
