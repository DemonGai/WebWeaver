import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authToken } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, SectionHeader } from '@/components/ui'
import { IconDevices, IconMonitor, IconPower, IconRefresh } from '@/components/icons'
import { formatDateTime, formatRelative } from '@/lib/format'
import { ErrorState, Loading } from '@/pages/OverviewPage'
import type { SessionItem } from '@/types/domain'

const REASON_LABEL: Record<string, string> = {
  logout: '主动退出',
  password_reset: '修改密码后失效',
  admin: '被踢下线',
}

export default function SessionsPage() {
  const navigate = useNavigate()
  const { data, status, error, reload } = useApi(endpoints.sessions, [])
  const [items, setItems] = useState<SessionItem[]>([])
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (data) setItems(data.items)
  }, [data])

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

  const active = items.filter((item) => !item.revoked)

  const revoke = async (item: SessionItem) => {
    // 两段式确认：第一次点击只是「待确认」，避免误触把自己踢下线
    if (pendingId !== item.id) {
      setPendingId(item.id)
      return
    }

    setPendingId(null)
    setBusyId(item.id)
    setNotice(null)
    try {
      const res = await endpoints.revokeSession(item.id)
      setNotice(res.message)
      if (res.signed_out) {
        // 踢的是自己这台：令牌已经失效，清掉本地并回登录页
        authToken.clear()
        navigate('/login')
        return
      }
      reload()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="登录设备管理"
        subtitle={`当前 ${active.length} 台设备在线；陌生设备可以立即下线`}
        actions={
          <button type="button" onClick={reload} className="btn-ghost !h-8 !text-[12px]">
            <IconRefresh size={13} />
            刷新
          </button>
        }
      />

      {notice && (
        <p className="mb-3 rounded-xl bg-[#fafafa] px-3 py-2 text-[12px] text-[var(--ink-600)]">
          {notice}
        </p>
      )}

      <Card>
        <div className="card-pad pb-0">
          <SectionHeader icon={<IconDevices size={14} />} title="会话列表" />
        </div>
        <table className="mt-3 w-full">
          <thead>
            <tr className="border-y border-[var(--line)] bg-[#fafafa]">
              <th className="table-th">设备</th>
              <th className="table-th">IP</th>
              <th className="table-th">登录时间</th>
              <th className="table-th">最近活跃</th>
              <th className="table-th">到期</th>
              <th className="table-th text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--line)]">
            {items.map((item) => (
              <tr key={item.id} className={item.revoked ? 'opacity-55' : ''}>
                <td className="table-td">
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--ink-400)]">
                      <IconMonitor size={14} />
                    </span>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12.5px] font-medium text-[var(--ink-900)]">
                          {item.device}
                        </span>
                        {item.current && (
                          <span className="chip bg-emerald-50 text-[10px] text-emerald-600">
                            本机
                          </span>
                        )}
                      </div>
                      <div className="text-[10.5px] text-[var(--ink-400)]">
                        {item.revoked
                          ? `已失效：${REASON_LABEL[item.revoked_reason ?? ''] ?? item.revoked_reason ?? '未知原因'}`
                          : item.browser}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="table-td tnum">{item.ip_address ?? '—'}</td>
                <td className="table-td tnum">{formatDateTime(item.issued_at)}</td>
                <td className="table-td">{formatRelative(item.last_seen_at)}</td>
                <td className="table-td tnum">{formatDateTime(item.expires_at)}</td>
                <td className="table-td text-right">
                  {item.revoked ? (
                    <span className="text-[11.5px] text-[var(--ink-400)]">已下线</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => revoke(item)}
                      onBlur={() => setPendingId(null)}
                      disabled={busyId === item.id}
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px] font-medium transition-colors ${
                        pendingId === item.id
                          ? 'bg-rose-500 text-white hover:bg-rose-600'
                          : 'text-rose-500 hover:bg-rose-50'
                      }`}
                    >
                      <IconPower size={11} />
                      {busyId === item.id
                        ? '处理中…'
                        : pendingId === item.id
                          ? item.current
                            ? '确认退出？'
                            : '确认下线？'
                          : item.current
                            ? '退出'
                            : '下线'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="table-td py-10 text-center text-[12px] text-[var(--ink-400)]">
                  暂无登录会话
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <p className="mt-3 text-[11.5px] text-[var(--ink-400)]">
        退出当前设备等同于注销登录；修改密码会自动让其他设备全部下线。
      </p>
    </PageShell>
  )
}
