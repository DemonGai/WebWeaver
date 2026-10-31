import { useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, SectionHeader } from '@/components/ui'
import { SelectMenu } from '@/components/SelectMenu'
import {
  IconChevronLeft,
  IconChevronRight,
  IconFilter,
  IconList,
  IconRefresh,
  IconShield,
} from '@/components/icons'
import { formatDateTime } from '@/lib/format'
import { ErrorState, Loading } from '@/pages/OverviewPage'
import type { AuditLogItem } from '@/types/domain'

const ACTION_LABEL: Record<string, string> = {
  create: '新建',
  update: '修改',
  delete: '删除',
  bind: '绑定',
  unbind: '解绑',
  start: '启动',
  stop: '停止',
  login: '登录',
  logout: '退出',
  reset_password: '重置密码',
  export: '导出',
  import: '导入',
}

const RESOURCE_LABEL: Record<string, string> = {
  browser: '浏览器',
  account: '账号',
  ip: 'IP',
  fingerprint: '指纹',
  kernel: '内核',
  group: '分组',
  binding: '绑定',
  auth: '认证',
  user: '成员',
  role: '角色',
  system: '系统',
}

const PAGE_SIZE = 20

/** 我的操作日志：只看自己（operator 由后端按登录态钉死） */
export default function AuditLogsPage() {
  const [action, setAction] = useState('')
  const [result, setResult] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, status, error, reload } = useApi(
    () =>
      endpoints.myAuditLogs({
        action: action || undefined,
        result: result || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [action, result, offset],
  )

  const filterBar = (
    <div className="mb-3 flex items-center gap-2">
      <SelectMenu
        value={action}
        onChange={(v) => {
          setAction(v)
          setOffset(0)
        }}
        icon={<IconFilter size={12} />}
        placeholder="全部动作"
        panelHeader="按动作筛选"
        items={[
          { value: '', label: '全部动作' },
          ...Object.entries(ACTION_LABEL).map(([value, label]) => ({ value, label })),
        ]}
      />
      <SelectMenu
        value={result}
        onChange={(v) => {
          setResult(v)
          setOffset(0)
        }}
        icon={<IconShield size={12} />}
        placeholder="全部结果"
        panelHeader="按结果筛选"
        items={[
          { value: '', label: '全部结果' },
          { value: 'success', label: '成功' },
          { value: 'failure', label: '失败' },
        ]}
      />
      <button type="button" onClick={reload} className="btn-ghost !h-8 !text-[12px]">
        <IconRefresh size={13} />
        刷新
      </button>
    </div>
  )

  if (status === 'loading')
    return (
      <PageShell>
        <PageHeader title="账号操作日志" subtitle="记录自己的登录、改密与资源操作" />
        {filterBar}
        <Loading />
      </PageShell>
    )
  if (status === 'error')
    return (
      <PageShell>
        <PageHeader title="账号操作日志" subtitle="记录自己的登录、改密与资源操作" />
        {filterBar}
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!data) return null

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
  const page = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <PageShell>
      <PageHeader
        title="账号操作日志"
        subtitle={`共 ${data.total} 条记录，只显示当前账号自己的操作`}
      />
      {filterBar}

      <Card>
        <div className="card-pad pb-0">
          <SectionHeader icon={<IconList size={14} />} title="操作记录" />
        </div>
        <table className="mt-3 w-full">
          <thead>
            <tr className="border-y border-[var(--line)] bg-[#fafafa]">
              <th className="table-th">时间</th>
              <th className="table-th">动作</th>
              <th className="table-th">对象</th>
              <th className="table-th">详情</th>
              <th className="table-th">结果</th>
              <th className="table-th">IP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--line)]">
            {data.items.map((item) => (
              <Row key={item.id} item={item} />
            ))}
            {data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="table-td py-10 text-center text-[12px] text-[var(--ink-400)]">
                  没有符合条件的记录
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="flex items-center justify-between px-4 py-3 text-[11.5px] text-[var(--ink-400)]">
          <span>
            第 {page} / {pages} 页
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="inline-flex items-center gap-0.5 rounded-full px-2.5 py-1 hover:bg-[#f4f4f5] disabled:opacity-40"
            >
              <IconChevronLeft size={12} />
              上一页
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="inline-flex items-center gap-0.5 rounded-full px-2.5 py-1 hover:bg-[#f4f4f5] disabled:opacity-40"
            >
              下一页
              <IconChevronRight size={12} />
            </button>
          </div>
        </div>
      </Card>
    </PageShell>
  )
}

function Row({ item }: { item: AuditLogItem }) {
  const failed = item.result === 'failure'
  // 失败记录显示错误信息，成功记录显示 detail；两者都没有就退回「—」
  const text = failed ? (item.error_message ?? item.detail) : item.detail

  return (
    <tr className={failed ? 'bg-rose-50/40' : ''}>
      <td className="table-td tnum whitespace-nowrap">{formatDateTime(item.occurred_at)}</td>
      <td className="table-td whitespace-nowrap">
        {ACTION_LABEL[item.action] ?? item.action}
      </td>
      <td className="table-td whitespace-nowrap">
        <span className="text-[var(--ink-400)]">
          {RESOURCE_LABEL[item.resource_type] ?? item.resource_type}
        </span>
        {item.resource_name && (
          <span className="ml-1 text-[var(--ink-900)]">{item.resource_name}</span>
        )}
      </td>
      <td className="table-td max-w-[420px]">
        <div className="truncate" title={text ?? ''}>
          {text ?? '—'}
        </div>
        {item.changes && <Changes changes={item.changes} />}
      </td>
      <td className="table-td whitespace-nowrap">
        <span className={`chip ${failed ? 'bg-rose-50 text-rose-500' : 'bg-emerald-50 text-emerald-600'}`}>
          {failed ? '失败' : '成功'}
        </span>
      </td>
      <td className="table-td tnum whitespace-nowrap">{item.ip_address ?? '—'}</td>
    </tr>
  )
}

function Changes({ changes }: { changes: Record<string, { before: unknown; after: unknown }> }) {
  const entries = Object.entries(changes).slice(0, 3)
  if (entries.length === 0) return null

  const render = (value: unknown) =>
    value === null || value === undefined ? '空' : String(value)

  return (
    <div className="mt-0.5 flex flex-wrap gap-1">
      {entries.map(([field, diff]) => (
        <span key={field} className="chip bg-[#f4f4f5] text-[10px] text-[var(--ink-500)]">
          {field}: {render(diff.before)} → {render(diff.after)}
        </span>
      ))}
    </div>
  )
}
