import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

const base = (size = 16) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
})

const make = (path: React.ReactNode) =>
  function Icon({ size, ...rest }: IconProps) {
    return (
      <svg {...base(size)} {...rest}>
        {path}
      </svg>
    )
  }

export const IconOverview = make(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5v4.8l3.2 1.9" />
  </>,
)

export const IconBrowser = make(
  <>
    <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
    <path d="M3 9h18M6.6 6.8h.01M9.2 6.8h.01" />
  </>,
)

export const IconUser = make(
  <>
    <circle cx="12" cy="8.5" r="3.6" />
    <path d="M4.8 19.5c1.3-3.4 3.9-5 7.2-5s5.9 1.6 7.2 5" />
  </>,
)

export const IconGlobe = make(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.3 3.4 8.5S14.3 18.1 12 20.5c-2.3-2.4-3.4-5.3-3.4-8.5S9.7 5.9 12 3.5z" />
  </>,
)

export const IconFingerprint = make(
  <>
    <path d="M12 4.2c-2.1 0-4 .8-5.4 2.2M18.4 9.6A6.5 6.5 0 0 0 12 4.2" />
    <path d="M8.2 18.6c-.6-1.4-.9-2.9-.9-4.4a4.7 4.7 0 0 1 9.4 0c0 .9-.1 1.8-.3 2.6" />
    <path d="M12 9.7a4.5 4.5 0 0 1 4.5 4.5c0 1.3-.2 2.5-.6 3.6M9.3 16.6c.3-1.1.5-2.3.5-3.5a2.2 2.2 0 0 1 4.4 0" />
  </>,
)

export const IconTasks = make(
  <>
    <path d="M9 6.5h11M9 12h11M9 17.5h11" />
    <path d="M4.2 6.5l1.2 1.2 2-2.2M4.2 12l1.2 1.2 2-2.2M4.2 17.5l1.2 1.2 2-2.2" />
  </>,
)

export const IconSearch = make(
  <>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </>,
)

export const IconBell = make(
  <>
    <path d="M6.5 9.8a5.5 5.5 0 0 1 11 0c0 4 1.2 5.4 1.2 5.4H5.3s1.2-1.4 1.2-5.4z" />
    <path d="M10 18.5a2.2 2.2 0 0 0 4 0" />
  </>,
)

export const IconPlus = make(<path d="M12 5v14M5 12h14" />)
export const IconMinus = make(<path d="M5 12h14" />)

export const IconDownload = make(
  <>
    <path d="M12 4v10M8 10.5l4 4 4-4" />
    <path d="M5 18.5h14" />
  </>,
)

export const IconUpload = make(
  <>
    <path d="M12 15V5M8 8.5l4-4 4 4" />
    <path d="M5 18.5h14" />
  </>,
)

export const IconArrowUpRight = make(<path d="M8 16 16 8M9.5 8H16v6.5" />)
export const IconArrowRight = make(<path d="M5 12h13M13 6.5l5.5 5.5L13 17.5" />)
export const IconArrowLeft = make(<path d="M19 12H6M11 6.5 5.5 12 11 17.5" />)

export const IconChevronDown = make(<path d="m7 10 5 5 5-5" />)
export const IconChevronLeft = make(<path d="m14 7-5 5 5 5" />)
export const IconChevronRight = make(<path d="m10 7 5 5-5 5" />)

export const IconMore = make(
  <>
    <circle cx="12" cy="5.5" r="1.1" fill="currentColor" />
    <circle cx="12" cy="12" r="1.1" fill="currentColor" />
    <circle cx="12" cy="18.5" r="1.1" fill="currentColor" />
  </>,
)

export const IconExpand = make(<path d="M4.5 9V4.5H9M15 4.5h4.5V9M19.5 15v4.5H15M9 19.5H4.5V15" />)

export const IconShield = make(
  <>
    <path d="M12 3.8 19 6v5.4c0 4.3-2.9 7.3-7 8.8-4.1-1.5-7-4.5-7-8.8V6z" />
    <path d="m9 12 2 2 4-4" />
  </>,
)

export const IconWifi = make(
  <>
    <path d="M4 9.5a12 12 0 0 1 16 0M7 13a7.6 7.6 0 0 1 10 0M10 16.4a3.2 3.2 0 0 1 4 0" />
    <circle cx="12" cy="19.4" r="1" fill="currentColor" />
  </>,
)

