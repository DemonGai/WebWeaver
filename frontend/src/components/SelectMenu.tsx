import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import type { ReactNode } from 'react'
import { IconCheck, IconChevronDown } from './icons'

export type SelectMenuItem = {
  value: string
  label: string
  /** 右侧计数，例如每个分组下有几台实例 */
  count?: number
  /** 左侧色点，用于状态类分组 */
  tone?: string
}

/**
 * 基于 Headless UI Listbox 的下拉选择器。
 * 只负责交互与可访问性（键盘、焦点、portal 定位），视觉全部由这里接管。
 */
export function SelectMenu({
  value,
  items,
  onChange,
  icon,
  placeholder = '全部',
  panelHeader,
  className = '',
  width = 'min-w-[190px]',
}: {
  value: string
  items: SelectMenuItem[]
  onChange: (value: string) => void
  icon?: ReactNode
  placeholder?: string
  panelHeader?: string
  className?: string
  width?: string
}) {
  const current = items.find((it) => it.value === value)
  const active = value !== '' && current != null

  return (
    <Listbox value={value} onChange={onChange}>
      <ListboxButton
        className={`group inline-flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium transition-colors outline-none ${
          active
            ? 'border-[#18181b]/15 bg-[#f7f7f8] text-[var(--ink-900)]'
            : 'border-[var(--line)] bg-white text-[var(--ink-700)] hover:border-[#dcdce2] hover:bg-[#fafafa]'
        } data-open:border-[#d4d4d8] data-open:bg-[#f4f4f5] data-focus-visible:ring-2 data-focus-visible:ring-[#18181b]/12 ${className}`}
      >
        {icon && (
          <span className="text-[var(--ink-400)] transition-colors group-data-open:text-[var(--ink-600)]">
            {icon}
          </span>
        )}
        <span className="max-w-[124px] truncate">{current?.label ?? placeholder}</span>
        <span className="flex items-center gap-1 text-[var(--ink-400)]">
          <IconChevronDown
            size={12}
            className="transition-transform duration-200 group-data-open:rotate-180"
          />
        </span>
      </ListboxButton>

      <ListboxOptions
        anchor="bottom end"
        transition
        className={`z-50 [--anchor-gap:6px] ${width} max-h-[320px] origin-top-right overflow-y-auto rounded-xl border border-[var(--line)] bg-white p-1.5 shadow-[0_18px_44px_-16px_rgba(16,24,40,0.28)] transition duration-150 ease-out outline-none data-[closed]:translate-y-1 data-[closed]:opacity-0`}
      >
        {panelHeader && (
          <div className="px-2 pt-0.5 pb-1 text-[10.5px] font-medium tracking-wide text-[var(--ink-400)]">
            {panelHeader}
          </div>
        )}
        {items.map((it) => (
          <ListboxOption
            key={it.value || '__all__'}
            value={it.value}
            className="group/opt flex cursor-pointer items-center gap-2 rounded-lg px-2 py-[6.5px] text-[12px] text-[var(--ink-700)] outline-none data-focus:bg-[#f6f6f7] data-selected:font-medium data-selected:text-[var(--ink-900)]"
          >
            {it.tone && (
              <span
                className="size-[5px] shrink-0 rounded-full"
                style={{ backgroundColor: it.tone }}
              />
            )}
            <span className="flex-1 truncate">{it.label}</span>
            {typeof it.count === 'number' && (
              <span className="tnum text-[11px] text-[var(--ink-400)] group-data-selected/opt:text-[var(--ink-500)]">
                {it.count}
              </span>
            )}
            <span className="w-3 shrink-0 text-[#18181b] opacity-0 group-data-selected/opt:opacity-100">
              <IconCheck size={11} />
            </span>
          </ListboxOption>
        ))}
      </ListboxOptions>
    </Listbox>
  )
}
