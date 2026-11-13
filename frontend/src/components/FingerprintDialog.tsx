import { useMemo, useState } from 'react'
import { Modal } from '@/components/Modal'
import { Hint } from '@/components/Hint'
import { Field, IconInput, SelectField } from '@/components/fields'
import { SearchableSelect } from '@/components/Select'
import { IconFingerprint, IconRefresh, IconSparkle } from '@/components/icons'
import { endpoints } from '@/api/endpoints'
import type {
  FingerprintDetail,
  FingerprintFormValues,
  KernelFingerprintCaps,
  PlatformFamily,
} from '@/types/domain'

/**
 * 可选平台只留四个：两个桌面族 + 两个移动族。
 * Linux 桌面不提供 —— 指纹库里没有、筛选栏也没有，露出来只会让人建出一个
 * 在「全部」以外任何标签页都看不到的模板。库里若有历史 linux 模板，
 * 编辑时会把当前值临时补回下拉（见 platformOptions）。
 */
const FAMILIES: { value: PlatformFamily; label: string; hint?: string }[] = [
  { value: 'windows', label: 'Windows' },
  { value: 'macos', label: 'macOS' },
  { value: 'android', label: 'Android', hint: '伪移动' },
  { value: 'ios', label: 'iOS', hint: '伪移动' },
]

const FAMILY_LABELS: Record<PlatformFamily, string> = {
  windows: 'Windows',
  macos: 'macOS',
  linux: 'Linux',
  android: 'Android',
  ios: 'iOS',
}

/** 移动族底下实际跑的是桌面内核的哪一族人格：android→linux、ios→macos。 */
const PSEUDO_HOST: Record<string, string> = {
  android: 'Linux',
  ios: 'macOS',
}

/** 平台版本的占位值，跟着平台走，省得对着 Android 填 10.0.0。 */
const VERSION_PLACEHOLDER: Record<PlatformFamily, string> = {
  windows: '10.0.0',
  macos: '14.5.0',
  linux: '6.8.0',
  android: '13.0.0',
  ios: '17.5.0',
}

/** 常用时区，只是给输入框做提示，用户仍然可以手填任意 IANA 名。 */
const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Asia/Hong_Kong',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Los_Angeles',
]

const LANGUAGES = ['zh-CN', 'zh-TW', 'ja-JP', 'en-US', 'en-GB', 'de-DE', 'fr-FR']

/**
 * 新建 / 编辑指纹。
 *
 * 表单会按选中内核的能力实时显隐字段：选了 ungoogled-chromium 时所有指纹字段都
 * 灰掉并说明原因，选了 CloakBrowser 时「平台版本 / 品牌 / 硬件并发」不出现 ——
 * 因为那两个内核根本不认这些参数，摆出来只会让人以为设了就生效。
 */
