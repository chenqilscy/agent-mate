import { useEffect, useState } from 'react'
import { api, type FileEntry } from '../../lib/api'
import { useUIStore } from '../../stores/uiStore'
import { clickable } from '../../lib/a11y'

export interface FileScope { project?: string; session?: string }

// Real workspace tree (spec M3). Fed by /api/files/tree; clicking a file opens it
// in the viewer. Dirs expand/collapse locally.
function iconFor(entry: FileEntry): string {
  if (entry.type === 'd') return '📁'
  const ext = entry.name.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    md: 'Ⓜ️', json: '🧾', html: '🌐', py: '🐍', svg: '🖼️', png: '🖼️', css: '🎨',
  }
  return map[ext] ?? '📄'
}

function Node({ entry, depth, onOpen }: { entry: FileEntry; depth: number; onOpen: (path: string) => void }) {
  const [open, setOpen] = useState(depth === 0)
  const viewerPath = useUIStore((s) => s.viewerPath)
  const isDir = entry.type === 'd'

  return (
    <>
      <div
        className={`ws-row ${!isDir && viewerPath === entry.path ? 'on' : ''}`.trim()}
        style={{ paddingLeft: 16 + depth * 16 }}
        {...clickable}
        onClick={() => (isDir ? setOpen((v) => !v) : onOpen(entry.path))}
      >
        <span className="wi">{iconFor(entry)}</span>
        {entry.name}
        {isDir && (
          <span className="wc">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d={open ? 'M6 9l6 6 6-6' : 'M9 6l6 6-6 6'} />
            </svg>
          </span>
        )}
      </div>
      {isDir && open && entry.children?.map((c) => <Node key={c.path} entry={c} depth={depth + 1} onOpen={onOpen} />)}
    </>
  )
}

export function FileTree({ scope }: { scope?: FileScope }) {
  const [entries, setEntries] = useState<FileEntry[] | null>(null)
  const openFile = useUIStore((s) => s.openFile)

  useEffect(() => {
    let alive = true
    setEntries(null)
    api.filesTree(scope).then((r) => alive && setEntries(r.entries)).catch(() => alive && setEntries([]))
    return () => {
      alive = false
    }
  }, [scope?.project, scope?.session])

  if (!entries) return <div className="ws-h">加载中…</div>
  if (entries.length === 0) {
    return (
      <div className="ov-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
        暂无文件<small>任务产出的文件会显示在这里</small>
      </div>
    )
  }
  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <div className="ws-h">工作空间</div>
      {entries.map((e) => <Node key={e.path} entry={e} depth={0} onOpen={openFile} />)}
    </div>
  )
}
