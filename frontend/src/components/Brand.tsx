/** 品牌标识：Header 与账号安全页共用，避免两处各画一份。 */
export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <div
      className="flex items-center justify-center rounded-xl bg-[#18181b]"
      style={{ width: size, height: size }}
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none">
        <path
          d="M4 7.5 7.4 17h2.2L12 10.4 14.4 17h2.2L20 7.5"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  )
}

export function BrandLockup({
  vertical = false,
  markSize = 36,
}: {
  vertical?: boolean
  markSize?: number
}) {
  return (
    <div className={vertical ? 'flex flex-col items-center gap-2.5' : 'flex items-center gap-2.5'}>
      <BrandMark size={markSize} />
      <div className={vertical ? 'text-center leading-none' : 'leading-none'}>
        <div className="text-[14px] font-semibold tracking-tight text-[var(--ink-900)]">
          WebWeaver 浏览器集群
        </div>
        <div className="mt-1 text-[9.5px] font-medium tracking-[0.08em] text-[var(--ink-400)] uppercase">
          Browser Cluster Console
        </div>
      </div>
    </div>
  )
}