export const IconSliders = make(
  <>
    <path d="M5 7h9M18 7h1M5 17h3M12 17h7" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="10" cy="17" r="2" />
  </>,
)

export const IconMonitor = make(
  <>
    <rect x="3" y="5" width="18" height="11.5" rx="2" />
    <path d="M9 20h6M12 16.5V20" />
  </>,
)

export const IconClock = make(
  <>
    <circle cx="12" cy="12" r="8.2" />
    <path d="M12 7.6V12l3 1.8" />
  </>,
)

export const IconTag = make(
  <>
    <path d="M12.6 4.2H19v6.4l-8.4 8.4a2 2 0 0 1-2.8 0l-3.6-3.6a2 2 0 0 1 0-2.8z" />
    <circle cx="15.8" cy="8.2" r="1.1" fill="currentColor" stroke="none" />
  </>,
)

export const IconX = make(<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />)
export const IconCheck = make(<path d="m5.5 12.5 4.2 4.2 8.8-9" />)

export const IconPause = make(
  <>
    <rect x="7" y="5.5" width="3.4" height="13" rx="1" />
    <rect x="13.6" y="5.5" width="3.4" height="13" rx="1" />
  </>,
)

export const IconRefresh = make(
  <>
    <path d="M19.2 12a7.2 7.2 0 1 1-2.1-5.1" />
    <path d="M19.5 4.5V9H15" />
  </>,
)

export const IconLink = make(
  <>
    <path d="M10 13.8a3.6 3.6 0 0 0 5.1 0l2.6-2.6a3.6 3.6 0 0 0-5.1-5.1l-1.4 1.4" />
    <path d="M14 10.2a3.6 3.6 0 0 0-5.1 0l-2.6 2.6a3.6 3.6 0 0 0 5.1 5.1l1.4-1.4" />
  </>,
)

// 「复制到剪贴板」用双矩形而不是「板 + 夹子」：夹子那根线在 11~12px 下
// 会糊成一个空心小方框，远看像在按钮前面多印了个「0」。
export const IconClipboard = make(
  <>
    <rect x="9" y="9" width="11" height="11" rx="2.4" />
    <path d="M5 15.2V5.6A1.6 1.6 0 0 1 6.6 4h9.6" />
  </>,
)

export const IconGrid = make(
  <>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
  </>,
)

export const IconList = make(
  <>
    <path d="M8.5 6.5h11M8.5 12h11M8.5 17.5h11" />
    <circle cx="4.8" cy="6.5" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="4.8" cy="12" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="4.8" cy="17.5" r="1.1" fill="currentColor" stroke="none" />
  </>,
)

export const IconFilter = make(<path d="M4.5 6.5h15l-5.8 6.6v5l-3.4 1.6v-6.6z" />)

export const IconPower = make(
  <>
    <path d="M12 4v7.5" />
    <path d="M7.3 7.2a6.5 6.5 0 1 0 9.4 0" />
  </>,
)

export const IconBolt = make(<path d="M13.2 3.5 6 13.4h4.6l-.8 7.1 7.2-9.9h-4.6z" />)

export const IconLayers = make(
  <>
    <path d="m12 3.8 8 4.3-8 4.3-8-4.3z" />
    <path d="m4 12.2 8 4.3 8-4.3M4 16.4l8 4.3 8-4.3" />
  </>,
)

export const IconTrend = make(<path d="M4 16.5 9 11l3.4 3.4L20 6.5M15.5 6.5H20V11" />)

export const IconActivity = make(<path d="M3.5 12h3.2l2.3-5.5 3.6 11 2.4-5.5h5.5" />)

export const IconTag2 = IconTag

export const IconLock = make(
  <>
    <rect x="5" y="10.5" width="14" height="9.5" rx="2.2" />
    <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
  </>,
)

export const IconSparkle = make(
  <path d="M12 3.8l1.7 4.9 4.9 1.7-4.9 1.7L12 17l-1.7-4.9L5.4 10.4l4.9-1.7z" />,
)

export const IconShare = make(
  <>
    <path d="M9 12.5 15 9M9 11.5l6 3.5" />
    <circle cx="6.5" cy="12" r="2.3" />
    <circle cx="17.5" cy="7.5" r="2.3" />
    <circle cx="17.5" cy="16.5" r="2.3" />
  </>,
)

