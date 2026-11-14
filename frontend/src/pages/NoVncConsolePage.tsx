import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { copyText } from '@/lib/clipboard'
import { PageShell } from '@/components/Layout'
import { Card, SearchInput, SoftChip, type Tone } from '@/components/ui'
import { IdBadge } from '@/components/IdBadge'
import { Toast, useToast } from '@/components/Toast'
import {
  IconArrowLeft,
  IconArrowUpRight,
  IconBrowser,
  IconEye,
  IconPower,
  IconRefresh,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstanceStatus, NoVncTarget } from '@/types/domain'

type Availability = NoVncTarget['availability']

const meta: Record<InstanceStatus, { label: string; tone: Tone; dot: string }> = {
  running: { label: '运行中', tone: 'emerald', dot: 'bg-emerald-500' },
  idle: { label: '空闲', tone: 'blue', dot: 'bg-blue-500' },
  error: { label: '异常', tone: 'rose', dot: 'bg-rose-500' },
  stopped: { label: '已停止', tone: 'zinc', dot: 'bg-zinc-300' },
  queued: { label: '排队中', tone: 'amber', dot: 'bg-amber-500' },
}

const availability: Record<Availability, { label: string; tone: Tone; chip: string }> = {
  ready: { label: '可接管', tone: 'emerald', chip: 'bg-emerald-50 text-emerald-600' },
  stopped: { label: '待启动', tone: 'blue', chip: 'bg-blue-50 text-blue-600' },
  unsupported: { label: '镜像无 noVNC', tone: 'rose', chip: 'bg-rose-50 text-rose-500' },
  blocked: { label: '待配置', tone: 'amber', chip: 'bg-amber-50 text-amber-600' },
}

/**
 * noVNC 控制台：左边挑实例，右边直接看画面。
 *
 * 之前拆成「清单页 + 单台页」，看第二台要退出去再点一次，一次只能看一台。改成
 * 左右分栏后切换实例只是在左侧换一行，右侧 iframe 跟着换地址，不离开页面。
 *
 * 能不能看画面由后端按镜像判定（``services/browser_novnc.py``）：镜像里没有
 * noVNC、实例没启动、缺内核或镜像，都在右侧就地说明并给出下一步，而不是塞一个
 * 打不开的 iframe。
 */
