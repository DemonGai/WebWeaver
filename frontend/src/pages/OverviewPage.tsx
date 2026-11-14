import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import {
  AreaChart,
  Card,
  OutlineChip,
  PillTabs,
  StatusDot,
  type Tone,
} from '@/components/ui'
import {
  IconActivity,
  IconArrowRight,
  IconBrowser,
  IconDownload,
  IconExpand,
  IconMonitor,
  IconPause,
  IconPlus,
  IconRefresh,
  IconShield,
  IconTrend,
} from '@/components/icons'
import type { InstanceStatus, OverviewPayload, OverviewRange } from '@/types/domain'

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

// 健康分低于这个值就不再是「看看就好」，要进主卡的待处理清单
const RISK_SCORE = 90

// 每个健康分项对应一个能真正解决问题的地方，待办点了要能到得了
const HEALTH_HREF: Record<string, string> = {
  instances: '/browsers',
  exit: '/ip-pool',
  accounts: '/accounts',
  fingerprints: '/fingerprints',
}

const RANGE_LABEL: Record<OverviewRange, string> = {
  '24h': '最近 24 小时',
  '7d': '最近 7 天',
  '30d': '最近 30 天',
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

  const offline = Math.max(cluster.total - cluster.online, 0)
  const grade = healthGrade(cluster.health)
  // 待处理不是另算一套指标：就是健康分掉下来的那几项，点了直接去对应维护页
  const risks = health_parts.filter((p) => p.score < RISK_SCORE)
  const accountCard = cards.find((c) => c.key === 'accounts')
  const ipCard = cards.find((c) => c.key === 'ip')
  const fpCard = cards.find((c) => c.key === 'fingerprints')

  return (
    <PageShell>
      {/* ── 页头：只留标题与操作，状态全交给下面那块 ────────── */}
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-[24px] leading-tight font-semibold tracking-tight">集群总览</h1>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                auto ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'
              }`}
            >
              <span
                className={`size-[5px] rounded-full ${auto ? 'animate-pulse bg-emerald-500' : 'bg-zinc-400'}`}
              />
              {auto ? '实时同步' : '已暂停'}
            </span>
          </div>
          <p className="mt-1.5 text-[12px] text-[var(--ink-400)]">
            {cluster.total} 台实例 · {cluster.accounts_total} 个账号 · {cluster.ip_total} 个出口 IP
            · 数据更新于 {relativeTime(cluster.updated_seconds)}
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

      {/* ── 第一层：一屏里唯一的重色块，回答「集群现在怎么样、要做什么」 ── */}
      <section className="relative overflow-hidden rounded-2xl bg-[linear-gradient(118deg,#171b23_0%,#242c3a_58%,#1b2230_100%)] px-6 py-5 text-white">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_352px]">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-white/55">
                <IconShield size={12} />
                集群健康度
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full bg-white/[0.08] px-2 py-[3px] text-[10.5px] font-medium ring-1 ring-white/10 ring-inset ${grade.text}`}
              >
                <span className={`size-[4px] rounded-full ${grade.dot}`} />
                {grade.label}
              </span>
            </div>

            <div className="mt-2.5 flex items-end gap-2">
              <span className="tnum text-[52px] leading-none font-semibold tracking-tight">
                {cluster.health}
              </span>
              <span className="pb-1.5 text-[12px] text-white/40">/ 100</span>
            </div>

            <p className="mt-3 text-[12px] text-white/55">
              <span className="tnum font-medium text-white/85">{cluster.online}</span> 台在线
              <span className="mx-2 text-white/20">·</span>
              <span className="tnum">{offline}</span> 台未运行
              <span className="mx-2 text-white/20">·</span>
              平均响应 <span className="tnum">{cluster.avg_latency_ms}</span> ms
              <span className="mx-2 text-white/20">·</span>
              noVNC <span className="tnum">{cluster.novnc_fps}</span> fps
            </p>

            {/* 按状态分段的容量条：几百台也不会细成发丝，长度就是占比 */}
            <div className="mt-5 flex h-[10px] gap-[3px] overflow-hidden rounded-full">
              {pool_status
                .filter((p) => p.value > 0)
                .map((p) => (
                  <span
                    key={p.label}
                    title={`${p.label} ${p.value} 台`}
                    style={{ width: `${cluster.total ? (p.value / cluster.total) * 100 : 0}%` }}
                    className={`h-full rounded-full transition-opacity hover:opacity-75 ${laneBg[p.status]}`}
                  />
                ))}
              {cluster.total === 0 && <span className="h-full flex-1 rounded-full bg-white/10" />}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-white/45">
              {pool_status
                .filter((p) => p.value > 0)
                .map((p) => (
                  <span key={p.label} className="flex items-center gap-1.5">
                    <span className={`size-[5px] rounded-full ${laneBg[p.status]}`} />
                    {p.label}
                    <span className="tnum text-white/70">{p.value}</span>
                  </span>
                ))}
              {cluster.total === 0 && <span>还没有实例，先到浏览器池新建一台</span>}
            </div>
          </div>

          {/* 右侧：待处理。这是「主」的另一半——看完状态就该知道下一步 */}
          <div className="flex h-full flex-col border-white/10 lg:border-l lg:pl-5">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-medium text-white/55">需要处理</span>
              <span
                className={`rounded-full px-2 py-[2px] text-[10.5px] font-semibold ${
                  risks.length
                    ? 'bg-rose-400/15 text-rose-300'
                    : 'bg-emerald-400/15 text-emerald-300'
                }`}
              >
                {risks.length ? `${risks.length} 项` : '无'}
              </span>
            </div>

            {risks.length === 0 ? (
              <div className="mt-2.5 rounded-xl bg-white/[0.05] px-3 py-3.5 text-[11.5px] leading-relaxed text-white/45">
                四项指标都在 {RISK_SCORE} 分以上，暂时没有需要处理的事项。
              </div>
            ) : (
              <ul className="mt-2 flex-1 space-y-0.5">
                {risks.map((p) => (
                  <li key={p.key}>
                    <button
                      type="button"
                      onClick={() => navigate(HEALTH_HREF[p.key] ?? '/browsers')}
                      className="group flex w-full items-center justify-between gap-3 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-white/[0.07]"
                    >
                      <div className="min-w-0">
                        <p className="flex items-center gap-1.5 text-[12.5px] font-medium">
                          {p.label}
                          <span className={`tnum text-[11px] ${healthText[asTone(p.tone)]}`}>
                            {p.score}%
                          </span>
                        </p>
                        <p className="mt-0.5 truncate text-[10.5px] text-white/40">{p.detail}</p>
                      </div>
                      <IconArrowRight
                        size={13}
                        className="shrink-0 text-white/20 transition-colors group-hover:text-white/80"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {health_parts.some((p) => p.score >= RISK_SCORE) && (
              <div className="mt-3 space-y-1.5 border-t border-white/10 pt-2.5">
                <div className="text-[10px] tracking-wide text-white/30">其余分项</div>
                {health_parts
                  .filter((p) => p.score >= RISK_SCORE)
                  .map((p) => (
                    <div key={p.key} className="flex items-center justify-between text-[11px]">
                      <span className="text-white/40">{p.label}</span>
                      <span className="tnum text-white/70">{p.score}%</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── 第二层：资源水位。一张卡切开，不做成一排同质小卡 ────── */}
      <div className="mt-4 grid grid-cols-2 divide-[var(--line)] overflow-hidden rounded-2xl border border-[var(--line)] bg-white sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
        {[
          {
            key: 'accounts',
            label: '账号会话',
            value: `${cluster.accounts_used}`,
            unit: `/ ${cluster.accounts_total}`,
            hint: accountCard?.hint,
          },
          {
            key: 'ip',
            label: '出口占用',
            value: `${cluster.ip_used}`,
            unit: `/ ${cluster.ip_total}`,
            hint: ipCard?.hint,
          },
          {
            key: 'fingerprints',
            label: '指纹模板',
            value: `${fpCard?.value ?? 0}`,
            unit: '套',
            hint: fpCard?.hint,
          },
          {
            key: 'latency',
            label: '平均响应',
            value: `${cluster.avg_latency_ms}`,
            unit: 'ms',
            hint: '在线实例的 CDP 往返',
          },
          {
            key: 'fps',
            label: 'noVNC 帧率',
            value: `${cluster.novnc_fps}`,
            unit: 'fps',
            hint: '画面流畅度参考值',
          },
          {
            key: 'refresh',
            label: '状态更新',
            value: relativeTime(cluster.updated_seconds),
            unit: '',
            hint: auto ? '每 30 秒自动同步' : '自动同步已暂停',
          },
        ].map((m) => (
          <div key={m.key} className="px-4 py-3">
            <div className="text-[10.5px] text-[var(--ink-400)]">{m.label}</div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="tnum text-[19px] leading-none font-semibold tracking-tight text-[var(--ink-900)]">
                {m.value}
              </span>
              {m.unit && (
                <span className="text-[10.5px] text-[var(--ink-400)]">{m.unit}</span>
              )}
            </div>
            {m.hint && (
              <div className="mt-1 truncate text-[10px] text-[var(--ink-400)]" title={m.hint}>
                {m.hint}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── 第三层：明细。标题压到 11px，刻意比主卡弱 ──────────── */}
      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_356px] xl:items-stretch">
        <section className="flex flex-col">
          <div className="mb-2 flex items-end justify-between gap-3">
            <div className="flex items-baseline gap-2">
              <h2 className="text-[12.5px] font-semibold text-[var(--ink-900)]">活跃实例</h2>
              <span className="text-[10.5px] text-[var(--ink-400)]">
                {instances.length} 台中显示 {visible.length} 台
              </span>
            </div>
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

          <Card className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--line)] bg-[#fcfcfd]">
                  <th className="table-th w-[27%]">实例名称</th>
                  <th className="table-th w-[12%]">状态</th>
                  <th className="table-th w-[19%]">绑定账号</th>
                  <th className="table-th w-[17%]">出口 IP</th>
                  <th className="table-th w-[14%]">指纹模板</th>
                  <th className="table-th w-[11%] text-right">画面</th>
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
                            <div className="truncate font-medium text-[var(--ink-900)]">
                              {it.name}
                            </div>
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
                    <td
                      colSpan={6}
                      className="px-5 py-10 text-center text-[12px] text-[var(--ink-400)]"
                    >
                      {emptyHint}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>

            <div className="flex items-center justify-between border-t border-[var(--line)] px-4 py-2.5">
              <span className="text-[11px] text-[var(--ink-400)]">
                {statusFilter !== 'all'
                  ? `已筛选 ${filtered.length} 台 / 共 ${instances.length} 台`
                  : `共 ${instances.length} 台`}
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
        </section>

        <section className="flex flex-col">
          <div className="mb-2 flex items-end justify-between gap-3">
            <h2 className="text-[12.5px] font-semibold text-[var(--ink-900)]">最近操作</h2>
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-[2px] text-[10px] font-semibold text-rose-500">
              <span className="size-[4px] rounded-full bg-rose-500" />
              LIVE
            </span>
          </div>

          <Card className="flex flex-1 flex-col p-4">
            <div className="flex-1 space-y-3.5">
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
                <div className="flex h-full flex-col items-center justify-center gap-2 py-10 text-center">
                  <span className="text-[var(--ink-400)]">
                    <IconActivity size={20} />
                  </span>
                  <p className="text-[12px] text-[var(--ink-400)]">暂无操作记录</p>
                </div>
              )}
            </div>

            <div className="mt-3 flex items-center justify-between border-t border-[var(--line)] pt-3">
              <span className="text-[10.5px] text-[var(--ink-400)]">来自审计日志</span>
              <Link
                to="/settings/audit-logs"
                className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-700)] hover:text-[var(--ink-900)]"
              >
                全部日志
                <IconArrowRight size={12} />
              </Link>
            </div>
          </Card>
        </section>
      </div>

      {/* ── 第四层：趋势。放最底下、压到最矮，是「有就行」的信息 ── */}
      <div className="mt-5">
        <div className="mb-2 flex items-end justify-between">
          <h2 className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--ink-900)]">
            <span className="text-[var(--ink-400)]">
              <IconTrend size={13} />
            </span>
            操作趋势
          </h2>
          <span className="text-[10.5px] text-[var(--ink-400)]">
            {RANGE_LABEL[range]} · 按审计日志统计
          </span>
        </div>
        <Card className="grid grid-cols-12 items-center gap-6 p-4">
          <div className="col-span-12 xl:col-span-9">
            <AreaChart
              primary={trend.series}
              secondary={trend.companion}
              labels={trend.labels}
              height={128}
              primaryLabel="操作数"
              secondaryLabel="失败数"
            />
          </div>
          <div className="col-span-12 grid grid-cols-3 gap-2 xl:col-span-3 xl:grid-cols-1">
            {trend_stats.map((s) => (
              <div key={s.label} className="rounded-xl bg-[#fafafa] px-3 py-2">
                <div className="text-[10px] text-[var(--ink-400)]">{s.label}</div>
                <div className="tnum mt-0.5 text-[15px] font-semibold">
                  {s.value}
                  <span className="ml-0.5 text-[10px] font-normal text-[var(--ink-400)]">
                    {s.unit}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </PageShell>
  )
}

/* ── 局部工具 ─────────────────────────────────────────── */
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

function healthGrade(score: number) {
  if (score >= 90) return { label: '健康', text: 'text-emerald-300', dot: 'bg-emerald-400' }
  if (score >= 75) return { label: '良好', text: 'text-sky-300', dot: 'bg-sky-400' }
  if (score >= 60) return { label: '需关注', text: 'text-amber-300', dot: 'bg-amber-400' }
  return { label: '风险', text: 'text-rose-300', dot: 'bg-rose-400' }
}

function relativeTime(seconds: number) {
  if (seconds < 60) return `${Math.max(seconds, 0)} 秒前`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  return `${Math.floor(seconds / 86400)} 天前`
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
