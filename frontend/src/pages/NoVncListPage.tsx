import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { copyText } from '@/lib/clipboard'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, PillTabs, SearchInput, SoftChip, type Tone } from '@/components/ui'
import { StatTile } from '@/components/StatTile'
import { IdBadge } from '@/components/IdBadge'
import { Toast, useToast } from '@/components/Toast'
import {
  IconArrowLeft,
  IconArrowUpRight,
  IconBrowser,
  IconEye,
  IconMonitor,
  IconPlay,
  IconPower,
  IconRefresh,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstanceStatus, NoVncTarget } from '@/types/domain'

const meta: Record<InstanceStatus, { label: string; tone: Tone; chip: string }> = {
  running: { label: '运行中', tone: 'emerald', chip: 'bg-emerald-50 text-emerald-600' },
  idle: { label: '空闲', tone: 'blue', chip: 'bg-blue-50 text-blue-600' },
  error: { label: '异常', tone: 'rose', chip: 'bg-rose-50 text-rose-500' },
  stopped: { label: '已停止', tone: 'zinc', chip: 'bg-zinc-100 text-zinc-500' },
  queued: { label: '排队中', tone: 'amber', chip: 'bg-amber-50 text-amber-600' },
}

const availability: Record<
  NoVncTarget['availability'],
  { label: string; tone: Tone }
> = {
  ready: { label: 'noVNC 可用', tone: 'emerald' },
  stopped: { label: '待启动', tone: 'blue' },
  unsupported: { label: '镜像无 noVNC', tone: 'rose' },
  blocked: { label: '待配置', tone: 'amber' },
}

/**
 * noVNC 详情：所有实例的画面入口。
 *
 * 这一页解决的是「哪台能看、哪台不能、为什么不能」——浏览器池里逐张卡片点进去
 * 只能一台台试，镜像不支持 noVNC 的还要白跑一趟。能力判定在后端按镜像做
 * （见 ``services/browser_novnc.py``），这里只负责把结论和下一步动作摆出来。
 */
export default function NoVncListPage() {
  const navigate = useNavigate()
  const { data, status, error, reload } = useApi(endpoints.novncOverview, [])
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState('all')
  const { toast, notify, dismiss } = useToast()

  const instances = data?.instances ?? []

  const tabs = useMemo(() => {
    const count = (key: string) => {
      if (key === 'all') return instances.length
      if (key === 'ready') return instances.filter((it) => it.availability === 'ready').length
      if (key === 'stopped') return instances.filter((it) => it.availability === 'stopped').length
      // 「不可用」把两种都收进来：镜像没有 noVNC 的，和还没配好内核/镜像的
      return instances.filter(
        (it) => it.availability === 'unsupported' || it.availability === 'blocked',
      ).length
    }
    return [
      { key: 'all', label: '全部' },
      { key: 'ready', label: '可接管' },
      { key: 'stopped', label: '待启动' },
      { key: 'unavailable', label: '不可用' },
    ].map((item) => ({ ...item, count: count(item.key) }))
  }, [instances])

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return instances.filter((it) => {
      if (tab === 'ready' && it.availability !== 'ready') return false
      if (tab === 'stopped' && it.availability !== 'stopped') return false
      if (tab === 'unavailable' && it.availability !== 'unsupported' && it.availability !== 'blocked')
        return false
      if (!keyword) return true
      return [it.name, it.id, it.kernel ?? '', it.account, it.ip, it.group, it.kernel_version ?? '']
        .join(' ')
        .toLowerCase()
        .includes(keyword)
    })
  }, [instances, tab, query])

  const copyId = async (item: NoVncTarget) => {
    const ok = await copyText(item.id)
    notify(ok ? 'ok' : 'err', ok ? '实例 ID 已复制' : '复制失败')
  }

  const totals = data?.totals

  return (
    <PageShell>
      <PageHeader
        icon={<IconMonitor size={19} />}
        title="noVNC 详情"
        subtitle="所有实例的实时画面入口；镜像不带 noVNC 或实例没启动时无法接管"
        actions={
          <>
            <button type="button" className="btn-ghost" onClick={() => navigate('/browsers')}>
              <IconArrowLeft size={14} />
              返回浏览器池
            </button>
            <button type="button" className="btn-ghost" onClick={reload}>
              <IconRefresh size={14} />
              刷新
            </button>
          </>
        }
      />

      {status === 'error' && <ErrorState message={error} onRetry={reload} />}
      {status === 'loading' && !data && <Loading />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile
              label="实例总数"
              value={String(totals?.total ?? 0)}
              hint="已登记的实例"
              tone="dark"
              icon={<IconBrowser size={15} />}
            />
            <StatTile
              label="可接管"
              value={String(totals?.ready ?? 0)}
              hint="点开即看画面"
              tone="emerald"
              icon={<IconEye size={15} />}
            />
            <StatTile
              label="待启动"
              value={String(totals?.offline ?? 0)}
              hint="启动后可接管"
              tone="blue"
              icon={<IconPlay size={15} />}
            />
            <StatTile
              label="不可用"
              value={String((totals?.unsupported ?? 0) + (totals?.blocked ?? 0))}
              hint={
                totals?.unsupported
                  ? `${totals.unsupported} 台镜像没装 noVNC`
                  : totals?.blocked
                    ? `${totals.blocked} 台缺内核或镜像`
                    : '都能接管'
              }
              tone={totals?.unsupported || totals?.blocked ? 'rose' : 'zinc'}
              icon={<IconX size={15} />}
            />
          </div>

          <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 p-3.5">
            <div className="flex flex-wrap items-center gap-3">
              <SearchInput
                placeholder="按实例名、ID、内核或 IP 搜索"
                width="w-[280px]"
                value={query}
                onChange={setQuery}
              />
              <PillTabs
                items={tabs.map((item) => ({
                  ...item,
                  tone:
                    item.key === 'ready'
                      ? 'emerald'
                      : item.key === 'stopped'
                        ? 'blue'
                        : item.key === 'unavailable'
                          ? 'rose'
                          : 'zinc',
                }))}
                active={tab}
                onSelect={setTab}
              />
            </div>
            <span className="text-[11px] text-[var(--ink-400)]">
              画面地址取自实例启动时分配的端口，容器没跑时打不开是正常的
            </span>
          </Card>

          {visible.length === 0 ? (
            <Card className="mt-4 flex flex-col items-center gap-2 px-6 py-16 text-center">
              <span className="flex size-11 items-center justify-center rounded-2xl bg-[#f4f4f5] text-[var(--ink-400)]">
                <IconMonitor size={18} />
              </span>
              <p className="text-[13px] font-medium text-[var(--ink-700)]">没有符合条件的实例</p>
              <p className="text-[11.5px] text-[var(--ink-400)]">
                换个关键词，或到浏览器池里新建一台
              </p>
            </Card>
          ) : (
            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {visible.map((item) => (
                <NoVncCard
                  key={item.id}
                  item={item}
                  onCopyId={() => copyId(item)}
                  onOpen={() => navigate(`/novnc/${item.id}`)}
                  onStart={() => navigate('/browsers')}
                />
              ))}
            </div>
          )}
        </>
      )}

      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
  )
}

