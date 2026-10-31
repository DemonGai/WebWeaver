import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, Checkbox, PillTabs, SearchInput, SelectBox } from '@/components/ui'
import {
  IconAndroid,
  IconApple,
  IconBolt,
  IconCheck,
  IconChevronLeft,
  IconCpu,
  IconDownload,
  IconGrid,
  IconList,
  IconMonitor,
  IconMore,
  IconPlus,
  IconWindows,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { FingerprintTemplate, PlatformFamily } from '@/types/domain'

const familyStyle: Record<PlatformFamily, { tile: string; glyph: ReactNode }> = {
  windows: { tile: 'bg-blue-50 text-blue-500', glyph: <IconWindows size={13} /> },
  macos: { tile: 'bg-zinc-100 text-zinc-700', glyph: <IconApple size={13} /> },
  linux: { tile: 'bg-orange-50 text-orange-600', glyph: <IconCpu size={13} /> },
  android: { tile: 'bg-emerald-50 text-emerald-600', glyph: <IconAndroid size={13} /> },
  ios: { tile: 'bg-sky-50 text-sky-600', glyph: <IconApple size={13} /> },
}

/** 后端将来新增平台族时也不能整页崩：取不到样式就退回中性图标。 */
const fallbackFamily = { tile: 'bg-zinc-100 text-zinc-600', glyph: <IconMonitor size={13} /> }

const styleOf = (family: PlatformFamily) => familyStyle[family] ?? fallbackFamily

/** 筛选里的「移动」是分组，落到具体平台族是 android + ios。 */
const MOBILE_FAMILIES: PlatformFamily[] = ['android', 'ios']

const matchesTab = (family: PlatformFamily, tab: string) =>
  tab === 'all' || family === tab || (tab === 'mobile' && MOBILE_FAMILIES.includes(family))

export default function FingerprintsPage() {
  const { data, status, error, reload } = useApi(endpoints.fingerprints, [])
  const [tab, setTab] = useState('all')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string[]>([])

  const rows = useMemo(() => {
    if (!data) return []
    const keyword = query.trim().toLowerCase()
    return data.templates
      .filter((t) => matchesTab(t.platform_family, tab))
      .filter((t) =>
        keyword === ''
          ? true
          : [t.name, t.ua, t.timezone, t.fp_id, t.platform]
              .join(' ')
              .toLowerCase()
              .includes(keyword),
      )
  }, [data, tab, query])

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

  const allChecked = rows.length > 0 && rows.every((r) => selected.includes(r.id))

  return (
    <PageShell>
      <PageHeader
        title="指纹库"
        subtitle="列表视图 · 逐行比对 UA、时区、分辨率与伪装项覆盖情况"
        actions={
          <>
            <button type="button" className="btn-ghost">
              <IconDownload size={14} />
              从真实设备采集
            </button>
            <button type="button" className="btn-dark">
              <IconPlus size={14} />
              新建模板
            </button>
          </>
        }
      />

      <Card className="flex flex-wrap items-center justify-between gap-3 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            placeholder="搜索模板名 / UA / 时区"
            width="w-[236px]"
            value={query}
            onChange={setQuery}
          />
          <PillTabs
            items={data.filters.map((f) => ({ key: f.key, label: f.label, count: f.count }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectBox label={`内核 ${data.kernels}`} />
          <SelectBox label="唯一性优先" />
          <div className="flex items-center gap-0.5 rounded-full border border-[var(--line)] p-0.5">
            <button
              type="button"
              aria-label="卡片视图"
              className="flex size-6 items-center justify-center rounded-full text-[var(--ink-400)] transition-colors hover:bg-[#f4f4f5]"
            >
              <IconGrid size={13} />
            </button>
            <button
              type="button"
              aria-label="列表视图"
              className="flex size-6 items-center justify-center rounded-full bg-[#18181b] text-white"
            >
              <IconList size={13} />
            </button>
          </div>
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="table-th w-[19%]">模板名称</th>
                <th className="table-th w-[14%]">UA / 平台</th>
                <th className="table-th w-[15%]">时区 / 语言</th>
                <th className="table-th w-[10%]">分辨率</th>
                <th className="table-th w-[14%]">伪装项</th>
                <th className="table-th w-[6%]">唯一性</th>
                <th className="table-th w-[6%]">使用实例</th>
                <th className="table-th w-[16%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <Row key={t.id} template={t} checked={selected.includes(t.id)} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center text-[12.5px] text-[var(--ink-400)]">
                    没有匹配的指纹模板
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-3">
          <div className="flex items-center gap-2 text-[11.5px] text-[var(--ink-500)]">
            <Checkbox
              checked={allChecked}
              onChange={(next) => setSelected(next ? rows.map((r) => r.id) : [])}
              label="全选当前页模板"
            />
            显示 {rows.length} / {data.total} 条模板，已选择 {selected.length} 条
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              className="icon-btn size-7 text-[var(--ink-400)]"
              aria-label="上一页"
              disabled
            >
              <IconChevronLeft size={13} />
            </button>
            {[1, 2, 3].map((p) => (
              <button
                key={p}
                type="button"
                className={`size-7 rounded-full text-[11.5px] font-medium transition-colors ${
                  p === data.page
                    ? 'bg-[#18181b] text-white'
                    : 'text-[var(--ink-500)] hover:bg-[#f4f4f5]'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </PageShell>
  )
}

function Row({ template: t, checked }: { template: FingerprintTemplate; checked: boolean }) {
  const family = styleOf(t.platform_family)
  const pairs = chunk(t.disguises)

  return (
    <tr className="border-b border-[#f4f4f6] last:border-0 hover:bg-[#fcfcfd]">
      <td className="table-td">
        <div className="flex items-center gap-2.5">
          <span
            className={`flex size-7 shrink-0 items-center justify-center rounded-md ${family.tile}`}
          >
            {family.glyph}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate text-[12.5px] font-medium text-[var(--ink-900)]">
                {t.name}
              </span>
              {checked && (
                <span className="text-emerald-500">
                  <IconCheck size={11} />
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{t.fp_id}</div>
          </div>
        </div>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{t.platform}</div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{t.ua}</div>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{t.timezone}</div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{t.language}</div>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{t.resolution}</div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{t.dpr}</div>
      </td>

      <td className="table-td">
        <div className="space-y-1">
          {t.warning && (
            <span className="chip bg-amber-50 text-amber-600">{t.warning}</span>
          )}
          {pairs.slice(0, t.warning ? 1 : 2).map((pair, i) => (
            <div key={i} className="text-[10.5px] text-[var(--ink-500)]">
              {pair.join(' · ')}
            </div>
          ))}
        </div>
      </td>

      <td className="table-td">
        {t.uniqueness === null ? (
          <span className="chip bg-rose-50 text-rose-500">—</span>
        ) : (
          <span
            className={`chip ${
              t.uniqueness >= 90 ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
            }`}
          >
            {t.uniqueness}
          </span>
        )}
      </td>

      <td className="table-td tnum whitespace-nowrap">{t.instances} 台</td>

      <td className="table-td">
        <div className="flex items-center justify-end gap-1.5 whitespace-nowrap">
          <button type="button" className="btn-dark !h-7 shrink-0 !px-2.5 !text-[11px]">
            {t.action ? t.action : <><IconBolt size={11} />应用实例</>}
          </button>
          <button type="button" className="btn-ghost !h-7 shrink-0 !px-2 !text-[11px]">
            详情
          </button>
          <button type="button" className="icon-btn size-7 shrink-0">
            <IconMore size={12} />
          </button>
        </div>
      </td>
    </tr>
  )
}

function chunk(items: string[], size = 2): string[][] {
  const out: string[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}
