import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, PillTabs, SearchInput, StatusDot } from '@/components/ui'
import { StatTile } from '@/components/StatTile'
import { SelectMenu } from '@/components/SelectMenu'
import { Toast, useToast } from '@/components/Toast'
import {
  IconAlert,
  IconBolt,
  IconCheckCircle,
  IconClipboard,
  IconGlobe,
  IconLink,
  IconRefresh,
  IconWifi,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { IpResource, IpStatus } from '@/types/domain'

const STATUS_META: Record<IpStatus, { label: string; tone: 'emerald' | 'blue' | 'rose' }> = {
  available: { label: '可用', tone: 'emerald' },
  in_use: { label: '占用', tone: 'blue' },
  failed: { label: '失败', tone: 'rose' },
}

/** 筛选标签的 key 是英文枚举，表格里是中文类型，这里做一次对照。 */
const KIND_OF_TAB: Record<string, IpResource['type']> = {
  residential: '住宅',
  datacenter: '机房',
  mobile: '移动',
}

/** 类型对应的图标块与胶囊配色，和指纹页按平台族上色是一个路子。 */
const KIND_STYLE: Record<IpResource['type'], { tile: string; chip: string; glyph: ReactNode }> = {
  住宅: {
    tile: 'bg-emerald-50 text-emerald-600',
    chip: 'bg-emerald-50 text-emerald-600',
    glyph: <IconGlobe size={13} />,
  },
  机房: {
    tile: 'bg-blue-50 text-blue-600',
    chip: 'bg-blue-50 text-blue-600',
    glyph: <IconBolt size={13} />,
  },
  移动: {
    tile: 'bg-violet-50 text-violet-600',
    chip: 'bg-violet-50 text-violet-600',
    glyph: <IconWifi size={13} />,
  },
}

const fallbackKind = { tile: 'bg-zinc-100 text-zinc-600', chip: 'bg-zinc-100 text-zinc-600' }
const kindStyle = (kind: IpResource['type']) => KIND_STYLE[kind] ?? fallbackKind

/**
 * 复制到剪贴板。
 *
 * 异步剪贴板 API 在非安全上下文（内网 http 部署）或权限被拒时会直接抛错，
 * 而「复制代理地址」是这页最常用的动作，不能因此变成死按钮 —— 失败就退回
 * 「建个隐藏 textarea 选中再 execCommand」这套老办法。
 */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(ta)
    return ok
  }
}

