import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import { Card, ProgressBar } from '@/components/ui'
import { Markdown, InlineMarkdown } from '@/components/Markdown'
import {
  IconAlert,
  IconArrowLeft,
  IconArrowUpRight,
  IconBox,
  IconCheck,
  IconCheckCircle,
  IconClipboard,
  IconCloudDown,
  IconDownload,
  IconInfo,
  IconKernel,
  IconMonitor,
  IconRefresh,
  IconStarFilled,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type {
  AcquireKind,
  EnginePackage,
  EngineProfile,
  EngineVersionView,
  InstallJob,
  KernelCard,
} from '@/types/domain'

const toneTile: Record<string, string> = {
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
  dark: 'bg-[#18181b] text-white',
}

const KIND_LABEL: Record<AcquireKind, string> = {
  pip: '包管理器',
  archive: '直链下载',
  manual: '手动下载',
}

const LINK_LABEL: Record<string, string> = {
  release: '发布页',
  docs: '文档',
  bucket: '索引站',
  mirror: '镜像',
}

const OS_LABEL: Record<string, string> = {
  windows: 'Windows',
  linux: 'Linux',
  macos: 'macOS',
  any: '全平台',
}

type Toast = { tone: 'ok' | 'err'; text: string } | null

export default function KernelDetailPage() {
  const { slug = '' } = useParams()
  const { data, status, error, reload, refresh } = useApi(
    () => endpoints.kernelDetail(slug),
    [slug],
  )

  const [job, setJob] = useState<InstallJob | null>(null)
  const [startedAt, setStartedAt] = useState(0)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState<Toast>(null)
  const [copied, setCopied] = useState('')

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = useCallback(
    (tone: 'ok' | 'err', text: string) => setToast({ tone, text }),
    [],
  )

  // 进页面时捡回正在跑的任务：刷新或离开再回来，后端那个任务还在，别让它「消失」
  useEffect(() => {
    let cancelled = false
    endpoints
      .installJobs()
      .then((list) => {
        if (cancelled) return
        const mine = list.find((item) => item.slug === slug && item.status === 'running')
        if (mine) {
          setJob(mine)
          setStartedAt(Date.now())
          setNowMs(Date.now())
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [slug])

  // 只轮询正在跑的任务；跑完那一下 refresh 一次，让磁盘状态跟上
  const runningId = job && job.status === 'running' ? job.id : null

  // 秒表只用来告诉用户「它还在动」——后端下载阶段不细分进度，没有时长会让人以为卡死
  useEffect(() => {
    if (!runningId) return
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [runningId])

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
                ? `${next.version} 已就绪，刷新后可设为当前版本`
                : (next.error ?? '获取失败'),
            )
          }
        })
        .catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [runningId, refresh, notify])

  const copy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      window.setTimeout(() => setCopied(''), 1600)
    } catch {
      notify('err', '浏览器不允许写剪贴板，请手动选中复制')
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
    // 404 不是「后端没起来」，别拿通用错误页误导人
    const unknown = (error ?? '').includes('没有这个内核')
    return (
      <PageShell>
        {unknown ? (
          <div className="flex h-[60vh] flex-col items-center justify-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl bg-[#f1f1f3] text-[var(--ink-500)]">
              <IconKernel size={20} />
            </span>
            <p className="text-[13px] text-[var(--ink-700)]">没有这个内核引擎</p>
            <p className="text-[12px] text-[var(--ink-400)]">
              只支持 CloakBrowser、Camoufox、fingerprint-chromium、ungoogled-chromium 四套
              {slug ? `，收到的是「${slug}」` : ''}
            </p>
            <Link to="/kernels" className="btn-dark !h-8 !px-4 !text-[12px]">
              返回内核管理
            </Link>
          </div>
        ) : (
          <ErrorState message={error ?? '引擎详情加载失败'} onRetry={reload} />
        )}
      </PageShell>
    )
  }

  const { card, profile } = data

  const elapsedSec =
    job && job.status === 'running' && startedAt > 0
      ? Math.max(0, Math.floor((nowMs - startedAt) / 1000))
      : 0
  const elapsedText =
    elapsedSec >= 60
      ? `${Math.floor(elapsedSec / 60)} 分 ${elapsedSec % 60} 秒`
      : `${elapsedSec} 秒`

  const install = async (version: string, pkg: EnginePackage) => {
    setBusy(version)
    try {
      const created = await endpoints.installKernel(slug, {
        version,
        os: pkg.os === 'any' ? undefined : pkg.os,
        arch: pkg.arch === 'any' ? undefined : pkg.arch,
      })
      setJob(created)
      setStartedAt(Date.now())
      setNowMs(Date.now())
      notify('ok', `已开始获取 ${version}（${KIND_LABEL[created.kind] ?? created.kind}）`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '获取失败')
    } finally {
      setBusy('')
    }
  }

  const activate = async (version: string) => {
    setBusy(version)
    try {
      await endpoints.switchKernelVersion(card.id, version)
      refresh()
      notify('ok', `当前版本已切到 ${version}，旧版本目录保留，老实例需要批量迁移才会跟进`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '切换版本失败')
    } finally {
      setBusy('')
    }
  }

  const makePrimary = async () => {
    if (card.is_primary) return
    setBusy('primary')
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

  return (
    <PageShell>
      <div className="flex items-center gap-2 text-[12px] text-[var(--ink-400)]">
        <Link
          to="/kernels"
          className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 hover:bg-[#f4f4f5] hover:text-[var(--ink-700)]"
        >
          <IconArrowLeft size={13} />
          内核管理
        </Link>
        <span>/</span>
        <span className="text-[var(--ink-700)]">{profile?.name ?? card.name}</span>
      </div>

      <Hero
        card={card}
        profile={profile}
        installedCount={data.versions.filter((v) => v.installed).length}
        onPrimary={makePrimary}
        busy={busy === 'primary'}
      />

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

      {job && (
        <div className="mt-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3">
          <div className="flex items-center gap-2 text-[12px]">
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
                job.status === 'success'
                  ? 'bg-emerald-50 text-emerald-600'
                  : job.status === 'failed'
                    ? 'bg-rose-50 text-rose-600'
                    : 'bg-blue-50 text-blue-600'
              }`}
            >
              {job.status === 'success' ? (
                <IconCheck size={12} />
              ) : job.status === 'failed' ? (
                <IconAlert size={12} />
              ) : (
                <IconCloudDown size={12} />
              )}
            </span>
            <span className="font-medium text-[var(--ink-900)]">
              {job.version} · {KIND_LABEL[job.kind] ?? job.kind}
            </span>
            <span className="tnum text-[var(--ink-500)]">{Math.round(job.progress * 100)}%</span>
            <span className="min-w-0 flex-1 truncate text-[var(--ink-500)]">
              {job.error ?? job.message}
            </span>
            {job.status === 'running' && startedAt > 0 && (
              <span className="tnum shrink-0 text-[10.5px] text-[var(--ink-400)]">
                已运行 {elapsedText}
              </span>
            )}
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
          {job.status === 'running' && job.progress >= 0.05 && job.progress < 0.7 && (
            <p className="mt-1.5 text-[10.5px] text-[var(--ink-400)]">
              500MB 以上的包要下十几分钟；后端用 16 条连接抓取，单条连接会被限速到 30 KB/s
            </p>
          )}
        </div>
      )}

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_306px] items-start gap-4">
        <div className="space-y-4">
          {profile && <IntroCard profile={profile} />}

          <VersionCard
            versionCount={data.versions.length}
            versions={data.versions}
            hint={data.install_hint}
            busy={busy}
            runningVersion={job?.status === 'running' ? job.version : null}
            onInstall={install}
            onActivate={activate}
          />

          {profile && profile.install_notes.length > 0 && (
            <Card className="p-5">
              <CardTitle icon={<IconInfo size={13} />} title="安装注意" />
              <ul className="mt-3 space-y-1.5">
                {profile.install_notes.map((note, index) => (
                  <li key={index} className="flex gap-2 text-[12px] leading-relaxed text-[var(--ink-700)]">
                    <span className="mt-[7px] size-[3.5px] shrink-0 rounded-full bg-[var(--ink-400)]" />
                    <span className="min-w-0 flex-1">
                      <InlineMarkdown text={note} />
                    </span>
                  </li>
                ))}
              </ul>
              {data.versions.length > 0 && (
                <>
                  <div className="mt-3.5 text-[11px] text-[var(--ink-400)]">
                    手动放进来的版本也要落在这个位置，才会被扫描到
                  </div>
                  <div className="mt-1.5 flex items-center gap-2 rounded-xl bg-[#fafafa] px-3 py-2">
                    <code className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-[var(--ink-700)]">
                      {`${card.disk_path}\\<版本号>\\`}
                    </code>
                    <button
                      type="button"
                      onClick={() => copy(`${card.disk_path}\\${data.versions[0].version}\\`, 'cmd')}
                      className="shrink-0 text-[var(--ink-400)] hover:text-[var(--ink-700)]"
                      title="复制目录"
                    >
                      {copied === 'cmd' ? <IconCheck size={12} /> : <IconClipboard size={12} />}
                    </button>
                  </div>
                </>
              )}
            </Card>
          )}

          {data.docs && (
            <Card className="p-5">
              <CardTitle
                icon={<IconBox size={13} />}
                title="引擎文档"
                extra={<span className="font-mono text-[10px] text-[var(--ink-400)]">{data.docs_path}</span>}
              />
              <div className="mt-3">
                <Markdown text={data.docs} />
              </div>
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <DiskCard
            card={card}
            installedCount={data.versions.filter((v) => v.installed).length}
            knownCount={data.versions.length}
          />
          <LinkCard profile={profile} fallback={card} />
          {!data.profile_ok && (
            <Card className="p-4">
              <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-rose-600">
                <IconAlert size={12} />
                档案读取失败
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--ink-500)]">
                {data.profile_error ?? 'engine.json 有问题'}。磁盘状态仍然可用，补齐档案后刷新即可。
              </p>
            </Card>
          )}
        </aside>
      </div>
    </PageShell>
  )
}

function CardTitle({
  icon,
  title,
  extra,
}: {
  icon: React.ReactNode
  title: string
  extra?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="flex size-6 items-center justify-center rounded-lg bg-[#f4f4f5] text-[var(--ink-500)]">
        {icon}
      </span>
      <h3 className="text-[13px] font-semibold tracking-tight text-[var(--ink-900)]">{title}</h3>
      {extra && <span className="ml-auto min-w-0 truncate">{extra}</span>}
    </div>
  )
}

function Hero({
  card,
  profile,
  installedCount,
  onPrimary,
  busy,
}: {
  card: KernelCard
  profile: EngineProfile | null
  installedCount: number
  onPrimary: () => void
  busy: boolean
}) {
  const tagline = profile?.tagline ?? card.tagline
  const links = profile?.links ?? []

  return (
    <div className="mt-3 flex items-start justify-between gap-5 rounded-2xl border border-[var(--line)] bg-white p-5">
      <div className="flex min-w-0 items-start gap-3.5">
        <span
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${
            toneTile[profile?.tone ?? card.tone] ?? toneTile.sky
          }`}
        >
          <IconKernel size={19} />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <h1 className="text-[20px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
              {profile?.name ?? card.name}
            </h1>
            {card.is_primary && (
              <span className="chip bg-[#18181b] px-1.5 text-[10px] text-white">
                <IconStarFilled size={9} />
                主力
              </span>
            )}
            <span className="chip border border-[var(--line)] bg-white text-[10px] text-[var(--ink-500)]">
              {profile?.engine ?? card.engine}
            </span>
            <span className="text-[10.5px] text-[var(--ink-400)]">
              {card.channel} · {card.arch}
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">{tagline ?? '—'}</p>
          {profile?.detection_level && (
            <p className="mt-1 text-[11px] text-[var(--ink-400)]">
              反检测层级：{profile.detection_level}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <div className="flex items-center gap-2">
          {links[0] && (
            <a href={links[0].url} target="_blank" rel="noreferrer" className="btn-ghost !h-7 !px-3 !text-[11.5px]">
              {links[0].label}
              <IconArrowUpRight size={11} />
            </a>
          )}
          <button
            type="button"
            onClick={onPrimary}
            disabled={card.is_primary || busy}
            className={`btn-ghost !h-7 !px-3 !text-[11.5px] disabled:cursor-default disabled:opacity-50`}
          >
            <IconStarFilled size={11} />
            {card.is_primary ? '当前主力' : '设为主力'}
          </button>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-[var(--ink-400)]">
          <span className="tnum">{installedCount} 个版本已落盘</span>
          <span className="h-3 w-px bg-[var(--line)]" />
          <span className="tnum">{card.instance_count} 台实例</span>
          {card.stale_count > 0 && (
            <span className="tnum text-amber-600">{card.stale_count} 台待迁移</span>
          )}
        </div>
      </div>
    </div>
  )
}

function IntroCard({ profile }: { profile: EngineProfile }) {
  return (
    <Card className="p-5">
      {profile.best_for && (
        <div className="rounded-xl bg-[#fafafa] px-3.5 py-3">
          <div className="text-[10.5px] text-[var(--ink-400)]">适合什么场景</div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--ink-700)]">
            <InlineMarkdown text={profile.best_for} />
          </p>
        </div>
      )}

      <div className="mt-3.5 grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-emerald-700">
            <IconCheckCircle size={12} />
            优势
          </div>
          <ul className="mt-2 space-y-1.5">
            {profile.pros.map((item, index) => (
              <li key={index} className="flex gap-2 text-[12px] leading-relaxed text-[var(--ink-700)]">
                <IconCheck size={11} className="mt-[4px] shrink-0 text-emerald-500" />
                <span className="min-w-0 flex-1">
                  <InlineMarkdown text={item} />
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-rose-600">
            <IconAlert size={12} />
            劣势
          </div>
          <ul className="mt-2 space-y-1.5">
            {profile.cons.map((item, index) => (
              <li key={index} className="flex gap-2 text-[12px] leading-relaxed text-[var(--ink-700)]">
                <IconX size={11} className="mt-[4px] shrink-0 text-rose-400" />
                <span className="min-w-0 flex-1">
                  <InlineMarkdown text={item} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  )
}

function VersionCard({
  versions,
  versionCount,
  hint,
  busy,
  runningVersion,
  onInstall,
  onActivate,
}: {
  versions: EngineVersionView[]
  versionCount: number
  hint: string | null
  busy: string
  runningVersion: string | null
  onInstall: (version: string, pkg: EnginePackage) => void
  onActivate: (version: string) => void
}) {
  return (
    <Card className="p-5">
      <CardTitle
        icon={<IconDownload size={13} />}
        title="可获取的版本"
        extra={
          <span className="text-[10.5px] text-[var(--ink-400)]">
            档案登记 {versionCount} 个 · 以页面选择为准
          </span>
        }
      />

      {hint && <p className="mt-2 text-[11px] text-[var(--ink-400)]">{hint}</p>}

      {versions.length === 0 ? (
        <div className="py-10 text-center text-[12px] text-[var(--ink-400)]">
          档案里还没登记可下载的版本
        </div>
      ) : (
        <div className="mt-3 space-y-2.5">
          {versions.map((item) => (
            <VersionBlock
              key={item.version}
              item={item}
              busy={busy === item.version}
              running={runningVersion === item.version}
              onInstall={onInstall}
              onActivate={() => onActivate(item.version)}
            />
          ))}
        </div>
      )}
    </Card>
  )
}

function VersionBlock({
  item,
  busy,
  running,
  onInstall,
  onActivate,
}: {
  item: EngineVersionView
  busy: boolean
  running: boolean
  onInstall: (version: string, pkg: EnginePackage) => void
  onActivate: () => void
}) {
  const [os, setOs] = useState<string>(() => item.packages[0]?.os ?? 'any')
  const platforms = useMemo(() => {
    const seen: string[] = []
    item.packages.forEach((pkg) => {
      if (!seen.includes(pkg.os)) seen.push(pkg.os)
    })
    return seen
  }, [item.packages])

  const pkg = useMemo(
    () =>
      item.packages.find((p) => p.os === os) ??
      item.packages.find((p) => p.os === 'any') ??
      item.packages[0],
    [item.packages, os],
  )

  const manual = !pkg || pkg.kind === 'manual'

  return (
    <div className="rounded-xl border border-[var(--line)] px-3.5 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="tnum text-[13px] font-semibold text-[var(--ink-900)]">
              {item.version}
            </span>
            {item.is_current && (
              <span className="chip bg-emerald-50 text-[10px] text-emerald-600">当前生效</span>
            )}
            {item.installed ? (
              <span className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">
                已落盘{item.installed_size ? ` · ${item.installed_size}` : ''}
              </span>
            ) : (
              <span className="chip bg-zinc-100 text-[10px] text-zinc-500">未下载</span>
            )}
            {item.channel && (
              <span className="text-[10px] text-[var(--ink-400)]">{item.channel} 通道</span>
            )}
            {item.released_at && (
              <span className="tnum text-[10px] text-[var(--ink-400)]">发布于 {item.released_at}</span>
            )}
            {item.on_disk_only && (
              <span className="chip bg-amber-50 text-[10px] text-amber-600">档案未登记</span>
            )}
          </div>
          <div className="mt-1 text-[11px] text-[var(--ink-500)]">
            {item.base ?? '—'}
            {item.notes && (
              <>
                {' · '}
                <InlineMarkdown text={item.notes} />
              </>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {item.installed && !item.is_current && (
            <button
              type="button"
              disabled={busy}
              onClick={onActivate}
              className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:opacity-50"
            >
              设为当前
            </button>
          )}
          {!item.installed &&
            (manual ? (
              pkg?.url && (
                <a
                  href={pkg.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8]"
                >
                  打开下载页
                  <IconArrowUpRight size={10} />
                </a>
              )
            ) : (
              <button
                type="button"
                disabled={busy || running}
                onClick={() => pkg && onInstall(item.version, pkg)}
                className="inline-flex h-7 items-center gap-1 rounded-full bg-[#18181b] px-3 text-[11px] font-medium text-white transition-colors hover:bg-black disabled:opacity-50"
              >
                <IconCloudDown size={11} />
                {busy || running ? '获取中…' : pkg?.kind === 'pip' ? '安装' : '下载'}
              </button>
            ))}
        </div>
      </div>

      {item.packages.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-2">
          {platforms.length > 1 ? (
            <div className="flex items-center gap-1">
              {platforms.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setOs(name)}
                  className={`inline-flex h-6 items-center rounded-full px-2 text-[10.5px] font-medium transition-colors ${
                    name === os
                      ? 'bg-[#18181b] text-white'
                      : 'bg-[#f4f4f5] text-[var(--ink-500)] hover:bg-[#e9e9ec]'
                  }`}
                >
                  {OS_LABEL[name] ?? name}
                </button>
              ))}
            </div>
          ) : (
            <span className="text-[10.5px] text-[var(--ink-400)]">{OS_LABEL[os] ?? os}</span>
          )}
          <span className="text-[10.5px] text-[var(--ink-400)]">
            {[pkg?.arch && pkg.arch !== 'any' ? pkg.arch : '', pkg?.size ?? '']
              .filter(Boolean)
              .join(' · ')}
          </span>
          <span className="chip bg-[#f4f4f5] px-1.5 text-[10px] text-[var(--ink-500)]">
            {KIND_LABEL[pkg?.kind ?? 'manual'] ?? pkg?.kind}
          </span>
          {pkg?.sha256 ? (
            <span className="chip bg-emerald-50 px-1.5 text-[10px] text-emerald-600">sha256 已登记</span>
          ) : (
            <span
              className="chip bg-zinc-100 px-1.5 text-[10px] text-zinc-500"
              title="上游没公示校验值，下载后不会核对"
            >
              未校验
            </span>
          )}
          {pkg?.url && (
            <a
              href={pkg.url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto inline-flex items-center gap-0.5 text-[10.5px] text-[var(--ink-400)] hover:text-[var(--ink-700)]"
            >
              原始地址
              <IconArrowUpRight size={10} />
            </a>
          )}
        </div>
      )}

      {pkg?.note && (
        <div className="mt-1.5 text-[10.5px] text-[var(--ink-400)]">
          <InlineMarkdown text={pkg.note} />
        </div>
      )}
    </div>
  )
}

function DiskCard({
  card,
  installedCount,
  knownCount,
}: {
  card: KernelCard
  installedCount: number
  knownCount: number
}) {
  return (
    <Card className="p-4">
      <CardTitle
        icon={<IconMonitor size={13} />}
        title="磁盘状态"
        extra={
          <span
            className={`chip ${
              card.downloaded ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'
            }`}
          >
            {card.downloaded ? '已安装' : '未安装'}
          </span>
        }
      />

      <div className="mt-3 rounded-xl bg-[#fafafa] px-3 py-2.5">
        <div className="text-[10.5px] text-[var(--ink-400)]">当前生效版本</div>
        <div className="mt-0.5 flex items-baseline gap-1.5">
          <span
            className={`tnum text-[16px] leading-none font-semibold ${
              card.downloaded ? 'text-[var(--ink-900)]' : 'text-[var(--ink-400)]'
            }`}
          >
            {card.current_version ?? '—'}
          </span>
          {!card.downloaded && card.current_version && (
            <span className="text-[10px] text-rose-500">磁盘缺失</span>
          )}
        </div>
      </div>

      <dl className="mt-3 space-y-1.5 text-[11.5px]">
        <Row label="磁盘最新" value={card.latest_version ?? '—'} />
        <Row
          label="已落盘版本"
          value={installedCount > 0 ? `${installedCount} 个` : `0 个（档案登记 ${knownCount}）`}
          tone={installedCount === 0 ? 'muted' : undefined}
        />
        <Row label="绑定实例" value={`${card.instance_count} 台`} />
        <Row
          label="待迁移"
          value={card.stale_count > 0 ? `${card.stale_count} 台仍在旧版本` : '无'}
          tone={card.stale_count > 0 ? 'warn' : undefined}
        />
        <Row label="最近扫描" value={card.scanned_at} />
      </dl>

      <div className="mt-3 flex items-start gap-1.5 border-t border-[var(--line)] pt-2.5 text-[10.5px] text-[var(--ink-400)]">
        <IconBox size={11} className="mt-[1px] shrink-0" />
        <span className="min-w-0 font-mono break-words">
          {/* 按反斜杠切开再加 wbr：只在路径分隔符处换行，不会把 camoufox 断成 c/amoufox */}
          {card.disk_path.split(/(?<=\\)/).map((part, index) => (
            <span key={index}>
              {part}
              <wbr />
            </span>
          ))}
        </span>
      </div>
    </Card>
  )
}

function Row({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'warn' | 'muted'
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="shrink-0 text-[var(--ink-400)]">{label}</dt>
      <dd
        className={`tnum min-w-0 truncate text-right ${
          tone === 'warn'
            ? 'text-amber-600'
            : tone === 'muted'
              ? 'text-[var(--ink-400)]'
              : 'text-[var(--ink-700)]'
        }`}
      >
        {value}
      </dd>
    </div>
  )
}

function LinkCard({ profile, fallback }: { profile: EngineProfile | null; fallback: KernelCard }) {
  const links = profile?.links?.length
    ? profile.links
    : [
        ...(fallback.repo_url
          ? [{ label: 'GitHub 源仓库', url: fallback.repo_url, kind: 'release' as const }]
          : []),
        ...(fallback.mirror_url
          ? [{ label: 'Gitee 镜像', url: fallback.mirror_url, kind: 'mirror' as const }]
          : []),
      ]

  return (
    <Card className="p-4">
      <CardTitle icon={<IconArrowUpRight size={13} />} title="下载源与文档" />
      {links.length === 0 ? (
        <p className="mt-3 text-[11px] text-[var(--ink-400)]">档案里没有登记外链</p>
      ) : (
        <ul className="mt-2.5 space-y-1">
          {links.map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[11.5px] text-[var(--ink-700)] transition-colors hover:bg-[#f7f7f8]"
              >
                <span className="chip shrink-0 bg-[#f4f4f5] px-1.5 text-[9.5px] text-[var(--ink-500)]">
                  {LINK_LABEL[link.kind] ?? link.kind}
                </span>
                <span className="min-w-0 flex-1 truncate">{link.label}</span>
                <IconArrowUpRight size={10} className="shrink-0 text-[var(--ink-400)]" />
              </a>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex items-center gap-1 text-[10px] text-[var(--ink-400)]">
        <IconRefresh size={10} />
        档案随仓库更新，改完刷新本页即可
      </div>
    </Card>
  )
}
