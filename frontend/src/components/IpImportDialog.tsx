import { useMemo, useRef, useState } from 'react'
import { Modal } from '@/components/Modal'
import { Field, SelectField } from '@/components/fields'
import { Checkbox } from '@/components/ui'
import { endpoints } from '@/api/endpoints'
import {
  IconAlert,
  IconCheckCircle,
  IconDownload,
  IconUpload,
} from '@/components/icons'
import type { IpImportResult } from '@/types/domain'

const KIND_OPTIONS = [
  { value: 'residential', label: '住宅', hint: '默认' },
  { value: 'datacenter', label: '机房' },
  { value: 'mobile', label: '移动' },
]

/** 弹窗里的示例：三种写法各一行，跟后端解析器的三条分支一一对应。 */
const SAMPLE = [
  'socks5://brd-customer-hl_us02:uS8nC5mQ@104.28.16.74:8000',
  '45.132.88.19:1080:iproyal_user:pa55w0rd',
  '185.199.108.153,3128,https,mobile-01,p@ssw0rd,mobile,Oxylabs,JP,Tokyo,Tokyo',
].join('\n')

/**
 * 批量导入代理。
 *
 * 这页最常见的一步操作是「把供应商后台的清单整段粘进来」，所以弹窗主体就是
 * 一个大文本框，而不是一行一行的表单。模板单独给下载入口：CSV 带 BOM，
 * 用户拿 Excel 打开列名不会变乱码，填完再粘回来或直接上传都行。
 */
export function IpImportDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean
  onClose: () => void
  onImported: () => void
}) {
  const [text, setText] = useState('')
  const [kind, setKind] = useState('residential')
  const [supplier, setSupplier] = useState('未标注')
  const [overwrite, setOverwrite] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<IpImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  /** 行数只做参考：表头与注释行后端会跳过，这里不重复那套判断 */
  const lineCount = useMemo(
    () => text.split('\n').filter((line) => line.trim() && !line.trim().startsWith('#')).length,
    [text],
  )

  const reset = () => {
    setText('')
    setResult(null)
    setError('')
    setBusy(false)
  }

  const close = () => {
    reset()
    onClose()
  }

  const pickFile = async (file: File | undefined) => {
    if (!file) return
    // Excel 导出的 CSV 带 BOM，不去掉的话第一列表头会变成 "\uFEFFip"
    const content = (await file.text()).replace(/^\uFEFF/, '')
    setText(content)
    setResult(null)
    setError('')
  }

  const downloadTemplate = async () => {
    try {
      const csv = await endpoints.ipTemplate()
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url
      link.download = '代理导入模板.csv'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await endpoints.importIps({
        text,
        default_kind: kind as 'residential' | 'datacenter' | 'mobile',
        default_supplier: supplier.trim() || '未标注',
        overwrite,
      })
      setResult(res)
      onImported()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const blocked = !text.trim() || busy
  const hasProblem = result != null && (result.failed > 0 || result.skipped > 0)

  return (
    <Modal
      open={open}
      onClose={close}
      title="导入代理"
      subtitle="一行一个代理，支持 URL / 地址:端口:账号:密码 / CSV 三种写法"
      icon={<IconUpload size={16} />}
      width="max-w-[680px]"
      footer={
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--ink-400)]">
            {result
              ? `本次新增 ${result.created} 条${result.updated ? `、更新 ${result.updated} 条` : ''}`
              : lineCount > 0
                ? `识别到 ${lineCount} 行，地址端口重复的会自动跳过`
                : '还没粘内容：也可以先下载模板，填好再上传'}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            {result ? (
              <button type="button" className="btn-dark" onClick={close}>
                完成
              </button>
            ) : (
              <>
                <button type="button" className="btn-ghost" onClick={close} disabled={busy}>
                  取消
                </button>
                <button type="button" className="btn-dark" onClick={submit} disabled={blocked}>
                  {busy ? '导入中…' : lineCount > 0 ? `导入 ${lineCount} 条` : '导入'}
                </button>
              </>
            )}
          </div>
        </div>
      }
    >
      <div className="space-y-4 pb-2">
        {result ? (
          <ResultPanel result={result} />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="默认类型">
                <SelectField
                  value={kind}
                  onChange={setKind}
                  panelHeader="清单里没写类型时用这个"
                  options={KIND_OPTIONS}
                />
              </Field>
              <Field label="默认供应商" htmlFor="ip-import-supplier">
                <input
                  id="ip-import-supplier"
                  className="h-11 w-full rounded-xl border border-[var(--line)] bg-white px-3.5 text-[13px] text-[var(--ink-900)] outline-none focus:border-[#18181b] placeholder:text-[var(--ink-400)]"
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                  placeholder="例如 Bright Data"
                />
              </Field>
            </div>

            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor="ip-import-text"
                  className="text-[12px] font-medium text-[var(--ink-700)]"
                >
                  代理清单
                </label>
                <div className="flex items-center gap-2">
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".csv,.txt,text/csv,text/plain"
                    className="hidden"
                    onChange={(e) => {
                      void pickFile(e.target.files?.[0])
                      // 清空 value：同一个文件连选两次也要能触发 change
                      e.target.value = ''
                    }}
                  />
                  <button
                    type="button"
                    className="btn-ghost !h-7 !px-2.5 !text-[11.5px]"
                    onClick={() => fileRef.current?.click()}
                  >
                    <IconUpload size={11} />
                    选择文件
                  </button>
                  <button
                    type="button"
                    className="btn-ghost !h-7 !px-2.5 !text-[11.5px]"
                    onClick={downloadTemplate}
                  >
                    <IconDownload size={11} />
                    下载模板
                  </button>
                </div>
              </div>
              <textarea
                id="ip-import-text"
                className="h-[168px] w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3.5 py-3 font-mono text-[12px] leading-relaxed text-[var(--ink-900)] outline-none focus:border-[#18181b] placeholder:text-[var(--ink-400)]"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={SAMPLE}
                spellCheck={false}
              />
              <p className="text-[11px] leading-relaxed text-[var(--ink-400)]">
                认这么多写法：<span className="font-mono">socks5://账号:密码@地址:端口</span>、
                <span className="font-mono">地址:端口:账号:密码</span>、带表头的 CSV；
                <span className="font-mono">#</span> 开头的行当注释忽略。
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="ip-import-overwrite"
                checked={overwrite}
                onChange={setOverwrite}
                label="覆盖已存在的地址端口"
              />
              <label
                htmlFor="ip-import-overwrite"
                className="cursor-pointer text-[12px] text-[var(--ink-700)]"
              >
                覆盖已存在的同地址端口（默认跳过，不覆盖已有账号密码）
              </label>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[11.5px] text-rose-700">
                <span className="mt-0.5 shrink-0">
                  <IconAlert size={12} />
                </span>
                <span className="min-w-0">{error}</span>
              </div>
            )}
          </>
        )}

        {result && hasProblem && (
          <button type="button" className="btn-ghost" onClick={reset}>
            再导一批
          </button>
        )}
      </div>
    </Modal>
  )
}

