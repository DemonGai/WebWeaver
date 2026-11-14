import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { copyText } from '@/lib/clipboard'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, SoftChip, type Tone } from '@/components/ui'
import { IdBadge } from '@/components/IdBadge'
import { Toast, useToast } from '@/components/Toast'
import {
  IconArrowLeft,
  IconArrowUpRight,
  IconBrowser,
  IconMonitor,
  IconPower,
  IconRefresh,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { InstanceStatus, NoVncTarget } from '@/types/domain'

const availability: Record<
  NoVncTarget['availability'],
  { label: string; tone: Tone; title: string }
> = {
  ready: { label: 'noVNC 可用', tone: 'emerald', title: '可以接管' },
  stopped: { label: '待启动', tone: 'blue', title: '实例还没起来' },
  unsupported: { label: '镜像无 noVNC', tone: 'rose', title: '这个镜像没有 noVNC' },
  blocked: { label: '待配置', tone: 'amber', title: '实例还缺内核或镜像' },
}

const meta: Record<InstanceStatus, { label: string; tone: Tone }> = {
  running: { label: '运行中', tone: 'emerald' },
  idle: { label: '空闲', tone: 'blue' },
  error: { label: '异常', tone: 'rose' },
  stopped: { label: '已停止', tone: 'zinc' },
  queued: { label: '排队中', tone: 'amber' },
}

/**
 * 单台实例的 noVNC 画面。
 *
 * 画面本身是 noVNC 自带网页（容器里的 websockify 提供），这里只做「嵌进去 + 给出
 * 周边信息」。地址不在前端拼：端口是实例启动时分配的，能力判定也在后端（镜像
 * 不带 noVNC 时进去只会白屏，那种情况这里直接给出原因）。
 */
export default function NoVncPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data, status, error, reload } = useApi(() => endpoints.novncTarget(id), [id])
  // iframe 的 src 不变时 reload 不会重新连接，用 key 强制重建
  const [nonce, setNonce] = useState(0)
  const { toast, notify, dismiss } = useToast()

  const copyId = async () => {
    const ok = await copyText(id)
    notify(ok ? 'ok' : 'err', ok ? '实例 ID 已复制' : '复制失败')
  }

  if (status === 'loading') {
    return (
      <PageShell>
        <Loading />
      </PageShell>
    )
  }
  if (status === 'error') {
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  }
  if (!data) return null

  const state = meta[data.status]

  return (
    <PageShell>
      <PageHeader
        icon={<IconMonitor size={19} />}
        title={data.name}
        subtitle={
          data.ready
            ? 'noVNC 实时接管 · 画面来自容器内的 websockify，关掉页面不会结束会话'
            : '当前不可接管，下方给出原因与下一步'
        }
        actions={
          <>
            <button type="button" className="btn-ghost" onClick={() => navigate('/novnc')}>
              <IconArrowLeft size={14} />
              返回 noVNC 列表
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setNonce((n) => n + 1)}
              disabled={!data.ready}
            >
              <IconRefresh size={14} />
              重载画面
            </button>
            {data.url && (
              <a className="btn-dark" href={data.url} target="_blank" rel="noreferrer">
                <IconArrowUpRight size={14} />
                新窗口打开
              </a>
            )}
          </>
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <IdBadge id={data.id} onCopy={copyId} />
        <SoftChip tone={state.tone}>{state.label}</SoftChip>
        <SoftChip tone={availability[data.availability].tone}>
          {availability[data.availability].label}
        </SoftChip>
        {data.kernel && (
          <SoftChip tone="zinc">
            {data.kernel}
            {data.kernel_version ? ` · ${data.kernel_version}` : ''}
          </SoftChip>
        )}
        {data.port && <span className="tnum text-[11px] text-[var(--ink-400)]">端口 {data.port}</span>}
      </div>

      <Card className="overflow-hidden">
        {data.ready && data.url ? (
          <iframe
            key={nonce}
            src={data.url}
            title={`${data.name} 的 noVNC 画面`}
            className="h-[calc(100vh-300px)] min-h-[520px] w-full border-0 bg-[#f7f7f8]"
            allow="clipboard-read; clipboard-write; fullscreen"
          />
        ) : (
          <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 px-6 py-16 text-center">
            <span className="flex size-12 items-center justify-center rounded-2xl bg-[#f4f4f5] text-[var(--ink-400)]">
              {data.availability === 'stopped' ? <IconPower size={20} /> : <IconX size={20} />}
            </span>
            <div>
              <p className="text-[14px] font-medium text-[var(--ink-900)]">
                {availability[data.availability].title}
              </p>
              <p className="mt-1 max-w-[420px] text-[12px] leading-relaxed text-[var(--ink-500)]">
                {data.reason ?? '暂时拿不到画面地址'}
              </p>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => navigate('/browsers')}
              >
                <IconBrowser size={13} />
                回浏览器池处理
              </button>
              <button type="button" className="btn-ghost" onClick={reload}>
                <IconRefresh size={13} />
                重新检测
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 p-4 md:grid-cols-3 xl:grid-cols-6">
        <Field label="内核">{data.kernel ?? '未绑定'}</Field>
        <Field label="版本">{data.kernel_version ?? '—'}</Field>
        <Field label="绑定账号">{data.account}</Field>
        <Field label="出口 IP">{data.ip}</Field>
        <Field label="分组">{data.group}</Field>
        <Field label="镜像" title={data.image ?? ''}>
          {data.image ?? '—'}
        </Field>
      </Card>

      <p className="mt-3 text-[11px] text-[var(--ink-400)]">
        找不到画面？先确认实例在运行中，再核对镜像是否带 noVNC；
        <Link to="/novnc" className="ml-1 text-[var(--ink-700)] underline underline-offset-2">
          回到列表看全部实例
        </Link>
        。
      </p>

      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
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
      <div className="text-[10.5px] text-[var(--ink-400)]">{label}</div>
      <div className="mt-1 truncate text-[12px] font-medium text-[var(--ink-700)]" title={title}>
        {children}
      </div>
    </div>
  )
}
