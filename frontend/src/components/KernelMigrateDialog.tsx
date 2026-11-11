import { useEffect, useMemo, useState } from 'react'
import { endpoints } from '@/api/endpoints'
import { useApi } from '@/hooks/useApi'
import { Modal } from '@/components/Modal'
import { SelectMenu } from '@/components/SelectMenu'
import { Checkbox, SoftChip } from '@/components/ui'
import { IconAlert, IconInfo, IconRefresh } from '@/components/icons'
import type { KernelCard } from '@/types/domain'

/**
 * 批量迁移实例到某个内核版本。
 *
 * 只列「不在当前版本上」的实例：切换当前版本后，老实例留在旧版本上等着被迁，
 * 这里就是那批机器的清单。默认全选，允许取消个别实例（比如正在跑任务的）。
 */
export function KernelMigrateDialog({
  card,
  open,
  onClose,
  onDone,
}: {
  card: KernelCard | null
  open: boolean
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [target, setTarget] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const versionItems = useMemo(
    () =>
      (card?.versions ?? []).map((v) => ({
        value: v.version,
        label: v.version,
        count: v.instances,
      })),
    [card],
  )

  const {
    data: instances,
    status,
    reload,
  } = useApi(
    () => (open && card ? endpoints.kernelInstances(card.id, { stale: true }) : Promise.resolve([])),
    [open, card?.id],
  )

  useEffect(() => {
    if (!open || !card) return
    setTarget(card.current_version ?? '')
    setError('')
    setSelected([])
  }, [open, card])

  useEffect(() => {
    if (!instances) return
    // 默认全选：绝大多数场景就是"这批都要迁"
    setSelected(instances.map((item) => item.id))
  }, [instances])

  const allChecked = Boolean(instances?.length) && selected.length === (instances?.length ?? 0)

  const submit = async () => {
    if (!card || !target) return
    setSubmitting(true)
    setError('')
    try {
      const res = await endpoints.migrateKernelVersion(card.id, target, selected)
      onDone(res.message)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '迁移失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (!card) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="批量迁移实例版本"
      subtitle={`${card.name} · 当前版本 ${card.current_version ?? '未设置'}，还有 ${card.stale_count} 台实例留在旧版本上`}
      icon={<IconRefresh size={15} />}
      width="max-w-[560px]"
      footer={
        <>
          <button type="button" className="btn-ghost !h-9" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            disabled={submitting || selected.length === 0 || !target}
            onClick={submit}
            className="!h-9 inline-flex items-center gap-1.5 rounded-full bg-[#18181b] px-4 text-[13px] font-medium text-white hover:bg-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconRefresh size={12} />
            {submitting ? '迁移中…' : `迁移 ${selected.length} 台`}
          </button>
        </>
      }
    >
      <div className="pt-1">
        <div className="flex items-center justify-between gap-3 rounded-xl bg-[#fafafa] px-3.5 py-3">
          <div>
            <div className="text-[10.5px] text-[var(--ink-400)]">目标版本</div>
            <div className="mt-0.5 text-[11.5px] text-[var(--ink-500)]">
              迁移后实例会重启并加载该版本内核
            </div>
          </div>
          <SelectMenu
            value={target}
            items={versionItems}
            onChange={setTarget}
            placeholder="选择版本"
            panelHeader="已下载版本"
          />
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11.5px] text-[var(--ink-500)]">
            <Checkbox
              checked={allChecked}
              indeterminate={selected.length > 0 && !allChecked}
              onChange={(next) =>
                setSelected(next ? (instances ?? []).map((item) => item.id) : [])
              }
              label="全选待迁移实例"
            />
            已选 {selected.length} / {instances?.length ?? 0} 台
          </div>
          <button
            type="button"
            onClick={() => reload()}
            className="text-[11px] text-[var(--ink-400)] hover:text-[var(--ink-700)]"
          >
            重新读取
          </button>
        </div>

        <div className="mt-2 max-h-[260px] overflow-y-auto rounded-xl border border-[var(--line)]">
          {status === 'loading' ? (
            <div className="py-10 text-center text-[11.5px] text-[var(--ink-400)]">读取实例中…</div>
          ) : !instances || instances.length === 0 ? (
            <div className="py-10 text-center text-[11.5px] text-[var(--ink-400)]">
              该内核下没有留在旧版本的实例
            </div>
          ) : (
            instances.map((item) => (
              <label
                key={item.id}
                className="flex cursor-pointer items-center gap-3 border-b border-[var(--line)] px-3.5 py-2.5 last:border-0 hover:bg-[#fafafa]"
              >
                <Checkbox
                  checked={selected.includes(item.id)}
                  onChange={() =>
                    setSelected((prev) =>
                      prev.includes(item.id)
                        ? prev.filter((x) => x !== item.id)
                        : [...prev, item.id],
                    )
                  }
                  label={`选择 ${item.name}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] font-medium text-[var(--ink-900)]">
                    {item.name}
                  </div>
                  <div className="mt-0.5 truncate text-[10.5px] text-[var(--ink-400)]">
                    {item.group}
                  </div>
                </div>
                <span className="tnum shrink-0 text-[11px] text-[var(--ink-500)]">
                  {item.version ?? '跟随当前'}
                </span>
                <SoftChip tone={STATUS_TONE[item.status] ?? 'zinc'}>
                  {STATUS_LABEL[item.status] ?? item.status}
                </SoftChip>
              </label>
            ))
          )}
        </div>

        {error && (
          <div className="mt-3 flex items-start gap-1.5 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] text-rose-600">
            <IconAlert size={12} className="mt-[2px] shrink-0" />
            {error}
          </div>
        )}

        <p className="mt-3 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-[var(--ink-400)]">
          <IconInfo size={11} className="mt-[2px] shrink-0" />
          迁移只改实例绑定的版本号，旧版本目录不会删除，随时可以迁回去。
        </p>
      </div>
    </Modal>
  )
}

const STATUS_LABEL: Record<string, string> = {
  running: '运行中',
  idle: '空闲',
  queued: '排队中',
  error: '异常',
  stopped: '已停止',
}

const STATUS_TONE: Record<string, 'emerald' | 'blue' | 'amber' | 'rose' | 'zinc'> = {
  running: 'emerald',
  idle: 'blue',
  queued: 'amber',
  error: 'rose',
  stopped: 'zinc',
}
