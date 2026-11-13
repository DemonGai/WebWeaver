import {
  Combobox,
  ComboboxButton,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
  Listbox,
  ListboxButton,
  ListboxOption,
  ListboxOptions,
} from '@headlessui/react'
import type { ReactNode } from 'react'
import { IconCheck, IconChevronDown } from './icons'

export type SelectOption = {
  value: string
  label: string
  /** 右侧浅色补注（「已被占用」「跟随当前」这类），比标签低一档 */
  hint?: string
  /** 右侧计数，筛选面板里用 */
  count?: number
  /** 左侧色点 */
  tone?: string
  disabled?: boolean
  /** 作为「未选择」的空档选项时置灰显示，避免看起来像已经选好了 */
  muted?: boolean
}

/** 面板共用：圆角、描边、投影、进出场。两个变体只差宽度和对齐方向。 */
const PANEL =
  'z-50 max-h-[300px] overflow-y-auto rounded-xl border border-[var(--line)] bg-white p-1.5 shadow-[0_18px_44px_-16px_rgba(16,24,40,0.28)] outline-none transition duration-150 ease-out data-[closed]:-translate-y-1 data-[closed]:opacity-0'

const OPTION =
  'group/opt flex items-center gap-2 rounded-lg px-2 py-[6.5px] text-[12.5px] text-[var(--ink-700)] outline-none select-none data-focus:bg-[#f6f6f7] data-selected:font-medium data-selected:text-[var(--ink-900)]'

/** 选项行：左边色点 / 标签（可截断）/ 右侧补注 / 计数 / 勾。 */
function OptionRow({ option }: { option: SelectOption }) {
  return (
    <>
      {option.tone && (
        <span
          className="size-[5px] shrink-0 rounded-full"
          style={{ backgroundColor: option.tone }}
        />
      )}
      <span className="min-w-0 flex-1 truncate">{option.label}</span>
      {option.hint && (
        <span className="shrink-0 text-[10.5px] text-[var(--ink-400)] group-data-selected/opt:text-[var(--ink-500)]">
          {option.hint}
        </span>
      )}
      {typeof option.count === 'number' && (
        <span className="tnum shrink-0 text-[11px] text-[var(--ink-400)] group-data-selected/opt:text-[var(--ink-500)]">
          {option.count}
        </span>
      )}
      <span className="w-3 shrink-0 text-[#18181b] opacity-0 group-data-selected/opt:opacity-100">
        <IconCheck size={11} />
      </span>
    </>
  )
}

/**
 * 全站唯一的下拉选择器。
 *
 * 原生 `<select>` 的弹层由操作系统绘制：字体、行高、圆角、hover 一律不受控，
 * 在 Windows 上还会突然变成一块直角灰蓝列表，和这里的版式完全不是一个世界。
 * 所以统一换成 Headless UI 的 Listbox —— 键盘、焦点、portal 定位它负责，
 * 视觉归这里。
 *
 * - `variant="form"`：表单里的方框（与输入框同高同圆角），面板宽度跟随控件；
 * - `variant="pill"`：筛选栏里的胶囊，面板右对齐、固定最小宽度。
 */
