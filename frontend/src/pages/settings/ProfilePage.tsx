import { useEffect, useState, type ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { PageHeader, PageShell } from '@/components/Layout'
import { Card, SectionHeader } from '@/components/ui'
import { IconCheck, IconLock, IconMail, IconShield, IconUser } from '@/components/icons'
import { formatDateTime } from '@/lib/format'
import { ErrorState, Loading } from '@/pages/OverviewPage'
import type { ProfilePayload } from '@/types/domain'

/**
 * 个人信息页
 * 能改的只有显示名：登录名是审计里的操作人、邮箱要走验证流程，
 * 都不放进一个「保存」按钮里草率处理。
 */
export default function ProfilePage() {
  const { data, status, error, reload } = useApi(endpoints.profile, [])
  const [profile, setProfile] = useState<ProfilePayload | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    if (!data) return
    setProfile(data)
    setDisplayName(data.display_name)
  }, [data])

  if (status === 'loading') return <PageShell><Loading /></PageShell>
  if (status === 'error')
    return (
      <PageShell>
        <ErrorState message={error} onRetry={reload} />
      </PageShell>
    )
  if (!profile) return null

  const dirty = displayName.trim() !== profile.display_name && displayName.trim().length > 0

  const save = async () => {
    if (!dirty || saving) return
    setSaving(true)
    setNotice(null)
    try {
      const res = await endpoints.updateProfile({ display_name: displayName.trim() })
      setProfile(res.profile)
      setDisplayName(res.profile.display_name)
      setNotice({ ok: true, text: res.message })
    } catch (err) {
      setNotice({ ok: false, text: err instanceof Error ? err.message : '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <PageShell>
      <PageHeader title="个人信息" subtitle="账号资料由工作区管理员维护，显示名可以自己改" />

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        {/* 身份卡 + 改名 */}
        <Card className="card-pad">
          <div className="flex items-start gap-3.5">
            <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-[#18181b] text-[20px] font-medium text-white">
              {profile.initial}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-[17px] font-semibold text-[var(--ink-900)]">
                  {profile.display_name}
                </h2>
                <span className="chip bg-blue-50 text-blue-600">{profile.role}</span>
                {profile.is_superuser && (
                  <span className="chip bg-amber-50 text-amber-600">超级管理员</span>
                )}
                <span
                  className={`chip ${
                    profile.status === 'active'
                      ? 'bg-emerald-50 text-emerald-600'
                      : 'bg-rose-50 text-rose-500'
                  }`}
                >
                  {profile.status === 'active' ? '正常' : profile.status}
                </span>
              </div>
              <p className="mt-1 truncate text-[12px] text-[var(--ink-400)]">
                {profile.username} · {profile.email}
              </p>
            </div>
          </div>

          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <label className="label-xs" htmlFor="display-name">
              显示名
            </label>
            <div className="mt-1.5 flex items-center gap-2">
              <input
                id="display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={64}
                className="h-9 w-full rounded-xl border border-[var(--line)] bg-white px-3 text-[13px] text-[var(--ink-900)] outline-none focus:border-[#18181b]"
                placeholder="输入显示名"
              />
              <button
                type="button"
                onClick={save}
                disabled={!dirty || saving}
                className="btn-dark shrink-0 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-[var(--ink-400)]">
              显示名用于头像浮层与操作日志；登录名与邮箱不支持自助修改。
            </p>
            {notice && (
              <p
                className={`mt-2 flex items-center gap-1 text-[11.5px] ${
                  notice.ok ? 'text-emerald-600' : 'text-rose-500'
                }`}
              >
                {notice.ok && <IconCheck size={12} />}
                {notice.text}
              </p>
            )}
          </div>
        </Card>

        {/* 资料明细 */}
        <Card className="card-pad">
          <SectionHeader icon={<IconUser size={14} />} title="账号信息" />
          <dl className="mt-3 divide-y divide-[var(--line)]">
            <InfoRow label="登录名" value={profile.username} mono />
            <InfoRow label="邮箱" value={profile.email} icon={<IconMail size={12} />} />
            <InfoRow label="角色" value={`${profile.role}${profile.role_code ? `（${profile.role_code}）` : ''}`} icon={<IconShield size={12} />} />
            <InfoRow
              label="默认工作区"
              value={
                profile.workspace
                  ? `${profile.workspace.name}${profile.workspace.note ? ` · ${profile.workspace.note}` : ''}`
                  : '未分配'
              }
            />
            <InfoRow label="加入时间" value={formatDateTime(profile.created_at)} />
            <InfoRow label="最近登录" value={formatDateTime(profile.last_login_at)} />
            <InfoRow label="上次改密" value={formatDateTime(profile.password_updated_at)} />
            <InfoRow label="在线设备" value={`${profile.active_sessions} 台`} icon={<IconLock size={12} />} />
          </dl>
        </Card>
      </div>
    </PageShell>
  )
}

function InfoRow({
  label,
  value,
  icon,
  mono,
}: {
  label: string
  value: string
  icon?: ReactNode
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="shrink-0 text-[11.5px] text-[var(--ink-400)]">{label}</dt>
      <dd
        className={`flex min-w-0 items-center gap-1 truncate text-right text-[12.5px] text-[var(--ink-900)] ${
          mono ? 'tnum' : ''
        }`}
      >
        {icon}
        <span className="truncate">{value}</span>
      </dd>
    </div>
  )
}
