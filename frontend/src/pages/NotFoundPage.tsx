import { Link } from 'react-router-dom'
import { PageShell } from '@/components/Layout'

export default function NotFoundPage() {
  return (
    <PageShell>
      <div className="flex flex-col items-center justify-center gap-3 py-28 text-center">
        <p className="text-[48px] leading-none font-semibold tracking-tight text-[var(--ink-300,#cbd5e1)]">
          404
        </p>
        <p className="text-[13px] text-[var(--ink-500)]">页面不存在</p>
        <Link
          to="/"
          className="mt-2 inline-flex h-9 items-center rounded-full bg-[#18181b] px-4 text-[12.5px] font-medium text-white"
        >
          返回集群总览
        </Link>
      </div>
    </PageShell>
  )
}
