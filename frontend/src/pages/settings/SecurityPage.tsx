import { useState } from 'react'
import { Link } from 'react-router-dom'
import { endpoints } from '@/api/endpoints'
import { useAuth } from '@/auth/AuthProvider'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, SectionHeader, StatusDot, type Tone } from '@/components/ui'
import { ChangePasswordDialog } from '@/components/ChangePasswordDialog'
import {
  IconActivity,
  IconAlert,
  IconCheckCircle,
  IconChevronRight,
  IconClock,
  IconDevices,
  IconLock,
  IconShield,
} from '@/components/icons'
import { formatDateTime, formatRelative, formatRemaining } from '@/lib/format'
import { ErrorState, Loading } from '@/pages/OverviewPage'

const RESULT_TONE: Record<string, Tone> = {
  success: 'emerald',
  failure: 'rose',
}

export default function SecurityPage() {
  const { data, status, error, reload } = useApi(endpoints.security, [])
  const { session } = useAuth()
  const [changing, setChanging] = useState(false)

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

  const locked = data.lock_remaining_minutes > 0

  return (
    <PageShell>
      <PageHeader
        title="安全与二次验证"
        subtitle="密码、登录保护与最近认证记录；两步验证待接入 TOTP 后开放"
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <Card className="card-pad">
            <SectionHeader icon={<IconLock size={14} />} title="登录密码" />
            <p className="mt-2 text-[12px] text-[var(--ink-500)]">
              {data.password_updated_at
                ? `上次修改：${formatDateTime(data.password_updated_at)}（${formatRelative(data.password_updated_at)}）`
                : '还没有修改过密码，当前是初始化时设置的演示口令'}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setChanging(true)}
                className="btn-dark !h-8 !text-[12px]"
              >
                <IconLock size={12} />
                修改密码
              </button>
              <Link to="/forgot-password" className="btn-ghost !h-8 !text-[12px]">
                邮件重置
                <IconChevronRight size={12} />
              </Link>
            </div>
            <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
              修改后会立即下线其他设备；忘记原密码时用「邮件重置」，那条路径会踢掉全部设备。
            </p>
          </Card>

          <Card className="card-pad">
            <SectionHeader icon={<IconClock size={14} />} title="登录有效期" />
            <dl className="mt-2 divide-y divide-[var(--line)]">
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">访问令牌（自动续期）</dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {formatRemaining(session?.accessExpiresAt)}
                  <span className="ml-1 text-[11px] text-[var(--ink-400)]">后换新</span>
                </dd>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">登录会话</dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {formatRemaining(session?.refreshExpiresAt)}
                  {session?.remember && (
                    <span className="ml-1.5 chip bg-blue-50 px-1.5 text-[10px] text-blue-600">
                      记住我
                    </span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">最迟需重新登录</dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {formatRemaining(session?.absoluteExpiresAt)}
                  <span className="ml-1 text-[11px] text-[var(--ink-400)]">（上限）</span>
                </dd>
              </div>
            </dl>
            <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
              访问令牌每 30 分钟换一次、用户无感；登录会话在活跃时会向后滑动，
              但越不过上面的「最迟需重新登录」，到期后只能重新登录。
            </p>
          </Card>

          <Card className="card-pad">
            <SectionHeader icon={<IconShield size={14} />} title="两步验证" />
            <div className="mt-2 flex items-center gap-2">
              <StatusDot tone="zinc" label="未开启" />
              <span className="text-[11.5px] text-[var(--ink-400)]">仅密码登录</span>
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-500)]">{data.mfa_note}</p>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="card-pad">
            <SectionHeader icon={<IconAlert size={14} />} title="登录保护" />
            <dl className="mt-2 divide-y divide-[var(--line)]">
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">连续失败</dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {data.failed_login_count} 次
                  <span className="ml-1 text-[11px] text-[var(--ink-400)]">（连续 5 次锁定 15 分钟）</span>
                </dd>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">账号状态</dt>
                <dd className="text-[12.5px]">
                  {locked ? (
                    <span className="text-rose-500">
                      已锁定，还需 {data.lock_remaining_minutes} 分钟
                    </span>
                  ) : (
                    <span className="text-emerald-600">正常</span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <dt className="text-[11.5px] text-[var(--ink-400)]">最近登录</dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {formatDateTime(data.last_login_at)}
                </dd>
              </div>
              <div className="flex items-center justify-between py-2.5">
                <dt className="flex items-center gap-1 text-[11.5px] text-[var(--ink-400)]">
                  <IconDevices size={12} />
                  在线设备
                </dt>
                <dd className="text-[12.5px] text-[var(--ink-900)]">
                  {data.active_sessions} 台
                  <Link to="/settings/sessions" className="ml-2 text-blue-600 hover:underline">
                    管理
                  </Link>
                </dd>
              </div>
            </dl>
          </Card>

          <Card className="card-pad">
            <SectionHeader icon={<IconActivity size={14} />} title="最近认证事件" />
            {data.recent_events.length === 0 ? (
              <p className="mt-3 text-[12px] text-[var(--ink-400)]">暂无记录</p>
            ) : (
              <ul className="mt-2 space-y-2.5">
                {data.recent_events.map((event) => (
                  <li key={event.id} className="flex items-start gap-2.5">
                    <span className="mt-1">
                      <StatusDot tone={RESULT_TONE[event.result] ?? 'zinc'} label="" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px] font-medium text-[var(--ink-900)]">
                          {event.action_label}
                        </span>
                        <span className="text-[10.5px] text-[var(--ink-400)]">
                          {formatDateTime(event.occurred_at)}
                        </span>
                      </div>
                      <p className="truncate text-[11px] text-[var(--ink-400)]">
                        {event.detail ?? '—'}
                        {event.ip_address ? ` · ${event.ip_address}` : ''}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Link
              to="/settings/audit-logs"
              className="mt-3 inline-flex items-center gap-0.5 text-[11.5px] text-blue-600 hover:underline"
            >
              查看全部操作日志
              <IconChevronRight size={11} />
            </Link>
          </Card>
        </div>
      </div>

      {data.failed_login_count === 0 && !locked && (
        <p className="mt-4 flex items-center gap-1 text-[11.5px] text-[var(--ink-400)]">
          <IconCheckCircle size={12} className="text-emerald-500" />
          未发现异常登录；如发现陌生设备，请到「登录设备管理」下线并修改密码。
        </p>
      )}

      <ChangePasswordDialog
        open={changing}
        onClose={() => {
          setChanging(false)
          // 改密会顺带刷新改密时间与事件列表，关掉弹窗后重新拉一次
          reload()
        }}
      />
    </PageShell>
  )
}