function NoVncCard({
  item,
  onCopyId,
  onOpen,
  onStart,
}: {
  item: NoVncTarget
  onCopyId: () => void
  onOpen: () => void
  onStart: () => void
}) {
  const status = meta[item.status]
  return (
    <Card className="flex flex-col p-4 transition-[box-shadow,border-color] duration-150 hover:border-[#e3e3e9] hover:shadow-[0_6px_20px_-12px_rgba(16,24,40,0.22)]">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[13px] font-medium text-[var(--ink-900)]">{item.name}</span>
            <IdBadge id={item.id} onCopy={onCopyId} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <SoftChip tone={status.tone}>{status.label}</SoftChip>
            <SoftChip tone={availability[item.availability].tone}>
              {availability[item.availability].label}
            </SoftChip>
            {item.port && <span className="tnum text-[10.5px] text-[var(--ink-400)]">:{item.port}</span>}
          </div>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-[var(--line)] pt-3 text-[11px]">
        <Meta label="内核">
          {item.kernel ? `${item.kernel}${item.kernel_version ? ` · ${item.kernel_version}` : ''}` : '未绑定'}
        </Meta>
        <Meta label="出口 IP">{item.ip}</Meta>
        <Meta label="账号">{item.account}</Meta>
        <Meta label="分组">{item.group}</Meta>
      </dl>

      <div className="mt-3 flex items-center gap-2 border-t border-[var(--line)] pt-3">
        {item.ready ? (
          <>
            <button type="button" className="btn-dark !h-8 flex-1 !text-[11.5px]" onClick={onOpen}>
              <IconEye size={12} />
              打开画面
            </button>
            {item.url && (
              <a
                className="icon-btn size-8"
                href={item.url}
                target="_blank"
                rel="noreferrer"
                title="在新窗口打开 noVNC"
              >
                <IconArrowUpRight size={13} />
              </a>
            )}
          </>
        ) : (
          <div className="flex w-full items-center justify-between gap-2">
            <span className="line-clamp-2 text-[11px] text-[var(--ink-400)]">{item.reason}</span>
            {item.availability !== 'unsupported' && (
              <button
                type="button"
                className="btn-ghost !h-7 shrink-0 !px-2.5 !text-[11px]"
                onClick={onStart}
              >
                <IconPower size={11} />
                {item.availability === 'stopped' ? '去启动' : '去配置'}
              </button>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] text-[var(--ink-400)]">{label}</dt>
      <dd className="mt-0.5 truncate text-[11.5px] text-[var(--ink-700)]" title={String(children)}>
        {children}
      </dd>
    </div>
  )
}
