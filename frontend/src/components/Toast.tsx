import { useCallback, useEffect, useState } from 'react'
import { IconAlert, IconCheckCircle, IconX } from '@/components/icons'

/**
 * 悬浮通知。
 *
 * 之前每个页面各自实现一份「在页面顶部塞一条色块」的提示，问题是它在文档流里：
 * 一出现就把下面的表格 / 卡片整体推下去，消失时又弹回来，看起来像页面抖了一下；
 * 而且提示和触发它的按钮经常不在一个视野里（采集按钮在表格底部，提示在页头）。
 *
 * 这里改成标准的 toast：`fixed` 挂在视口右下角，不进文档流，不遮操作区，
 * 4 秒自动消失，也能手动关。
 */

export type ToastTone = 'ok' | 'err'
export type ToastState = { tone: ToastTone; text: string } | null

export function Toast({ toast, onClose }: { toast: ToastState; onClose: () => void }) {
  if (!toast) return null
  const ok = toast.tone === 'ok'

  return (
    // 外层只负责定位，pointer-events 关掉，免得挡住底下的按钮
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[70] flex justify-center px-4 pb-6 sm:justify-end sm:pr-6">
      <div
        role="status"
        aria-live="polite"
        className="toast-in pointer-events-auto flex w-full max-w-[380px] items-start gap-2.5 rounded-xl border border-[var(--line)] bg-white px-3.5 py-3 shadow-[0_16px_40px_-16px_rgba(16,24,40,0.32)]"
      >
        <span className={`mt-px shrink-0 ${ok ? 'text-emerald-600' : 'text-rose-600'}`}>
          {ok ? <IconCheckCircle size={14} /> : <IconAlert size={14} />}
        </span>
        <p className="flex-1 text-[12.5px] leading-snug text-[var(--ink-700)]">{toast.text}</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭提示"
          className="shrink-0 text-[var(--ink-400)] transition-colors hover:text-[var(--ink-700)]"
        >
          <IconX size={12} />
        </button>
      </div>
    </div>
  )
}

/** 一套 toast 的开关 + 自动消失。页面里 `const { toast, notify, dismiss } = useToast()`。 */
export function useToast(ttl = 4000) {
  const [toast, setToast] = useState<ToastState>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), ttl)
    return () => window.clearTimeout(timer)
  }, [toast, ttl])

  const notify = useCallback((tone: ToastTone, text: string) => setToast({ tone, text }), [])
  const dismiss = useCallback(() => setToast(null), [])

  return { toast, notify, dismiss }
}