function ResultPanel({ result }: { result: IpImportResult }) {
  const allOk = result.failed === 0 && result.skipped === 0
  return (
    <div className="space-y-3">
      <div
        className={`flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-[11.5px] ${
          allOk
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-amber-200 bg-amber-50 text-amber-700'
        }`}
      >
        <span className="mt-0.5 shrink-0">
          {allOk ? <IconCheckCircle size={12} /> : <IconAlert size={12} />}
        </span>
        <span className="min-w-0">
          {allOk
            ? `全部导入成功，新增 ${result.created} 条代理`
            : `新增 ${result.created} 条，跳过 ${result.skipped} 条，失败 ${result.failed} 条`}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <Metric label="新增" value={result.created} tone="emerald" />
        <Metric label="更新" value={result.updated} tone="blue" />
        <Metric label="跳过" value={result.skipped} tone="zinc" />
        <Metric label="失败" value={result.failed} tone={result.failed > 0 ? 'rose' : 'zinc'} />
      </div>

      {result.rows.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-[var(--line)]">
          <div className="border-b border-[var(--line)] bg-[#fafafa] px-3 py-2 text-[11px] font-medium text-[var(--ink-500)]">
            未导入的行（最多显示 50 条）
          </div>
          <div className="max-h-[220px] overflow-y-auto">
            {result.rows.map((row) => (
              <div
                key={`${row.line}-${row.label}`}
                className="flex items-start gap-2.5 border-b border-[#f4f4f6] px-3 py-2 text-[11.5px] last:border-0"
              >
                <span className="w-8 shrink-0 text-right text-[10.5px] text-[var(--ink-400)]">
                  L{row.line}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--ink-700)]">
                  {row.label || '（空）'}
                </span>
                <span className="shrink-0 text-[10.5px] text-rose-600">{row.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'emerald' | 'blue' | 'rose' | 'zinc'
}) {
  const color =
    tone === 'emerald'
      ? 'text-emerald-600'
      : tone === 'blue'
        ? 'text-blue-600'
        : tone === 'rose'
          ? 'text-rose-600'
          : 'text-[var(--ink-500)]'
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[#fcfcfd] px-3 py-2.5">
      <div className="text-[10.5px] text-[var(--ink-400)]">{label}</div>
      <div className={`tnum mt-0.5 text-[18px] leading-none font-semibold ${color}`}>{value}</div>
    </div>
  )
}