/* ── 账号安全 / 表单相关 ──────────────────────────────── */
export const IconMail = make(
  <>
    <rect x="3" y="5.5" width="18" height="13" rx="2.4" />
    <path d="m4.4 7.3 6.4 4.9a2 2 0 0 0 2.4 0l6.4-4.9" />
  </>,
)

export const IconEye = make(
  <>
    <path d="M2.9 12S6.3 6.3 12 6.3 21.1 12 21.1 12 17.7 17.7 12 17.7 2.9 12 2.9 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </>,
)

export const IconEyeOff = make(
  <>
    <path d="m4.2 4.4 15.6 15.2" />
    <path d="M9.7 6.7A9.6 9.6 0 0 1 12 6.3c5.7 0 9.1 5.7 9.1 5.7a17 17 0 0 1-2.7 3.6" />
    <path d="M6.7 8.3A17.4 17.4 0 0 0 2.9 12S6.3 17.7 12 17.7c1.5 0 2.9-.4 4.1-1" />
  </>,
)

export const IconAlert = make(
  <>
    <path d="M10.6 5.1 3.2 18a1.6 1.6 0 0 0 1.4 2.4h14.8a1.6 1.6 0 0 0 1.4-2.4L13.4 5.1a1.6 1.6 0 0 0-2.8 0z" />
    <path d="M12 9.6v4M12 16.5h.01" />
  </>,
)

export const IconInfo = make(
  <>
    <circle cx="12" cy="12" r="8.4" />
    <path d="M12 11v5.2M12 8.1h.01" />
  </>,
)

export const IconBuilding = make(
  <>
    <rect x="4.5" y="3.8" width="15" height="16.4" rx="2" />
    <path d="M8.6 8h2M13.4 8h2M8.6 12h2M13.4 12h2M10 20.2v-3.6h4v3.6" />
  </>,
)

/* 浏览器内核管理 */
export const IconKernel = make(
  <>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
    <path d="M10 3.6v2.9M14 3.6v2.9M10 17.5v2.9M14 17.5v2.9M3.6 10h2.9M3.6 14h2.9M17.5 10h2.9M17.5 14h2.9" />
  </>,
)

/* ── 平台标识（指纹库列表用，实心小字形） ─────────────── */
export function IconWindows({ size = 16, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none" {...rest}>
      <rect x="3.6" y="3.6" width="7.6" height="7.6" rx="1.1" />
      <rect x="12.8" y="3.6" width="7.6" height="7.6" rx="1.1" />
      <rect x="3.6" y="12.8" width="7.6" height="7.6" rx="1.1" />
      <rect x="12.8" y="12.8" width="7.6" height="7.6" rx="1.1" />
    </svg>
  )
}

export function IconApple({ size = 16, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none" {...rest}>
      <path d="M12.1 7.9c-.8-1-2-1.6-3.1-1.5-2.2.2-3.9 2.3-3.9 5 0 3.4 2.5 6.6 4.6 6.6 1 0 1.5-.5 2.4-.5s1.4.5 2.4.5c2.1 0 4.6-3.2 4.6-6.6 0-2.7-1.7-4.8-3.9-5-1.1-.1-2.3.5-3.1 1.5z" />
      <path d="M12.4 6.3c.5-1.2 1.7-2 2.9-2.1-.1 1.3-.8 2.4-1.7 3" />
    </svg>
  )
}

export function IconAndroid({ size = 16, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      {...rest}
    >
      <path d="M5.2 16.2a6.8 6.8 0 0 1 13.6 0z" fill="currentColor" stroke="none" />
      <path d="M8.2 11.6 6.7 9.2M15.8 11.6l1.5-2.4" fill="none" />
      <circle cx="9.4" cy="13.6" r=".85" fill="#fff" stroke="none" />
      <circle cx="14.6" cy="13.6" r=".85" fill="#fff" stroke="none" />
    </svg>
  )
}


/* ── 内核管理 / 账号菜单补充图标 ───────────────────────── */
export const IconStar = make(
  <path d="m12 4.6 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4L4.2 10.3l5.4-.8z" />,
)

export function IconStarFilled({ size = 16, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" {...rest}>
      <path d="m12 4.6 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4L4.2 10.3l5.4-.8z" />
    </svg>
  )
}

export const IconBox = make(
  <>
    <path d="M20.2 8.4v7.2L12 20l-8.2-4.4V8.4L12 4z" />
    <path d="M3.8 8.4 12 12.8l8.2-4.4M12 12.8V20" />
  </>,
)

