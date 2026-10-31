import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import { Card } from '@/components/ui'
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
  IconStarFilled,
  IconTrend,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { KernelCard, KernelStat, KernelVersion } from '@/types/domain'

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
  const [expanded, setExpanded] = useState<string[]>([])
  const [migrating, setMigrating] = useState<KernelCard | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = useCallback((tone: 'ok' | 'err', text: string) => setToast({ tone, text }), [])

  const rescan = async () => {
    setBusy('rescan')
    try {
      await endpoints.rescanKernels()
      refresh()
      notify('ok', '已重新扫描内核目录')
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '扫描失败')
    } finally {
      setBusy('')
    }
  }

  const activate = async (card: KernelCard, version: string) => {
    setBusy(card.id)
    try {
      await endpoints.switchKernelVersion(card.id, version)
      refresh()
      notify('ok', `${card.name} 当前版本已切到 ${version}，旧版本目录保留，可随时切回`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '切换版本失败')
    } finally {
      setBusy('')
    }
  }

  const makePrimary = async (card: KernelCard) => {
    if (card.is_primary) return
    setBusy(card.id)
    try {
      const res = await endpoints.setPrimaryKernel(card.id)
      refresh()
      notify(res.ok ? 'ok' : 'err', res.message)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '设置主力内核失败')
    } finally {
      setBusy('')
    }
  }

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

  const toggle = (id: string) =>
    setExpanded((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const upgradeable = data.cards.filter((c) => c.update_available).length
  const missing = data.cards.filter((c) => !c.downloaded).length

  return (
    <PageShell>
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
              浏览器内核管理
            </h1>
            {missing > 0 ? (
              <span className="chip bg-zinc-100 text-[11px] text-zinc-600">
                <IconAlert size={11} />
                {missing} 个内核未安装
              </span>
            ) : upgradeable > 0 ? (
              <span className="chip bg-blue-50 text-[11px] text-blue-600">
                <IconArrowUpRight size={11} />
                {upgradeable} 个内核有新版本
              </span>
            ) : (
              <span className="chip bg-emerald-50 text-[11px] text-emerald-600">
                <IconCheckCircle size={11} />
                全部已是最新
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">
            四套引擎固定；装了哪些版本、能不能更新，都以磁盘上的实际文件为准
          </p>
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

      {toast && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-xl px-4 py-2.5 text-[12px] ${
            toast.tone === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
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

      {/* 统计条 */}
      <div className="mt-4 grid grid-cols-4 gap-4">
        {data.stats.map((stat) => (
          <StatTile key={stat.key} stat={stat} />
        ))}
      </div>

      {/* 四张引擎卡 */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        {data.cards.map((card) => (
          <KernelCardView
            key={card.id}
            card={card}
            busy={busy === card.id}
            expanded={expanded.includes(card.id)}
            onToggle={() => toggle(card.id)}
            onActivate={(version) => activate(card, version)}
            onMigrate={() => setMigrating(card)}
            onPrimary={() => makePrimary(card)}
          />
        ))}
      </div>

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
        className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] ${
          toneTile[stat.tone] ?? toneTile.dark
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
  expanded,
  onToggle,
  onActivate,
  onMigrate,
  onPrimary,
}: {
  card: KernelCard
  busy: boolean
  expanded: boolean
  onToggle: () => void
  onActivate: (version: string) => void
  onMigrate: () => void
  onPrimary: () => void
}) {
  return (
    <Card className="flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${
              toneTile[card.tone] ?? toneTile.sky
            }`}
          >
            <IconKernel size={16} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <h3 className="text-[14px] font-semibold tracking-tight text-[var(--ink-900)]">
                {card.name}
              </h3>
              {card.is_primary && (
                <span className="chip bg-[#18181b] px-1.5 text-[10px] text-white">
                  <IconStarFilled size={9} />
                  主力
                </span>
              )}
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
          className={`chip shrink-0 ${
            card.downloaded ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'
          }`}
        >
          <span className="size-[5px] rounded-full bg-current" />
          {card.downloaded ? `已下载 ${card.version_count} 个版本` : '未下载'}
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

      {/* 版本 */}
      <div className="mt-3.5 rounded-xl bg-[#fafafa] px-3.5 py-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-[10.5px] text-[var(--ink-400)]">当前版本</div>
            <div className="tnum mt-1 flex items-baseline gap-1.5 text-[17px] leading-none font-semibold">
              <span className={card.downloaded ? 'text-[var(--ink-900)]' : 'text-[var(--ink-400)]'}>
                {card.current_version ?? '—'}
              </span>
              {!card.downloaded && card.current_version && (
                <span className="text-[10px] font-normal text-rose-500">磁盘缺失</span>
              )}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10.5px] text-[var(--ink-400)]">磁盘最新</div>
            <div className="tnum mt-1 text-[12px] font-medium text-[var(--ink-700)]">
              {card.latest_version ?? '—'}
            </div>
          </div>
        </div>

        {card.update_available && card.latest_version && (
          <div className="mt-2.5 flex items-center justify-between gap-2 rounded-lg bg-blue-50 px-2.5 py-1.5">
            <span className="flex min-w-0 items-center gap-1 text-[11px] text-blue-700">
              <IconArrowUpRight size={11} className="shrink-0" />
              <span className="truncate">磁盘上已有 {card.latest_version}，可切换为当前版本</span>
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

        {!card.downloaded && (
          <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--ink-500)]">
            还没有安装任何版本，进详情页选一个版本获取即可
          </p>
        )}
      </div>

      {/* 元信息 */}
      <div className="mt-3 space-y-1.5 text-[11px] text-[var(--ink-400)]">
        <div className="flex items-center gap-1.5">
          <IconBox size={11} className="shrink-0" />
          <span className="truncate font-mono text-[10.5px]" title={card.disk_path}>
            {card.disk_path}
          </span>
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
            type="button"
            onClick={onToggle}
            className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8]"
          >
            版本列表 {card.version_count}
            <IconChevronDown
              size={11}
              className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
            />
          </button>
        )}
        {!card.downloaded && (
          <Link
            to={`/kernels/${card.slug}`}
            className="btn-dark !h-7 !px-3 !text-[11px]"
          >
            <IconCloudDown size={11} />
            获取内核
          </Link>
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
        <button
          type="button"
          onClick={onPrimary}
          disabled={card.is_primary || busy}
          className="ml-auto inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium transition-colors disabled:cursor-default disabled:opacity-50 ${
            card.is_primary
              ? 'text-[var(--ink-400)]'
              : 'text-[var(--ink-700)] hover:bg-[#f4f4f5]'
          }"
        >
          <IconStarFilled size={11} />
          {card.is_primary ? '当前主力' : '设为主力'}
        </button>
        <Link
          to={`/kernels/${card.slug}`}
          className="inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium text-[var(--ink-700)] transition-colors hover:bg-[#f4f4f5]"
        >
          详情
          <IconArrowRight size={11} />
        </Link>
      </div>

      {expanded && (
        <div className="mt-3 overflow-hidden rounded-xl border border-[var(--line)]">
          {card.versions.length === 0 ? (
            <div className="py-8 text-center text-[11.5px] text-[var(--ink-400)]">
              该内核目录下还没有任何版本
            </div>
          ) : (
            <table className="w-full table-fixed">
              <colgroup>
                <col className="w-[38%]" />
                <col className="w-[15%]" />
                <col className="w-[22%]" />
                <col className="w-[10%]" />
                <col className="w-[15%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-[var(--line)] bg-[#fcfcfd]">
                  <th className="table-th !py-2 !pl-3.5">版本 / 基线</th>
                  <th className="table-th !py-2">大小</th>
                  <th className="table-th !py-2">落盘时间</th>
                  <th className="table-th !py-2">实例</th>
                  <th className="table-th !py-2 !pr-3.5 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {card.versions.map((version) => (
                  <VersionRow
                    key={version.version}
                    item={version}
                    busy={busy}
                    onActivate={() => onActivate(version.version)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </Card>
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
          ) : item.ready ? (
            <span className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">已就绪</span>
          ) : (
            <span className="chip bg-amber-50 text-[10px] text-amber-600" title={item.warning ?? ''}>
              未就绪
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-[10px] text-[var(--ink-400)]">
          {item.base ?? item.warning ?? '—'}
        </div>
      </td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-700)]">{item.size ?? '—'}</td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-500)]">
        {item.packaged_at ?? '—'}
      </td>
      <td className="table-td !py-2 tnum text-[11px] text-[var(--ink-700)]">
        {item.instances || '—'}
      </td>
      <td className="table-td !py-2 !pr-3.5 text-right">
        <button
          type="button"
          disabled={item.current || !item.ready || busy}
          onClick={onActivate}
          className="inline-flex h-6.5 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[10.5px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {item.current ? '使用中' : '设为当前'}
        </button>
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
