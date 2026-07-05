import type { TraceItem } from '../../lib/types'
import { toast } from '../../stores/toastStore'

// Renders accumulated trace items — one shape per event type (spec 5.2). The
// `cur` pulse on the last item while streaming reproduces the prototype's live
// trace. Full population of these events lands in M2; the renderer is ready now.
const IC_TOOL = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg>
const IC_EYE = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="8" /></svg>
const IC_PEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>
const IC_TODO = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" strokeDasharray="3 3" /></svg>

export function TraceStream({ trace, streaming }: { trace: TraceItem[]; streaming: boolean }) {
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
                {IC_EYE}已读取 <a onClick={(e) => { e.preventDefault(); toast('打开 · ' + t.path) }}>{t.path}</a>
                {t.range && <span className="rng">{t.range}</span>}
              </div>
            )
          case 'diff':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_PEN}<span className="op">{t.op}</span>
                <a onClick={(e) => { e.preventDefault(); toast('打开 · ' + t.file) }}>{t.file}</a>
                <span className="add">+{t.add}</span><span className="del">-{t.del}</span>
              </div>
            )
          case 'todo':
            return (
              <div key={i} className={`step ${cur ? 'cur' : ''}`.trim()}>
                {IC_TODO}<span>{t.text}</span>
              </div>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
