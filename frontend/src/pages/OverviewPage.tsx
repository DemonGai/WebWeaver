import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import {
  AreaChart,
  Card,
  HeroBadge,
  HeroCard,
  OutlineChip,
  ProgressBar,
  SectionHeader,
  SelectBox,
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
  IconClock,
  IconDownload,
  IconExpand,
  IconFingerprint,
  IconGlobe,
  IconMonitor,
  IconPlus,
  IconPower,
  IconShield,
  IconSliders,
  IconUser,
} from '@/components/icons'
import type { InstanceStatus } from '@/types/domain'

const statusMeta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空间', tone: 'blue' },
  error: { label: '异常', tone: 'rose' },
  stopped: { label: '已停止', tone: 'zinc' },
  queued: { label: '排队中', tone: 'amber' },
}

const toneOf: Record<string, Tone> = {
  emerald: 'emerald',
  blue: 'blue',
  rose: 'rose',
  amber: 'amber',
  violet: 'violet',
  zinc: 'zinc',
}

const eventTone: Record<string, Tone> = {
  emerald: 'emerald',
  violet: 'violet',
  amber: 'amber',
  rose: 'rose',
  blue: 'blue',
}

export default function OverviewPage() {
  const { data, status, error, reload } = useApi(endpoints.overview, [])

  if (status === 'loading') return <PageShell><Loading /></PageShell>
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const { cluster, pool_status, load, cards, instances, events, trend, trend_stats, novnc_preview } =
    data

  return (
    <PageShell>
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-[26px] leading-tight font-semibold tracking-tight">集群总览</h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-600">
              <span className="size-[5px] rounded-full bg-emerald-500" />
              实时同步 · {cluster.updated_seconds} 秒前
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">
            管理 {cluster.total} 台浏览器实例 · {cluster.accounts_total} 个账号 ·{' '}
            {cluster.ip_total} 个出口 IP · 24 套指纹模板
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SelectBox label="最近 24 小时" />
          <button type="button" className="btn-ghost">
            <IconDownload size={14} />
            导出报表
          </button>
          <button type="button" className="btn-dark">
            <IconPlus size={14} />
            新建实例
          </button>
        </div>
      </div>

      {/* 第一行：集群总览 + 池状态 + 资源负载 */}
      <div className="grid grid-cols-12 gap-4">
        <HeroCard
          className="col-span-5"
          eyebrow="浏览器集群运行总览"
          badge={
            <HeroBadge>
              <IconShield size={11} />
              集群健康 {cluster.health}%
            </HeroBadge>
          }
          value={cluster.online}
          unit={`/ ${cluster.total} 台在线`}
          footer={
            <div className="grid grid-cols-4 divide-x divide-white/10">
              {[
                { k: '账号在线', v: `${cluster.accounts_used} / ${cluster.accounts_total}` },
                { k: 'IP 可用', v: `${cluster.ip_used} / ${cluster.ip_total}` },
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
          <div className="mt-5 flex items-center gap-[7px]">
            {Array.from({ length: 16 }).map((_, i) => {
              const hi = [3, 5, 9, 12, 14].includes(i)
              return (
                <span
                  key={i}
                  className={`h-[22px] flex-1 rounded-full ${
                    hi ? 'bg-blue-400' : 'bg-white/15'
                  }`}
                />
              )
            })}
          </div>
        </HeroCard>

        <Card className="col-span-4 p-5">
          <SectionHeader
            icon={<IconBrowser size={15} />}
            title="浏览器池状态"
            extra={
              <span className="flex items-center gap-1 text-[11px] text-[var(--ink-400)]">
                实时
                <IconArrowUpRight size={12} />
              </span>
            }
          />
          <div className="mt-4 space-y-3.5">
            {pool_status.map((p) => {
              const tone = statusMeta[p.status].tone
              return (
                <div key={p.label}>
                  <div className="flex items-center justify-between">
                    <StatusDot tone={tone} label={p.label} />
                    <span className="tnum text-[13px] font-semibold">{p.value}</span>
                  </div>
                  <ProgressBar
                    value={(p.value / cluster.total) * 100}
                    tone={tone}
                    className="mt-2"
                  />
                </div>
              )
            })}
          </div>
        </Card>

        <Card className="col-span-3 flex flex-col p-5">
          <SectionHeader
            icon={<IconActivity size={15} />}
            title="资源负载"
            extra={<span className="text-[11px] text-[var(--ink-400)]">实时</span>}
          />
          <div className="mt-4 space-y-3">
            <LoadRow label="CPU 峰值" value={load.cpu} tone="violet" />
            <LoadRow label="内存占用" value={load.memory} tone="amber" />
            <LoadRow label="出口带宽" value={load.bandwidth} tone="emerald" />
          </div>
          <div className="mt-auto grid grid-cols-2 gap-2 pt-4">
            <MiniStat label="断连心率" value={String(load.disconnect_minutes)} unit="分钟" />
            <MiniStat label="自动重连" value={String(load.reconnects)} unit="次" />
          </div>
        </Card>
      </div>

      {/* 第二行：四个指标卡 */}
      <div className="mt-4 grid grid-cols-4 gap-4">
        {cards.map((c) => (
          <StatCard
            key={c.key}
            icon={cardIcon(c.key)}
            tone={toneOf[c.tone] ?? 'zinc'}
            title={c.title}
            value={c.value}
            unit={c.unit}
            hint={c.hint}
            progress={c.progress}
          />
        ))}
      </div>

      {/* 第三行：活跃实例 + 实时事件 */}
      <div className="mt-4 grid grid-cols-12 gap-4">
        <Card className="col-span-8 overflow-hidden">
          <div className="flex items-center justify-between px-5 pt-5 pb-3">
            <SectionHeader icon={<IconMonitor size={15} />} title="活跃实例" />
            <div className="flex items-center gap-2">
              <span className="tnum text-[11px] text-[var(--ink-400)]">
                {cluster.online} 运行中
              </span>
              <SelectBox label="全部状态" />
              <button type="button" className="icon-btn">
                <IconSliders size={13} />
              </button>
            </div>
          </div>

          <table className="w-full">
            <thead>
              <tr className="border-y border-[var(--line)] bg-[#fcfcfd]">
                <th className="table-th w-[24%]">实例名称</th>
                <th className="table-th w-[12%]">状态</th>
                <th className="table-th w-[18%]">绑定账号</th>
                <th className="table-th w-[16%]">出口 IP</th>
                <th className="table-th w-[18%]">指纹模板</th>
                <th className="table-th w-[12%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {instances.map((it) => {
                const meta = statusMeta[it.status]
                return (
                  <tr key={it.id} className="border-b border-[var(--line)] last:border-0">
                    <td className="table-td">
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--ink-400)]">
                          <IconBrowser size={13} />
                        </span>
                        <span className="font-medium text-[var(--ink-900)]">{it.name}</span>
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
                        {it.account}
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
                        <button type="button" className="btn-dark !h-7 !px-2.5 !text-[11.5px]">
                          <IconMonitor size={11} />
                          noVNC
                        </button>
                        <button type="button" className="icon-btn size-7">
                          {it.status === 'error' ? <IconPower size={12} /> : <IconExpand size={12} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <div className="flex items-center justify-between px-5 py-3">
            <span className="text-[11.5px] text-[var(--ink-400)]">
              显示 5 / {cluster.online} 台运行中实例
            </span>
            <a
              href="/browsers"
              className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-700)] hover:text-[var(--ink-900)]"
            >
              进入浏览器池
              <IconArrowRight size={12} />
            </a>
          </div>
        </Card>

        <Card className="col-span-4 flex flex-col p-5">
          <SectionHeader
            icon={<IconBolt size={15} />}
            title="实时事件"
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
                  className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full ${
                    dotBg[eventTone[e.tone] ?? 'zinc']
                  }`}
                >
                  <span className="size-[5px] rounded-full bg-current opacity-70" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] leading-snug font-medium text-[var(--ink-900)]">
                    {e.title}
                  </div>
                  {e.detail && (
                    <div className="mt-0.5 text-[11px] text-[var(--ink-500)]">{e.detail}</div>
                  )}
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className={`chip ${badgeTone[eventTone[e.tone] ?? 'zinc']}`}>
                      {e.tag}
                    </span>
                    <span className="text-[10.5px] text-[var(--ink-400)]">{e.time}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-[var(--line)] pt-3">
            <span className="text-[11px] text-[var(--ink-400)]">今日共 1,286 事件</span>
            <span className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-700)]">
              全部日志
              <IconArrowRight size={12} />
            </span>
          </div>
        </Card>
      </div>

      {/* 第四行：noVNC 预览 + 资源趋势 */}
      <div className="mt-4 grid grid-cols-12 gap-4">
        <Card className="col-span-7 p-5">
          <SectionHeader
            icon={<IconMonitor size={15} />}
            title="noVNC 实时画面"
            extra={
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[var(--ink-500)]">
                  {novnc_preview.instance} · {novnc_preview.fps} fps ·{' '}
                  {novnc_preview.latency_ms} ms
                </span>
                <button type="button" className="btn-dark !h-7 !px-2.5 !text-[11.5px]">
                  <IconExpand size={11} />
                  接入查看
                </button>
              </div>
            }
          />

          <div className="mt-4 overflow-hidden rounded-xl border border-[var(--line)]">
            <div className="flex items-center gap-2 border-b border-[var(--line)] bg-[#fafafa] px-3 py-2">
              <div className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-rose-400" />
                <span className="size-2 rounded-full bg-amber-400" />
                <span className="size-2 rounded-full bg-emerald-400" />
              </div>
              <div className="ml-2 flex h-5 flex-1 items-center gap-1.5 rounded-full bg-white px-2.5 text-[10px] text-[var(--ink-400)] ring-1 ring-[var(--line)] ring-inset">
                <IconShield size={9} className="text-emerald-500" />
                {novnc_preview.url}
              </div>
            </div>
            <ScreenPlaceholder />
          </div>
        </Card>

        <Card className="col-span-5 p-5">
          <SectionHeader
            icon={<IconActivity size={15} />}
            title="集群资源趋势"
            extra={<span className="text-[10.5px] text-[var(--ink-400)]">最近 24 小时 · 5 分钟粒度</span>}
          />
          <div className="mt-3">
            <AreaChart
              primary={trend.series}
              secondary={trend.companion}
              labels={trend.labels}
              height={132}
              primaryLabel="并发实例"
              secondaryLabel="可用 IP"
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {trend_stats.map((s) => (
              <div key={s.label} className="rounded-xl bg-[#fafafa] px-3 py-2.5">
                <div className="text-[10.5px] text-[var(--ink-500)]">{s.label}</div>
                <div className="tnum mt-1 text-[15px] font-semibold">
                  {s.value}
                  <span className="ml-0.5 text-[10.5px] font-normal text-[var(--ink-400)]">
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

function LoadRow({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  return (
    <div>
      <div className="flex items-center justify-between text-[11.5px]">
        <span className="text-[var(--ink-500)]">{label}</span>
        <span className="tnum font-semibold">{value}%</span>
      </div>
      <ProgressBar value={value} tone={tone} className="mt-1.5" height={4} />
    </div>
  )
}

function MiniStat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-xl bg-[#fafafa] px-2.5 py-2">
      <div className="text-[10px] text-[var(--ink-500)]">{label}</div>
      <div className="tnum mt-0.5 text-[13px] font-semibold">
        {value}
        <span className="ml-0.5 text-[10px] font-normal text-[var(--ink-400)]">{unit}</span>
      </div>
    </div>
  )
}

function cardIcon(key: string) {
  const map: Record<string, React.ReactNode> = {
    accounts: <IconUser size={13} />,
    ip: <IconGlobe size={13} />,
    fingerprints: <IconFingerprint size={13} />,
    tasks: <IconClock size={13} />,
  }
  return map[key] ?? <IconUser size={13} />
}

function ScreenPlaceholder() {
  return (
    <div className="relative h-[248px] w-full bg-[linear-gradient(120deg,#6b5e52_0%,#8d7f70_38%,#c9c4bd_62%,#9a8f84_100%)]">
      <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_18%_10%,rgba(255,255,255,0.45),transparent_55%)]" />
      <div className="absolute top-6 left-8 h-24 w-28 rounded-sm bg-white/35 blur-[1px]" />
      <div className="absolute bottom-8 left-1/3 h-16 w-24 rounded-md bg-[#8a4b2a]/50" />
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/35 px-3 py-1.5 text-[9.5px] text-white/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <span>32 fps</span>
          <span>48 ms</span>
          <span>WebSocket 已加密</span>
          <span>会话 01:12:48</span>
        </div>
        <span className="flex items-center gap-1">
          画质：高清
          <IconSliders size={9} />
        </span>
      </div>
    </div>
  )
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
