/**
 * 时间格式化：后端一律返回 UTC 的 ISO 串，这里按浏览器本地时区展示。
 * 不做成「几秒前」的全局默认——审计和安全页要把时间原样贴进工单。
 */

const pad = (n: number) => String(n).padStart(2, '0')

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 相对时间，只用在「最近活跃」这类辅助信息上。 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'

  const diff = Date.now() - date.getTime()
  if (diff < 0) return formatDateTime(iso)

  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return formatDate(iso)
}

/**
 * 未来还有多久（毫秒时间戳）。用于「登录有效期还剩 6 天」这类倒计时。
 *
 * 与 `formatRelative` 方向相反：那个算过去，这个算未来。
 */
export function formatRemaining(at: number | null | undefined): string {
  if (!at) return '—'
  const diff = at - Date.now()
  if (diff <= 0) return '已过期'

  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '不到 1 分钟'
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时`
  return `${Math.floor(hours / 24)} 天`
}
