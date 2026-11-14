import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { ApiError } from '@/api/client'
import { useApi } from '@/hooks/useApi'
import { copyText } from '@/lib/clipboard'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, Checkbox, PillTabs, SearchInput, type Tone } from '@/components/ui'
import { StatTile } from '@/components/StatTile'
import { SelectMenu } from '@/components/SelectMenu'
import { BrowserDialog } from '@/components/BrowserDialog'
import { IdBadge } from '@/components/IdBadge'
import { Modal } from '@/components/Modal'
import {
  IconBolt,
  IconBrowser,
  IconClock,
  IconCopy,
  IconFingerprint,
  IconGlobe,
  IconGrid,
  IconLayers,
  IconList,
  IconMonitor,
  IconMore,
  IconPlay,
  IconPlus,
  IconPower,
  IconRefresh,
  IconTrash,
  IconUser,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import { Toast, useToast } from '@/components/Toast'
import type {
  BrowserActionName,
  BrowserDetail,
  InstanceStatus,
  InstanceSummary,
} from '@/types/domain'

const meta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空闲', tone: 'blue' },
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
  const { data, status, error, reload, refresh } = useApi(endpoints.browsers, [])

  const [query, setQuery] = useState('')
  const [tab, setTab] = useState('all')
  const [group, setGroup] = useState('')
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState<string[]>([])
  const [dialog, setDialog] = useState<{ open: boolean; id: string | null }>({
    open: false,
    id: null,
  })
  const [confirming, setConfirming] = useState<InstanceSummary | null>(null)
  // 列表视图里同一时刻只允许开一个「更多」菜单，用 id 记账即可
  const [menuId, setMenuId] = useState<string | null>(null)
  const { toast, notify, dismiss } = useToast()

  const instances = data?.instances ?? []

  // 筛选项在本地算：后端只给四个状态，这里还要有「已停止」和搜索后的计数
  const tabs = useMemo(() => {
    const count = (key: string) =>
      key === 'all'
        ? instances.length
        : instances.filter((it) => it.status === (key as InstanceStatus)).length
    return [
      { key: 'all', label: '全部' },
      { key: 'running', label: '运行中' },
      { key: 'idle', label: '空闲' },
      { key: 'queued', label: '排队中' },
      { key: 'error', label: '异常' },
      { key: 'stopped', label: '已停止' },
    ].map((item) => ({ ...item, count: count(item.key) }))
  }, [instances])

  const groups = useMemo(() => {
    const map = new Map<string, number>()
    for (const it of instances) map.set(it.group, (map.get(it.group) ?? 0) + 1)
    return Array.from(map, ([value, count]) => ({ value, label: value, count })).sort((a, b) =>
      a.label.localeCompare(b.label, 'zh'),
    )
  }, [instances])

  const groupItems = useMemo(
    () => [{ value: '', label: '全部分组', count: instances.length }, ...groups],
    [groups, instances.length],
  )

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return instances.filter((it) => {
      if (tab !== 'all' && it.status !== tab) return false
      if (group && it.group !== group) return false
      if (!keyword) return true
      return [it.name, it.account, it.ip, it.region, it.fingerprint, it.group]
        .join(' ')
        .toLowerCase()
        .includes(keyword)
    })
  }, [instances, tab, group, query])

  const toggleSelect = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const allChecked = visible.length > 0 && visible.every((it) => selected.includes(it.id))
  const someChecked = visible.some((it) => selected.includes(it.id))

  const runAction = useCallback(
    async (id: string, action: BrowserActionName) => {
      setBusy((prev) => [...prev, id])
      try {
        const res = await endpoints.browserAction(id, action)
        notify(res.ok ? 'ok' : 'err', res.message)
        refresh()
      } catch (err) {
        notify('err', err instanceof ApiError || err instanceof Error ? err.message : '操作失败')
      } finally {
        setBusy((prev) => prev.filter((x) => x !== id))
      }
    },
    [notify, refresh],
  )

  const runBatch = useCallback(
    async (action: BrowserActionName) => {
      if (selected.length === 0) {
        notify('err', '先在卡片左上角勾选要操作的实例')
        return
      }
      setBusy(selected)
      try {
        const res = await endpoints.browserBatch(selected, action)
        const label = action === 'start' ? '启动' : action === 'stop' ? '停止' : '重启'
        if (res.failed === 0) {
          notify('ok', `已${label} ${res.succeeded} 台实例`)
        } else {
          // 失败原因逐条列出来，用户才知道是哪一台、为什么
          const first = res.items.find((item) => !item.ok)
          notify(
            'err',
            `${label}完成 ${res.succeeded} 台，失败 ${res.failed} 台${first ? `：${first.message}` : ''}`,
          )
        }
        setSelected([])
        refresh()
      } catch (err) {
        notify('err', err instanceof Error ? err.message : '批量操作失败')
      } finally {
        setBusy([])
      }
    },
    [notify, refresh, selected],
  )

  const duplicateInstance = async (item: InstanceSummary) => {
    setBusy((prev) => [...prev, item.id])
    try {
      const detail = await endpoints.duplicateBrowser(item.id)
      notify('ok', `已复制为 ${detail.name}，账号与出口需要重新绑定`)
      refresh()
    } catch (err) {
      notify('err', err instanceof ApiError || err instanceof Error ? err.message : '复制失败')
    } finally {
      setBusy((prev) => prev.filter((x) => x !== item.id))
    }
  }

  const copyInstanceId = async (item: InstanceSummary) => {
    const ok = await copyText(item.id)
    // 剪贴板被浏览器拦掉时把完整值直接摆出来，至少能手动抄
    notify(
      ok ? 'ok' : 'err',
      ok ? `已复制实例 ID ${item.id}` : `复制失败，完整 ID：${item.id}`,
    )
  }

  const removeInstance = async (item: InstanceSummary) => {
    try {
      await endpoints.deleteBrowser(item.id)
      notify('ok', `实例 ${item.name} 已删除`)
      setConfirming(null)
      setSelected((prev) => prev.filter((x) => x !== item.id))
      refresh()
    } catch (err) {
      setConfirming(null)
      notify('err', err instanceof ApiError || err instanceof Error ? err.message : '删除失败')
    }
  }

  const saved = (detail: BrowserDetail, created: boolean) => {
    setDialog({ open: false, id: null })
    notify('ok', created ? `实例 ${detail.name} 已创建` : `${detail.name} 的配置已保存`)
    refresh()
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

  // 统计口径直接取后端的 cards，避免前端再算一遍算错了
  const card = (title: string) => data.cards.find((c) => c.title === title)
  const schedulable = card('可调度')
  const needFix = card('需处理')
  const queue = card('队列')

  return (
    <PageShell>
      <PageHeader
        icon={<IconBrowser size={19} />}
        title="浏览器池"
        subtitle="每个实例可独立绑定账号、出口 IP 与浏览器指纹，并通过 noVNC 实时接管"
        actions={
          <>
            {/* 所有实例的画面入口集中在一页：这里只留一个门，卡片上的按钮仍直接进单台 */}
            <button type="button" className="btn-ghost" onClick={() => navigate('/novnc')}>
              <IconMonitor size={14} />
              noVNC 详情
            </button>
            <button type="button" className="btn-ghost" onClick={reload}>
              <IconRefresh size={14} />
              刷新
            </button>
            <button
              type="button"
              className="btn-dark"
              onClick={() => setDialog({ open: true, id: null })}
            >
              <IconPlus size={14} />
              新建浏览器实例
            </button>
          </>
        }
      />

      {/* 统计条：与内核管理、账号管理同一套 StatTile */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="实例总数"
          value={String(data.totals.total)}
          hint={`${data.totals.running} 台运行中`}
          tone="dark"
          icon={<IconBrowser size={15} />}
        />
        <StatTile
          label="运行中"
          value={String(data.totals.running)}
          hint="noVNC 可实时接管"
          tone="emerald"
          icon={<IconPlay size={15} />}
        />
        <StatTile
          label="可调度"
          value={String(schedulable?.value ?? 0)}
          hint={schedulable?.hint ?? '空闲待命'}
          tone="blue"
          icon={<IconBolt size={15} />}
        />
        <StatTile
          label="需处理"
          value={String(needFix?.value ?? 0)}
          hint={
            needFix && needFix.value > 0
              ? (needFix.hint ?? '异常中断')
              : queue && queue.value > 0
                ? `另有 ${queue.value} 台排队中`
                : '没有异常实例'
          }
          tone={needFix && needFix.value > 0 ? 'rose' : 'zinc'}
          icon={<IconMonitor size={15} />}
        />
      </div>

      {/* 筛选栏 */}
      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 p-3.5">
        <div className="flex items-center gap-3">
          <SearchInput
            placeholder="按实例名、账号或 IP 搜索"
            width="w-[260px]"
            value={query}
            onChange={setQuery}
          />
          <PillTabs
            items={tabs.map((f) => ({
              ...f,
              tone:
                f.key === 'running'
                  ? 'emerald'
                  : f.key === 'idle'
                    ? 'blue'
                    : f.key === 'error'
                      ? 'rose'
                      : f.key === 'queued'
                        ? 'amber'
                        : 'zinc',
            }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectMenu
            value={group}
            items={groupItems}
            onChange={setGroup}
            icon={<IconLayers size={13} />}
            placeholder="全部分组"
            panelHeader="按分组筛选"
          />
          <span className="mx-0.5 h-4 w-px bg-[var(--line)]" />
          <div className="flex items-center gap-0.5 rounded-full bg-[#f4f4f5] p-0.5">
            <button
              type="button"
              onClick={() => {
                setView('grid')
                setMenuId(null)
              }}
              aria-label="卡片视图"
              aria-pressed={view === 'grid'}
              title="卡片视图"
              className={`flex size-7 items-center justify-center rounded-full transition-all ${
                view === 'grid'
                  ? 'bg-white text-[var(--ink-900)] shadow-[0_1px_2px_rgba(16,24,40,0.14)]'
                  : 'text-[var(--ink-400)] hover:text-[var(--ink-700)]'
              }`}
            >
              <IconGrid size={13} />
            </button>
            <button
              type="button"
              onClick={() => {
                setView('list')
                setMenuId(null)
              }}
              aria-label="列表视图"
              aria-pressed={view === 'list'}
              title="列表视图"
              className={`flex size-7 items-center justify-center rounded-full transition-all ${
                view === 'list'
                  ? 'bg-white text-[var(--ink-900)] shadow-[0_1px_2px_rgba(16,24,40,0.14)]'
                  : 'text-[var(--ink-400)] hover:text-[var(--ink-700)]'
              }`}
            >
              <IconList size={13} />
            </button>
          </div>
        </div>
      </Card>

      {/* 批量操作条：只在有勾选时出现，不占常驻空间 */}
      {selected.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#dcdce2] bg-white px-4 py-2.5">
          <span className="text-[12px] text-[var(--ink-700)]">
            已选 <span className="tnum font-semibold">{selected.length}</span> 台实例
          </span>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]" onClick={() => runBatch('start')}>
              <IconPower size={11} />
              启动
            </button>
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]" onClick={() => runBatch('stop')}>
              停止
            </button>
            <button type="button" className="btn-ghost !h-7 !px-3 !text-[11.5px]" onClick={() => runBatch('restart')}>
              <IconRefresh size={11} />
              重启
            </button>
            <button
              type="button"
              className="icon-btn size-7"
              aria-label="取消选择"
              onClick={() => setSelected([])}
            >
              <IconX size={12} />
            </button>
          </div>
        </div>
      )}

      {/* 实例列表 */}
      {visible.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-[#dcdce2] px-6 py-14 text-center">
          <p className="text-[12.5px] font-medium text-[var(--ink-700)]">当前条件下没有实例</p>
          <p className="mt-1 text-[11.5px] text-[var(--ink-400)]">
            换个状态标签、分组，或清空搜索关键词
          </p>
        </div>
      ) : view === 'grid' ? (
        <div className="mt-4 grid grid-cols-2 gap-4">
          {visible.map((it, idx) => (
            <InstanceCard
              key={it.id}
              item={it}
              index={idx}
              checked={selected.includes(it.id)}
              busy={busy.includes(it.id)}
              onToggle={() => toggleSelect(it.id)}
              onOpen={() => navigate('/novnc/' + it.id)}
              onAction={(action) => runAction(it.id, action)}
              onConfigure={() => setDialog({ open: true, id: it.id })}
              onDuplicate={() => duplicateInstance(it)}
              onCopyId={() => copyInstanceId(it)}
              onDelete={() => setConfirming(it)}
            />
          ))}
        </div>
      ) : (
        /* 不能用 overflow-hidden：行末的「更多」菜单是 absolute，会被裁掉 */
        <Card className="mt-4">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="w-11 px-4 py-3">
                  <Checkbox
                    checked={allChecked}
                    indeterminate={someChecked && !allChecked}
                    onChange={(next) => setSelected(next ? visible.map((it) => it.id) : [])}
                    label="全选"
                  />
                </th>
                <th className="table-th">实例</th>
                <th className="table-th">状态</th>
                <th className="table-th">账号 / 出口</th>
                <th className="table-th">指纹</th>
                <th className="table-th">分组</th>
                <th className="table-th text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((it, idx) => {
                const busyNow = busy.includes(it.id)
                // 最后一行向下弹会顶到页面底，改成向上展开
                const menuUp = idx === visible.length - 1
                // 与卡片同一套判定：idle 也已经起来了，主操作就该是接管画面
                const running = it.status === 'running' || it.status === 'idle'
                const primary = running
                  ? {
                      label: '打开 noVNC',
                      icon: <IconMonitor size={11} />,
                      run: () => navigate('/novnc/' + it.id),
                    }
                  : it.status === 'error'
                    ? {
                        label: '重新启动',
                        icon: <IconRefresh size={11} />,
                        run: () => runAction(it.id, 'restart'),
                      }
                    : {
                        label: '启动实例',
                        icon: <IconPlay size={11} />,
                        run: () => runAction(it.id, 'start'),
                      }
                return (
                  <tr key={it.id} className="border-b border-[var(--line)] last:border-0">
                    <td className="px-4 py-3">
                      <Checkbox
                        checked={selected.includes(it.id)}
                        onChange={() => toggleSelect(it.id)}
                        label={`选择 ${it.name}`}
                      />
                    </td>
                    <td className="table-td">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <span
                          className="truncate font-medium text-[var(--ink-900)]"
                          title={it.name}
                        >
                          {it.name}
                        </span>
                        <IdBadge id={it.id} onCopy={() => copyInstanceId(it)} />
                      </div>
                      {/* 备注常常就是状态文案（如「已停止」），跟左边 chip 重了、或者压根没填，就不占这行 */}
                      {it.note && it.note !== meta[it.status].label && (
                        <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
                          {it.note}
                        </div>
                      )}
                    </td>
                    <td className="table-td">
                      <span className={`chip ${statusChip[it.status]}`}>
                        <span className="size-[4px] rounded-full bg-current" />
                        {meta[it.status].label}
                      </span>
                    </td>
                    <td className="table-td">
                      <div>{it.account}</div>
                      <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">
                        {it.ip} · {it.region}
                      </div>
                    </td>
                    <td className="table-td">
                      {/* 与卡片同一个琥珀色 chip，一眼能看出这条是套了模板还是默认 */}
                      <span className="chip max-w-[168px] bg-amber-50 text-amber-600">
                        <IconFingerprint size={10} className="shrink-0" />
                        <span className="min-w-0 truncate">{it.fingerprint}</span>
                      </span>
                    </td>
                    <td className="table-td text-[11.5px]">{it.group}</td>
                    <td className="table-td">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          disabled={busyNow}
                          onClick={primary.run}
                          className="btn-dark !h-7 !px-2.5 !text-[11px] disabled:opacity-60"
                        >
                          {busyNow ? <IconRefresh size={11} /> : primary.icon}
                          {busyNow ? '处理中…' : primary.label}
                        </button>
                        <button
                          type="button"
                          onClick={() => setDialog({ open: true, id: it.id })}
                          className="btn-ghost !h-7 !px-2.5 !text-[11px]"
                        >
                          编辑配置
                        </button>
                        <div className="relative">
                          <button
                            type="button"
                            aria-label="更多操作"
                            onClick={() => setMenuId(menuId === it.id ? null : it.id)}
                            className="icon-btn size-7 !border-transparent !bg-transparent"
                          >
                            <IconMore size={13} />
                          </button>
                          {menuId === it.id && (
                            <>
                              <div className="fixed inset-0 z-10" onClick={() => setMenuId(null)} />
                              <div
                                className={`absolute right-0 z-20 w-[132px] overflow-hidden rounded-xl border border-[var(--line)] bg-white py-1 shadow-[0_12px_32px_-8px_rgba(16,24,40,0.24)] ${
                                  menuUp ? 'bottom-full mb-1' : 'mt-1'
                                }`}
                              >
                                {/* 表格里没有卡片那颗电源键，停止与重启都收进菜单 */}
                                {running && (
                                  <MenuItem
                                    onClick={() => {
                                      setMenuId(null)
                                      runAction(it.id, 'stop')
                                    }}
                                    icon={<IconPower size={11} />}
                                    label="停止"
                                  />
                                )}
                                {running && (
                                  <MenuItem
                                    onClick={() => {
                                      setMenuId(null)
                                      runAction(it.id, 'restart')
                                    }}
                                    icon={<IconRefresh size={11} />}
                                    label="重启"
                                  />
                                )}
                                <MenuItem
                                  onClick={() => {
                                    setMenuId(null)
                                    duplicateInstance(it)
                                  }}
                                  icon={<IconCopy size={11} />}
                                  label="复制实例"
                                />
                                <MenuItem
                                  onClick={() => {
                                    setMenuId(null)
                                    setConfirming(it)
                                  }}
                                  icon={<IconTrash size={11} />}
                                  label="删除"
                                  danger
                                />
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--ink-400)]">
        <span>
          共 {instances.length} 台实例 · 当前筛选显示 {visible.length} 台
          {selected.length > 0 && ` · 已选 ${selected.length} 台`}
        </span>
        {visible.length > 0 && (
          <button
            type="button"
            onClick={() => setSelected(allChecked ? [] : visible.map((it) => it.id))}
            className="rounded-full px-2 py-0.5 text-[11px] font-medium text-[var(--ink-500)] transition-colors hover:bg-[#f4f4f5] hover:text-[var(--ink-900)]"
          >
            {allChecked ? '取消全选' : `全选当前 ${visible.length} 台`}
          </button>
        )}
      </div>

      <BrowserDialog
        open={dialog.open}
        browserId={dialog.id}
        onClose={() => setDialog({ open: false, id: null })}
        onSaved={saved}
      />

      <Modal
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title="删除实例"
        subtitle={
          confirming
            ? `将删除 ${confirming.name} 及其绑定流水，审计记录会保留`
            : undefined
        }
        icon={<IconTrash size={15} />}
        width="max-w-[440px]"
        footer={
          <>
            <button type="button" className="btn-ghost !h-9" onClick={() => setConfirming(null)}>
              取消
            </button>
            <button
              type="button"
              className="!h-9 inline-flex items-center gap-1.5 rounded-full bg-rose-600 px-4 text-[13px] font-medium text-white hover:bg-rose-700"
              onClick={() => confirming && removeInstance(confirming)}
            >
              <IconTrash size={12} />
              确认删除
            </button>
          </>
        }
      >
        <p className="py-3 text-[12px] leading-relaxed text-[var(--ink-600)]">
          实例运行中无法删除，请先停止。删除后账号、出口 IP 与指纹会回到可分配状态，
          对应的绑定流水一并清理。
        </p>
      </Modal>
      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
  )
}

function InstanceCard({
  item,
  index,
  checked,
  busy,
  onToggle,
  onOpen,
  onAction,
  onConfigure,
  onDuplicate,
  onCopyId,
  onDelete,
}: {
  item: InstanceSummary
  index: number
  checked: boolean
  busy: boolean
  onToggle: () => void
  onOpen: () => void
  onAction: (action: BrowserActionName) => void
  onConfigure: () => void
  onDuplicate: () => void
  onCopyId: () => void
  onDelete: () => void
}) {
  const [menu, setMenu] = useState(false)
  const badge = meta[item.status]
  // 已经起来的实例主操作一律是接管画面：noVNC 才是真正要干的事
  const running = item.status === 'running' || item.status === 'idle'

  const primary = running
    ? { label: '打开 noVNC', icon: <IconMonitor size={11} />, run: onOpen }
    : item.status === 'error'
      ? { label: '重新启动', icon: <IconRefresh size={11} />, run: () => onAction('restart') }
      : { label: '启动实例', icon: <IconPlay size={11} />, run: () => onAction('start') }

  return (
    <Card
      className={`group relative flex gap-4 p-4 transition-[box-shadow,border-color] duration-150 hover:border-[#e3e3e9] hover:shadow-[0_6px_20px_-12px_rgba(16,24,40,0.22)] ${
        checked
          ? 'border-[#18181b]/25 shadow-[0_6px_20px_-12px_rgba(16,24,40,0.28)]'
          : ''
      }`}
    >
      <div
        className={`size-[104px] shrink-0 rounded-xl transition-opacity ${
          thumbs[index % thumbs.length]
        } ${checked ? 'opacity-75' : ''}`}
        aria-hidden
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <Checkbox
              checked={checked}
              onChange={onToggle}
              label={`选择 ${item.name}`}
              className="mt-[3px]"
            />
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-1.5">
                <span
                  className="truncate text-[13.5px] font-semibold tracking-tight text-[var(--ink-900)]"
                  title={item.name}
                >
                  {item.name}
                </span>
                {/* ID 太长（UUID 36 位），卡片上只露前 8 位；点一下复制完整 ID */}
                <IdBadge id={item.id} onCopy={onCopyId} />
              </div>
              {/* 状态已经在右上角 chip 里了，这里只在 note 讲的是别的事时才补一句 */}
              <div className="mt-1 truncate text-[11px] text-[var(--ink-400)]">
                分组：{item.group}
                {item.note && item.note !== badge.label ? ` · ${item.note}` : ''}
              </div>
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
          {running && item.fps != null ? (
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
          ) : item.status === 'error' ? (
            <span className="chip bg-rose-50 text-rose-500">{item.note ?? '会话异常'}</span>
          ) : null}
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={primary.run}
              className="btn-dark !h-7 !px-3 !text-[11.5px] disabled:opacity-60"
            >
              {busy ? <IconRefresh size={11} /> : primary.icon}
              {busy ? '处理中…' : primary.label}
            </button>
            <button
              type="button"
              onClick={onConfigure}
              className="btn-ghost !h-7 !px-3 !text-[11.5px]"
            >
              编辑配置
            </button>
          </div>
          <div className="flex items-center gap-1">
            {/* 只在已经起来的时候给「停止」：没起来时主按钮就是启动，这里再来一个纯属重复 */}
            {running && (
              <button
                type="button"
                disabled={busy}
                aria-label="停止实例"
                title="停止实例"
                onClick={() => onAction('stop')}
                className="icon-btn size-7 !border-transparent !bg-transparent text-emerald-600 disabled:opacity-50"
              >
                <IconPower size={12} />
              </button>
            )}
            <div className="relative">
              <button
                type="button"
                aria-label="更多操作"
                onClick={() => setMenu((v) => !v)}
                className="icon-btn size-7 !border-transparent !bg-transparent"
              >
                <IconMore size={13} />
              </button>
              {menu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
                  <div className="absolute right-0 z-20 mt-1 w-[132px] overflow-hidden rounded-xl border border-[var(--line)] bg-white py-1 shadow-[0_12px_32px_-8px_rgba(16,24,40,0.24)]">
                    {/* 没起来的实例没有「重启」可言，那个动作就是主按钮的启动 */}
                    {running && (
                      <MenuItem
                        onClick={() => {
                          setMenu(false)
                          onAction('restart')
                        }}
                        icon={<IconRefresh size={11} />}
                        label="重启"
                      />
                    )}
                    <MenuItem
                      onClick={() => {
                        setMenu(false)
                        onDuplicate()
                      }}
                      icon={<IconCopy size={11} />}
                      label="复制实例"
                    />
                    <MenuItem
                      onClick={() => {
                        setMenu(false)
                        onDelete()
                      }}
                      icon={<IconTrash size={11} />}
                      label="删除"
                      danger
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

function MenuItem({
  onClick,
  icon,
  label,
  danger,
}: {
  onClick: () => void
  icon: ReactNode
  label: string
  danger?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11.5px] hover:bg-[#f7f7f8] ${
        danger ? 'text-rose-600' : 'text-[var(--ink-700)]'
      }`}
    >
      <span className={danger ? 'text-rose-500' : 'text-[var(--ink-400)]'}>{icon}</span>
      {label}
    </button>
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
