import { useState, type ReactNode } from 'react'
import type { ChatMessage } from '../../lib/types'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { FileTree } from './FileTree'
import { FileViewer } from './FileViewer'
import { clickable } from '../../lib/a11y'

// Project-execution side panel (spec 4.2): 产物 / 工作空间文件 / 变更. The 变更 tab
// lists every diff the agent made (the real "变更(N)" list); 产物 lists the unique
// output files. Both derive from the diff trace — real, and replay from history.
type Tab = 'prod' | 'files' | 'diff'

interface Diff { op: string; file: string; add: number; del: number }

function allDiffs(messages: ChatMessage[]): Diff[] {
  const out: Diff[] = []
  for (const m of messages) {
    if (m.role !== 'assistant') continue
    for (const t of m.trace) if (t.kind === 'diff') out.push({ op: t.op, file: t.file, add: t.add, del: t.del })
  }
  return out
}

function artifacts(messages: ChatMessage[]): { path: string; name: string; op: string }[] {
  const byPath = new Map<string, { path: string; name: string; op: string }>()
  for (const d of allDiffs(messages)) byPath.set(d.file, { path: d.file, name: d.file.split('/').pop() ?? d.file, op: d.op })
  return [...byPath.values()]
}

const IC_PEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>

export function PePanel({ messages }: { messages: ChatMessage[] }) {
  const [tab, setTab] = useState<Tab>('prod')
  const viewerPath = useUIStore((s) => s.viewerPath)
  const openFile = useUIStore((s) => s.openFile)
  const closeFile = useUIStore((s) => s.closeFile)
  const activeId = useChatStore((s) => s.activeId)
  const scope = activeId ? { session: activeId } : undefined

  const diffs = allDiffs(messages)
  const arts = artifacts(messages)

  const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: 'prod', label: '产物', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg> },
    { id: 'files', label: '工作空间文件', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg> },
    { id: 'diff', label: `变更${diffs.length ? ` (${diffs.length})` : ''}`, icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6" /></svg> },
  ]

  return (
    <aside className="ovpanel pe open">
      <div className="ov-inner">
        <div className="pe-tabs">
          {TABS.map((t) => (
            <span key={t.id} className={`pe-tab ${tab === t.id ? 'active' : ''}`.trim()} {...clickable} onClick={() => { setTab(t.id); if (t.id !== 'prod') closeFile() }}>
              {t.icon}{t.label}
            </span>
          ))}
        </div>

        {viewerPath ? (
          <FileViewer path={viewerPath} onClose={closeFile} scope={scope} />
        ) : tab === 'prod' ? (
          arts.length ? (
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {arts.map((a) => (
                <div className="ov-art" key={a.path} {...clickable} onClick={() => openFile(a.path)}>
                  <span className="oa-ic">{(a.name.split('.').pop()?.toUpperCase() ?? '').slice(0, 3) || 'F'}</span>
                  <div style={{ minWidth: 0 }}><div className="oa-n">{a.name}</div><div className="oa-m">{a.op} · 工作空间产物</div></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pe-empty">请开始执行，任务产出的产物会显示在这里</div>
          )
        ) : tab === 'files' ? (
          <FileTree scope={scope} />
        ) : diffs.length ? (
          <div style={{ flex: 1, overflowY: 'auto', padding: '10px 14px' }}>
            {diffs.map((d, i) => (
              <div className="step" key={i} {...clickable} onClick={() => openFile(d.file)} style={{ cursor: 'pointer' }}>
                {IC_PEN}<span className="op">{d.op}</span>
                <a>{d.file}</a>
                <span className="add">+{d.add}</span><span className="del">-{d.del}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="pe-empty">暂无变更</div>
        )}
      </div>
    </aside>
  )
}
