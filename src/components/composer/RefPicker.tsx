import { useEffect, useState } from 'react'
import { api, type FileEntry } from '../../lib/api'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { toast } from '../../stores/toastStore'

// "引用对话中的文件": pick a file from the current session/project workspace and
// attach its content to the next message. Content is fetched real from
// /api/files/content (text files only — binaries can't be fed as context).
type Scope = { project?: string; session?: string }

function flatten(entries: FileEntry[], out: FileEntry[] = []): FileEntry[] {
  for (const e of entries) {
    if (e.type === 'f') out.push(e)
    else if (e.children) flatten(e.children, out)
  }
  return out
}

export function RefPicker({ scope, onClose }: { scope: Scope; onClose: () => void }) {
  const [files, setFiles] = useState<FileEntry[] | null>(null)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState('')
  const addRef = useLoadoutStore((s) => s.addRef)

  useEffect(() => {
    let alive = true
    api
      .filesTree(scope)
      .then((r) => { if (alive) setFiles(flatten(r.entries)) })
      .catch(() => { if (alive) setFiles([]) })
    return () => { alive = false }
  }, [scope.project, scope.session])

  const pick = async (f: FileEntry) => {
    if (busy) return
    setBusy(f.path)
    try {
      const c = await api.fileContent(f.path, scope)
      if (c.kind !== 'text' || c.content == null) {
        toast('该文件不是文本，无法引用')
        return
      }
      addRef({ name: f.path, content: c.content })
      toast('已引用 · ' + f.name)
      onClose()
    } catch {
      toast('读取失败')
    } finally {
      setBusy('')
    }
  }

  const shown = (files ?? []).filter((f) => f.path.toLowerCase().includes(q.trim().toLowerCase()))

  return (
    <div className="np-overlay open" style={{ zIndex: 160 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal pk-modal mid" role="dialog" aria-modal="true" aria-label="引用对话中的文件">
        <div className="np-h">
          引用对话中的文件
          <div className="search-box" style={{ marginLeft: 'auto', width: 220 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input placeholder="搜索文件…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          </div>
          <button className="np-x" onClick={onClose}>×</button>
        </div>
        <div className="np-body" style={{ paddingTop: 2, minHeight: 120 }}>
          {files === null && <div className="rp-empty">加载中…</div>}
          {files !== null && shown.length === 0 && (
            <div className="rp-empty">{q ? '没有匹配的文件' : '当前工作空间还没有文件'}</div>
          )}
          {shown.map((f) => (
            <div className={`pkc-row ${busy === f.path ? 'sel' : ''}`.trim()} key={f.path} onClick={() => pick(f)}>
              <span className="pi">📄</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="pn">{f.name}</div>
                <div className="pd">{f.path}</div>
              </div>
              <span className="ckc">{busy === f.path ? '…' : '＋'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
