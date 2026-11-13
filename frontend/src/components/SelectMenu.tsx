import type { ReactNode } from 'react'
import { Select, type SelectOption } from './Select'

export type SelectMenuItem = SelectOption

/**
 * 筛选栏里的胶囊下拉。
 *
 * 视觉与交互都收在 `Select`（`variant="pill"`）里，这里只保留旧的调用方式，
 * 免得四个筛选页各写一遍面板样式。
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
  return (
    <Select
      variant="pill"
      value={value}
      options={items}
      onChange={onChange}
      icon={icon}
      placeholder={placeholder}
      panelHeader={panelHeader}
      panelWidth={width}
      className={className}
    />
  )
}
