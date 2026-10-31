import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * 路由级错误兜底。
 *
 * 没有它的话，任何一页里一个 `undefined.tile` 就会让整个 React 树卸载，
 * 用户看到的是一片白屏、控制台一条报错——连"哪一页坏了"都不知道。
 * 这里把错误留在页面内，并给出可操作的出口（重试 / 回总览）。
 *
 * 重置策略：App 里用 ``key={location.pathname}`` 挂载，切页即重建边界，
 * 不会出现"修好了别的页仍卡在报错页"的情况。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 开发期把组件栈打全，定位是哪一行渲染炸的
    console.error('[ErrorBoundary] 页面渲染失败:', error, info.componentStack)
  }

  private reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="flex min-h-[70vh] items-center justify-center px-6">
        <div className="w-full max-w-[520px] rounded-2xl border border-[var(--line)] bg-white p-7">
          <div className="flex items-center gap-2 text-[15px] font-semibold text-[var(--ink-900)]">
            <span className="flex size-8 items-center justify-center rounded-xl bg-rose-50 text-rose-500">
              !
            </span>
            页面渲染失败
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--ink-500)]">
            这一页在渲染时抛了异常，其它页面不受影响。下面是具体报错，方便贴给开发排查。
          </p>
          <pre className="mt-3 max-h-[160px] overflow-auto rounded-xl bg-[#fafafa] p-3 text-[11.5px] leading-relaxed whitespace-pre-wrap text-rose-600">
            {error.message || String(error)}
          </pre>
          <div className="mt-5 flex items-center gap-2">
            <button type="button" className="btn-dark" onClick={this.reset}>
              重试
            </button>
            <Link to="/" className="btn-ghost" onClick={this.reset}>
              返回总览
            </Link>
          </div>
        </div>
      </div>
    )
  }
}
