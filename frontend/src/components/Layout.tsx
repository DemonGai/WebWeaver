import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { BrandLockup } from './Brand'
import { NotifyButton, UserMenu } from './UserMenu'
import {
  IconBrowser,
  IconFingerprint,
  IconGlobe,
  IconKernel,
  IconOverview,
  IconSearch,
  IconUser,
} from './icons'

const NAV = [
  { to: '/', label: '总览', icon: IconOverview, end: true },
  { to: '/browsers', label: '浏览器池', icon: IconBrowser },
  { to: '/accounts', label: '账号池', icon: IconUser },
  { to: '/ip-pool', label: '代理管理', icon: IconGlobe },
  { to: '/fingerprints', label: '指纹管理', icon: IconFingerprint },
  { to: '/kernels', label: '内核管理', icon: IconKernel },
]

const SEARCH_HINT: Record<string, string> = {
  '/kernels': '搜索内核版本',
  '/fingerprints': '搜索指纹模板',
  '/accounts': '搜索账号 / 平台',
  '/ip-pool': '搜索代理 / 供应商',
  '/browsers': '搜索实例 / 分组',
}

export function Header() {
  const { pathname } = useLocation()
  // 前缀匹配：/kernels/camoufox 这类子页面也要拿到「搜索内核版本」
  const placeholder =
    SEARCH_HINT[pathname] ??
    Object.entries(SEARCH_HINT).find(([path]) => pathname.startsWith(`${path}/`))?.[1] ??
    '搜索实例 / 账号 / IP'

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-white/95 backdrop-blur">
      <div className="flex h-16 w-full items-center gap-7 px-7">
        {/* Logo + 产品名 */}
        <div className="shrink-0">
          <BrandLockup />
        </div>

        {/* 导航 */}
        <nav className="flex flex-1 items-center gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  'flex h-8 items-center gap-1.5 rounded-full px-3 text-[12.5px] font-medium transition-colors',
                  isActive
                    ? 'bg-[#18181b] text-white'
                    : 'text-[var(--ink-500)] hover:bg-[#f4f4f5] hover:text-[var(--ink-900)]',
                ].join(' ')
              }
            >
              <Icon size={14} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* 右侧操作区 */}
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="flex h-9 w-[230px] items-center gap-2 rounded-full border border-[var(--line)] bg-[#fafafa] px-3.5">
            <span className="text-[var(--ink-400)]">
              <IconSearch size={14} />
            </span>
            <input
              placeholder={placeholder}
              className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-[var(--ink-400)]"
            />
          </div>
          <NotifyButton />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}

export function PageHeader({
  icon,
  title,
  subtitle,
  actions,
}: {
  /** 给了就渲染「墨色圆角块 + 图标」，规格与内核管理页同款 */
  icon?: ReactNode
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className={`mb-5 flex justify-between gap-4 ${icon ? 'items-center' : 'items-end'}`}>
      <div className="flex items-center gap-3">
        {icon && (
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#18181b] text-white shadow-[0_1px_2px_rgba(24,24,27,0.24)]">
            {icon}
          </span>
        )}
        <div>
          <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-[var(--ink-900)]">
            {title}
          </h1>
          {subtitle && <p className="mt-1.5 text-[12.5px] text-[var(--ink-500)]">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-full">
      <Header />
      <main className="w-full px-7 py-6">{children}</main>
    </div>
  )
}
