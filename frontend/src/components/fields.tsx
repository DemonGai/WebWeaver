import { useState } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { IconChevronDown, IconEye, IconEyeOff } from './icons'

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

/** 密码框：右侧带一个「显示 / 隐藏」按钮。
 *
 * 浏览器（Edge）本来会自带一个同样的眼睛（`::-ms-reveal`），但那个控件
 * 只在用户真敲了字之后才出现，位置和样式都没法控制，和我们自己的按钮
 * 一叠就是两个眼睛。`index.css` 里已经把它藏了，显隐状态统一归这里管。
 */
export function PasswordInput({
  icon,
  trailing,
  invalid,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  icon?: ReactNode
  /** 右侧附加内容（如「一致」标记），排在眼睛左边 */
  trailing?: ReactNode
  invalid?: boolean
}) {
  const [visible, setVisible] = useState(false)

  return (
    <IconInput
      {...props}
      icon={icon}
      invalid={invalid}
      type={visible ? 'text' : 'password'}
      trailing={
        <>
          {trailing}
          <button
            type="button"
            aria-label={visible ? '隐藏密码' : '显示密码'}
            onClick={() => setVisible((v) => !v)}
            className="flex text-[var(--ink-400)] transition-colors hover:text-[var(--ink-700)]"
          >
            {visible ? <IconEyeOff size={14} /> : <IconEye size={14} />}
          </button>
        </>
      }
    />
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
