import { Modal } from '@/components/Modal'
import { IconAlert, IconCheckCircle } from '@/components/icons'
import type { KernelPayload } from '@/types/domain'

/**
 * 「重新扫描」的结果弹窗。
 *
 * 原来扫描完只在页面底部弹一条 toast（「已重新扫描本地镜像」），信息量等于零：
 * 用户按了按钮，最想知道的是这次扫出来什么——几个内核有镜像、版本变了没有、
 * 哪几张卡可以切新版本。所以改成弹窗，把每张卡这次的结果列出来。
 *
 * 数据直接复用 `/kernels/rescan` 的返回（和页面首次加载是同一个 payload），
 * 不额外发请求。
 */
export function KernelScanDialog({
  result,
  onClose,
}: {
  result: KernelPayload | null
  onClose: () => void
}) {
  if (!result) return null

  const { cards, docker_ok, docker_error, scanned_at, total_versions } = result
  const supported = cards.filter((c) => c.supported)
  const installed = supported.filter((c) => c.installed)

  const summary = docker_ok
    ? `${supported.length} 个可用内核里，${installed.length} 个本地已有镜像，共 ${total_versions} 个版本`
    : 'Docker 不可用，这次没能读到本地镜像'

  return (
    <Modal
      open
      onClose={onClose}
      title="扫描完成"
      subtitle={`扫描于 ${scanned_at}`}
      icon={<IconCheckCircle size={15} />}
      width="max-w-[520px]"
      footer={
        <button type="button" onClick={onClose} className="btn-dark !h-8 !px-4 !text-[12px]">
          知道了
        </button>
      }
    >
      <div className="mt-4 space-y-3 pb-2">
        {!docker_ok && (
          <div className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2.5 text-[11.5px] text-amber-800">
            <IconAlert size={12} className="mt-[2px] shrink-0" />
            <div className="min-w-0">
              <div className="font-medium">读不到本地镜像</div>
              <div className="mt-0.5 leading-relaxed text-amber-700">
                {docker_error ?? '请确认 Docker 已启动，并且 docker 命令在 PATH 里'}
              </div>
            </div>
          </div>
        )}

        <p className="text-[11.5px] leading-relaxed text-[var(--ink-500)]">{summary}</p>

        <div className="overflow-hidden rounded-xl border border-[var(--line)]">
          {cards.map((card, index) => (
            <div
              key={card.id}
              className={`flex items-center justify-between gap-3 px-3.5 py-2.5 ${
                index > 0 ? 'border-t border-[var(--line)]' : ''
              }`}
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span
                  className={`size-[6px] shrink-0 rounded-full ${
                    !card.supported
                      ? 'bg-zinc-300'
                      : card.installed
                        ? 'bg-emerald-500'
                        : 'bg-amber-400'
                  }`}
                />
                <div className="min-w-0">
                  <div
                    className={`truncate text-[12.5px] font-medium ${
                      card.supported ? 'text-[var(--ink-900)]' : 'text-[var(--ink-500)]'
                    }`}
                  >
                    {card.name}
                  </div>
                  <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
                    {!card.supported
                      ? '暂未支持'
                      : card.installed
                        ? `镜像就绪 ${card.version_count} 个${card.total_size ? ` · ${card.total_size}` : ''}`
                        : '本地没有镜像'}
                  </div>
                </div>
              </div>

              <div className="shrink-0 text-right">
                {card.supported && card.installed ? (
                  <>
                    <div className="tnum text-[11.5px] text-[var(--ink-700)]">
                      {card.current_version ?? '—'}
                    </div>
                    {(card.update_available || card.stale_count > 0) && (
                      <div className="mt-0.5 flex items-center justify-end gap-2 text-[10px]">
                        {card.update_available && card.latest_version && (
                          <span className="text-blue-600">可切到 {card.latest_version}</span>
                        )}
                        {card.stale_count > 0 && (
                          <span className="tnum text-amber-600">
                            {card.stale_count} 台待迁移
                          </span>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <span className="text-[10.5px] text-[var(--ink-400)]">
                    {card.supported ? '未获取' : '—'}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {docker_ok && installed.length === 0 && (
          <p className="text-[11px] leading-relaxed text-[var(--ink-400)]">
            还没有任何内核镜像。点卡片上的「获取内核」会把镜像拉到本地。
          </p>
        )}
      </div>
    </Modal>
  )
}
