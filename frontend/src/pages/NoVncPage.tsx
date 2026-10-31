import { Link, useParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import {
  Card,
  OutlineChip,
  SectionHeader,
  SoftChip,
  StatusDot,
  type Tone,
} from '@/components/ui'
import {
  IconArrowLeft,
  IconChevronRight,
  IconClipboard,
  IconDownload,
  IconExpand,
  IconGlobe,
  IconList,
  IconLock,
  IconMonitor,
  IconPlus,
  IconRefresh,
  IconShield,
  IconSliders,
  IconTag,
  IconUser,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstanceStatus } from '@/types/domain'

const statusMeta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空间', tone: 'blue' },
  error: { label: '异常', tone: 'rose' },
  stopped: { label: '已停止', tone: 'zinc' },
  queued: { label: '排队中', tone: 'amber' },
}

export default function NoVncPage() {
  const { id = 'brw-us-west-042' } = useParams()
  const { data, status, error, reload } = useApi(() => endpoints.novnc(id), [id])

  if (status === 'loading') return <Shell><Loading /></Shell>
  if (status === 'error')
    return (
      <Shell>
        <ErrorState message={error} onRetry={reload} />
      </Shell>
    )
  if (!data) return null

  const { instance, state, account, exit_ip, fingerprint, logs } = data
  const s = statusMeta[instance.status]

  return (
    <Shell>
      {/* 顶部工具栏 */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/browsers" className="icon-btn size-8">
            <IconArrowLeft size={14} />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[15px] font-semibold tracking-tight">{instance.name}</h1>
              <span className="chip bg-emerald-50 text-emerald-600 gap-1">
                <span className="size-[4px] rounded-full bg-emerald-500" />
                {instance.connection}
              </span>
            </div>
            <div className="mt-0.5 text-[11px] text-[var(--ink-400)]">
              noVNC 实时接管 · 分组：{instance.group}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost">
            <IconPlus size={13} />
            新建标签
          </button>
          <button type="button" className="btn-ghost">
            <IconClipboard size={13} />
            同步剪贴板
          </button>
          <button type="button" className="btn-dark">
            <IconX size={13} />
            结束会话
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* 左侧：浏览器画面 */}
        <Card className="col-span-8 flex flex-col overflow-hidden">
          {/* 地址栏 */}
          <div className="flex items-center gap-2 border-b border-[var(--line)] px-4 py-2.5">
            <div className="flex items-center gap-1 text-[var(--ink-400)]">
              <button type="button" className="icon-btn size-6 !border-transparent">
                <IconArrowLeft size={12} />
              </button>
              <button type="button" className="icon-btn size-6 !border-transparent">
                <IconChevronRight size={12} />
              </button>
              <button type="button" className="icon-btn size-6 !border-transparent">
                <IconRefresh size={12} />
              </button>
            </div>
            <div className="flex h-7 flex-1 items-center gap-2 rounded-full bg-[#f7f7f8] px-3 text-[11.5px] text-[var(--ink-700)]">
              <IconLock size={10} className="text-emerald-500" />
              {instance.url}
              <span className="ml-auto text-[var(--ink-400)]">
                <IconTag size={10} />
              </span>
            </div>
            <OutlineChip>{instance.quality === '高清' ? '1440 × 900' : instance.quality}</OutlineChip>
            <button type="button" className="icon-btn size-7">
              <IconExpand size={12} />
            </button>
          </div>

          {/* 标签页 */}
          <div className="flex items-center gap-1.5 border-b border-[var(--line)] px-4 py-2">
            <TabChip active label="Seller Dashboard" />
            <TabChip label="Order Center" />
            <button type="button" className="flex size-6 items-center justify-center rounded-md text-[var(--ink-400)] hover:bg-[#f4f4f5]">
              <IconPlus size={12} />
            </button>
          </div>

          {/* 画面 */}
          <div className="relative min-h-[420px] flex-1 bg-[linear-gradient(125deg,#7a6c5d_0%,#a3937f_35%,#d8d3ca_62%,#8f8274_100%)]">
            <div className="absolute inset-0 bg-[radial-gradient(110%_80%_at_20%_8%,rgba(255,255,255,0.5),transparent_58%)]" />
            <div className="absolute top-8 left-10 h-32 w-40 rounded-sm bg-white/40 blur-[1px]" />
            <div className="absolute bottom-12 left-1/3 h-20 w-28 rounded-md bg-[#8a4b2a]/45" />
          </div>

          {/* 状态栏 */}
          <div className="flex items-center justify-between border-t border-[var(--line)] px-4 py-2.5">
            <div className="flex items-center gap-4 text-[11px] text-[var(--ink-500)]">
              <span className="flex items-center gap-1">
                <IconMonitor size={11} />
                {instance.fps} fps
              </span>
              <span className="flex items-center gap-1">
                <IconRefresh size={11} />
                {instance.latency_ms} ms
              </span>
              <span className="flex items-center gap-1">
                <IconShield size={11} className="text-emerald-500" />
                WebSocket 已加密
              </span>
              <span className="flex items-center gap-1">
                <IconList size={11} />
                会话 {instance.session_time}
              </span>
            </div>
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11px]">
              画质：{instance.quality}
              <IconSliders size={10} />
            </button>
          </div>
        </Card>

        {/* 右侧信息面板 */}
        <div className="col-span-4 space-y-4">
          <div className="rounded-2xl bg-[linear-gradient(120deg,#192236_0%,#283448_100%)] p-5 text-white">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-white/50">实例状态</span>
              <span className="text-white/40">
                <IconMonitor size={13} />
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[22px] font-semibold">{s.label}</span>
              <span className="size-[6px] rounded-full bg-emerald-400" />
            </div>
            <div className="mt-4 space-y-2 border-t border-white/10 pt-3">
              <DarkRow label="启动时间" value={state.started_at} />
              <DarkRow label="内核版本" value={state.kernel} />
              <DarkRow label="内存占用" value={state.memory} />
            </div>
          </div>

          <Card className="p-5">
            <SectionHeader
              icon={<IconUser size={14} />}
              title="绑定账号"
              extra={
                <span className="text-[var(--ink-400)]">
                  <IconSliders size={12} />
                </span>
              }
            />
            <div className="mt-3 flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-blue-50 text-[12px] font-semibold text-blue-500">
                {account.name.slice(5, 6).toUpperCase() || 'S'}
              </span>
              <div>
                <div className="text-[12.5px] font-medium">{account.name}</div>
                <div className="text-[10.5px] text-[var(--ink-400)]">
                  {account.platform} · {account.region}
                </div>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-1.5">
              {account.tags.map((t) => (
                <SoftChip key={t} tone="emerald">
                  {t}
                </SoftChip>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader
              icon={<IconGlobe size={14} />}
              title="出口 IP"
              extra={
                <span className="text-[var(--ink-400)]">
                  <IconGlobe size={12} />
                </span>
              }
            />
            <div className="tnum mt-3 text-[17px] font-semibold tracking-tight">{exit_ip.ip}</div>
            <div className="mt-2 flex items-center gap-1.5">
              <SoftChip tone="blue">{exit_ip.location}</SoftChip>
              <SoftChip tone="blue">{exit_ip.type}</SoftChip>
            </div>
            <div className="mt-3 flex items-center justify-between rounded-lg bg-[#fafafa] px-3 py-2 text-[11px]">
              <span className="text-[var(--ink-500)]">代理延迟</span>
              <span className="tnum font-medium">{exit_ip.latency_ms} ms</span>
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader
              icon={<IconShield size={14} />}
              title="浏览器指纹"
              extra={
                <span className="text-[11px] font-medium text-emerald-600">
                  可信度 {fingerprint.score}%
                </span>
              }
            />
            <div className="mt-3 space-y-2">
              <FpRow label="User-Agent" value={fingerprint.user_agent} />
              <FpRow label="时区 / 语言" value={fingerprint.timezone} />
              <FpRow label="分辨率" value={fingerprint.resolution} />
              <FpRow
                label="Canvas 噪声"
                value={fingerprint.canvas_noise ? '已开启' : '未开启'}
                highlight={fingerprint.canvas_noise}
              />
            </div>
          </Card>
        </div>
      </div>

      {/* 操作日志 */}
      <Card className="mt-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <SectionHeader icon={<IconList size={15} />} title="本次会话操作日志" />
          <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]">
            <IconDownload size={11} />
            导出日志
          </button>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-y border-[var(--line)] bg-[#fcfcfd]">
              <th className="table-th w-[12%]">时间</th>
              <th className="table-th w-[16%]">动作</th>
              <th className="table-th w-[52%]">详情</th>
              <th className="table-th w-[20%]">结果</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.time} className="border-b border-[var(--line)] last:border-0">
                <td className="table-td tnum text-[var(--ink-500)]">{l.time}</td>
                <td className="table-td">
                  <span className="flex items-center gap-1.5 font-medium text-[var(--ink-900)]">
                    <span className="text-[var(--ink-400)]">
                      <IconTag size={11} />
                    </span>
                    {l.action}
                  </span>
                </td>
                <td className="table-td text-[var(--ink-500)]">{l.detail}</td>
                <td className="table-td">
                  <span
                    className={`chip ${
                      l.result === '成功'
                        ? 'bg-emerald-50 text-emerald-600'
                        : 'bg-blue-50 text-blue-600'
                    }`}
                  >
                    {l.result}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full">
      <div className="sticky top-0 z-30 border-b border-[var(--line)] bg-white/95 backdrop-blur">
        <div className="flex h-16 w-full items-center gap-2 px-7">
          <Link
            to="/"
            className="flex size-8 items-center justify-center rounded-lg border border-[var(--line)] text-[var(--ink-500)] hover:bg-[#f7f7f8]"
          >
            <IconArrowLeft size={14} />
          </Link>
          <span className="text-[12.5px] font-medium text-[var(--ink-700)]">WebWeaver</span>
          <span className="text-[12px] text-[var(--ink-400)]">/ 浏览器池 / noVNC 实时接管</span>
        </div>
      </div>
      <main className="w-full px-7 py-5">{children}</main>
    </div>
  )
}

function TabChip({ label, active }: { label: string; active?: boolean }) {
  return (
    <span
      className={`inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11.5px] ${
        active
          ? 'bg-white font-medium text-[var(--ink-900)] ring-1 ring-[var(--line)]'
          : 'bg-transparent text-[var(--ink-500)] hover:bg-[#f7f7f8]'
      }`}
    >
      <IconTag size={10} className="text-[var(--ink-400)]" />
      {label}
      <IconX size={9} className="text-[var(--ink-400)]" />
    </span>
  )
}

function DarkRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-white/45">{label}</span>
      <span className="font-medium text-white/90">{value}</span>
    </div>
  )
}

function FpRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-[var(--ink-400)]">{label}</span>
      <span className={highlight ? 'font-medium text-emerald-600' : 'font-medium text-[var(--ink-700)]'}>
        {value}
      </span>
    </div>
  )
}

// 供其他页面可能的空状态使用
export function EmptyStatus({ tone, label }: { tone: Tone; label: string }) {
  return <StatusDot tone={tone} label={label} />
}
