import { useCallback, useEffect, useState } from 'react'

type State<T> =
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: string }

/**
 * 轻量数据请求 hook：组件挂载时拉取，支持手动刷新。
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<State<T>>({ status: 'loading', data: null, error: null })

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps)

  const load = useCallback(() => {
    let cancelled = false
    setState({ status: 'loading', data: null, error: null })
    run()
      .then((data) => {
        if (!cancelled) setState({ status: 'success', data, error: null })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            status: 'error',
            data: null,
            error: err instanceof Error ? err.message : '请求失败',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [run])

  useEffect(load, [load])

  return { ...state, reload: load }
}
