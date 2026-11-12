import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import { Card, ProgressBar } from '@/components/ui'
import { KernelMigrateDialog } from '@/components/KernelMigrateDialog'
import {
  IconAlert,
  IconArrowRight,
  IconArrowUpRight,
  IconBox,
  IconCheckCircle,
  IconChevronDown,
  IconCloudDown,
  IconDownload,
  IconKernel,
  IconLayers,
  IconMonitor,
  IconRefresh,
  IconTrend,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstallJob, KernelCard, KernelStat, KernelVersion } from '@/types/domain'

const toneTile: Record<string, string> = {
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
  dark: 'bg-[#18181b] text-white',
}

const statIcon: Record<string, ReactNode> = {
  layers: <IconLayers size={15} />,
  download: <IconCloudDown size={15} />,
  trend: <IconTrend size={15} />,
  monitor: <IconMonitor size={15} />,
}

type Toast = { tone: 'ok' | 'err'; text: string } | null

export default function KernelsPage() {
  const { data, status, error, reload, refresh } = useApi(endpoints.kernels, [])
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState<Toast>(null)
  /** 版本浮层：记住是哪张卡、锚在哪个按钮上 */
  const [versions, setVersions] = useState<{ id: string; anchor: HTMLElement } | null>(null)
  const [migrating, setMigrating] = useState<KernelCard | null>(null)
  const [job, setJob] = useState<InstallJob | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = useCallback((tone: 'ok' | 'err', text: string) => setToast({ tone, text }), [])

  // 拉取中每隔 1.5 秒问一次；结束时 refresh 一次让镜像状态跟上
  const runningId = job && job.status === 'running' ? job.id : null
  useEffect(() => {
    if (!runningId) return
    const timer = window.setInterval(() => {
      endpoints
        .installJob(runningId)
        .then((next) => {
          setJob(next)
          if (next.status !== 'running') {
            refresh()
            notify(
              next.status === 'success' ? 'ok' : 'err',
              next.status === 'success'
                ? `${next.version} 镜像已就绪`
                : (next.error ?? '拉取失败'),
            )
          }
        })
        .catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [runningId, refresh, notify])

  const rescan = async () => {
    setBusy('rescan')
    try {
      await endpoints.rescanKernels()
      refresh()
      notify('ok', '已重新扫描本地镜像')
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '扫描失败')
    } finally {
      setBusy('')
    }
  }

  const pull = async (card: KernelCard) => {
    setBusy(card.id)
    try {
      const created = await endpoints.installKernel(card.slug)
      setJob(created)
      notify('ok', `开始拉取 ${created.image_ref}`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '拉取失败')
    } finally {
      setBusy('')
    }
  }

  const activate = async (card: KernelCard, version: string) => {
    setBusy(card.id)
    try {
      await endpoints.switchKernelVersion(card.id, version)
      refresh()
      notify('ok', `${card.name} 当前版本已切到 ${version}，旧镜像保留，可随时切回`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '切换版本失败')
    } finally {
      setBusy('')
    }
  }

  const toggleVersions = useCallback((id: string, anchor: HTMLButtonElement | null) => {
    if (!anchor) return
    setVersions((prev) => (prev?.id === id ? null : { id, anchor }))
  }, [])

  const closeVersions = useCallback(() => setVersions(null), [])

  if (status === 'loading') {
    return (
      <PageShell>
        <Loading />
      </PageShell>
    )
  }
  if (status === 'error' || !data) {
    return (
      <PageShell>
        <ErrorState message={error ?? '内核数据加载失败'} onRetry={reload} />
      </PageShell>
    )
  }

  // 版本浮层要跟着数据走：refresh 之后卡片是新对象，靠 id 现取，避免拿到旧数据
  const versionsCard = versions ? (data.cards.find((c) => c.id === versions.id) ?? null) : null

  return (
    <PageShell>
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
              内核管理
            </h1>
          </div>
        </div>
        <button
          type="button"
          onClick={rescan}
          disabled={busy === 'rescan'}
          className="btn-ghost shrink-0"
        >
          <IconRefresh size={13} />
          {busy === 'rescan' ? '扫描中…' : '重新扫描'}
        </button>
      </div>

      {!data.docker_ok && (
        <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800">
          <IconAlert size={13} className="mt-[2px] shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-medium">Docker 不可用，无法读取本地镜像</div>
            <div className="mt-0.5 text-[11px] text-amber-700">
              {data.docker_error ?? '请确认 Docker 已启动，并且 docker 命令在 PATH 里'}
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-xl px-4 py-2.5 text-[12px] ${toast.tone === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
            }`}
        >
          <span className="mt-[1px] shrink-0">
            {toast.tone === 'ok' ? <IconCheckCircle size={13} /> : <IconAlert size={13} />}
          </span>
          <span className="flex-1">{toast.text}</span>
          <button type="button" onClick={() => setToast(null)} className="shrink-0 opacity-60">
            <IconX size={12} />
          </button>
        </div>
      )}

      {job && (
        <div className="mt-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3">
          <div className="flex items-center gap-2 text-[12px]">
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full ${job.status === 'success'
                ? 'bg-emerald-50 text-emerald-600'
                : job.status === 'failed'
                  ? 'bg-rose-50 text-rose-600'
                  : 'bg-blue-50 text-blue-600'
                }`}
            >
              {job.status === 'success' ? (
                <IconCheckCircle size={12} />
              ) : job.status === 'failed' ? (
                <IconAlert size={12} />
              ) : (
                <IconCloudDown size={12} />
              )}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--ink-700)]">
              {job.image_ref}
            </span>
            <span className="tnum shrink-0 text-[var(--ink-500)]">
              {Math.round(job.progress * 100)}%
            </span>
            <span className="min-w-0 max-w-[38%] truncate text-[11px] text-[var(--ink-500)]">
              {job.error ?? job.message}
            </span>
            {job.status !== 'running' && (
              <button
                type="button"
                onClick={() => setJob(null)}
                className="shrink-0 text-[var(--ink-400)] hover:text-[var(--ink-700)]"
              >
                <IconX size={12} />
              </button>
            )}
          </div>
          <ProgressBar
            value={job.progress * 100}
            tone={job.status === 'failed' ? 'rose' : job.status === 'success' ? 'emerald' : 'blue'}
            className="mt-2"
          />
        </div>
      )}

      {/* 统计条 */}
      <div className="mt-4 grid grid-cols-4 gap-4">
        {data.stats.map((stat) => (
          <StatTile key={stat.key} stat={stat} />
        ))}
      </div>

      {/* 四张引擎卡：等高等宽，版本明细走浮层，不参与网格排版 */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        {data.cards.map((card) => (
          <KernelCardView
            key={card.id}
            card={card}
            busy={busy === card.id}
            versionsOpen={versions?.id === card.id}
            pulling={job?.status === 'running' && job.slug === card.slug}
            onToggleVersions={(anchor) => toggleVersions(card.id, anchor)}
            onActivate={(version) => activate(card, version)}
            onPull={() => pull(card)}
            onMigrate={() => setMigrating(card)}
          />
        ))}
      </div>

      {versions && versionsCard && (
        <VersionPopover
          card={versionsCard}
          anchor={versions.anchor}
          busy={busy === versionsCard.id}
          onClose={closeVersions}
          onActivate={(version) => activate(versionsCard, version)}
        />
      )}

      <KernelMigrateDialog
        card={migrating}
        open={migrating !== null}
        onClose={() => setMigrating(null)}
        onDone={(message) => {
          refresh()
          notify('ok', message)
        }}
      />
    </PageShell>
  )
}

