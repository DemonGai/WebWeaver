import { useMemo, useRef, useState } from 'react'
import { Modal } from '@/components/Modal'
import { Checkbox } from '@/components/ui'
import { ImportResultPanel } from '@/components/ImportResultPanel'
import { endpoints } from '@/api/endpoints'
import { IconAlert, IconDownload, IconUpload } from '@/components/icons'
import type { AccountImportResult } from '@/types/domain'

/** 示例与后端解析器的位置约定一一对应：登录地址,账号,邮箱,地区,健康度,备注 */
const SAMPLE = [
  'https://sellercentral.amazon.com/ap/signin,shop_us_101,shop_us_101@example.com,美国区,90,主店',
  'https://www.tiktok.com/login,kol_jp_022,kol_jp_022@example.com,日本区,100',
  'https://admin.shopify.com/store/shop-uk-007\tshop_uk_007\tshop_uk_007@example.com\t英国区\t85\t需要换 Cookie',
].join('\n')

/**
 * 批量导入账号。
 *
 * 和导入代理同一个套路：主体是一个大文本框，供应商 / 同事给的 CSV 直接
 * 整段粘进来；也可以上传文件。区别是账号清单通常就几列，所以额外提供一个
 * 「默认平台」——只粘一列账号名时（`shop_us_102`）靠它补齐平台。
 *
 * Cookie 不在这里导：它是大段 JSON，塞进 CSV 既会撑坏分隔符也不好核对，
 * 采集完在「编辑账号」里单独贴。
 */
export function AccountImportDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean
  onClose: () => void
  onImported: () => void
}) {
  const [text, setText] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AccountImportResult | null>(null)
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
    // Excel 导出的 CSV 带 BOM，不去掉第一列表头会变成 "\uFEFFlogin_url"
    setText((await file.text()).replace(/^\uFEFF/, ''))
    setResult(null)
    setError('')
  }

  const downloadTemplate = async () => {
    try {
      const csv = await endpoints.accountTemplate()
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url
      link.download = '账号导入模板.csv'
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
      const res = await endpoints.importAccounts({ text, overwrite })
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
      title="批量导入账号"
      subtitle="一行一个账号，第一列填登录地址，平台自动识别；同登录页的重复账号默认跳过"
      icon={<IconUpload size={16} />}
      width="max-w-[680px]"
      footer={
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--ink-400)]">
            {result
              ? `本次新增 ${result.created} 条${result.updated ? `、更新 ${result.updated} 条` : ''}`
              : lineCount > 0
                ? `识别到 ${lineCount} 行，同登录页同名账号会自动跳过`
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
          <ImportResultPanel result={result} unit="个账号" />
        ) : (
          <>
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor="acct-import-text"
                  className="text-[12px] font-medium text-[var(--ink-700)]"
                >
                  账号清单
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
                id="acct-import-text"
                className="h-[168px] w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3.5 py-3 font-mono text-[12px] leading-relaxed text-[var(--ink-900)] outline-none focus:border-[#18181b] placeholder:text-[var(--ink-400)]"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={SAMPLE}
                spellCheck={false}
              />
              <p className="text-[11px] leading-relaxed text-[var(--ink-400)]">
                列序：<span className="font-mono">登录地址, 账号, 邮箱, 地区, 健康度, 备注</span>；
                平台由地址自动识别（Amazon / Shopify / TikTok …），不用也不能手填；
                带表头的 CSV 按列名取值，列序颠倒也认；<span className="font-mono">#</span> 开头的行当注释忽略。
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="acct-import-overwrite"
                checked={overwrite}
                onChange={setOverwrite}
                label="覆盖已存在的账号"
              />
              <label
                htmlFor="acct-import-overwrite"
                className="cursor-pointer text-[12px] text-[var(--ink-700)]"
              >
                覆盖已存在的同登录页账号（只更新资料，不动 Cookie 与绑定关系）
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
