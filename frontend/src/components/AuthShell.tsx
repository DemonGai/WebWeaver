import type { ReactNode } from 'react'
import { BrandLockup } from './Brand'

/** 账号安全类页面的统一外壳：居中卡片 + 可选品牌区 + 底部说明。 */
export function AuthShell({
  children,
  brand = true,
  bottom,
}: {
  children: ReactNode
  brand?: boolean
  bottom?: ReactNode
}) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6 py-12">
      {brand && (
        <div className="mb-6">
          <BrandLockup vertical />
        </div>
      )}
      <div className="w-full max-w-[480px] rounded-2xl border border-[var(--line)] bg-white p-8 shadow-[0_1px_2px_rgba(24,24,27,0.04),0_18px_44px_-28px_rgba(24,24,27,0.18)]">
        {children}
      </div>
      {bottom && <div className="mt-6 text-[11.5px] text-[var(--ink-400)]">{bottom}</div>}
    </div>
  )
}

export function AuthTitle({ title, subtitle }: { title: string; subtitle?: ReactNode }) {
  return (
    <div>
      <h1 className="text-[24px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
        {title}
      </h1>
      {subtitle && (
        <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--ink-500)]">{subtitle}</p>
      )}
    </div>
  )
}
