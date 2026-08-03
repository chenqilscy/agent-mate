import type { TraceItem } from '../../lib/types'
import { useUIStore } from '../../stores/uiStore'

// Renders accumulated trace items — one shape per event type (spec 5.2). The
// `cur` pulse on the last item while streaming reproduces the prototype's live
// trace. Full population of these events lands in M2; the renderer is ready now.
const IC_TOOL = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg>
const IC_EYE = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="8" /></svg>
const IC_PEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>
const IC_TODO = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" strokeDasharray="3 3" /></svg>

export function TraceStream({ trace, streaming }: { trace: TraceItem[]; streaming: boolean }) {
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
