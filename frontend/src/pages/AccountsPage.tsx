import { useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import {
  Card,
  HeroBadge,
  HeroCard,
  PillTabs,
  ProgressBar,
  SearchInput,
  SelectBox,
  type Tone,
} from '@/components/ui'
import {
  IconBolt,
  IconCheck,
  IconLock,
  IconMore,
  IconPlus,
  IconRefresh,
  IconShield,
  IconTag,
  IconUpload,
  IconUser,
  IconX,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { AccountCard, AccountStatus } from '@/types/domain'

const meta: Record<AccountStatus, { label: string; tone: Tone }> = {
  logged_in: { label: '已登录', tone: 'emerald' },
  in_session: { label: '会话中', tone: 'blue' },
  restricted: { label: '风控', tone: 'rose' },
  unbound: { label: '未绑定', tone: 'zinc' },
}

const chipTone: Record<AccountStatus, string> = {
  logged_in: 'bg-emerald-50 text-emerald-600',
  in_session: 'bg-blue-50 text-blue-600',
  restricted: 'bg-rose-50 text-rose-500',
  unbound: 'bg-zinc-100 text-zinc-500',
}

const platformStyle: Record<string, string> = {
  Amazon: 'bg-amber-50 text-amber-500',
  Shopify: 'bg-emerald-50 text-emerald-500',
  TikTok: 'bg-zinc-100 text-zinc-800',
  Meta: 'bg-blue-50 text-blue-500',
  Instagram: 'bg-violet-50 text-violet-500',
  X: 'bg-zinc-100 text-zinc-700',
  Shopee: 'bg-orange-50 text-orange-500',
}

export default function AccountsPage() {
  const { data, status, error, reload } = useApi(endpoints.accounts, [])
  const [tab, setTab] = useState('all-platform')

  if (status === 'loading') return <PageShell><Loading /></PageShell>
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const { totals, cards, accounts, filters } = data

  return (
    <PageShell>
      <PageHeader
        title="账号池"
        subtitle="统一管理多平台账号，支持一键绑定到浏览器实例并自动同步登录态"
        actions={
          <>
            <button type="button" className="btn-ghost">
              <IconUpload size={14} />
              批量导入
            </button>
            <button type="button" className="btn-dark">
              <IconPlus size={14} />
              新增账号
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-4">
        <HeroCard
          variant="blue"
          className="col-span-4"
          eyebrow="账号总量"
          badge={
            <HeroBadge>
              <IconShield size={10} />
              健康率 {totals.health}%
            </HeroBadge>
          }
          value={totals.total}
          unit="个账号"
        >
          <div className="mt-6 space-y-1.5">
            <ProgressBar value={67} tone="zinc" height={3} className="!bg-white/20 [&>div]:!bg-white" />
            <ProgressBar value={25} tone="zinc" height={3} className="!bg-white/20 [&>div]:!bg-white/60" />
          </div>
        </HeroCard>

        <div className="col-span-8 grid grid-cols-3 gap-4">
          {cards.map((c) => (
            <Card key={c.title} className="flex flex-col justify-between p-5">
              <div className="flex items-start justify-between">
                <span className={`flex size-7 items-center justify-center rounded-lg ${iconTone[c.tone]}`}>
                  {cardIcon(c.title)}
                </span>
                <span className="text-[11px] text-[var(--ink-400)]">{c.tag}</span>
              </div>
              <div>
                <div className="tnum text-[30px] leading-none font-semibold tracking-tight">
                  {c.value}
                </div>
                <div className="mt-1.5 text-[12px] text-[var(--ink-500)]">{c.hint}</div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 p-3.5">
        <div className="flex items-center gap-3">
          <SearchInput placeholder="搜索账号名 / 平台 / 备注" width="w-[240px]" />
          <PillTabs
            items={filters.map((f) => ({ key: f.key, label: f.label, count: f.count }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectBox label="全部区域" />
          <SelectBox label="最近使用" />
        </div>
      </Card>

      <div className="mt-4 grid grid-cols-4 gap-4">
        {accounts.map((a) => (
          <AccountTile key={a.id} account={a} />
        ))}

        <button
          type="button"
          className="flex min-h-[186px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[#dcdce2] bg-white/60 transition-colors hover:bg-white"
        >
          <span className="flex size-9 items-center justify-center rounded-xl bg-[#f4f4f5] text-[var(--ink-500)]">
            <IconUser size={16} />
          </span>
          <span className="text-[13px] font-medium text-[var(--ink-900)]">新增账号</span>
          <span className="text-[11px] text-[var(--ink-400)]">支持 Cookie 导入</span>
        </button>
      </div>
    </PageShell>
  )
}

function AccountTile({ account: a }: { account: AccountCard }) {
  const badge = meta[a.status]
  const restricted = a.status === 'restricted'

  const action =
    a.status === 'restricted'
      ? { label: '修复会话', icon: <IconRefresh size={11} /> }
      : a.status === 'in_session'
        ? { label: '打开会话', icon: <IconBolt size={11} /> }
        : a.status === 'unbound'
          ? { label: '绑定实例', icon: <IconTag size={11} /> }
          : { label: '更换绑定', icon: <IconRefresh size={11} /> }

  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-start justify-between">
        <span
          className={`flex size-8 items-center justify-center rounded-lg text-[12px] font-semibold ${
            platformStyle[a.platform] ?? 'bg-zinc-100 text-zinc-500'
          }`}
        >
          {a.platform.slice(0, 2)}
        </span>
        <span className={`chip ${chipTone[a.status]} gap-1`}>
          {a.status === 'logged_in' && <IconCheck size={9} />}
          {restricted && <IconShield size={9} />}
          {badge.label}
        </span>
      </div>

      <div className="mt-2.5">
        <div className="text-[13px] font-semibold tracking-tight text-[var(--ink-900)]">
          {a.name}
        </div>
        <div className="mt-0.5 text-[10.5px] text-[var(--ink-400)]">
          {a.platform} · {a.region} · 注册 {a.registered_days} 天
        </div>
      </div>

      <div className="mt-2.5 space-y-1.5">
        <Row label="绑定实例" value={a.bound_instance ?? '未绑定'} muted={!a.bound_instance} />
        {restricted ? (
          <>
            <Row label="异常原因" value={a.note ?? '—'} danger />
            <Row label="建议动作" value="更换住宅 IP" danger />
          </>
        ) : (
          <Row label="出口 IP" value={a.exit_ip ?? '待分配'} muted={!a.exit_ip} mono />
        )}
        {a.status === 'unbound' && a.note && <Row label="建议实例" value={a.note} />}
      </div>

      <ProgressBar
        value={a.health}
        tone={restricted ? 'rose' : a.status === 'in_session' ? 'blue' : 'emerald'}
        height={4}
        className="mt-3"
      />

      <div className="mt-3 flex items-center gap-2">
        <button type="button" className="btn-dark !h-8 flex-1 !px-3 !text-[11.5px]">
          {action.icon}
          {action.label}
        </button>
        <button type="button" className="icon-btn size-8">
          <IconMore size={13} />
        </button>
      </div>
    </Card>
  )
}

function Row({
  label,
  value,
  muted,
  danger,
  mono,
}: {
  label: string
  value: string
  muted?: boolean
  danger?: boolean
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-[var(--ink-400)]">{label}</span>
      <span
        className={`${mono ? 'tnum' : ''} ${
          danger
            ? 'font-medium text-rose-500'
            : muted
              ? 'text-[var(--ink-400)]'
              : 'text-[var(--ink-700)]'
        }`}
      >
        {value}
      </span>
    </div>
  )
}

const iconTone: Record<string, string> = {
  emerald: 'bg-emerald-50 text-emerald-500',
  blue: 'bg-blue-50 text-blue-500',
  amber: 'bg-amber-50 text-amber-500',
  rose: 'bg-rose-50 text-rose-500',
  violet: 'bg-violet-50 text-violet-500',
  zinc: 'bg-zinc-100 text-zinc-500',
}

function cardIcon(title: string) {
  if (title.includes('可用')) return <IconCheck size={13} />
  if (title.includes('会话')) return <IconBolt size={13} />
  if (title.includes('受限')) return <IconLock size={13} />
  return <IconX size={13} />
}