export function FingerprintDialog({
  open,
  onClose,
  caps,
  initial,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  caps: KernelFingerprintCaps[]
  /** null 表示新建 */
  initial: FingerprintDetail | null
  onSaved: (detail: FingerprintDetail, mode: 'create' | 'edit') => void
}) {
  const supportedCaps = useMemo(() => caps.filter((c) => c.supported), [caps])
  const [form, setForm] = useState<FingerprintFormValues>(() => initForm(initial, supportedCaps))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const active =
    caps.find((c) => c.kernel_id === form.kernel_id) ?? null
  const features = new Set(active?.features ?? [])
  const seedRange = active?.seed_range ?? null

  const set = <K extends keyof FingerprintFormValues>(key: K, value: FingerprintFormValues[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const seedInvalid =
    form.seed != null &&
    seedRange != null &&
    (form.seed < seedRange[0] || form.seed > seedRange[1])

  const family = form.platform_family ?? 'windows'
  /** 移动族 → 实际承载它的桌面族；null 表示这是真平台。 */
  const pseudoHost = PSEUDO_HOST[family] ?? null
  // 历史 linux 模板不在 FAMILIES 里，编辑时得把当前值补回去，否则下拉显示空白
  const platformOptions = useMemo(() => {
    const opts: { value: string; label: string; hint?: string }[] = FAMILIES.map((item) => ({
      value: item.value as string,
      label: item.label,
      hint: item.hint,
    }))
    if (!FAMILIES.some((item) => item.value === family)) {
      opts.push({ value: family, label: FAMILY_LABELS[family] })
    }
    return opts
  }, [family])

  const randomize = () => {
    // 和后端 `PORTABLE_SEED_RANGE` 对齐：10000–99999，这个区间两个内核都收
    set('seed', 10000 + Math.floor(Math.random() * 90000))
  }

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const body: FingerprintFormValues & { name: string } = {
        ...form,
        name: (form.name ?? '').trim(),
      }
      const detail = initial
        ? await endpoints.updateFingerprint(initial.id, body)
        : await endpoints.createFingerprint(body)
      onSaved(detail, initial ? 'edit' : 'create')
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const nameMissing = !(form.name ?? '').trim()
  const blocked = !active?.supported || nameMissing || seedInvalid

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={initial ? '编辑指纹' : '新建指纹'}
      subtitle={
        initial
          ? '改种子等于换一个人，改完要重新采集才知道长什么样'
          : '种子决定整套人格，不给就随机分配一个'
      }
      icon={<IconFingerprint size={16} />}
      width="max-w-[640px]"
      footer={
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--ink-400)]">
            {active?.note || '种子是唯一输入，UA / 分辨率 / 显卡都是它算出来的'}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
              取消
            </button>
            <button type="button" className="btn-dark" onClick={submit} disabled={busy || blocked}>
              {busy ? '保存中…' : initial ? '保存' : '创建'}
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label="名称" htmlFor="fp-name">
          <input
            id="fp-name"
            className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] text-[var(--ink-900)] outline-none focus:border-[#18181b]"
            value={form.name ?? ''}
            onChange={(e) => set('name', e.target.value)}
            placeholder="例如 Win11 · 美国西岸"
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="适配内核">
            <SelectField
              value={form.kernel_id ?? ''}
              onChange={(v) => set('kernel_id', v || null)}
              placeholder="请选择"
              panelHeader="支持指纹的内核"
              options={[
                { value: '', label: '请选择', muted: true },
                ...supportedCaps.map((item) => ({ value: item.kernel_id, label: item.label })),
              ]}
            />
          </Field>

          <Field label="平台">
            <SelectField
              value={family}
              onChange={(v) => set('platform_family', v as PlatformFamily)}
              options={platformOptions}
            />
          </Field>
        </div>

        {pseudoHost && (
          <Hint tone="amber">
            伪移动：UA / 视口 / DPR 按 {FAMILY_LABELS[family]} 下发，
            navigator.platform、Client Hints、TLS 仍然是 {pseudoHost} 桌面。
            骗得过只看 UA 的站点，骗不过带风控的。
          </Hint>
        )}

        {active == null && (
          <Hint tone="zinc">
            只有 CloakBrowser 和 fingerprint-chromium 带指纹补丁。
            ungoogled-chromium 是纯净 Chromium、Camoufox 还没有镜像，这两个都选不了。
          </Hint>
        )}

        {active != null && !active.supported && (
          <Hint tone="rose">{active.reason ?? '这个内核不支持指纹'}</Hint>
        )}

        {active?.supported && (
          <>
            <Field label="种子" htmlFor="fp-seed">
              <IconInput
                id="fp-seed"
                icon={<IconSparkle size={14} />}
                inputMode="numeric"
                invalid={seedInvalid}
                value={form.seed ?? ''}
                onChange={(e) => {
                  const raw = e.target.value.replace(/[^0-9]/g, '')
                  set('seed', raw ? Number(raw) : null)
                }}
                placeholder={seedRange ? `${seedRange[0]} – ${seedRange[1]}` : ''}
                trailing={
                  <button
                    type="button"
                    onClick={randomize}
                    className="flex items-center gap-1 text-[11.5px] font-medium text-[var(--ink-500)] hover:text-[var(--ink-900)]"
                  >
                    <IconRefresh size={12} />
                    随机
                  </button>
                }
              />
            </Field>
            {seedInvalid && seedRange && (
              <p className="-mt-2 text-[11.5px] text-rose-600">
                {active.label} 的种子必须在 {seedRange[0]} – {seedRange[1]} 之间
              </p>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Field label="时区">
                <SearchableSelect
                  value={form.timezone ?? ''}
                  onChange={(v) => set('timezone', v)}
                  placeholder="Asia/Shanghai"
                  panelHeader="常用时区，也可直接输入"
                  options={TIMEZONES}
                />
              </Field>

              <Field label="界面语言">
                <SelectField
                  value={form.language ?? 'zh-CN'}
                  onChange={(v) => set('language', v)}
                  options={LANGUAGES.map((lang) => ({ value: lang, label: lang }))}
                />
              </Field>
            </div>

            {/* 下面这些只有 fingerprint-chromium 认，CloakBrowser 里种子一并决定 */}
            {(features.has('brand') ||
              features.has('platform_version') ||
              features.has('hardware_concurrency') ||
              features.has('accept_lang')) && (
              <div className="rounded-xl border border-[var(--line)] bg-[#fcfcfd] p-3.5">
                <p className="mb-3 text-[11.5px] text-[var(--ink-400)]">
                  可选微调项，留空就按种子算出来的值走
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {features.has('brand') && (
                    <Field label="浏览器品牌">
                      <SelectField
                        value={form.brand ?? ''}
                        onChange={(v) => set('brand', v || null)}
                        options={[
                          { value: '', label: '内核默认' },
                          { value: 'Chrome', label: 'Chrome' },
                          { value: 'Edge', label: 'Edge' },
                          { value: 'Opera', label: 'Opera' },
                        ]}
                      />
                    </Field>
                  )}
                  {features.has('platform_version') && (
                    <Field label="平台版本">
                      <input
                        className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] outline-none focus:border-[#18181b]"
                        value={form.platform_version ?? ''}
                        onChange={(e) => set('platform_version', e.target.value || null)}
                        placeholder={VERSION_PLACEHOLDER[family]}
                      />
                    </Field>
                  )}
                  {features.has('hardware_concurrency') && (
                    <Field label="硬件并发">
                      <input
                        inputMode="numeric"
                        className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] outline-none focus:border-[#18181b]"
                        value={form.hardware_concurrency ?? ''}
                        onChange={(e) => {
                          const raw = e.target.value.replace(/[^0-9]/g, '')
                          set('hardware_concurrency', raw ? Number(raw) : null)
                        }}
                        placeholder="按种子"
                      />
                    </Field>
                  )}
                  {features.has('accept_lang') && (
                    <Field label="Accept-Language">
                      <input
                        className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] outline-none focus:border-[#18181b]"
                        value={form.accept_lang ?? ''}
                        onChange={(e) => set('accept_lang', e.target.value || null)}
                        placeholder="按界面语言派生"
                      />
                    </Field>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {error && <Hint tone="rose">{error}</Hint>}
      </div>
    </Modal>
  )
}

function initForm(
  initial: FingerprintDetail | null,
  caps: KernelFingerprintCaps[],
): FingerprintFormValues {
  if (initial) {
    return {
      name: initial.name,
      kernel_id: caps.find((c) => c.slug === initial.kernel_slug)?.kernel_id ?? null,
      platform_family: initial.platform_family,
      seed: initial.seed,
      platform_version: initial.platform_version,
      brand: initial.brand,
      brand_version: initial.brand_version,
      hardware_concurrency: initial.hardware_concurrency,
      timezone: initial.timezone,
      language: initial.language,
      accept_lang: initial.accept_lang,
      canvas_noise: initial.canvas_noise,
      webgl_noise: initial.webgl_noise,
      audio_noise: initial.audio_noise,
      webrtc_protected: initial.webrtc_protected,
    }
  }
  return {
    name: '',
    kernel_id: caps[0]?.kernel_id ?? null,
    platform_family: 'windows',
    // 新建时先给一个种子：空种子会让内核自己随机，人格不可复现
    seed: 10000 + Math.floor(Math.random() * 90000),
    timezone: 'Asia/Shanghai',
    language: 'zh-CN',
  }
}
