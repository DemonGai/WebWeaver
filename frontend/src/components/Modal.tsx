import { useEffect, type ReactNode } from 'react'
import { IconX } from '@/components/icons'

/**
 * 通用弹窗外壳：遮罩、Esc 关闭、锁滚动、头像栏与页脚插槽。
 *
 * 只是壳——表单状态由调用方自己管。抽出来的原因是项目里已经有第二处
 * 需要弹窗（内核升级），第三处（浏览器新建/编辑）不该再抄一遍
 * 「按 Esc 关闭 + 打开时禁止页面滚动」这种细节。
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = 'max-w-[560px]',
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  icon?: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/35 px-4 py-10 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative flex max-h-[calc(100vh-56px)] w-full ${width} flex-col rounded-2xl bg-white shadow-[0_24px_64px_-12px_rgba(16,24,40,0.28)]`}
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-6">
          <div className="flex items-start gap-3">
            {icon && (
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#18181b] text-white">
                {icon}
              </span>
            )}
            <div>
              <h2 className="text-[15.5px] font-semibold tracking-tight text-[var(--ink-900)]">
                {title}
              </h2>
              {subtitle && (
                <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--ink-500)]">
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          <button type="button" onClick={onClose} className="icon-btn size-7 shrink-0 border-0">
            <IconX size={14} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-2">{children}</div>

        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[var(--line)] px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
