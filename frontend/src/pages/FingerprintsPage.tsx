import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, PillTabs, SearchInput } from '@/components/ui'
import { SelectMenu } from '@/components/SelectMenu'
import { Modal } from '@/components/Modal'
import { FingerprintDialog } from '@/components/FingerprintDialog'
import { FingerprintDrawer } from '@/components/FingerprintDrawer'
import {
  IconAlert,
  IconAndroid,
  IconApple,
  IconCheckCircle,
  IconCpu,
  IconFingerprint,
  IconMonitor,
  IconPlus,
  IconRefresh,
  IconSparkle,
  IconTrash,
  IconWindows,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type {
  FingerprintDetail,
  FingerprintTemplate,
  PlatformFamily,
  ProbeState,
} from '@/types/domain'

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

const PROBE_CHIP: Record<ProbeState, { label: string; className: string }> = {
  never: { label: '未采集', className: 'bg-zinc-100 text-zinc-500' },
  fresh: { label: '已采集', className: 'bg-emerald-50 text-emerald-600' },
  stale: { label: '待重采', className: 'bg-amber-50 text-amber-600' },
  failed: { label: '采集失败', className: 'bg-rose-50 text-rose-600' },
}

/** 筛选里的「移动」是分组，落到具体平台族是 android + ios。 */
const MOBILE_FAMILIES: PlatformFamily[] = ['android', 'ios']
const matchesTab = (family: PlatformFamily, tab: string) =>
  tab === 'all' || family === tab || (tab === 'mobile' && MOBILE_FAMILIES.includes(family))

type Toast = { tone: 'ok' | 'err'; text: string } | null

export default function FingerprintsPage() {
  const { data, status, error, reload, refresh } = useApi(endpoints.fingerprints, [])
  const caps = useApi(endpoints.fingerprintCapabilities, [])
  const options = useApi(endpoints.fingerprintOptions, [])

  const [tab, setTab] = useState('all')
  const [query, setQuery] = useState('')
  const [kernel, setKernel] = useState('')
  const [toast, setToast] = useState<Toast>(null)
  const [probing, setProbing] = useState('')
  const [detail, setDetail] = useState<FingerprintDetail | null>(null)
  const [dialog, setDialog] = useState<{ open: boolean; initial: FingerprintDetail | null }>({
    open: false,
    initial: null,
  })
  const [pendingDelete, setPendingDelete] = useState<FingerprintTemplate | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = useCallback((tone: 'ok' | 'err', text: string) => setToast({ tone, text }), [])

  const kernelItems = useMemo(() => {
    const seen = new Map<string, string>()
    for (const item of data?.templates ?? []) {
      if (item.kernel_slug && item.kernel) seen.set(item.kernel_slug, item.kernel)
    }
    return [
      { value: '', label: '全部内核' },
      ...[...seen.entries()].map(([slug, label]) => ({ value: slug, label })),
    ]
  }, [data])

  const rows = useMemo(() => {
    if (!data) return []
    const keyword = query.trim().toLowerCase()
    return data.templates
      .filter((t) => matchesTab(t.platform_family, tab))
      .filter((t) => kernel === '' || t.kernel_slug === kernel)
      .filter((t) =>
        keyword === ''
          ? true
          : [t.name, t.ua, t.timezone, t.fp_id, t.platform, t.gpu ?? '']
              .join(' ')
              .toLowerCase()
              .includes(keyword),
      )
  }, [data, tab, query, kernel])

  const openDetail = useCallback(
    async (id: string) => {
      try {
        setDetail(await endpoints.fingerprintDetail(id))
      } catch (err) {
        notify('err', err instanceof Error ? err.message : '读取详情失败')
      }
    },
    [notify],
  )

  const probe = useCallback(
    async (id: string) => {
      setProbing(id)
      try {
        const next = await endpoints.probeFingerprint(id)
        notify('ok', `采集完成：${next.gpu ?? '已读到人格'}`)
        // 抽屉开着就同步刷新，否则只刷新列表
        setDetail((prev) => (prev && prev.id === id ? next : prev))
        refresh()
      } catch (err) {
        notify('err', err instanceof Error ? err.message : '采集失败')
        refresh()
      } finally {
        setProbing('')
      }
    },
    [notify, refresh],
  )

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return
    try {
      await endpoints.deleteFingerprint(pendingDelete.id)
      notify('ok', `已删除 ${pendingDelete.name}`)
      setPendingDelete(null)
      setDetail(null)
      refresh()
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '删除失败')
      setPendingDelete(null)
    }
  }, [pendingDelete, notify, refresh])

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

  return (
    <PageShell>
      <PageHeader
        icon={<IconFingerprint size={19} />}
        title="指纹管理"
        subtitle="一条指纹 = 一整套人格，UA / 分辨率 / 显卡都由它派生"
        actions={
          <button
            type="button"
            className="btn-dark"
            onClick={() => setDialog({ open: true, initial: null })}
          >
            <IconPlus size={14} />
            新建指纹
          </button>
        }
      />

      {toast && (
        <div
          className={`mb-3 flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-[12px] ${
            toast.tone === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
          }`}
        >
          {toast.tone === 'ok' ? <IconCheckCircle size={13} /> : <IconAlert size={13} />}
          <span className="flex-1">{toast.text}</span>
          <button type="button" onClick={() => setToast(null)} aria-label="关闭提示">
            <IconX size={12} />
          </button>
        </div>
      )}

      {/* 统计条 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="指纹总数" value={String(data.total)} hint="含暂不可下发的" />
        <Stat
          label="支持指纹的内核"
          value={`${data.supported_kernels}/${data.kernels}`}
          hint="带指纹补丁的内核数量"
        />
        <Stat label="已采集" value={String(data.probed)} hint="读回过真实人格" tone="emerald" />
        <Stat
          label="待重采"
          value={String(data.stale)}
          hint="参数改过，实测值过期"
          tone={data.stale > 0 ? 'amber' : 'zinc'}
        />
      </div>

      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            placeholder="搜索名称 / 种子 / GPU / 时区"
            width="w-[240px]"
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
          <SelectMenu
            value={kernel}
            items={kernelItems}
            onChange={setKernel}
            width="min-w-[170px]"
            panelHeader="按内核筛选"
          />
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1140px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="table-th w-[20%]">模板 / 编号</th>
                <th className="table-th w-[10%]">种子</th>
                <th className="table-th w-[13%]">适配内核</th>
                <th className="table-th w-[20%]">实测人格</th>
                <th className="table-th w-[13%]">时区 / 语言</th>
                <th className="table-th w-[7%]">实例</th>
                <th className="table-th w-[17%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row
                  key={row.id}
                  template={row}
                  probing={probing === row.id}
                  onProbe={() => probe(row.id)}
                  onOpen={() => openDetail(row.id)}
                  onDelete={() => setPendingDelete(row)}
                />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-16 text-center text-[12.5px] text-[var(--ink-400)]"
                  >
                    没有匹配的指纹
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-3">
          <div className="text-[11.5px] text-[var(--ink-500)]">
            显示 {rows.length} / {data.total} 条
            {data.probed > 0 && `，其中 ${data.probed} 条采集过实测人格`}
          </div>
          <div className="text-[11px] text-[var(--ink-400)]">
            种子相同 = 同一个人；换种子就是换人
          </div>
        </div>
      </Card>

      {detail && (
        <FingerprintDrawer
          detail={detail}
          instances={options.data ?? []}
          busy={probing === detail.id}
          onClose={() => setDetail(null)}
          onProbe={() => probe(detail.id)}
          onEdit={() => setDialog({ open: true, initial: detail })}
          onChanged={() => {
            refresh()
            openDetail(detail.id)
          }}
          notify={notify}
        />
      )}

      {dialog.open && (
        <FingerprintDialog
          open
          onClose={() => setDialog({ open: false, initial: null })}
          caps={caps.data ?? []}
          initial={dialog.initial}
          onSaved={(next, mode) => {
            setDialog({ open: false, initial: null })
            notify('ok', mode === 'create' ? `已创建 ${next.name}` : `已保存 ${next.name}`)
            // 新建后种子还没生效过，直接把详情打开，省一次点击
            setDetail(next)
            refresh()
          }}
        />
      )}

      <Modal
        open={pendingDelete != null}
        onClose={() => setPendingDelete(null)}
        title="删除指纹"
        subtitle="只删这条记录，不影响已经写进容器的指纹文件"
        icon={<IconTrash size={15} />}
        width="max-w-[440px]"
        footer={
          <div className="flex w-full justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={() => setPendingDelete(null)}>
              取消
            </button>
            <button type="button" className="btn-dark" onClick={confirmDelete}>
              确认删除
            </button>
          </div>
        }
      >
        <p className="text-[12.5px] text-[var(--ink-600)]">
          确定删除 <span className="font-medium text-[var(--ink-900)]">{pendingDelete?.name}</span>
          （<span className="font-mono">{pendingDelete?.fp_id}</span>）？
          如果还有实例在用这条指纹，后端会拒绝删除并提示是哪些实例。
        </p>
      </Modal>
    </PageShell>
  )
}

function Stat({
  label,
  value,
  hint,
  tone = 'zinc',
}: {
  label: string
  value: string
  hint: string
  tone?: 'zinc' | 'emerald' | 'amber'
}) {
  const valueStyle =
    tone === 'emerald'
      ? 'text-emerald-600'
      : tone === 'amber'
        ? 'text-amber-600'
        : 'text-[var(--ink-900)]'
  return (
    <Card className="px-4 py-3">
      <p className="text-[11px] text-[var(--ink-400)]">{label}</p>
      <p className={`mt-1 text-[19px] font-semibold tnum ${valueStyle}`}>{value}</p>
      <p className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{hint}</p>
    </Card>
  )
}

function Row({
  template: t,
  probing,
  onProbe,
  onOpen,
  onDelete,
}: {
  template: FingerprintTemplate
  probing: boolean
  onProbe: () => void
  onOpen: () => void
  onDelete: () => void
}) {
  const family = styleOf(t.platform_family)
  const chip = PROBE_CHIP[t.probe_state]

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
              <button
                type="button"
                onClick={onOpen}
                className="truncate text-left text-[12.5px] font-medium text-[var(--ink-900)] hover:underline"
              >
                {t.name}
              </button>
            </div>
            <div className="mt-0.5 font-mono text-[10.5px] text-[var(--ink-400)]">{t.fp_id}</div>
          </div>
        </div>
      </td>

      <td className="table-td">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[12.5px] text-[var(--ink-900)]">
            {t.seed ?? '—'}
          </span>
          {t.seed == null && <IconSparkle size={11} className="text-[var(--ink-300)]" />}
        </div>
        <span className={`chip mt-1 ${chip.className}`}>{chip.label}</span>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{t.kernel ?? '未绑定'}</div>
        {t.supported ? (
          <div className="mt-0.5 text-[10.5px] text-emerald-600">可下发</div>
        ) : (
          <div
            className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-rose-500"
            title={t.unsupported_reason ?? ''}
          >
            {t.unsupported_reason}
          </div>
        )}
      </td>

      <td className="table-td">
        {t.probe_state === 'never' ? (
          <div className="text-[11px] text-[var(--ink-400)]">
            未采集
            <button
              type="button"
              onClick={onProbe}
              disabled={probing || !t.supported}
              className="ml-1 text-[11px] font-medium text-[var(--ink-700)] underline-offset-2 hover:underline disabled:no-underline disabled:opacity-40"
            >
              {probing ? '采集中…' : '立即采集'}
            </button>
          </div>
        ) : (
          <>
            <div className="truncate text-[12px] text-[var(--ink-900)]" title={t.gpu ?? ''}>
              {t.gpu ?? '—'}
            </div>
            <div className="mt-0.5 font-mono text-[10.5px] text-[var(--ink-400)]">
              {t.resolution || '—'} · {t.dpr || '—'}
              {t.canvas_hash ? ` · canvas ${t.canvas_hash}` : ''}
            </div>
          </>
        )}
        {t.warning && (
          <div className="mt-1 line-clamp-2 text-[10.5px] leading-snug text-amber-600" title={t.warning}>
            {t.warning}
          </div>
        )}
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{t.timezone}</div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">{t.language}</div>
      </td>

      <td className="table-td tnum whitespace-nowrap">{t.instances} 台</td>

      <td className="table-td">
        <div className="flex items-center justify-end gap-1.5 whitespace-nowrap">
          <button
            type="button"
            onClick={onProbe}
            disabled={probing || !t.supported}
            className="btn-ghost !h-7 shrink-0 !px-2 !text-[11px]"
            title={t.supported ? '按当前种子起容器采集真实人格' : '该内核不支持指纹'}
          >
            <IconRefresh size={11} />
            {probing ? '采集中' : '采集'}
          </button>
          <button type="button" onClick={onOpen} className="btn-dark !h-7 shrink-0 !px-2.5 !text-[11px]">
            <IconFingerprint size={11} />
            详情
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="icon-btn size-7 shrink-0 text-[var(--ink-400)] hover:text-rose-600"
            aria-label="删除"
          >
            <IconTrash size={12} />
          </button>
        </div>
      </td>
    </tr>
  )
}
