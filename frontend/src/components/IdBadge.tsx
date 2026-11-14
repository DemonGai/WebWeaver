/**
 * 实例 ID 徽标。
 *
 * UUID 36 位在卡片上放不下，只露前 8 位；点一下复制完整值，
 * 排查日志、docker ps 对号时不用再翻详情页。
 */
export function IdBadge({ id, onCopy }: { id: string; onCopy: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        // 卡片/行本身可能有其它点击行为，别让复制连带触发
        e.stopPropagation()
        onCopy()
      }}
      title={`${id}\n点击复制完整 ID`}
      className="shrink-0 rounded-[5px] border border-[var(--line)] bg-[#f7f7f8] px-1 py-px font-mono text-[10px] leading-[14px] text-[var(--ink-500)] transition-colors hover:border-[#d9d9e0] hover:bg-[#f0f0f2] hover:text-[var(--ink-700)]"
    >
      {id.slice(0, 8)}
    </button>
  )
}
