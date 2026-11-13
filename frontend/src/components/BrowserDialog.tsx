import { useEffect, useState, type ReactNode } from 'react'
import { endpoints } from '@/api/endpoints'
import { Modal } from '@/components/Modal'
import { Select as SelectControl } from '@/components/Select'
import { IconBolt, IconBrowser, IconCheck } from '@/components/icons'
import { ApiError } from '@/api/client'
import type { BrowserDetail, BrowserFormValues, BrowserOptions } from '@/types/domain'

/**
 * 新建 / 编辑实例表单。
 *
 * 新建与编辑共用一个组件：字段完全一致，差别只在标题、初始值，以及
 * 提交时打哪个接口。拆成两个组件会让「加个字段」变成改两处。
 *
 * 下拉里把「直连（本机 IP）」与「默认指纹」作为一等选项列出来，而不是
 * 留一个空白的「请选择」——它们在数据模型里是正常取值，不是「没填」。
 */
export function BrowserDialog({
  open,
  browserId,
  onClose,
  onSaved,
}: {
  open: boolean
  browserId: string | null
  onClose: () => void
  onSaved: (detail: BrowserDetail, created: boolean) => void
}) {
  const editing = Boolean(browserId)
  const [options, setOptions] = useState<BrowserOptions | null>(null)
  const [form, setForm] = useState<Required<Pick<BrowserFormValues, 'name'>> & BrowserFormValues>({
    name: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(false)

  // 每次打开都重新拉候选资源：别的标签页刚绑走一个账号，这里必须看到最新的占用状态
  useEffect(() => {
    if (!open) return
    setError(null)
    setLoading(true)
    Promise.all([
      endpoints.browserOptions(),
      browserId ? endpoints.browserDetail(browserId) : Promise.resolve(null),
    ])
      .then(([opts, detail]) => {
        setOptions(opts)
        if (detail) {
          setForm({
            name: detail.name,
            group_id: detail.group_id,
            kernel_id: detail.kernel_id,
            kernel_version: detail.kernel_version,
            account_id: detail.account_id,
            ip_id: detail.ip_id,
            fingerprint_id: detail.fingerprint_id,
            note: detail.note,
          })
        } else {
          setForm({
            name: '',
            group_id: null,
            kernel_id: null,
            kernel_version: null,
            account_id: null,
            ip_id: null,
            fingerprint_id: null,
            note: null,
          })
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '加载选项失败'))
      .finally(() => setLoading(false))
  }, [open, browserId])

  const patch = (next: BrowserFormValues) => setForm((prev) => ({ ...prev, ...next }))

  // 归一化后端的 { kernel_id: [versions] }，只保留当前选中内核的已下载版本
  const kernelVersions = form.kernel_id ? (options?.kernel_versions[form.kernel_id] ?? []) : []

  const submit = async () => {
    const name = (form.name ?? '').trim()
    if (name.length < 2) {
      setError('实例名至少 2 个字符')
      return
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) {
      setError('实例名只能包含字母、数字、点、下划线和短横线，且以字母或数字开头')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const body: BrowserFormValues = {
        group_id: form.group_id ?? null,
        kernel_id: form.kernel_id ?? null,
        kernel_version: form.kernel_version ?? null,
        account_id: form.account_id ?? null,
        ip_id: form.ip_id ?? null,
        fingerprint_id: form.fingerprint_id ?? null,
        note: form.note?.trim() ? form.note.trim() : null,
      }
      const detail = editing
        ? await endpoints.updateBrowser(browserId as string, { ...body, name })
        : await endpoints.createBrowser({ ...body, name })
      onSaved(detail, !editing)
    } catch (err) {
      // 后端把「账号已被 X 占用」这类原因写在 detail 里，原样展示比「请求失败」有用
      setError(err instanceof ApiError || err instanceof Error ? err.message : '保存失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      icon={editing ? <IconBolt size={15} /> : <IconBrowser size={15} />}
      title={editing ? `配置 ${form.name || '实例'}` : '新建浏览器实例'}
      subtitle={
        editing
          ? '绑定账号、出口 IP 与指纹模板；清空出口 IP 或指纹即切回直连与默认指纹'
          : '实例建好后为停止状态，绑定好账号与出口再启动接管'
      }
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-ghost !h-9">
            取消
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || loading}
            className="btn-dark !h-9 disabled:opacity-60"
          >
            {submitting ? '保存中…' : editing ? '保存配置' : '创建实例'}
          </button>
        </>
      }
    >
      {loading && <p className="py-10 text-center text-[12px] text-[var(--ink-400)]">加载中…</p>}

      {!loading && options && (
        <div className="pb-2">
          <Field label="实例名称" hint="唯一标识，如 brw-us-west-043">
            <input
              value={form.name ?? ''}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="brw-us-west-043"
              className="h-9 w-full rounded-xl border border-[var(--line)] bg-white px-3 text-[12.5px] text-[var(--ink-900)] outline-none focus:border-[#d4d4d8]"
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="分组">
              <Select
                value={form.group_id ?? ''}
                onChange={(v) => patch({ group_id: v || null })}
                placeholder="未分组"
                options={options.groups}
              />
            </Field>
            <Field label="内核">
              <Select
                value={form.kernel_id ?? ''}
                onChange={(v) => patch({ kernel_id: v || null, kernel_version: null })}
                placeholder="使用默认内核"
                options={options.kernels}
              />
            </Field>
          </div>

          {kernelVersions.length > 0 && (
            <Field label="内核版本" hint="留空则跟随该内核当前版本">
              <VersionSelect
                value={form.kernel_version ?? ''}
                onChange={(v) => patch({ kernel_version: v || null })}
                versions={kernelVersions}
                current={options.kernels.find((k) => k.id === form.kernel_id)?.hint ?? ''}
              />
            </Field>
          )}

          <Field label="平台账号" hint="一个账号只能绑一台实例">
            <Select
              value={form.account_id ?? ''}
              onChange={(v) => patch({ account_id: v || null })}
              placeholder="暂不绑定"
              options={options.accounts}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="出口 IP">
              <Select
                value={form.ip_id ?? ''}
                onChange={(v) => patch({ ip_id: v || null })}
                placeholder="直连（本机 IP）"
                options={options.ips}
              />
            </Field>
            <Field label="指纹模板">
              <Select
                value={form.fingerprint_id ?? ''}
                onChange={(v) => patch({ fingerprint_id: v || null })}
                placeholder="默认指纹（不套模板）"
                options={options.fingerprints}
              />
            </Field>
          </div>

          <Field label="备注">
            <input
              value={form.note ?? ''}
              onChange={(e) => patch({ note: e.target.value })}
              placeholder="用途、负责人等，可留空"
              className="h-9 w-full rounded-xl border border-[var(--line)] bg-white px-3 text-[12.5px] text-[var(--ink-900)] outline-none focus:border-[#d4d4d8]"
            />
          </Field>

          {error && (
            <div className="mt-3 rounded-xl bg-rose-50 px-3.5 py-2.5 text-[11.5px] text-rose-600">
              {error}
            </div>
          )}

          {!editing && (
            <div className="mt-3 flex items-start gap-2 rounded-xl bg-[#fafafa] px-3.5 py-2.5 text-[11px] text-[var(--ink-500)]">
              <span className="mt-[1px] shrink-0 text-emerald-500">
                <IconCheck size={11} />
              </span>
              创建后可随时在卡片上「启动 / 停止」，或点「绑定配置」重新调整资源
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="mt-4">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="label-xs">{label}</span>
        {hint && <span className="text-[10.5px] text-[var(--ink-400)]">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (value: string) => void
  options: { id: string; label: string; hint: string; disabled: boolean }[]
  placeholder: string
}) {
  const current = options.find((o) => o.id === value)
  return (
    <div>
      <SelectControl
        value={value}
        onChange={onChange}
        size="sm"
        options={[
          { value: '', label: placeholder },
          ...options.map((o) => ({
            value: o.id,
            label: o.label,
            hint: o.disabled ? '已被占用' : undefined,
            // 已被别的实例绑走的资源不能选，但仍然列出来 —— 看不到就不知道去向
            disabled: o.disabled,
          })),
        ]}
      />
      <p className="mt-1 min-h-[14px] truncate text-[10.5px] text-[var(--ink-400)]">
        {current?.hint ?? ''}
      </p>
    </div>
  )
}

/**
 * 内核版本下拉：只列磁盘上确实下载好的版本。
 * 留空表示跟随该内核的当前版本——老实例维持原状时就用这个口径。
 */
function VersionSelect({
  value,
  onChange,
  versions,
  current,
}: {
  value: string
  onChange: (value: string) => void
  versions: string[]
  current: string
}) {
  return (
    <div>
      <SelectControl
        value={value}
        onChange={onChange}
        size="sm"
        panelHeader="已下载版本"
        options={[
          { value: '', label: '跟随内核当前版本' },
          ...versions.map((version) => ({ value: version, label: version })),
        ]}
      />
      <p className="mt-1 min-h-[14px] truncate text-[10.5px] text-[var(--ink-400)]">
        {value ? `固定使用 ${value}` : `内核当前版本：${current || '—'}`}
      </p>
    </div>
  )
}