export default function NoVncConsolePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, status, error, reload } = useApi(endpoints.novncOverview, [])
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState('all')
  // iframe 的 src 不变时重建 key 才能重连，靠这个计数器强制刷新
  const [nonce, setNonce] = useState(0)
  const [busy, setBusy] = useState(false)
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

  // 地址里有 id 就用它；直接进 /novnc 时优先落到一台能看的，省得先看到空画面
  const selected = useMemo(() => {
    if (instances.length === 0) return null
    if (id) return instances.find((it) => it.id === id) ?? instances[0]
    return instances.find((it) => it.availability === 'ready') ?? instances[0]
  }, [id, instances])

  const pick = (target: NoVncTarget) => {
    setNonce(0)
    // replace：从一长串实例里来回点不该把浏览历史塞满，返回键仍回浏览器池
    navigate(`/novnc/${target.id}`, { replace: true })
  }

  const copyId = async (value: string) => {
    const ok = await copyText(value)
    notify(ok ? 'ok' : 'err', ok ? '实例 ID 已复制' : '复制失败')
  }

  const startSelected = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const result = await endpoints.browserAction(selected.id, 'start')
      notify(result.ok ? 'ok' : 'err', result.message)
      if (result.ok) {
        reload()
        // 启动要等容器起来，稍后自动重连一次，省得用户再点「重载」
        window.setTimeout(() => setNonce((n) => n + 1), 2500)
      }
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '启动失败')
    } finally {
      setBusy(false)
    }
  }

  const cap = selected ? availability[selected.availability] : null
  const state = selected ? meta[selected.status] : null

  return (
    <PageShell>
      {/* 不再占一整块页头：标题对使用者没有增量信息，把返回入口直接放到列表上方 */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <button type="button" className="btn-ghost !h-8 !px-3 !text-[12px]" onClick={() => navigate('/browsers')}>
          <IconArrowLeft size={13} />
          返回浏览器池
        </button>
        <button type="button" className="btn-ghost !h-8 !px-3 !text-[12px]" onClick={reload}>
          <IconRefresh size={13} />
          刷新
        </button>
      </div>

      {status === 'error' && <ErrorState message={error} onRetry={reload} />}
      {status === 'loading' && !data && <Loading />}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:h-[calc(100vh-156px)] lg:min-h-[560px] lg:grid-cols-[318px_minmax(0,1fr)]">
          {/* 左：实例选择 */}
          <Card className="flex max-h-[460px] flex-col overflow-hidden lg:h-full lg:max-h-none">
            <div className="space-y-2 border-b border-[var(--line)] p-2.5">
              <SearchInput
                placeholder="搜索实例名 / ID / 账号"
                width="w-full"
                value={query}
                onChange={setQuery}
              />
              {/* 318px 宽放不下 4 个 pill，会折成两行；这里用等宽分段控件 */}
              <div className="grid grid-cols-4 gap-0.5 rounded-full bg-[#f4f4f5] p-0.5">
                {tabs.map((item) => {
                  const active = item.key === tab
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setTab(item.key)}
                      className={`flex h-6 items-center justify-center gap-1 rounded-full text-[11px] transition-all ${
                        active
                          ? 'bg-white font-medium text-[var(--ink-900)] shadow-[0_1px_2px_rgba(16,24,40,0.14)]'
                          : 'text-[var(--ink-500)] hover:text-[var(--ink-700)]'
                      }`}
                    >
                      {item.label}
                      <span className={active ? 'text-[10px] text-[var(--ink-500)]' : 'text-[10px] text-[var(--ink-400)]'}>
                        {item.count}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-1.5">
              {visible.length === 0 ? (
                <p className="px-3 py-10 text-center text-[11.5px] text-[var(--ink-400)]">
                  没有符合条件的实例
                </p>
              ) : (
                visible.map((item) => (
                  <InstanceRow
                    key={item.id}
                    item={item}
                    active={selected?.id === item.id}
                    onSelect={() => pick(item)}
                  />
                ))
              )}
            </div>

            <div className="flex items-center justify-between border-t border-[var(--line)] px-3 py-2 text-[10.5px] text-[var(--ink-400)]">
              <span>
                共 {instances.length} 台 · 可接管 {data.totals.ready} 台
              </span>
              {data.totals.offline > 0 && <span>{data.totals.offline} 台待启动</span>}
            </div>
          </Card>

          {/* 右：画面 */}
          <Card className="flex min-h-[420px] flex-col overflow-hidden lg:h-full lg:min-h-0">
            {selected ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-3.5 py-2.5">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="truncate text-[13px] font-semibold tracking-tight text-[var(--ink-900)]"
                      title={selected.name}
                    >
                      {selected.name}
                    </span>
                    <IdBadge id={selected.id} onCopy={() => copyId(selected.id)} />
                    <SoftChip tone={state!.tone}>{state!.label}</SoftChip>
                    <SoftChip tone={cap!.tone}>{cap!.label}</SoftChip>
                    {selected.port && (
                      <span className="tnum text-[10.5px] text-[var(--ink-400)]">
                        端口 {selected.port}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      className="btn-ghost !h-7 !px-2.5 !text-[11px]"
                      onClick={() => setNonce((n) => n + 1)}
                      disabled={!selected.ready}
                    >
                      <IconRefresh size={11} />
                      重载画面
                    </button>
                    {selected.url && (
                      <a
                        className="btn-ghost !h-7 !px-2.5 !text-[11px]"
                        href={selected.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <IconArrowUpRight size={11} />
                        新窗口
                      </a>
                    )}
                  </div>
                </div>

                <div className="min-h-0 flex-1 bg-[#0d0d0f]">
                  {selected.ready && selected.url ? (
                    <iframe
                      key={`${selected.id}-${nonce}`}
                      src={selected.url}
                      title={`${selected.name} 的 noVNC 画面`}
                      className="h-full w-full border-0"
                      allow="clipboard-read; clipboard-write; fullscreen"
                    />
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-12 text-center">
                      <span className="flex size-12 items-center justify-center rounded-2xl bg-white/5 text-white/40">
                        {selected.availability === 'stopped' ? (
                          <IconPower size={20} />
                        ) : (
                          <IconX size={20} />
                        )}
                      </span>
                      <div>
                        <p className="text-[14px] font-medium text-white/90">
                          {selected.availability === 'stopped'
                            ? '实例还没起来'
                            : selected.availability === 'unsupported'
                              ? '这个镜像没有 noVNC'
                              : '实例还缺内核或镜像'}
                        </p>
                        <p className="mt-1 max-w-[440px] text-[12px] leading-relaxed text-white/45">
                          {selected.reason ?? '暂时拿不到画面地址'}
                        </p>
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        {selected.availability === 'stopped' && (
                          <button
                            type="button"
                            className="!h-8 inline-flex items-center gap-1.5 rounded-full bg-white px-4 text-[12px] font-medium text-[#18181b] hover:bg-white/90 disabled:opacity-60"
                            onClick={startSelected}
                            disabled={busy}
                          >
                            <IconPower size={12} />
                            {busy ? '启动中…' : '启动实例'}
                          </button>
                        )}
                        {selected.availability === 'blocked' && (
                          <button
                            type="button"
                            className="!h-8 inline-flex items-center gap-1.5 rounded-full bg-white px-4 text-[12px] font-medium text-[#18181b] hover:bg-white/90"
                            onClick={() => navigate('/browsers')}
                          >
                            <IconBrowser size={12} />
                            去浏览器池配置
                          </button>
                        )}
                        <button
                          type="button"
                          className="!h-8 inline-flex items-center gap-1.5 rounded-full border border-white/15 px-4 text-[12px] font-medium text-white/70 hover:bg-white/5"
                          onClick={reload}
                        >
                          <IconRefresh size={12} />
                          重新检测
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-x-5 gap-y-2 border-t border-[var(--line)] px-3.5 py-2.5 md:grid-cols-3 xl:grid-cols-6">
                  <Field label="内核">{selected.kernel ?? '未绑定'}</Field>
                  <Field label="版本">{selected.kernel_version ?? '—'}</Field>
                  <Field label="绑定账号">{selected.account}</Field>
                  <Field label="出口 IP">{selected.ip}</Field>
                  <Field label="分组">{selected.group}</Field>
                  <Field label="镜像" title={selected.image ?? ''}>
                    {selected.image ?? '—'}
                  </Field>
                </div>
              </>
            ) : (
              <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-[#f4f4f5] text-[var(--ink-400)]">
                  <IconEye size={20} />
                </span>
                <p className="text-[13px] font-medium text-[var(--ink-700)]">左侧还没有实例</p>
                <p className="text-[11.5px] text-[var(--ink-400)]">
                  到浏览器池新建一台，启动后就能在这里接管画面
                </p>
                <button
                  type="button"
                  className="btn-ghost mt-1"
                  onClick={() => navigate('/browsers')}
                >
                  <IconBrowser size={13} />
                  去浏览器池
                </button>
              </div>
            )}
          </Card>
        </div>
      )}

      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
  )
}

function InstanceRow({
  item,
  active,
  onSelect,
}: {
  item: NoVncTarget
  active: boolean
  onSelect: () => void
}) {
  const cap = availability[item.availability]
  const state = meta[item.status]
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active}
      className={`relative w-full rounded-xl px-2.5 py-2 text-left transition-colors ${
        active ? 'bg-[#f4f4f5]' : 'hover:bg-[#f7f7f8]'
      }`}
    >
      {active && (
        <span className="absolute top-1/2 left-0 h-5 w-[2px] -translate-y-1/2 rounded-full bg-[#18181b]" />
      )}
      <div className="flex items-center gap-1.5">
        <span className={`size-[5px] shrink-0 rounded-full ${state.dot}`} />
        <span
          className={`min-w-0 flex-1 truncate text-[12.5px] text-[var(--ink-900)] ${
            active ? 'font-semibold' : 'font-medium'
          }`}
          title={item.name}
        >
          {item.name}
        </span>
        <span className={`chip shrink-0 ${cap.chip}`}>{cap.label}</span>
      </div>
      <div className="mt-1 flex items-center gap-1 pl-[11px] text-[10.5px] text-[var(--ink-400)]">
        <span className="tnum shrink-0">{item.id.slice(0, 8)}</span>
        <span className="shrink-0">·</span>
        <span className="min-w-0 truncate">{item.account}</span>
        {item.port && (
          <>
            <span className="shrink-0">·</span>
            <span className="tnum shrink-0">{item.port}</span>
          </>
        )}
      </div>
    </button>
  )
}

function Field({
  label,
  children,
  title,
}: {
  label: string
  children: React.ReactNode
  title?: string
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] text-[var(--ink-400)]">{label}</div>
      <div className="mt-0.5 truncate text-[11.5px] font-medium text-[var(--ink-700)]" title={title}>
        {children}
      </div>
    </div>
  )
}
