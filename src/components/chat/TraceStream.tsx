import { useState } from 'react'
import { api } from '../../lib/api'
import type { RunPlanItem, TraceItem } from '../../lib/types'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { WbButton } from '../ui/Primitives'

// Renders accumulated trace items — one shape per event type (spec 5.2). The
// `cur` pulse on the last item while streaming reproduces the prototype's live
// trace. Full population of these events lands in M2; the renderer is ready now.
const IC_TOOL = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg>
const IC_EYE = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="8" /></svg>
const IC_PEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>
const IC_TODO = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" strokeDasharray="3 3" /></svg>

const PLAN_STATUS: Record<RunPlanItem['status'], string> = {
  pending: '○', in_progress: '◉', completed: '✓', blocked: '!',
}

function RunPlanTrace({
  version, items, projectId, runId, cur,
}: {
  version: number
  items: RunPlanItem[]
  projectId?: string | null
  runId?: string
  cur: boolean
}) {
  const [promoted, setPromoted] = useState<Record<string, string>>(() => Object.fromEntries(
    items.filter((item) => item.work_item_id).map((item) => [item.id, item.work_item_id as string]),
  ))
  const [busy, setBusy] = useState('')

  const promote = async (item: RunPlanItem) => {
    if (!runId || busy) return
    setBusy(item.id)
    try {
      const result = await api.promoteRunPlanItem(runId, item.id)
      setPromoted((current) => ({ ...current, [item.id]: result.work_item.id }))
      toast(result.created ? '已提升为项目任务' : '该项目任务已存在')
    } catch (error) {
      toast(error instanceof Error ? error.message : '提升项目任务失败')
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className={`step ${cur ? 'cur' : ''}`.trim()}>
        {IC_TODO}<span>执行计划 v{version} · {items.length} 项</span>
      </div>
      {items.map((item) => (
        <div className="step" key={item.id}>
          <span aria-label={item.status}>{PLAN_STATUS[item.status]}</span>
          <span>{item.title}</span>
          {item.depends_on.length > 0 && <span className="rng">依赖 {item.depends_on.length}</span>}
          {projectId && runId && (
            promoted[item.id]
              ? <span className="rng">已进入项目任务</span>
              : <WbButton className="wb-td-editlink" disabled={busy === item.id} onClick={() => void promote(item)}>
                  {busy === item.id ? '提升中…' : '提升为任务'}
                </WbButton>
          )}
        </div>
      ))}
    </div>
  )
}

export function TraceStream({ trace, streaming, runId }: { trace: TraceItem[]; streaming: boolean; runId?: string }) {
  const openFile = useUIStore((s) => s.openFile)
  if (!trace.length) return null
  const lastIdx = trace.length - 1
  return (
    <div className="trace">
      {trace.map((t, i) => {
        const cur = streaming && i === lastIdx
        switch (t.kind) {
          case 'think':
            return <div key={i} className={`think ${cur ? 'cur' : ''}`.trim()}>{t.text}</div>
          case 'step':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_TOOL}<span>{t.label}</span>
              </div>
            )
          case 'file_read':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_EYE}已读取 <a onClick={(e) => { e.preventDefault(); openFile(t.path) }}>{t.path}</a>
                {t.range && <span className="rng">{t.range}</span>}
              </div>
            )
          case 'diff':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_PEN}<span className="op">{t.op}</span>
                <a onClick={(e) => { e.preventDefault(); openFile(t.file) }}>{t.file}</a>
                <span className="add">+{t.add}</span><span className="del">-{t.del}</span>
              </div>
            )
          case 'todo':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_TODO}<span>{t.text}</span>
              </div>
            )
          case 'plan_snapshot':
          case 'plan_patch':
            return (
              <RunPlanTrace
                key={`${t.kind}-${t.version}`}
                version={t.version}
                items={t.items}
                projectId={t.project_id}
                runId={runId}
                cur={cur}
              />
            )
          case 'qa':
            return (
              <div key={i}>
                <div className="step">🙋 向用户提问</div>
                <div className="qa-card">
                  {t.qa.map((p, j) => (
                    <div key={j}>
                      <div className="qa-q">{p.q}</div>
                      <div className="qa-a">{p.a}</div>
                    </div>
                  ))}
                </div>
              </div>
            )
          case 'context_degraded':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                <span>⚠</span>
                <span>较早对话压缩失败，本轮仅带入 {t.excerpt_messages} 条受控原文摘录；下轮会重试压缩。</span>
              </div>
            )
          case 'artifact':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_PEN}<span className="op">交付</span>
                <a onClick={(e) => { e.preventDefault(); openFile(t.artifact.path) }}>{t.artifact.name}</a>
                <span className="rng">{t.artifact.acceptance_status === 'accepted' ? '已验收' : '待验收'}</span>
              </div>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
