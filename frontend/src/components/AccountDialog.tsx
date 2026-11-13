import { useEffect, useMemo, useRef, useState } from 'react'
import { Modal } from '@/components/Modal'
import { Field, IconInput, SelectField } from '@/components/fields'
import { Hint } from '@/components/Hint'
import { endpoints } from '@/api/endpoints'
import {
  IconAlert,
  IconCheckCircle,
  IconGlobe,
  IconLink,
  IconMail,
  IconUpload,
  IconUser,
} from '@/components/icons'
import type { AccountCookie, AccountStatus } from '@/types/domain'

const STATUS_OPTIONS = [
  { value: '', label: '自动', hint: '有 Cookie 记为已登录' },
  { value: 'logged_in', label: '已登录' },
  { value: 'in_session', label: '会话中' },
  { value: 'restricted', label: '受限' },
  { value: 'unbound', label: '未绑定' },
]

type Form = {
  loginUrl: string
  username: string
  email: string
  region: string
  health: number
  note: string
  status: AccountStatus | ''
  cookiesText: string
}

const EMPTY: Form = {
  loginUrl: '',
  username: '',
  email: '',
  region: '',
  health: 100,
  note: '',
  status: '',
  cookiesText: '',
}

type CookieProbe = { count: number; domains: string[]; error: string }

/**
 * 解析用户粘的 Cookie。
 *
 * 认两种输入：Playwright ``storage_state.json`` 整个对象（``{"cookies": [...]})``
 * 和裸的 cookies 数组。这里只做「预览 + 提交前拦错」，真正的归一化在后端——
 * 两份都做是因为前端要即时告诉用户「识别到 3 条」，而不是等一次往返。
 */
function probeCookies(text: string): CookieProbe {
  if (!text.trim()) return { count: 0, domains: [], error: '' }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (err) {
    return { count: 0, domains: [], error: `不是合法 JSON：${(err as Error).message}` }
  }
  const list = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === 'object' && 'cookies' in parsed
      ? (parsed as { cookies: unknown }).cookies
      : null
  if (!Array.isArray(list)) {
    return { count: 0, domains: [], error: '需要是 Cookie 数组，或 storage_state 对象' }
  }
  const domains = new Set<string>()
  for (const [index, item] of list.entries()) {
    if (!item || typeof item !== 'object') {
      return { count: 0, domains: [], error: `第 ${index + 1} 条不是对象` }
    }
    const { name, domain } = item as { name?: unknown; domain?: unknown }
    if (typeof name !== 'string' || !name) {
      return { count: 0, domains: [], error: `第 ${index + 1} 条缺少 name` }
    }
    if (typeof domain === 'string' && domain) domains.add(domain)
  }
  return { count: list.length, domains: [...domains].slice(0, 4), error: '' }
}

/**
 * 新建 / 编辑账号。
 *
 * 同一个弹窗两种用途：传 ``accountId`` 就是编辑，打开时先拉一次详情——
 * Cookie 不在列表接口里（几十条逐行下发没必要），要编辑就得单独取。
 */
