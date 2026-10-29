import { useEffect, useRef, useState, type ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import type { AccountMenu, MenuRow } from '@/types/domain'
import {
  IconBell,
  IconBuilding,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconDevices,
  IconGear,
  IconList,
  IconLock,
  IconLogout,
  IconShield,
  IconSwap,
  IconUser,
} from './icons'

const rowIcon: Record<string, ReactNode> = {
  user: <IconUser size={13} />,
  swap: <IconSwap size={13} />,
  lock: <IconLock size={13} />,
  shield: <IconShield size={13} />,
  devices: <IconDevices size={13} />,
  list: <IconList size={13} />,
  logout: <IconLogout size={13} />,
}

const badgeTone: Record<string, string> = {
  emerald: 'bg-emerald-50 text-emerald-600',
  zinc: 'bg-[#f4f4f5] text-[var(--ink-500)]',
  blue: 'bg-blue-50 text-blue-600',
}

/**
 * 头像菜单浮层
 * - 悬停 120ms 后展开，头像出现 2px 深色描边高亮
 * - 右边缘与头像右边缘对齐，向下偏移 8px，宽度 320px
 * - 移出浮层 / 点击外部 / Esc 均可关闭
 */
export function UserMenu() {
  const { data } = useApi<AccountMenu>(() => endpoints.accountMenu())
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const openTimer = useRef<number | null>(null)
  const closeTimer = useRef<number | null>(null)

  const clearTimers = () => {
    if (openTimer.current) window.clearTimeout(openTimer.current)
    if (closeTimer.current) window.clearTimeout(closeTimer.current)
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  useEffect(() => clearTimers, [])

  const onEnter = () => {
    clearTimers()
    openTimer.current = window.setTimeout(() => setOpen(true), 120)
  }

  const onLeave = () => {
    clearTimers()
    closeTimer.current = window.setTimeout(() => setOpen(false), 90)
  }

  const initial = data?.initial ?? '林'

  return (
    <div ref={wrapRef} className="relative" onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="账号菜单"
        onClick={() => setOpen((v) => !v)}
        className={`flex size-9 items-center justify-center rounded-full bg-[#18181b] text-[12px] font-medium text-white transition-all ${
          open ? 'ring-2 ring-[#18181b] ring-offset-2' : ''
        }`}
      >
        {initial}
      </button>

      {open && data && (
        <div
          role="menu"
          className="absolute top-[calc(100%+8px)] right-0 z-50 w-[320px] rounded-2xl border border-[var(--line)] bg-white shadow-[0_18px_44px_-12px_rgba(16,24,40,0.22)]"
        >
          {/* 用户信息 */}
          <div className="flex items-start gap-2.5 px-4 pt-4 pb-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#18181b] text-[13px] font-medium text-white">
              {data.initial}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[13px] font-semibold text-[var(--ink-900)]">{data.name}</span>
                <span className="chip bg-blue-50 px-1.5 text-[10px] text-blue-600">{data.role}</span>
              </div>
              <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">{data.email}</div>
            </div>
            <button type="button" className="shrink-0 text-[var(--ink-400)] hover:text-[var(--ink-500)]">
              <IconGear size={14} />
            </button>
          </div>

          {/* 工作区 */}
          <div className="mx-3 mb-1 flex items-center justify-between rounded-xl bg-[#fafafa] px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-[var(--ink-400)]">
                <IconBuilding size={14} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-[12px] font-medium text-[var(--ink-900)]">
                  {data.workspace}
                </div>
                <div className="text-[10px] text-[var(--ink-400)]">{data.workspace_note}</div>
              </div>
            </div>
            <button
              type="button"
              className="flex shrink-0 items-center gap-0.5 text-[11px] font-medium text-blue-600 hover:underline"
            >
              切换
              <IconChevronDown size={11} />
            </button>
          </div>

          {/* 菜单分组 */}
          {data.groups.map((group, gi) => (
            <div key={gi}>
              <div className="mx-3 my-1 h-px bg-[var(--line)]" />
              <div className="px-1.5 py-1">
                {group.map((row) => (
                  <MenuRowItem key={row.key} row={row} />
                ))}
              </div>
            </div>
          ))}

          {/* 页脚 */}
          <div className="mx-3 mt-0.5 flex items-center justify-between border-t border-[var(--line)] py-2.5 text-[10px] text-[var(--ink-400)]">
            <span className="flex items-center gap-1">
              <IconClock size={10} />
              {data.last_login}
            </span>
            <span className="tnum">{data.version}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function MenuRowItem({ row }: { row: MenuRow }) {
  return (
    <button
      type="button"
      role="menuitem"
      className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[8px] text-left transition-colors hover:bg-[#fafafa] ${
        row.danger ? 'text-rose-500' : 'text-[var(--ink-700)]'
      }`}
    >
      <span className={row.danger ? 'text-rose-500' : 'text-[var(--ink-400)]'}>{rowIcon[row.icon]}</span>
      <span className="flex-1 text-[12px]">{row.label}</span>
      {row.badge && (
        <span className={`chip px-1.5 text-[10px] ${badgeTone[row.badge_tone ?? 'zinc'] ?? badgeTone.zinc}`}>
          {row.badge}
        </span>
      )}
      <span className={row.danger ? 'text-rose-300' : 'text-[#d4d4d8]'}>
        <IconChevronRight size={11} />
      </span>
    </button>
  )
}

/** 顶部通知按钮（设计稿中无未读红点） */
export function NotifyButton() {
  return (
    <button type="button" className="icon-btn size-9" aria-label="通知">
      <IconBell size={15} />
    </button>
  )
}