function StatTile({ stat }: { stat: KernelStat }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3.5">
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] ${toneTile[stat.tone] ?? toneTile.dark
          }`}
      >
        {statIcon[stat.icon] ?? <IconKernel size={15} />}
      </span>
      <div className="min-w-0">
        <div className="text-[10.5px] text-[var(--ink-400)]">{stat.label}</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="tnum text-[19px] leading-none font-semibold text-[var(--ink-900)]">
            {stat.value}
          </span>
          <span className="truncate text-[10.5px] text-[var(--ink-400)]">{stat.hint}</span>
        </div>
      </div>
    </div>
  )
}

function KernelCardView({
  card,
  busy,
  versionsOpen,
  pulling,
  onToggleVersions,
  onActivate,
  onPull,
  onMigrate,
}: {
  card: KernelCard
  busy: boolean
  versionsOpen: boolean
  pulling: boolean
  onToggleVersions: (anchor: HTMLButtonElement | null) => void
  onActivate: (version: string) => void
  onPull: () => void
  onMigrate: () => void
}) {
  const disabled = !card.supported
  const versionsBtn = useRef<HTMLButtonElement>(null)

  return (
    <Card
      className={`flex h-full flex-col p-5 ${disabled ? 'border-dashed bg-[#fcfcfd]' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${disabled ? 'bg-[#f4f4f5] text-[var(--ink-400)]' : (toneTile[card.tone] ?? toneTile.sky)
              }`}
          >
            <IconKernel size={16} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <h3
                className={`text-[14px] font-semibold tracking-tight ${disabled ? 'text-[var(--ink-500)]' : 'text-[var(--ink-900)]'
                  }`}
              >
                {card.name}
              </h3>
              <span className="chip border border-[var(--line)] bg-white text-[10px] text-[var(--ink-500)]">
                {card.engine}
              </span>
              <span className="text-[10px] text-[var(--ink-400)]">
                {card.channel} · {card.arch}
              </span>
            </div>
            <p className="mt-1 truncate text-[11px] text-[var(--ink-500)]">{card.tagline}</p>
          </div>
        </div>
        <span
          className={`chip shrink-0 ${disabled
            ? 'bg-[#f4f4f5] text-[var(--ink-500)]'
            : card.installed
              ? 'bg-emerald-50 text-emerald-600'
              : 'bg-zinc-100 text-zinc-500'
            }`}
        >
          <span className="size-[5px] rounded-full bg-current" />
          {disabled
            ? '暂未支持'
            : card.installed
              ? `镜像就绪 ${card.version_count} 个`
              : '未获取'}
        </span>
      </div>

      {/* 源仓库 */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {card.repo_url ? (
          <RepoLink href={card.repo_url} label="GitHub 源仓库" />
        ) : (
          <span className="text-[11px] text-[var(--ink-400)]">未配置源仓库</span>
        )}
        {card.mirror_url && <RepoLink href={card.mirror_url} label="Gitee 镜像" />}
        {card.detection_level && (
          <span className="ml-auto text-[10.5px] text-[var(--ink-400)]">
            {card.detection_level}
          </span>
        )}
      </div>

      {/* 镜像版本 */}
      <div className="mt-3.5 rounded-xl bg-[#fafafa] px-3.5 py-3">
        {disabled ? (
          <div className="py-2 text-center">
            <p className="text-[12px] font-medium text-[var(--ink-500)]">暂未支持，敬请期待</p>
            <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
              {card.unsupported_reason ?? '该内核还在做镜像，做好后这里会出现拉取入口'}
            </p>
          </div>
        ) : (
          <>
            {/* 只留「当前版本」大数字。原来右边还有一列「本地最新」，
                但三张卡里它和当前版本一模一样，等于同一个数字印两遍；
                真不同的时候下面那条蓝色提示已经把最新版说清楚了。 */}
            <div>
              <div className="text-[10.5px] text-[var(--ink-400)]">当前版本</div>
              <div className="tnum mt-1 flex items-baseline gap-1.5 text-[17px] leading-none font-semibold">
                <span className={card.installed ? 'text-[var(--ink-900)]' : 'text-[var(--ink-400)]'}>
                  {card.current_version ?? '—'}
                </span>
                {!card.installed && (
                  <span className="text-[10px] font-normal text-[var(--ink-400)]">未获取</span>
                )}
              </div>
            </div>

            {card.update_available && card.latest_version && (
              <div className="mt-2.5 flex items-center justify-between gap-2 rounded-lg bg-blue-50 px-2.5 py-1.5">
                <span className="flex min-w-0 items-center gap-1 text-[11px] text-blue-700">
                  <IconArrowUpRight size={11} className="shrink-0" />
                  <span className="truncate">本地已有 {card.latest_version}，可切换为当前版本</span>
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onActivate(card.latest_version as string)}
                  className="shrink-0 rounded-full bg-blue-600 px-2.5 py-1 text-[10.5px] font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60"
                >
                  启用
                </button>
              </div>
            )}

            {!card.installed && (
              <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--ink-500)]">
                点「获取内核」会执行{' '}
                <code className="font-mono text-[10px] text-[var(--ink-700)]">
                  docker pull {card.registry}:{card.slug}
                </code>
              </p>
            )}
          </>
        )}
      </div>

      {/* 元信息 */}
      <div className="mt-3 space-y-1.5 text-[11px] text-[var(--ink-400)]">
        <div className="flex items-center gap-1.5">
          <IconBox size={11} className="shrink-0" />
          <span className="truncate font-mono text-[10.5px]" title={card.registry}>
            {card.registry}:{card.slug}
          </span>
          {card.total_size && (
            <span className="ml-auto shrink-0 tnum text-[10.5px]">{card.total_size}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1">
            <IconMonitor size={11} />
            {card.instance_count} 台实例
          </span>
          {card.stale_count > 0 && (
            <span className="flex items-center gap-1 text-amber-600">
              <IconAlert size={11} />
              {card.stale_count} 台仍在旧版本
            </span>
          )}
          <span className="ml-auto">扫描于 {card.scanned_at}</span>
        </div>
      </div>

      {/* 操作 */}
      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-3">
        {card.version_count > 0 && (
          <button
            ref={versionsBtn}
            type="button"
            aria-haspopup="dialog"
            aria-expanded={versionsOpen}
            onClick={() => onToggleVersions(versionsBtn.current)}
            className={`inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-[11px] font-medium transition-colors ${
              versionsOpen
                ? 'border-[#18181b] bg-[#18181b] text-white'
                : 'border-[var(--line)] bg-white text-[var(--ink-700)] hover:bg-[#f7f7f8]'
            }`}
          >
            镜像版本 {card.version_count}
            <IconChevronDown
              size={11}
              className={`transition-transform ${versionsOpen ? 'rotate-180' : ''}`}
            />
          </button>
        )}
        {!disabled && !card.installed && (
          <button
            type="button"
            onClick={onPull}
            disabled={busy || pulling}
            className="btn-dark !h-7 !px-3 !text-[11px] disabled:opacity-60"
          >
            <IconCloudDown size={11} />
            {pulling ? '拉取中…' : '获取内核'}
          </button>
        )}
        {!disabled && card.installed && (
          <button
            type="button"
            onClick={onPull}
            disabled={busy || pulling}
            className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:opacity-50"
          >
            <IconRefresh size={11} />
            {pulling ? '拉取中…' : '拉取最新'}
          </button>
        )}
        {card.stale_count > 0 && (
          <button
            type="button"
            onClick={onMigrate}
            disabled={busy}
            className="inline-flex h-7 items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 text-[11px] font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-60"
          >
            <IconDownload size={11} />
            迁移 {card.stale_count} 台
          </button>
        )}
        <Link
          to={`/kernels/${card.slug}`}
          className="ml-auto inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium text-[var(--ink-700)] transition-colors hover:bg-[#f4f4f5]"
        >
          详情
          <IconArrowRight size={11} />
        </Link>
      </div>
    </Card>
  )
}

/**
 * 镜像版本浮层。
 *
 * 为什么不做成行内展开：四张卡在 `grid-cols-2` 里，网格项默认 `stretch`，
 * 一张长高整行都跟着长——旁边那张没有版本表的卡被拉到同样高度，中间空出
 * 一大块。浮层不占布局，四张卡永远等高等宽。
 *
 * 为什么不用 hover 打开：面板里有「设为当前」要点击，鼠标从按钮移过去的
 * 途中偏出面板就关了，很难点中；触屏也没有 hover。所以是点开、点外面或
 * Esc 关，按钮本身给 `aria-expanded`。
 *
 * 用 fixed + portal 挂到 body：卡片容器都没有 `overflow:hidden`，但浮层要
 * 盖住相邻卡片和页头，挂到 body 上就不用跟各层 z-index 打架，也不会被
 * 将来的滚动容器裁掉。位置在每次滚动 / 缩放时按锚点重新算，空间不够就
 * 翻到按钮上方。
 */
function VersionPopover({
  card,
  anchor,
  busy,
  onClose,
  onActivate,
}: {
  card: KernelCard
  anchor: HTMLElement
  busy: boolean
  onClose: () => void
  onActivate: (version: string) => void
}) {
  const panel = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<{ top: number; left: number; width: number } | null>(null)

  useLayoutEffect(() => {
    const place = () => {
      const el = panel.current
      if (!el) return
      const a = anchor.getBoundingClientRect()
      const gap = 8
      const margin = 12
      const width = Math.min(560, window.innerWidth - margin * 2)
      const height = el.offsetHeight
      const left = Math.min(Math.max(margin, a.left), window.innerWidth - width - margin)
      let top = a.bottom + gap
      if (top + height > window.innerHeight - margin) {
        const above = a.top - height - gap
        top = above >= margin ? above : Math.max(margin, window.innerHeight - height - margin)
      }
      setBox({ top, left, width })
    }
    place()
    // capture：页面里任何一层滚动都要跟着重算
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [anchor])

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      // 点按钮自己交回给 toggle，否则会「关了又立刻开」
      if (panel.current?.contains(target) || anchor.contains(target)) return
      onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [anchor, onClose])

  return createPortal(
    <div
      ref={panel}
      role="dialog"
      aria-label={`${card.name} 的镜像版本`}
      style={{
        top: box?.top ?? -9999,
        left: box?.left ?? -9999,
        width: box?.width ?? 560,
        visibility: box ? 'visible' : 'hidden',
      }}
      className="fixed z-[80] overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[0_4px_12px_rgba(16,24,40,0.06),0_20px_48px_-12px_rgba(16,24,40,0.28)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-2.5">
        <div className="min-w-0">
          <div className="text-[12.5px] font-semibold text-[var(--ink-900)]">镜像版本</div>
          <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
            {card.name} · 本地 {card.versions.length} 个
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="flex size-6 shrink-0 items-center justify-center rounded-full text-[var(--ink-400)] transition-colors hover:bg-[#f4f4f5] hover:text-[var(--ink-700)]"
        >
          <IconX size={12} />
        </button>
      </div>

      {card.versions.length === 0 ? (
        <div className="py-10 text-center text-[11.5px] text-[var(--ink-400)]">
          本地还没有这个内核的镜像
        </div>
      ) : (
        <div className="max-h-[340px] overflow-y-auto">
          <table className="w-full table-fixed">
            <colgroup>
              <col className="w-[36%]" />
              <col className="w-[12%]" />
              <col className="w-[22%]" />
              <col className="w-[11%]" />
              <col className="w-[19%]" />
            </colgroup>
            <thead>
              <tr className="border-b border-[var(--line)] bg-[#fcfcfd]">
                <th className="table-th sticky top-0 bg-[#fcfcfd] !py-2 !pl-4 whitespace-nowrap">
                  版本 / 镜像 tag
                </th>
                <th className="table-th sticky top-0 bg-[#fcfcfd] !py-2 whitespace-nowrap">大小</th>
                <th className="table-th sticky top-0 bg-[#fcfcfd] !py-2 whitespace-nowrap">
                  构建时间
                </th>
                <th className="table-th sticky top-0 bg-[#fcfcfd] !py-2 whitespace-nowrap">实例</th>
                <th className="table-th sticky top-0 bg-[#fcfcfd] !py-2 !pr-4 text-right whitespace-nowrap">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {card.versions.map((version) => (
                <VersionRow
                  key={version.image_ref}
                  item={version}
                  busy={busy}
                  onActivate={() => onActivate(version.version)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>,
    document.body,
  )
}

function VersionRow({
  item,
  busy,
  onActivate,
}: {
  item: KernelVersion
  busy: boolean
  onActivate: () => void
}) {
  return (
    <tr className="border-b border-[var(--line)] last:border-0">
      <td className="table-td !py-2 !pl-3.5">
        <div className="flex items-center gap-1.5">
          <span className="tnum text-[11.5px] font-medium text-[var(--ink-900)]">
            {item.version}
          </span>
          {item.current ? (
            <span className="chip bg-emerald-50 text-[10px] text-emerald-600">当前</span>
          ) : (
            <span className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">已就绪</span>
          )}
          {!item.pinned && (
            <span
              className="chip bg-amber-50 text-[10px] text-amber-600"
              title="只有滚动 tag，下次构建会被覆盖"
            >
              滚动
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--ink-400)]">
          {item.tag}
        </div>
      </td>
      <td className="table-td !py-2 tnum text-[11px] whitespace-nowrap text-[var(--ink-700)]">
        {item.size ?? '—'}
      </td>
      <td className="table-td !py-2 tnum text-[11px] whitespace-nowrap text-[var(--ink-500)]">
        {item.created_at ?? '—'}
      </td>
      <td className="table-td !py-2 tnum text-[11px] whitespace-nowrap text-[var(--ink-700)]">
        {item.instances || '—'}
      </td>
      <td className="table-td !py-2 !pr-3.5 text-right">
        {/* 当前版本那行不给按钮：名字后面已经有「当前」标记，
            再来一个灰掉的「使用中」按钮只是噪音 */}
        {item.current ? (
          <span className="text-[10.5px] whitespace-nowrap text-[var(--ink-500)]">使用中</span>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={onActivate}
            className="inline-flex h-6.5 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[10.5px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:cursor-not-allowed disabled:opacity-40"
          >
            设为当前
          </button>
        )}
      </td>
    </tr>
  )
}

function RepoLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-full bg-[#f4f4f5] px-2 py-[3px] text-[10.5px] font-medium text-[var(--ink-700)] transition-colors hover:bg-[#e9e9ec]"
    >
      {label}
      <IconArrowUpRight size={10} />
    </a>
  )
}
