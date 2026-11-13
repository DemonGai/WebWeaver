import { useMemo, useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, PillTabs, ProgressBar, SearchInput, StatusDot } from '@/components/ui'
import { StatTile } from '@/components/StatTile'
import { SelectMenu } from '@/components/SelectMenu'
import { AccountDialog } from '@/components/AccountDialog'
import { AccountImportDialog } from '@/components/AccountImportDialog'
import { Toast, useToast } from '@/components/Toast'
import { copyText } from '@/lib/clipboard'
import {
  IconArrowUpRight,
  IconBolt,
  IconCheckCircle,
  IconClipboard,
  IconGear,
  IconGlobe,
  IconLock,
  IconPlus,
  IconRefresh,
  IconUpload,
  IconUser,
} from '@/components/icons'
import { ErrorState, Loading } from './OverviewPage'
import type { AccountCard, AccountStatus } from '@/types/domain'

/** 状态与配色。四个状态正好对上四个统计口径里的三个，剩下一个是「未绑定」。 */
const STATUS_META: Record<AccountStatus, { label: string; tone: 'emerald' | 'blue' | 'rose' | 'zinc' }> = {
  logged_in: { label: '已登录', tone: 'emerald' },
  in_session: { label: '会话中', tone: 'blue' },
  restricted: { label: '风控', tone: 'rose' },
  unbound: { label: '未绑定', tone: 'zinc' },
}

/** 平台色块：每个平台一个固定色，扫一眼就能分清是哪家店铺。 */
const PLATFORM_STYLE: Record<string, string> = {
  Amazon: 'bg-amber-50 text-amber-600',
  Shopify: 'bg-emerald-50 text-emerald-600',
  TikTok: 'bg-zinc-100 text-zinc-700',
  Meta: 'bg-blue-50 text-blue-600',
  Instagram: 'bg-violet-50 text-violet-600',
  X: 'bg-zinc-100 text-zinc-600',
  Shopee: 'bg-orange-50 text-orange-600',
}

const platformStyle = (platform: string) => PLATFORM_STYLE[platform] ?? 'bg-zinc-100 text-zinc-500'

/**
 * 登录页列：去掉协议头让路径多露几个字，主域名才是要看的，
 * 整条地址仍放 title 和 href 里，不受这里截断影响。
 */
