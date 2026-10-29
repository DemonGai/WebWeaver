import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { IconChevronDown } from './icons'

export function Field({
  label,
  htmlFor,
  children,
  className = '',
}: {
  label: string
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <label htmlFor={htmlFor} className="block text-[12px] font-medium text-[var(--ink-700)]">
        {label}
      </label>
      {children}
    </div>
  )
}

const boxBase =
  'flex h-11 w-full items-center gap-2.5 rounded-xl border bg-white px-3.5 transition-colors'

/** 带前置图标的输入框，可选右侧附加内容（如"一致"标记）。 */
export function IconInput({
  icon,
  trailing,
  invalid,
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  icon?: ReactNode
  trailing?: ReactNode
  invalid?: boolean
}) {
  return (
    <div
      className={`${boxBase} ${
        invalid
          ? 'border-rose-300 focus-within:border-rose-400'
          : 'border-[var(--line)] focus-within:border-[#18181b]'
      } ${className}`}
    >
      {icon && <span className="shrink-0 text-[var(--ink-400)]">{icon}</span>}
      <input
        {...props}
        className="w-full bg-transparent text-[13px] text-[var(--ink-900)] outline-none placeholder:text-[var(--ink-400)]"
      />
      {trailing && <span className="shrink-0">{trailing}</span>}
    </div>
  )
}

export function SelectField({
  icon,
  className = '',
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { icon?: ReactNode }) {
  return (
    <div className={`${boxBase} border-[var(--line)] focus-within:border-[#18181b] ${className}`}>
      {icon && <span className="shrink-0 text-[var(--ink-400)]">{icon}</span>}
      <div className="relative w-full">
        <select
          {...props}
          className="w-full appearance-none bg-transparent pr-6 text-[13px] text-[var(--ink-900)] outline-none"
        >
          {children}
        </select>
        <span className="pointer-events-none absolute top-1/2 right-0 -translate-y-1/2 text-[var(--ink-400)]">
          <IconChevronDown size={14} />
        </span>
      </div>
    </div>
  )
}

/** 图形验证码：用旋转字形模拟扭曲字符，点击换一张。 */
export function CaptchaBox({ code, onRefresh }: { code: string; onRefresh: () => void }) {
  const tilt = [-16, 10, -8, 14]

  return (
    <button
      type="button"
      onClick={onRefresh}
      title="点击换一张"
      className="flex h-11 w-[104px] shrink-0 items-center justify-center gap-1 rounded-xl border border-[var(--line)] bg-[#f7f7f8] transition-colors hover:bg-[#f2f2f4]"
    >
      {code.split('').map((ch, i) => (
        <span
          key={`${ch}-${i}`}
          className="text-[17px] leading-none font-semibold tracking-tight text-[#3f3f46] select-none"
          style={{ transform: `rotate(${tilt[i % tilt.length]}deg)` }}
        >
          {ch}
        </span>
      ))}
    </button>
  )
}
