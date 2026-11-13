import { IconAlert, IconCheckCircle } from '@/components/icons'

/** 导入结果的最小形状：代理与账号两边字段完全一致 */
export type ImportSummary = {
  created: number
  updated: number
  skipped: number
  failed: number
  rows: { line: number; ok: boolean; label: string; message: string }[]
}

/**
 * 批量导入的结果面板：四个汇总数字 + 未导入行的明细。
 *
 * 代理和账号两个导入弹窗共用一份，只有「条代理 / 个账号」这种量词不同，
 * 所以量词由调用方传进来。全部成功时也保留面板（不自动关弹窗），
 * 用户能确认到底进了多少条。
 */
export function ImportResultPanel({ result, unit }: { result: ImportSummary; unit: string }) {
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
            ? `全部导入成功，新增 ${result.created} ${unit}`
            : `新增 ${result.created} ${unit}，跳过 ${result.skipped}，失败 ${result.failed}`}
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
