import { useEffect, useMemo, useState } from 'react'
import {
  IconAlert,
  IconCheckCircle,
  IconClipboard,
  IconFingerprint,
  IconPlay,
  IconRefresh,
  IconWrench,
  IconX,
} from '@/components/icons'
import { Checkbox } from '@/components/ui'
import { endpoints } from '@/api/endpoints'
import type {
  FingerprintApplyResult,
  FingerprintDetail,
  FingerprintInstanceRef,
  ProbeState,
} from '@/types/domain'

const PROBE_META: Record<ProbeState, { label: string; className: string; hint: string }> = {
  never: {
    label: '未采集',
    className: 'bg-zinc-100 text-zinc-600',
    hint: '还没起过容器读人格，下面的实测值是空的',
  },
  fresh: {
    label: '已采集',
    className: 'bg-emerald-50 text-emerald-600',
    hint: '实测值与当前参数一致',
  },
  stale: {
    label: '待重采',
    className: 'bg-amber-50 text-amber-600',
    hint: '参数改过了，下面的人格还是上一版算出来的',
  },
  failed: {
    label: '采集失败',
    className: 'bg-rose-50 text-rose-600',
    hint: '上一次采集没成功，实测值可能已经过时',
  },
}

type MaterialTab = 'json' | 'env' | 'args'

/**
 * 指纹详情抽屉。
 *
 * 分三块：实测人格（内核真的算出了什么）、下发物料（写进容器的东西）、
 * 绑定的实例。三块分开是因为它们回答三个不同的问题：像不像真人、
 * 给内核什么、影响了谁。
 */