export default function IpPoolPage() {
  const { data, status, error, reload } = useApi(endpoints.ipPool, [])

  const [tab, setTab] = useState('all')
  const [query, setQuery] = useState('')
  const [region, setRegion] = useState('')
  const { toast, notify, dismiss } = useToast()

  /** 地区下拉的候选按库里实际出现的国家码生成，不写死一份清单 */
  const regionItems = useMemo(() => {
    const counts = new Map<string, number>()
    for (const item of data?.resources ?? []) {
      counts.set(item.region, (counts.get(item.region) ?? 0) + 1)
    }
    return [
      { value: '', label: '全部地区' },
      ...[...counts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([code, count]) => ({ value: code, label: code, count })),
    ]
  }, [data])

  const rows = useMemo(() => {
    if (!data) return []
    const keyword = query.trim().toLowerCase()
    const kind = KIND_OF_TAB[tab]
    return data.resources
      .filter((r) => (kind ? r.type === kind : true))
      .filter((r) => (region === '' ? true : r.region === region))
      .filter((r) =>
        keyword === ''
          ? true
          : [r.ip, r.supplier, r.region, r.city, r.type, r.protocol]
              .join(' ')
              .toLowerCase()
              .includes(keyword),
      )
  }, [data, tab, region, query])

  const copyProxy = async (r: IpResource) => {
    const text = `${r.protocol}://${r.ip}:${r.port}`
    const ok = await copyText(text)
    notify(ok ? 'ok' : 'err', ok ? `已复制 ${text}` : '复制失败，请手动选中复制')
  }

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

  const inUse = data.resources.filter((r) => r.status === 'in_use').length
  const failed = data.resources.filter((r) => r.status === 'failed').length
  const boundInRows = rows.filter((r) => r.bound_instance != null).length

  return (
    <PageShell>
      <PageHeader
        icon={<IconGlobe size={19} />}
        title="代理管理"
        subtitle="一个代理 = 一个出口，住宅 / 机房 / 移动统一调度"
        actions={
          <button type="button" className="btn-ghost" onClick={reload}>
            <IconRefresh size={14} />
            刷新
          </button>
        }
      />

      {/* 统计条：与指纹管理、内核管理同一套 StatTile */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="代理总数"
          value={String(data.totals.total)}
          hint={`在线率 ${data.totals.online_rate}%`}
          tone="dark"
          icon={<IconGlobe size={15} />}
        />
        <StatTile
          label="可用"
          value={String(data.totals.available)}
          hint="可直接绑定实例"
          tone="emerald"
          icon={<IconCheckCircle size={15} />}
        />
        <StatTile
          label="占用"
          value={String(inUse)}
          hint="不可再分配"
          tone="blue"
          icon={<IconLink size={15} />}
        />
        <StatTile
          label="失败"
          value={String(failed)}
          hint="连接失败，待替换"
          tone={failed > 0 ? 'amber' : 'zinc'}
          icon={<IconAlert size={15} />}
        />
      </div>

      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            placeholder="搜索代理 / 供应商 / 地区"
            width="w-[240px]"
            value={query}
            onChange={setQuery}
          />
          <PillTabs
            items={data.filters.map((f) => ({
              key: f.key,
              label: f.label,
              count: f.count,
              tone:
                f.key === 'residential' ? 'emerald' : f.key === 'datacenter' ? 'blue' : 'violet',
            }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectMenu
            value={region}
            items={regionItems}
            onChange={setRegion}
            icon={<IconGlobe size={13} />}
            width="min-w-[180px]"
            panelHeader="按国家/地区筛选"
          />
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="table-th w-[24%]">代理 / 供应商</th>
                <th className="table-th w-[12%]">地区</th>
                <th className="table-th w-[9%]">协议</th>
                <th className="table-th w-[9%]">类型</th>
                <th className="table-th w-[8%]">延迟</th>
                <th className="table-th w-[12%]">状态</th>
                <th className="table-th w-[16%]">绑定实例</th>
                <th className="table-th w-[10%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row key={row.id} resource={row} onCopy={() => copyProxy(row)} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="px-4 py-16 text-center text-[12.5px] text-[var(--ink-400)]"
                  >
                    没有匹配的代理
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-3">
          <div className="text-[11.5px] text-[var(--ink-500)]">
            显示 {rows.length} / {data.totals.total} 条
            {boundInRows > 0 && `，其中 ${boundInRows} 条已绑定实例`}
          </div>
          <div className="text-[11px] text-[var(--ink-400)]">
            代理跟着实例走：绑上去才真正生效
          </div>
        </div>
      </Card>

      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
  )
}

function Row({ resource: r, onCopy }: { resource: IpResource; onCopy: () => void }) {
  const meta = STATUS_META[r.status]
  const kind = kindStyle(r.type)

  return (
    <tr className="border-b border-[#f4f4f6] last:border-0 hover:bg-[#fcfcfd]">
      <td className="table-td">
        <div className="flex items-center gap-2.5">
          <span className={`flex size-7 shrink-0 items-center justify-center rounded-md ${kind.tile}`}>
            {kind.glyph}
          </span>
          <div className="min-w-0">
            <div className="truncate font-mono text-[12.5px] font-medium text-[var(--ink-900)]">
              {r.ip}
              <span className="text-[var(--ink-400)]">:{r.port || '默认'}</span>
            </div>
            <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">{r.supplier}</div>
          </div>
        </div>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{r.region}</div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{r.city}</div>
      </td>

      <td className="table-td">
        <span className="font-mono text-[11.5px] text-[var(--ink-700)]">{r.protocol}</span>
      </td>

      <td className="table-td">
        <span className={`chip ${kind.chip}`}>{r.type}</span>
      </td>

      <td className="table-td tnum whitespace-nowrap">
        {r.latency_ms > 0 ? `${r.latency_ms} ms` : '—'}
      </td>

      <td className="table-td">
        <StatusDot tone={meta.tone} label={meta.label} />
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">
          {/* 失败的行还挂着 100% 健康度会自相矛盾，直接说探测失败 */}
          {r.status === 'failed' ? '最近探测失败' : `健康 ${r.health}%`}
        </div>
      </td>

      <td className="table-td">
        {r.bound_instance ? (
          <span className="text-[12px] text-[var(--ink-700)]">{r.bound_instance}</span>
        ) : (
          <span className="text-[12px] text-[var(--ink-400)]">未绑定</span>
        )}
      </td>

      <td className="table-td">
        <div className="flex items-center justify-end gap-1.5 whitespace-nowrap">
          <button
            type="button"
            onClick={onCopy}
            className="btn-ghost !h-7 shrink-0 !px-2 !text-[11px]"
            title={`复制 ${r.protocol}://${r.ip}:${r.port}`}
          >
            <IconClipboard size={11} />
            复制
          </button>
        </div>
      </td>
    </tr>
  )
}