export function Select({
  value,
  options,
  onChange,
  placeholder = '请选择',
  icon,
  size = 'lg',
  variant = 'form',
  panelHeader,
  panelWidth = 'min-w-[190px]',
  disabled = false,
  invalid = false,
  className = '',
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  /** 当前值不在 options 里时显示的兜底文案 */
  placeholder?: string
  icon?: ReactNode
  size?: 'sm' | 'lg'
  variant?: 'form' | 'pill'
  panelHeader?: string
  /** 仅 pill 变体使用：面板固定宽度 */
  panelWidth?: string
  disabled?: boolean
  invalid?: boolean
  className?: string
}) {
  const current = options.find((it) => it.value === value)
  /** 没有选中任何一项（或者选中的是占位项）时，文字压一档 */
  const muted = current == null || current.muted === true

  const buttonClass =
    variant === 'pill'
      ? `group inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium outline-none transition-colors ${
          value !== ''
            ? 'border-[#18181b]/15 bg-[#f7f7f8] text-[var(--ink-900)]'
            : 'border-[var(--line)] bg-white text-[var(--ink-700)] hover:border-[#dcdce2] hover:bg-[#fafafa]'
        } data-open:border-[#d4d4d8] data-open:bg-[#f4f4f5] data-focus-visible:ring-2 data-focus-visible:ring-[#18181b]/12 ${
          disabled ? 'cursor-not-allowed opacity-50' : ''
        } ${className}`
      : `group flex w-full items-center gap-2 rounded-xl border bg-white text-left outline-none transition-colors ${
          size === 'sm' ? 'h-9 px-3 text-[12.5px]' : 'h-11 px-3.5 text-[13px]'
        } ${
          disabled
            ? 'cursor-not-allowed border-[var(--line)] bg-[#fafafa] text-[var(--ink-400)]'
            : invalid
              ? 'border-rose-300 hover:border-rose-400 data-open:border-rose-400'
              : 'border-[var(--line)] hover:border-[#dcdce2] data-open:border-[#18181b]'
        } data-focus-visible:border-[#18181b] data-focus-visible:ring-2 data-focus-visible:ring-[#18181b]/10 ${className}`

  const panelClass =
    variant === 'pill'
      ? `${PANEL} ${panelWidth} origin-top-right`
      : `${PANEL} min-w-[180px] origin-top w-[var(--button-width)]`

  return (
    <Listbox value={value} onChange={onChange} disabled={disabled}>
      <ListboxButton className={buttonClass}>
        {icon && (
          <span className="shrink-0 text-[var(--ink-400)] transition-colors group-data-open:text-[var(--ink-600)]">
            {icon}
          </span>
        )}
        <span
          className={`min-w-0 flex-1 truncate ${variant === 'pill' ? 'max-w-[168px]' : ''} ${
            muted && variant === 'form' ? 'text-[var(--ink-400)]' : ''
          }`}
        >
          {current?.label ?? placeholder}
        </span>
        <span className="flex shrink-0 items-center text-[var(--ink-400)]">
          <IconChevronDown
            size={variant === 'pill' ? 12 : 14}
            className="transition-transform duration-200 group-data-open:rotate-180"
          />
        </span>
      </ListboxButton>

      <ListboxOptions
        anchor={variant === 'pill' ? 'bottom end' : 'bottom start'}
        transition
        className={`${panelClass} [--anchor-gap:6px]`}
      >
        {panelHeader && (
          <div className="px-2 pt-0.5 pb-1 text-[10.5px] font-medium tracking-wide text-[var(--ink-400)]">
            {panelHeader}
          </div>
        )}

        {options.length === 0 && (
          <div className="px-2 py-3 text-center text-[11.5px] text-[var(--ink-400)]">暂无可选项</div>
        )}

        {options.map((it) => (
          <ListboxOption
            key={it.value || '__empty__'}
            value={it.value}
            disabled={it.disabled}
            className={`${OPTION} ${
              it.disabled ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'
            }`}
          >
            <OptionRow option={it} />
          </ListboxOption>
        ))}
      </ListboxOptions>
    </Listbox>
  )
}

/**
 * 可搜可选的下拉：既能从候选里点，也允许手填任意值（时区这类）。
 *
 * 用 Combobox 而不是 `<input list=...>` + `<datalist>`，因为 datalist 的
 * 候选框同样是操作系统画的，样式完全插不进去，展开位置也常被浏览器算歪。
 */
export function SearchableSelect({
  value,
  options,
  onChange,
  placeholder,
  icon,
  size = 'lg',
  panelHeader,
}: {
  value: string
  options: string[]
  onChange: (value: string) => void
  placeholder?: string
  icon?: ReactNode
  size?: 'sm' | 'lg'
  panelHeader?: string
}) {
  const query = value.trim().toLowerCase()
  const matched = query
    ? options.filter((it) => it.toLowerCase().includes(query))
    : options
  // 输入已经等于某个候选时不再过滤，否则面板会缩成孤零零一行
  const visible = matched.length === 1 && matched[0].toLowerCase() === query ? options : matched

  return (
    <Combobox value={value} onChange={(next: string | null) => onChange(next ?? '')} immediate>
      <div
        className={`flex w-full items-center gap-2 rounded-xl border border-[var(--line)] bg-white transition-colors focus-within:border-[#18181b] focus-within:ring-2 focus-within:ring-[#18181b]/10 ${
          size === 'sm' ? 'h-9 px-3 text-[12.5px]' : 'h-11 px-3.5 text-[13px]'
        }`}
      >
        {icon && <span className="shrink-0 text-[var(--ink-400)]">{icon}</span>}
        <ComboboxInput
          className="w-full min-w-0 bg-transparent text-[inherit] text-[var(--ink-900)] outline-none placeholder:text-[var(--ink-400)]"
          displayValue={(v: string) => v}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
        <ComboboxButton className="group/chev flex shrink-0 items-center text-[var(--ink-400)] outline-none transition-colors hover:text-[var(--ink-600)]">
          <IconChevronDown
            size={14}
            className="transition-transform duration-200 group-data-open/chev:rotate-180"
          />
        </ComboboxButton>
      </div>

      <ComboboxOptions
        anchor="bottom start"
        transition
        className={`${PANEL} [--anchor-gap:6px] min-w-[180px] w-[var(--input-width)] origin-top`}
      >
        {panelHeader && (
          <div className="px-2 pt-0.5 pb-1 text-[10.5px] font-medium tracking-wide text-[var(--ink-400)]">
            {panelHeader}
          </div>
        )}

        {visible.length === 0 ? (
          <div className="px-2 py-3 text-center text-[11.5px] text-[var(--ink-400)]">
            没有匹配项，可直接使用「{value}」
          </div>
        ) : (
          visible.map((it) => (
            <ComboboxOption
              key={it}
              value={it}
              className={`${OPTION} cursor-pointer`}
            >
              <span className="min-w-0 flex-1 truncate">{it}</span>
            </ComboboxOption>
          ))
        )}
      </ComboboxOptions>
    </Combobox>
  )
}