export function AccountDialog({
  open,
  accountId,
  onClose,
  onSaved,
}: {
  open: boolean
  accountId: string | null
  onClose: () => void
  onSaved: (message: string) => void
}) {
  const [form, setForm] = useState<Form>(EMPTY)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // 平台识别结果由后端算（映射只有一份，别在前端抄第二份）
  const [detected, setDetected] = useState<{ platform: string; known: boolean } | null>(null)
  const [detectError, setDetectError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const editing = accountId != null
  const probe = useMemo(() => probeCookies(form.cookiesText), [form.cookiesText])

  // 打开时重置；编辑模式再补一次详情。accountId 变了要重新拉，
  // 否则点第二行「编辑」会看到上一行的内容
  useEffect(() => {
    if (!open) return
    setError('')
    setBusy(false)
    if (!accountId) {
      setForm(EMPTY)
      return
    }
    setLoading(true)
    endpoints
      .accountDetail(accountId)
      .then((detail) => {
        setForm({
          loginUrl: detail.login_url ?? '',
          username: detail.username,
          email: detail.email ?? '',
          region: detail.region,
          health: detail.health,
          note: detail.note ?? '',
          status: detail.status,
          cookiesText: detail.cookies?.length
            ? JSON.stringify(detail.cookies, null, 2)
            : '',
        })
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [open, accountId])

  useEffect(() => {
    const url = form.loginUrl.trim()
    if (!open || !url) {
      setDetected(null)
      setDetectError('')
      return
    }
    // 每敲一个字符都打接口没必要，等用户停手再问
    const timer = setTimeout(() => {
      endpoints
        .detectPlatform(url)
        .then((res) => {
          setDetected({ platform: res.platform, known: res.known })
          setDetectError('')
        })
        .catch((err: Error) => {
          setDetected(null)
          setDetectError(err.message)
        })
    }, 350)
    return () => clearTimeout(timer)
  }, [open, form.loginUrl])

  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const pickFile = async (file: File | undefined) => {
    if (!file) return
    set('cookiesText', (await file.text()).replace(/^\uFEFF/, ''))
  }

  const submit = async () => {
    setError('')
    if (!form.loginUrl.trim()) {
      setError('登录地址不能为空')
      return
    }
    if (detectError) {
      setError(`登录地址无法识别：${detectError}`)
      return
    }
    if (!form.username.trim()) {
      setError('账号名不能为空')
      return
    }
    if (probe.error) {
      setError(`Cookie 有问题：${probe.error}`)
      return
    }

    // 空文本框 = 明确清空登录态；新建时它本来就是空，语义一致
    let cookies: AccountCookie[] | null = null
    if (form.cookiesText.trim()) {
      const parsed = JSON.parse(form.cookiesText) as unknown
      cookies = (Array.isArray(parsed) ? parsed : (parsed as { cookies: unknown }).cookies) as
        | AccountCookie[]
        | null
    }

    const body = {
      login_url: form.loginUrl.trim(),
      username: form.username.trim(),
      email: form.email.trim() || null,
      region: form.region.trim(),
      health: form.health,
      note: form.note.trim() || null,
      // status 留空时不传，交给后端按「有没有 Cookie」推断
      ...(form.status ? { status: form.status } : {}),
      cookies,
    }

    setBusy(true)
    try {
      const label = detected ? `${detected.platform} / ${body.username}` : body.username
      if (accountId) {
        await endpoints.updateAccount(accountId, body)
        onSaved(`已保存 ${label}`)
      } else {
        await endpoints.createAccount(body)
        onSaved(`已新建 ${label}`)
      }
      onClose()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const blocked = busy || loading

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? '编辑账号' : '新增账号'}
      subtitle={
        editing
          ? '改资料或更新登录态；Cookie 会原样明文存进库里'
          : '填账号资料，顺手把 storage_state 里的 Cookie 贴进来就是已登录'
      }
      icon={<IconUser size={16} />}
      width="max-w-[620px]"
      footer={
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--ink-400)]">
            {probe.count > 0
              ? `识别到 ${probe.count} 条 Cookie`
              : '同一个登录页下账号名不能重复'}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
              取消
            </button>
            <button type="button" className="btn-dark" onClick={submit} disabled={blocked}>
              {busy ? '保存中…' : editing ? '保存' : '新建账号'}
            </button>
          </div>
        </div>
      }
    >
      {loading ? (
        <p className="py-10 text-center text-[12.5px] text-[var(--ink-400)]">正在读取账号…</p>
      ) : (
        <div className="space-y-4 pb-2">
          {/* 登录地址独占一行：它决定平台，比其他字段都长 */}
          <Field label="登录地址" htmlFor="acct-login-url">
            <IconInput
              id="acct-login-url"
              icon={<IconLink size={14} />}
              value={form.loginUrl}
              onChange={(e) => set('loginUrl', e.target.value)}
              placeholder="https://sellercentral.amazon.com/ap/signin"
              autoComplete="off"
              spellCheck={false}
              invalid={Boolean(detectError)}
            />
          </Field>
          {detectError ? (
            <Hint tone="rose">{detectError}</Hint>
          ) : detected ? (
            <Hint tone={detected.known ? 'emerald' : 'amber'}>
              {detected.known
                ? `识别为 ${detected.platform}`
                : `这个域名没收录，平台按注册域记为「${detected.platform}」`}
            </Hint>
          ) : (
            <Hint tone="zinc">
              平台由登录地址自动识别，不用手选；同一平台的不同国家站点填各自的登录页
            </Hint>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="账号名" htmlFor="acct-username">
              <IconInput
                id="acct-username"
                icon={<IconUser size={14} />}
                value={form.username}
                onChange={(e) => set('username', e.target.value)}
                placeholder="shop_us_101"
                autoComplete="off"
              />
            </Field>
            <Field label="邮箱（可选）" htmlFor="acct-email">
              <IconInput
                id="acct-email"
                icon={<IconMail size={14} />}
                value={form.email}
                onChange={(e) => set('email', e.target.value)}
                placeholder="shop_us_101@example.com"
                autoComplete="off"
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="地区" htmlFor="acct-region">
              <IconInput
                id="acct-region"
                icon={<IconGlobe size={14} />}
                value={form.region}
                onChange={(e) => set('region', e.target.value)}
                placeholder="美国区"
              />
            </Field>
            <Field label="状态">
              <SelectField
                value={form.status}
                onChange={(v) => set('status', v as AccountStatus | '')}
                panelHeader="留「自动」由 Cookie 决定"
                options={STATUS_OPTIONS}
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="健康度 %" htmlFor="acct-health">
              <IconInput
                id="acct-health"
                inputMode="numeric"
                value={String(form.health)}
                onChange={(e) => {
                  const raw = e.target.value.replace(/[^0-9]/g, '')
                  set('health', raw ? Math.min(100, Number(raw)) : 0)
                }}
                trailing={<span className="text-[11px] text-[var(--ink-400)]">0 – 100</span>}
              />
            </Field>
            <Field label="备注（可选）" htmlFor="acct-note">
              <input
                id="acct-note"
                className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] text-[var(--ink-900)] outline-none focus:border-[#18181b] placeholder:text-[var(--ink-400)]"
                value={form.note}
                onChange={(e) => set('note', e.target.value)}
                placeholder="例如：主店，待绑定实例"
              />
            </Field>
          </div>

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label
                htmlFor="acct-cookies"
                className="text-[12px] font-medium text-[var(--ink-700)]"
              >
                Cookie（可选，明文存储）
              </label>
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={(e) => {
                    void pickFile(e.target.files?.[0])
                    e.target.value = ''
                  }}
                />
                <button
                  type="button"
                  className="btn-ghost !h-7 !px-2.5 !text-[11.5px]"
                  onClick={() => fileRef.current?.click()}
                >
                  <IconUpload size={11} />
                  选择 storage_state.json
                </button>
                {form.cookiesText && (
                  <button
                    type="button"
                    className="btn-ghost !h-7 !px-2.5 !text-[11.5px]"
                    onClick={() => set('cookiesText', '')}
                  >
                    清空
                  </button>
                )}
              </div>
            </div>
            <textarea
              id="acct-cookies"
              className="h-[132px] w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3.5 py-3 font-mono text-[11.5px] leading-relaxed text-[var(--ink-900)] outline-none focus:border-[#18181b] placeholder:text-[var(--ink-400)]"
              value={form.cookiesText}
              onChange={(e) => set('cookiesText', e.target.value)}
              placeholder={'[{"name":"session-id","value":"...","domain":".amazon.com","path":"/"}]'}
              spellCheck={false}
            />
            {probe.error ? (
              <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
                <span className="mt-0.5 shrink-0">
                  <IconAlert size={11} />
                </span>
                <span className="min-w-0">{probe.error}</span>
              </div>
            ) : probe.count > 0 ? (
              <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700">
                <span className="mt-0.5 shrink-0">
                  <IconCheckCircle size={11} />
                </span>
                <span className="min-w-0">
                  识别到 {probe.count} 条 Cookie
                  {probe.domains.length > 0 && `（${probe.domains.join('、')}）`}
                  ，保存后账号记为已登录
                </span>
              </div>
            ) : (
              <p className="text-[11px] leading-relaxed text-[var(--ink-400)]">
                直接粘 Playwright <span className="font-mono">storage_state.json</span> 的整份内容，
                或只粘 <span className="font-mono">cookies</span> 数组。留空表示还没采集，
                账号记为未绑定。
              </p>
            )}
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[11.5px] text-rose-700">
              <span className="mt-0.5 shrink-0">
                <IconAlert size={12} />
              </span>
              <span className="min-w-0">{error}</span>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
