import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageShell } from '@/components/Layout'
import { Card, ProgressBar } from '@/components/ui'
import { Markdown } from '@/components/Markdown'
import {
  IconAlert,
  IconArrowLeft,
  IconArrowUpRight,
  IconBox,
  IconCheck,
  IconClipboard,
  IconCloudDown,
  IconPlay,
  IconDownload,
  IconInfo,
  IconKernel,
  IconMonitor,
  IconRefresh,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import { Toast, useToast } from '@/components/Toast'
import type { InstallJob, KernelCard, KernelVersion } from '@/types/domain'

const toneTile: Record<string, string> = {
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-zinc-100 text-zinc-500',
  sky: 'bg-sky-50 text-sky-600',
  dark: 'bg-[#18181b] text-white',
}

export default function KernelDetailPage() {
  const { slug = '' } = useParams()
  const { data, status, error, reload, refresh } = useApi(
    () => endpoints.kernelDetail(slug),
    [slug],
  )

  const [job, setJob] = useState<InstallJob | null>(null)
  const [busy, setBusy] = useState('')
  const { toast, notify, dismiss } = useToast()
  const [copied, setCopied] = useState('')
  const [customTag, setCustomTag] = useState('')

  // 进页面捡回正在跑的任务：刷新或离开再回来，后端那个拉取还在跑
  useEffect(() => {
    let cancelled = false
    endpoints
      .installJobs()
      .then((list) => {
        if (cancelled) return
        const mine = list.find((item) => item.slug === slug && item.status === 'running')
        if (mine) setJob(mine)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [slug])

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
              next.status === 'success' ? `${next.version} 镜像已就绪` : (next.error ?? '拉取失败'),
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
          <ErrorState message={error ?? '内核详情加载失败'} onRetry={reload} />
        )}
      </PageShell>
    )
  }

  const { card } = data

  const pull = async (tag?: string) => {
    setBusy(tag ?? 'pull')
    try {
      const created = await endpoints.installKernel(slug, tag ? { tag } : {})
      setJob(created)
      notify('ok', `开始拉取 ${created.image_ref}`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '拉取失败')
    } finally {
      setBusy('')
    }
  }

  const activate = async (version: string) => {
    setBusy(version)
    try {
      await endpoints.switchKernelVersion(card.id, version)
      refresh()
      notify('ok', `当前版本已切到 ${version}，旧镜像保留，老实例需要批量迁移才会跟进`)
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '切换版本失败')
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
        <span className="text-[var(--ink-700)]">{card.name}</span>
      </div>

      <Hero card={card} />

      {!data.docker_ok && (
        <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800">
          <IconAlert size={13} className="mt-[2px] shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-medium">Docker 不可用，读不到本地镜像</div>
            <div className="mt-0.5 text-[11px] text-amber-700">
              {data.docker_error ?? '请确认 Docker 已启动，并且 docker 命令在 PATH 里'}
            </div>
          </div>
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
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--ink-700)]">
              {job.image_ref}
            </span>
            <span className="tnum shrink-0 text-[var(--ink-500)]">
              {Math.round(job.progress * 100)}%
            </span>
            <span className="min-w-0 max-w-[40%] truncate text-[11px] text-[var(--ink-500)]">
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
          {job.status === 'running' && (
            <p className="mt-1.5 text-[10.5px] text-[var(--ink-400)]">
              压缩层通常 500MB 左右，取决于上行带宽；进度按已完成层数估算
            </p>
          )}
        </div>
      )}

      {!card.supported ? (
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_306px] items-start gap-4">
          <Card className="p-8">
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-[#f4f4f5] text-[var(--ink-400)]">
                <IconKernel size={22} />
              </span>
              <p className="text-[14px] font-semibold text-[var(--ink-700)]">暂未支持，敬请期待</p>
              <p className="max-w-[420px] text-[12px] leading-relaxed text-[var(--ink-500)]">
                {card.unsupported_reason ?? '这个内核暂时还没有做容器镜像。'}
              </p>
              <p className="max-w-[420px] text-[12px] leading-relaxed text-[var(--ink-400)]">
                镜像做好后会在这里出现「获取内核」入口，不需要改任何配置。
              </p>
              <p className="mt-1 text-[11px] text-[var(--ink-400)]">
                当前支持：CloakBrowser、fingerprint-chromium、ungoogled-chromium
              </p>
            </div>
          </Card>
          <aside className="space-y-4">
            <RepoCard card={card} />
          </aside>
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_306px] items-start gap-4">
          <div className="space-y-4">
            <VersionCard
              card={card}
              versions={data.versions}
              hint={data.hint}
              busy={busy}
              runningVersion={job?.status === 'running' ? job.tag : null}
              customTag={customTag}
              onCustomTag={setCustomTag}
              onPull={pull}
              onActivate={activate}
            />

            {data.run_command && (
              <Card className="p-5">
                <CardTitle
                  icon={<IconPlay size={13} />}
                  title="运行方式"
                  extra={
                    <button
                      type="button"
                      onClick={() => copy(data.run_command as string, 'run')}
                      className="inline-flex items-center gap-1 text-[10.5px] text-[var(--ink-400)] hover:text-[var(--ink-700)]"
                    >
                      {copied === 'run' ? <IconCheck size={11} /> : <IconClipboard size={11} />}
                      复制
                    </button>
                  }
                />
                <pre className="mt-3 overflow-x-auto rounded-xl bg-[#18181b] px-3.5 py-3 font-mono text-[11px] leading-relaxed text-[#e4e4e7]">
                  {data.run_command}
                </pre>
                <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
                  端口按内核固定分配，三个内核可以同时跑。<code className="font-mono">MODE=headless</code>{' '}
                  只开 CDP，纯服务端部署更省资源。
                </p>
              </Card>
            )}

            {data.docs && (
              <Card className="p-5">
                <CardTitle
                  icon={<IconBox size={13} />}
                  title="引擎文档"
                  extra={
                    <span className="font-mono text-[10px] text-[var(--ink-400)]">
                      browser_engine/{card.slug}/README.md
                    </span>
                  }
                />
                <div className="mt-3">
                  <Markdown text={data.docs} />
                </div>
              </Card>
            )}
          </div>

          <aside className="space-y-4">
            <ImageCard card={card} />
            <RepoCard card={card} />
            <Card className="p-4">
              <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-[var(--ink-700)]">
                <IconInfo size={12} />
                镜像从哪来
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--ink-500)]">
                页面只做 <code className="font-mono">docker pull</code>，不从上游下载二进制。
                换仓库改后端{' '}
                <code className="font-mono text-[10.5px]">kernel_image_registry</code> 即可。
              </p>
            </Card>
          </aside>
        </div>
      )}
      <Toast toast={toast} onClose={dismiss} />
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