const urlDisplay = (url: string) => url.replace(/^https?:\/\//, '').replace(/\/$/, '')

const healthTone = (a: AccountCard) =>
  a.status === 'restricted' ? 'rose' : a.status === 'in_session' ? 'blue' : 'emerald'

export default function AccountsPage() {
  const { data, status, error, reload, refresh } = useApi(endpoints.accounts, [])

  const [tab, setTab] = useState('all-platform')
  const [query, setQuery] = useState('')
  const [region, setRegion] = useState('')
  // null = 关闭；字符串 = 编辑该账号；'new' = 新建
  const [editing, setEditing] = useState<string | null | undefined>(undefined)
  const [importOpen, setImportOpen] = useState(false)
  const { toast, notify, dismiss } = useToast()

  /** 地区候选按库里实际出现的值生成，不写死一份国家清单 */
  const regionItems = useMemo(() => {
    const counts = new Map<string, number>()
    for (const item of data?.accounts ?? []) {
      counts.set(item.region, (counts.get(item.region) ?? 0) + 1)
    }
    return [
      { value: '', label: '全部地区' },
      ...[...counts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([code, count]) => ({ value: code, label: code, count })),
    ]
  }, [data])

  const rows = useMemo(() => {
    if (!data) return []
    const keyword = query.trim().toLowerCase()
    return data.accounts
      .filter((a) => (tab === 'all-platform' ? true : a.platform.toLowerCase() === tab))
      .filter((a) => (region === '' ? true : a.region === region))
      .filter((a) =>
        keyword === ''
          ? true
          : [
              a.name,
              a.platform,
              a.login_url ?? '',
              a.region,
              a.exit_ip ?? '',
              a.bound_instance ?? '',
              a.note ?? '',
            ]
              .join(' ')
              .toLowerCase()
              .includes(keyword),
      )
  }, [data, tab, region, query])

  const copyAccount = async (a: AccountCard) => {
    const ok = await copyText(a.name)
    notify(ok ? 'ok' : 'err', ok ? `已复制 ${a.name}` : '复制失败，请手动选中复制')
  }

  if (status === 'loading')
    return (
      <PageShell>
        <Loading />
      </PageShell>
    )
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  // 统计口径直接取后端的 cards，避免前端再算一遍算错了
  const card = (title: string) => data.cards.find((c) => c.title === title)
  const available = card('可用')
  const inSession = card('会话中')
  const restricted = card('受限')

  const boundInRows = rows.filter((a) => a.bound_instance != null).length

  return (
    <PageShell>
      <PageHeader
        icon={<IconUser size={19} />}
        title="账号管理"
        subtitle="多平台账号的登录态与出口，绑定后由浏览器实例接管"
        actions={
          <>
            <button type="button" className="btn-ghost" onClick={reload}>
              <IconRefresh size={14} />
              刷新
            </button>
            <button type="button" className="btn-ghost" onClick={() => setImportOpen(true)}>
              <IconUpload size={14} />
              批量导入
            </button>
            <button type="button" className="btn-dark" onClick={() => setEditing(null)}>
              <IconPlus size={14} />
              新增账号
            </button>
          </>
        }
      />

      {/* 统计条：与内核管理、指纹管理同一套 StatTile */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="账号总数"
          value={String(data.totals.total)}
          hint={`健康率 ${data.totals.health}%`}
          tone="dark"
          icon={<IconUser size={15} />}
        />
        <StatTile
          label="可用"
          value={String(available?.value ?? 0)}
          hint="登录态正常，可直接绑定"
          tone="emerald"
          icon={<IconCheckCircle size={15} />}
        />
        <StatTile
          label="会话中"
          value={String(inSession?.value ?? 0)}
          hint="已绑定运行中的实例"
          tone="blue"
          icon={<IconBolt size={15} />}
        />
        <StatTile
          label="受限"
          value={String(restricted?.value ?? 0)}
          hint={restricted && restricted.value > 0 ? '触发风控，需换 IP' : '没有被风控的账号'}
          tone={restricted && restricted.value > 0 ? 'rose' : 'zinc'}
          icon={<IconLock size={15} />}
        />
      </div>

      <Card className="mt-4 flex flex-wrap items-center justify-between gap-3 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            placeholder="搜索账号 / 平台 / 登录页"
            width="w-[250px]"
            value={query}
            onChange={setQuery}
          />
          <PillTabs
            items={data.filters.map((f) => ({ key: f.key, label: f.label, count: f.count }))}
            active={tab}
            onSelect={setTab}
          />
        </div>
        <div className="flex items-center gap-2">
          <SelectMenu
            value={region}
            items={regionItems}
            onChange={setRegion}
            icon={<IconGlobe size={13} />}
            width="min-w-[170px]"
            panelHeader="按国家/地区筛选"
          />
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1240px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="table-th w-[15%]">账号</th>
                <th className="table-th w-[19%]">登录页</th>
                <th className="table-th w-[12%]">状态</th>
                <th className="table-th w-[7%]">地区</th>
                <th className="table-th w-[11%]">绑定实例</th>
                <th className="table-th w-[11%]">出口 IP</th>
                <th className="table-th w-[7%]">Cookie</th>
                <th className="table-th w-[9%]">健康度</th>
                <th className="table-th w-[9%] text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row
                  key={row.id}
                  account={row}
                  onCopy={() => copyAccount(row)}
                  onEdit={() => setEditing(row.id)}
                />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td
                    colSpan={9}
                    className="px-4 py-16 text-center text-[12.5px] text-[var(--ink-400)]"
                  >
                    没有匹配的账号
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-3">
          <div className="text-[11.5px] text-[var(--ink-500)]">
            显示 {rows.length} / {data.totals.total} 条
            {boundInRows > 0 && `，其中 ${boundInRows} 条已绑定实例`}
          </div>
          <div className="text-[11px] text-[var(--ink-400)]">
            账号跟实例走：绑定和登录态同步都在浏览器池里完成
          </div>
        </div>
      </Card>

      <AccountDialog
        open={editing !== undefined}
        accountId={editing ?? null}
        onClose={() => setEditing(undefined)}
        onSaved={(message) => {
          notify('ok', message)
          // 用 refresh 而不是 reload：reload 会把页面打回骨架屏，弹窗还没来得及卸载
          refresh()
        }}
      />
      <AccountImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => {
          notify('ok', '导入完成，列表已更新')
          refresh()
        }}
      />

      <Toast toast={toast} onClose={dismiss} />
    </PageShell>
  )
}

function Row({
  account: a,
  onCopy,
  onEdit,
}: {
  account: AccountCard
  onCopy: () => void
  onEdit: () => void
}) {
  const meta = STATUS_META[a.status]
  const restricted = a.status === 'restricted'
  /**
   * 状态下面那行小字要说清「为什么是这个状态」。
   *
   * 「会话中」但取不到绑定实例是真实会出现的：实例被删了、或者是从别的机器
   * 迁走的账号，状态字段还停在 in_session。这时直接显示「未绑定」会跟上面
   * 的绿点自相矛盾，得明说实例已经掉线。
   */
  const hint = restricted
    ? (a.note ?? '触发风控')
    : a.status === 'unbound'
      ? '待分配实例'
      : a.status === 'in_session'
        ? (a.bound_instance ? '运行中' : '实例已下线，待重新绑定')
        : '可直接绑定实例'
  const hintTone = restricted
    ? 'text-rose-500'
    : a.status === 'in_session' && !a.bound_instance
      ? 'text-amber-600'
      : 'text-[var(--ink-400)]'

  return (
    <tr className="border-b border-[#f4f4f6] last:border-0 hover:bg-[#fcfcfd]">
      <td className="table-td">
        <div className="flex items-center gap-2.5">
          <span
            className={`flex size-7 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold ${platformStyle(a.platform)}`}
          >
            {a.platform.slice(0, 2)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12.5px] font-medium text-[var(--ink-900)]" title={a.name}>
              {a.name}
            </div>
            {/* 平台是登录地址推导出来的，地址本身在右边那列 */}
            <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">{a.platform}</div>
          </div>
        </div>
      </td>

      <td className="table-td">
        {a.login_url ? (
          <a
            href={a.login_url}
            target="_blank"
            rel="noreferrer"
            title={a.login_url}
            className="group flex max-w-full items-center gap-1 text-[11.5px] text-[var(--ink-500)] transition-colors hover:text-[var(--ink-900)]"
          >
            <span className="truncate">{urlDisplay(a.login_url)}</span>
            <IconArrowUpRight
              size={11}
              className="shrink-0 text-[var(--ink-400)] group-hover:text-[var(--ink-700)]"
            />
          </a>
        ) : (
          <span className="text-[11.5px] text-amber-600">未填登录地址</span>
        )}
      </td>

      <td className="table-td">
        <StatusDot tone={meta.tone} label={meta.label} />
        <div className={`mt-0.5 truncate text-[10.5px] ${hintTone}`} title={hint}>
          {hint}
        </div>
      </td>

      <td className="table-td">
        <div className="text-[12px] text-[var(--ink-900)]">{a.region}</div>
      </td>

      <td className="table-td">
        {a.bound_instance ? (
          <span className="text-[12px] text-[var(--ink-700)]">{a.bound_instance}</span>
        ) : (
          <span className="text-[12px] text-[var(--ink-400)]">未绑定</span>
        )}
      </td>

      <td className="table-td">
        {a.exit_ip ? (
          <span className="tnum text-[12px] text-[var(--ink-700)]">{a.exit_ip}</span>
        ) : (
          <span className="text-[12px] text-[var(--ink-400)]">待分配</span>
        )}
      </td>

      <td className="table-td">
        {a.cookie_count > 0 ? (
          <span className="tnum text-[12px] font-medium text-emerald-600">{a.cookie_count} 条</span>
        ) : (
          <span className="text-[12px] text-[var(--ink-400)]">未采集</span>
        )}
      </td>

      <td className="table-td">
        <div className="flex items-center gap-2">
          <ProgressBar value={a.health} tone={healthTone(a)} height={4} className="!w-10 shrink-0" />
          <span className="tnum text-[11.5px] text-[var(--ink-700)]">{a.health}%</span>
        </div>
      </td>

      <td className="table-td">
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={onEdit}
            className="btn-ghost !h-7 shrink-0 !px-2 !text-[11px]"
            title={`编辑 ${a.name}`}
          >
            <IconGear size={11} />
            编辑
          </button>
          <button
            type="button"
            onClick={onCopy}
            className="btn-ghost !h-7 shrink-0 !px-2 !text-[11px]"
            title={`复制 ${a.name}`}
          >
            <IconClipboard size={11} />
            复制
          </button>
        </div>
      </td>
    </tr>
  )
}