export function FingerprintDrawer({
  detail,
  instances,
  busy,
  onClose,
  onProbe,
  onEdit,
  onChanged,
  notify,
}: {
  detail: FingerprintDetail
  instances: FingerprintInstanceRef[]
  busy: boolean
  onClose: () => void
  onProbe: () => void
  onEdit: () => void
  onChanged: () => void
  notify: (tone: 'ok' | 'err', text: string) => void
}) {
  const [tab, setTab] = useState<MaterialTab>('json')
  const [picked, setPicked] = useState<string[]>([])
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState<FingerprintApplyResult | null>(null)

  useEffect(() => {
    // 换一条指纹时把上一次的应用结果清掉，否则会串到新记录上
    setResult(null)
    setPicked([])
  }, [detail.id])

  const meta = PROBE_META[detail.probe_state]
  const material = useMemo(() => {
    const render = detail.render
    if (!render) return ''
    if (tab === 'json') return JSON.stringify(render.payload, null, 2)
    if (tab === 'env') {
      return Object.entries(render.env)
        .map(([key, value]) => `-e ${key}=${value}`)
        .join(' \\\n  ')
    }
    return render.args.join(' \\\n  ')
  }, [detail.render, tab])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(material)
      notify('ok', '已复制到剪贴板')
    } catch {
      notify('err', '浏览器不允许写剪贴板，请手动选中复制')
    }
  }

  const apply = async () => {
    if (picked.length === 0) return
    setApplying(true)
    try {
      const res = await endpoints.applyFingerprint(detail.id, picked)
      setResult(res)
      if (res.ok) notify('ok', `已下发到 ${res.succeeded} 台实例`)
      else notify('err', `${res.failed} 台下发失败，看下面的原因`)
      onChanged()
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '下发失败')
    } finally {
      setApplying(false)
    }
  }

  const bound = detail.instances.length > 0
  const candidates = instances

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/25 backdrop-blur-[1px]">
      <button type="button" aria-label="关闭" className="flex-1" onClick={onClose} />
      <aside className="flex h-full w-full max-w-[620px] flex-col bg-white shadow-[-16px_0_48px_-16px_rgba(16,24,40,0.24)]">
        {/* 头部 */}
        <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#18181b] text-white">
              <IconFingerprint size={15} />
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate text-[14px] font-semibold text-[var(--ink-900)]">
                  {detail.name}
                </h2>
                <span
                  className={`chip shrink-0 ${
                    detail.supported
                      ? 'bg-emerald-50 text-emerald-600'
                      : 'bg-rose-50 text-rose-600'
                  }`}
                >
                  {detail.supported ? '可下发' : '不支持'}
                </span>
                {detail.pseudo_mobile && (
                  <span className="chip shrink-0 bg-amber-50 text-amber-600">伪移动</span>
                )}
              </div>
              <p className="mt-0.5 font-mono text-[11px] text-[var(--ink-400)]">
                {detail.fp_id} · {detail.kernel ?? '未绑定内核'}
                {detail.seed != null && ` · seed ${detail.seed}`}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="icon-btn size-7 shrink-0 text-[var(--ink-400)]"
            aria-label="关闭"
          >
            <IconX size={14} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {detail.unsupported_reason && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[11.5px] text-rose-700">
              <span className="mt-0.5 shrink-0">
                <IconAlert size={12} />
              </span>
              <span>{detail.unsupported_reason}</span>
            </div>
          )}

          {detail.pseudo_mobile_note && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-[11.5px] text-amber-700">
              <span className="mt-0.5 shrink-0">
                <IconAlert size={12} />
              </span>
              <span>{detail.pseudo_mobile_note}</span>
            </div>
          )}

          {/* 实测人格 */}
          <Section
            title="实测人格"
            extra={
              <div className="flex items-center gap-2">
                <span className={`chip ${meta.className}`}>{meta.label}</span>
                <button
                  type="button"
                  onClick={onProbe}
                  disabled={busy || !detail.supported}
                  className="btn-ghost !h-7 !px-2 !text-[11px]"
                >
                  <IconRefresh size={11} />
                  {busy ? '采集中…' : '采集'}
                </button>
              </div>
            }
          >
            {detail.probe_state === 'never' && (
              <p className="text-[11.5px] text-[var(--ink-400)]">
                {meta.hint}。点「采集」会起一个临时容器按当前种子跑一遍，
                约两秒后把 UA、显卡、分辨率读回来。
              </p>
            )}

            {detail.probe_error && (
              <p className="mb-2 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] text-rose-700">
                {detail.probe_error}
              </p>
            )}

            {detail.probe_state === 'stale' && (
              <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-[11.5px] text-amber-700">
                {meta.hint}，建议重新采集。
              </p>
            )}

            {detail.warnings.length > 0 && (
              <ul className="mb-2 space-y-1">
                {detail.warnings.map((warning) => (
                  <li
                    key={warning}
                    className="flex items-start gap-1.5 rounded-lg bg-rose-50 px-3 py-1.5 text-[11.5px] text-rose-700"
                  >
                    <span className="mt-0.5 shrink-0">
                      <IconAlert size={11} />
                    </span>
                    {warning}
                  </li>
                ))}
              </ul>
            )}

            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
              <Row label="显卡" value={detail.gpu ?? '—'} mono />
              <Row label="分辨率" value={detail.resolution || '—'} />
              <Row label="DPR" value={detail.dpr || '—'} />
              <Row label="Canvas" value={detail.canvas_hash ?? '—'} mono />
              <Row label="语言" value={detail.languages.join(', ') || '—'} />
              <Row label="WebDriver" value={fmtWebdriver(detail.webdriver)} />
              <Row
                label="采集时间"
                value={detail.probed_at ? fmtTime(detail.probed_at) : '—'}
              />
              <Row label="种子" value={detail.seed != null ? String(detail.seed) : '未指定'} mono />
            </dl>

            {detail.ua && (
              <div className="mt-3">
                <p className="mb-1 text-[11px] text-[var(--ink-400)]">User-Agent</p>
                <p className="rounded-lg bg-[#fafafa] px-3 py-2 font-mono text-[10.5px] leading-relaxed break-all text-[var(--ink-600)]">
                  {detail.ua}
                </p>
              </div>
            )}
          </Section>

          {/* 下发物料 */}
          <Section title="下发物料">
            {detail.render == null ? (
              <p className="text-[11.5px] text-[var(--ink-400)]">
                这个内核不认指纹参数，没有可下发的内容。
              </p>
            ) : (
              <>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-0.5 rounded-full border border-[var(--line)] p-0.5">
                    {(
                      [
                        ['json', 'fingerprint.json'],
                        ['env', '环境变量'],
                        ['args', 'chrome 参数'],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setTab(key)}
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
                          tab === key
                            ? 'bg-[#18181b] text-white'
                            : 'text-[var(--ink-500)] hover:bg-[#f4f4f5]'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={copy}
                    className="btn-ghost !h-7 !px-2 !text-[11px]"
                  >
                    <IconClipboard size={12} />
                    复制
                  </button>
                </div>
                <pre className="max-h-[220px] overflow-auto rounded-xl bg-[#18181b] px-3.5 py-3 font-mono text-[10.5px] leading-relaxed text-[#e4e4e7]">
                  {material}
                </pre>

                {detail.render.ignored.length > 0 && (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                    {detail.kernel} 不认这些字段，写进去也不会生效：
                    {detail.render.ignored.join('、')}
                  </p>
                )}
              </>
            )}
          </Section>

          {/* 应用实例 */}
          <Section
            title="应用到实例"
            extra={
              bound ? (
                <span className="chip bg-[var(--line)] text-[var(--ink-600)]">
                  已绑定 {detail.instances.length} 台
                </span>
              ) : null
            }
          >
            <p className="mb-2 text-[11.5px] text-[var(--ink-400)]">
              把指纹写成 <span className="font-mono">/data/fingerprint.json</span> 塞进容器再重启。
              重启只重建浏览器进程，profile 不动，登录态和历史都还在。
            </p>

            {candidates.length === 0 ? (
              <p className="text-[11.5px] text-[var(--ink-400)]">
                还没有实例。先去「浏览器池」建一台。
              </p>
            ) : (
              <div className="space-y-1 rounded-xl border border-[var(--line)] p-2">
                {candidates.map((item) => (
                  <label
                    key={item.id}
                    className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-[#fcfcfd]"
                  >
                    <Checkbox
                      checked={picked.includes(item.id)}
                      onChange={(next) =>
                        setPicked((prev) =>
                          next ? [...prev, item.id] : prev.filter((id) => id !== item.id),
                        )
                      }
                      label=""
                    />
                    <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--ink-900)]">
                      {item.name}
                    </span>
                    <span className="shrink-0 text-[10.5px] text-[var(--ink-400)]">
                      {item.status}
                    </span>
                  </label>
                ))}
              </div>
            )}

            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[11px] text-[var(--ink-400)]">
                已选 {picked.length} 台
              </span>
              <button
                type="button"
                onClick={apply}
                disabled={applying || picked.length === 0 || !detail.supported}
                className="btn-dark !h-8 !px-3 !text-[11.5px]"
              >
                <IconPlay size={11} />
                {applying ? '下发中…' : '写入并重启'}
              </button>
            </div>

            {result && (
              <ul className="mt-2 space-y-1">
                {result.items.map((item) => (
                  <li
                    key={item.instance_id}
                    className={`flex items-start gap-2 rounded-lg px-3 py-1.5 text-[11.5px] ${
                      item.ok
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-rose-50 text-rose-700'
                    }`}
                  >
                    <span className="mt-0.5 shrink-0">
                      {item.ok ? <IconCheckCircle size={11} /> : <IconAlert size={11} />}
                    </span>
                    <span className="min-w-0">
                      <span className="font-medium">{item.instance_name}</span>
                      <span className="mx-1 text-[10.5px] opacity-70">{item.container}</span>
                      {item.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        {/* 底部 */}
        <div className="flex items-center justify-between gap-2 border-t border-[var(--line)] px-5 py-3">
          <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--ink-400)]">
            {detail.note ?? ''}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="btn-ghost !h-8 !px-3 !text-[11.5px]" onClick={onEdit}>
              <IconWrench size={11} />
              编辑
            </button>
            <button type="button" className="btn-dark !h-8 !px-3 !text-[11.5px]" onClick={onClose}>
              完成
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}

function Section({
  title,
  extra,
  children,
}: {
  title: string
  extra?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-2xl border border-[var(--line)] bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-[12.5px] font-semibold text-[var(--ink-900)]">{title}</h3>
        {extra}
      </div>
      {children}
    </section>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10.5px] text-[var(--ink-400)]">{label}</dt>
      <dd
        className={`truncate text-[12px] text-[var(--ink-900)] ${mono ? 'font-mono text-[11.5px]' : ''}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  )
}

function fmtWebdriver(value: boolean | null): string {
  if (value === null) return '—'
  return value ? 'true（会被识别）' : 'false'
}

function fmtTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', { hour12: false })
}