function Hero({ card }: { card: KernelCard }) {
  return (
    <div className="mt-3 flex items-start justify-between gap-5 rounded-2xl border border-[var(--line)] bg-white p-5">
      <div className="flex min-w-0 items-start gap-3.5">
        <span
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${
            card.supported ? (toneTile[card.tone] ?? toneTile.sky) : 'bg-[#f4f4f5] text-[var(--ink-400)]'
          }`}
        >
          <IconKernel size={19} />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <h1 className="text-[20px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
              {card.name}
            </h1>
            <span className="chip border border-[var(--line)] bg-white text-[10px] text-[var(--ink-500)]">
              {card.engine}
            </span>
            {!card.supported && (
              <span className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">暂未支持</span>
            )}
            <span className="text-[10.5px] text-[var(--ink-400)]">
              {card.channel} · {card.arch}
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">{card.tagline}</p>
          {card.detection_level && (
            <p className="mt-1 text-[11px] text-[var(--ink-400)]">
              反检测层级：{card.detection_level}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <div className="flex items-center gap-2">
          {card.repo_url && (
            <a
              href={card.repo_url}
              target="_blank"
              rel="noreferrer"
              className="btn-ghost !h-7 !px-3 !text-[11.5px]"
            >
              源仓库
              <IconArrowUpRight size={11} />
            </a>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-[var(--ink-400)]">
          <span className="tnum">
            {card.supported ? `${card.version_count} 个镜像` : '暂无镜像'}
          </span>
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

function VersionCard({
  card,
  versions,
  hint,
  busy,
  runningVersion,
  customTag,
  onCustomTag,
  onPull,
  onActivate,
}: {
  card: KernelCard
  versions: KernelVersion[]
  hint: string | null
  busy: string
  runningVersion: string | null
  customTag: string
  onCustomTag: (value: string) => void
  onPull: (tag?: string) => void
  onActivate: (version: string) => void
}) {
  const rolling = `${card.registry}:${card.slug}`

  return (
    <Card className="p-5">
      <CardTitle
        icon={<IconDownload size={13} />}
        title="本地镜像"
        extra={
          <span className="text-[10.5px] text-[var(--ink-400)]">
            {versions.length} 个版本
            {card.total_size ? ` · ${card.total_size}` : ''}
          </span>
        }
      />

      {hint && <p className="mt-2 text-[11px] text-[var(--ink-400)]">{hint}</p>}

      {versions.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-[12px] text-[var(--ink-500)]">本地还没有这个内核的镜像</p>
          <p className="mt-1 font-mono text-[10.5px] text-[var(--ink-400)]">{rolling}</p>
        </div>
      ) : (
        <div className="mt-3 space-y-2.5">
          {versions.map((item) => (
            <VersionBlock
              key={item.image_ref}
              item={item}
              busy={busy === item.version}
              onActivate={() => onActivate(item.version)}
            />
          ))}
        </div>
      )}

      {/* 拉取 */}
      <div className="mt-3.5 rounded-xl border border-[var(--line)] px-3.5 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[11.5px] font-medium text-[var(--ink-700)]">拉取最新（滚动 tag）</div>
            <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--ink-400)]">
              {rolling}
            </div>
          </div>
          <button
            type="button"
            onClick={() => onPull()}
            disabled={busy !== '' || runningVersion !== null}
            className="btn-dark !h-7 shrink-0 !px-3 !text-[11px] disabled:opacity-60"
          >
            <IconCloudDown size={11} />
            {runningVersion === card.slug ? '拉取中…' : '获取内核'}
          </button>
        </div>

        <div className="mt-3 flex items-center gap-2 border-t border-[var(--line)] pt-3">
          <input
            value={customTag}
            onChange={(event) => onCustomTag(event.target.value)}
            placeholder={`指定 tag，如 ${card.slug}-${card.latest_version ?? '148.0.7778.215'}`}
            className="h-8 min-w-0 flex-1 rounded-lg border border-[var(--line)] bg-white px-2.5 font-mono text-[11px] text-[var(--ink-800)] outline-none placeholder:text-[var(--ink-400)] focus:border-[var(--ink-400)]"
          />
          <button
            type="button"
            onClick={() => onPull(customTag.trim())}
            disabled={!customTag.trim() || busy !== '' || runningVersion !== null}
            className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-[var(--line)] bg-white px-3 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:opacity-40"
          >
            <IconRefresh size={11} />
            拉取
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-[var(--ink-400)]">
          tag 留空时会补上内核前缀；也可以直接粘完整的镜像名。
        </p>
      </div>
    </Card>
  )
}

function VersionBlock({
  item,
  busy,
  onActivate,
}: {
  item: KernelVersion
  busy: boolean
  onActivate: () => void
}) {
  return (
    <div className="rounded-xl border border-[var(--line)] px-3.5 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="tnum text-[13px] font-semibold text-[var(--ink-900)]">
              {item.version}
            </span>
            {item.current && (
              <span className="chip bg-emerald-50 text-[10px] text-emerald-600">当前生效</span>
            )}
            <span className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">
              已就绪{item.size ? ` · ${item.size}` : ''}
            </span>
            {!item.pinned && (
              <span className="chip bg-amber-50 text-[10px] text-amber-600">只有滚动 tag</span>
            )}
            {item.arch && (
              <span className="text-[10px] text-[var(--ink-400)]">{item.arch}</span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[10.5px] text-[var(--ink-500)]">
            <span className="font-mono">{item.image_ref}</span>
            {item.created_at && <span className="tnum">构建于 {item.created_at}</span>}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {item.current ? (
            <span className="inline-flex h-7 items-center rounded-full bg-emerald-50 px-2.5 text-[11px] font-medium text-emerald-600">
              使用中
            </span>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={onActivate}
              className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--line)] bg-white px-2.5 text-[11px] font-medium text-[var(--ink-700)] hover:bg-[#f7f7f8] disabled:opacity-50"
            >
              设为当前
            </button>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-[var(--line)] pt-2">
        <span className="text-[10px] text-[var(--ink-400)]">tag</span>
        {item.tags.map((tag) => (
          <span
            key={tag}
            className={`chip px-1.5 font-mono text-[10px] ${
              tag === item.tag
                ? 'bg-[#18181b] text-white'
                : 'bg-[#f4f4f5] text-[var(--ink-500)]'
            }`}
          >
            {tag}
          </span>
        ))}
        {item.digest && (
          <span
            className="ml-auto font-mono text-[10px] text-[var(--ink-400)]"
            title={item.digest}
          >
            {item.digest.slice(0, 19)}
          </span>
        )}
      </div>
    </div>
  )
}

function ImageCard({ card }: { card: KernelCard }) {
  return (
    <Card className="p-4">
      <CardTitle
        icon={<IconMonitor size={13} />}
        title="镜像状态"
        extra={
          <span
            className={`chip ${
              card.installed ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'
            }`}
          >
            {card.installed ? '已就绪' : '未获取'}
          </span>
        }
      />

      <div className="mt-3 rounded-xl bg-[#fafafa] px-3 py-2.5">
        <div className="text-[10.5px] text-[var(--ink-400)]">当前生效版本</div>
        <div className="mt-0.5 flex items-baseline gap-1.5">
          <span
            className={`tnum text-[16px] leading-none font-semibold ${
              card.installed ? 'text-[var(--ink-900)]' : 'text-[var(--ink-400)]'
            }`}
          >
            {card.current_version ?? '—'}
          </span>
          {!card.installed && (
            <span className="text-[10px] text-[var(--ink-400)]">未获取</span>
          )}
        </div>
        {card.current_ref && (
          <div className="mt-1 truncate font-mono text-[10px] text-[var(--ink-400)]">
            {card.current_ref}
          </div>
        )}
      </div>

      <dl className="mt-3 space-y-1.5 text-[11.5px]">
        <Row label="本地最新" value={card.latest_version ?? '—'} />
        <Row label="镜像版本" value={`${card.version_count} 个`} tone={card.version_count ? undefined : 'muted'} />
        <Row label="占用空间" value={card.total_size ?? '—'} />
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
        <span className="min-w-0 font-mono break-all">
          {card.registry}:{card.slug}
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

function RepoCard({ card }: { card: KernelCard }) {
  const links = [
    ...(card.repo_url ? [{ label: 'GitHub 源仓库', url: card.repo_url }] : []),
    ...(card.mirror_url ? [{ label: 'Gitee 镜像', url: card.mirror_url }] : []),
    { label: 'Docker Hub 镜像仓库', url: `https://hub.docker.com/r/${card.registry}` },
  ]

  return (
    <Card className="p-4">
      <CardTitle icon={<IconArrowUpRight size={13} />} title="来源与文档" />
      <ul className="mt-2.5 space-y-1">
        {links.map((link) => (
          <li key={link.url}>
            <a
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[11.5px] text-[var(--ink-700)] transition-colors hover:bg-[#f7f7f8]"
            >
              <span className="min-w-0 flex-1 truncate">{link.label}</span>
              <IconArrowUpRight size={10} className="shrink-0 text-[var(--ink-400)]" />
            </a>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex items-center gap-1 text-[10px] text-[var(--ink-400)]">
        <IconRefresh size={10} />
        镜像与文档随仓库更新，拉取后刷新本页即可
      </div>
    </Card>
  )
}