export const IconCloud = make(
  <path d="M7.2 17.5A3.9 3.9 0 0 1 7 9.7a5.2 5.2 0 0 1 10 .9 3.5 3.5 0 0 1-.5 6.9z" />,
)

export const IconCloudDown = make(
  <>
    <path d="M7.2 16.8A3.9 3.9 0 0 1 7 9a5.2 5.2 0 0 1 10 .9 3.5 3.5 0 0 1-.5 6.9" />
    <path d="M12 12.4v6.2M9.6 16.2 12 18.6l2.4-2.4" />
  </>,
)

export const IconGear = make(
  <>
    <circle cx="12" cy="12" r="3.1" />
    <path d="M19.2 13.6a7.6 7.6 0 0 0 0-3.2l1.5-1.1-1.9-3.3-1.8.7a7.5 7.5 0 0 0-2.8-1.6L13.9 3h-3.8l-.3 2.1a7.5 7.5 0 0 0-2.8 1.6l-1.8-.7-1.9 3.3 1.5 1.1a7.6 7.6 0 0 0 0 3.2l-1.5 1.1 1.9 3.3 1.8-.7a7.5 7.5 0 0 0 2.8 1.6l.3 2.1h3.8l.3-2.1a7.5 7.5 0 0 0 2.8-1.6l1.8.7 1.9-3.3z" />
  </>,
)

export const IconDevices = make(
  <>
    <rect x="2.8" y="5.4" width="12" height="9" rx="1.8" />
    <path d="M6 18.2h6" />
    <rect x="16.6" y="9.4" width="4.6" height="9" rx="1.4" />
  </>,
)

export const IconLogout = make(
  <>
    <path d="M14.4 6.4V4.8a1.6 1.6 0 0 0-1.6-1.6H5.4a1.6 1.6 0 0 0-1.6 1.6v14.4a1.6 1.6 0 0 0 1.6 1.6h7.4a1.6 1.6 0 0 0 1.6-1.6v-1.6" />
    <path d="M10.4 12h9.2M16.6 9 19.6 12l-3 3" />
  </>,
)

export const IconSwap = make(
  <>
    <path d="M5 8.4h13M14.8 5.2 18 8.4l-3.2 3.2" />
    <path d="M19 15.6H6M9.2 12.4 6 15.6l3.2 3.2" />
  </>,
)

export const IconWrench = make(
  <path d="M14.6 6.2a3.9 3.9 0 0 1 5.2 5.2l-8.2 8.2-3.8.8.8-3.8 8.2-8.2" />,
)

export const IconCheckCircle = make(
  <>
    <circle cx="12" cy="12" r="8.4" />
    <path d="m8.6 12 2.4 2.4 4.4-4.6" />
  </>,
)

export const IconTrash = make(
  <>
    <path d="M4.6 7h14.8M9.4 7V5.2A1.2 1.2 0 0 1 10.6 4h2.8a1.2 1.2 0 0 1 1.2 1.2V7" />
    <path d="M6.6 7l.8 11.4A1.6 1.6 0 0 0 9 20h6a1.6 1.6 0 0 0 1.6-1.6L17.4 7" />
  </>,
)

export const IconPlay = make(<path d="M8.4 5.6 18 12l-9.6 6.4z" />)

export const IconArrowUp = make(<path d="M12 19.5V5M6.4 10.6 12 5l5.6 5.6" />)

export const IconRocket = make(
  <>
    <path d="M14.4 4.6c2.2.6 4 2.4 4.6 4.6l-6.6 6.6-4.6-4.6z" />
    <path d="M8.6 11.2 5 12.2l-1.4 3.2 4 4 3.2-1.4.9-3.6" />
    <circle cx="15.6" cy="8.4" r="1.2" />
  </>,
)

export const IconRollback = make(
  <>
    <path d="M4.8 10.4h9.6a4.4 4.4 0 0 1 0 8.8H9.6" />
    <path d="M8.2 6.2 4 10.4l4.2 4.2" />
  </>,
)

export const IconCpu = make(
  <>
    <rect x="6.4" y="6.4" width="11.2" height="11.2" rx="2.2" />
    <rect x="10.2" y="10.2" width="3.6" height="3.6" rx="1" />
    <path d="M9.6 3.2v3.2M14.4 3.2v3.2M9.6 17.6v3.2M14.4 17.6v3.2M3.2 9.6h3.2M3.2 14.4h3.2M17.6 9.6h3.2M17.6 14.4h3.2" />
  </>,
)
