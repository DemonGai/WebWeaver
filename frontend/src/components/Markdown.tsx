import type { ReactNode } from 'react'

/**
 * 极简 Markdown：只覆盖引擎 README 实际用到的语法
 * （标题、段落、无序/有序列表、引用、代码块、分隔线、行内 code / 粗体 / 链接）。
 *
 * 不引 react-markdown 的原因：为这点语法加 40KB 依赖不划算，
 * 而且这里全部用 React 元素拼，天然没有 dangerouslySetInnerHTML 的 XSS 面。
 */

type Block =
  | { type: 'h'; level: number; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'code'; lang: string; code: string }
  | { type: 'quote'; text: string }
  | { type: 'hr' }

const BLOCK_START = /^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|```)/

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (/^```/.test(line.trim())) {
      const lang = line.trim().slice(3).trim()
      const buf: string[] = []
      i += 1
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i])
        i += 1
      }
      i += 1 // 跳过收尾围栏
      blocks.push({ type: 'code', lang, code: buf.join('\n') })
      continue
    }

    if (!line.trim()) {
      i += 1
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      blocks.push({ type: 'h', level: heading[1].length, text: heading[2].trim() })
      i += 1
      continue
    }

    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ type: 'hr' })
      i += 1
      continue
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, '').trim())
        i += 1
      }
      blocks.push({ type: 'ul', items })
      continue
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, '').trim())
        i += 1
      }
      blocks.push({ type: 'ol', items })
      continue
    }

    if (/^\s*>/.test(line)) {
      const buf: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, '').trim())
        i += 1
      }
      blocks.push({ type: 'quote', text: buf.join(' ') })
      continue
    }

    // 段落：一直吃到空行或下一个块的起始标记
    const buf: string[] = []
    while (i < lines.length && lines[i].trim() && !BLOCK_START.test(lines[i])) {
      buf.push(lines[i].trim())
      i += 1
    }
    blocks.push({ type: 'p', text: buf.join(' ') })
  }

  return blocks
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  INLINE.lastIndex = 0

  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    const token = match[0]
    const key = `${keyBase}-${match.index}`

    if (token.startsWith('**')) {
      out.push(
        <strong key={key} className="font-semibold text-[var(--ink-900)]">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      out.push(
        <code
          key={key}
          className="rounded-[5px] bg-[#f4f4f5] px-1 py-[1px] font-mono text-[11.5px] text-[var(--ink-700)]"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token)
      if (link) {
        out.push(
          <a
            key={key}
            href={link[2]}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 underline decoration-blue-200 underline-offset-2 hover:decoration-blue-500"
          >
            {link[1]}
          </a>,
        )
      } else {
        out.push(token)
      }
    }
    last = match.index + token.length
  }

  if (last < text.length) out.push(text.slice(last))
  return out
}

/** 单行文本里的行内标记（`code`、**粗体**、链接）。
 *  档案里的 install_notes / pros / cons 是纯文本字段，但作者会写反引号，
 *  直接当字符串渲染会出现一对裸露的反引号，这里统一过一遍行内解析。 */
export function InlineMarkdown({ text }: { text: string }) {
  return <>{inline(text, 'in')}</>
}

const HEADING_CLASS: Record<number, string> = {  1: 'mt-1 mb-2 text-[16px] font-semibold tracking-tight text-[var(--ink-900)]',
  2: 'mt-4 mb-1.5 text-[13.5px] font-semibold text-[var(--ink-900)]',
  3: 'mt-3 mb-1 text-[12.5px] font-semibold text-[var(--ink-700)]',
  4: 'mt-3 mb-1 text-[12px] font-semibold text-[var(--ink-700)]',
}

export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text)

  return (
    <div className="text-[12.5px] leading-[1.75] text-[var(--ink-700)]">
      {blocks.map((block, index) => {
        const key = `b${index}`
        switch (block.type) {
          case 'h': {
            const Tag = `h${Math.min(6, block.level + 1)}` as 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
            return (
              <Tag key={key} className={HEADING_CLASS[block.level] ?? HEADING_CLASS[3]}>
                {inline(block.text, key)}
              </Tag>
            )
          }
          case 'p':
            return (
              <p key={key} className="my-1.5">
                {inline(block.text, key)}
              </p>
            )
          case 'ul':
            return (
              <ul key={key} className="my-1.5 space-y-1">
                {block.items.map((item, row) => (
                  <li key={`${key}-${row}`} className="flex gap-2">
                    <span className="mt-[7px] size-[3.5px] shrink-0 rounded-full bg-[var(--ink-400)]" />
                    <span className="min-w-0 flex-1">{inline(item, `${key}-${row}`)}</span>
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={key} className="my-1.5 space-y-1">
                {block.items.map((item, row) => (
                  <li key={`${key}-${row}`} className="flex gap-2">
                    <span className="tnum mt-[1px] w-4 shrink-0 text-[11px] text-[var(--ink-400)]">
                      {row + 1}.
                    </span>
                    <span className="min-w-0 flex-1">{inline(item, `${key}-${row}`)}</span>
                  </li>
                ))}
              </ol>
            )
          case 'code':
            return (
              <pre
                key={key}
                className="my-2 overflow-x-auto rounded-xl bg-[#18181b] px-3.5 py-2.5 text-[11.5px] leading-[1.7] text-[#e4e4e7]"
              >
                <code className="font-mono">{block.code}</code>
              </pre>
            )
          case 'quote':
            return (
              <blockquote
                key={key}
                className="my-2 border-l-2 border-[#e4e4e7] pl-3 text-[12px] text-[var(--ink-500)]"
              >
                {inline(block.text, key)}
              </blockquote>
            )
          case 'hr':
            return <hr key={key} className="my-3 border-t border-[var(--line)]" />
          default:
            return null
        }
      })}
    </div>
  )
}
