import { useEffect, useState } from 'react'
import { api, type FileContent } from '../../lib/api'
import { renderMarkdown } from '../../lib/markdown'
import type { FileScope } from './FileTree'

// Real file viewer (spec M3): Markdown files render through the markdown pipeline;
// text/code render with a line-number gutter; binaries show a placeholder.
const ICONS: Record<string, string> = {
  md: 'Ⓜ️', json: '🧾', js: '📄', ts: '📄', tsx: '📄', jsx: '📄',
  py: '🐍', css: '🎨', html: '🌐', txt: '📄', yaml: '📄', yml: '📄',
  sh: '📄', svg: '🖼️', png: '🖼️', jpg: '🖼️',
}

function iconFor(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  return ICONS[ext] ?? '📄'
}

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]!))
}

export function FileViewer({ path, onClose, scope }: { path: string; onClose: () => void; scope?: FileScope }) {
  const [file, setFile] = useState<FileContent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const name = path.split('/').pop() ?? path

  useEffect(() => {
    let alive = true
    setFile(null)
    setError(null)
    api
      .fileContent(path, scope)
      .then((f) => alive && setFile(f))
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [path, scope?.project, scope?.session])

  const isMd = name.toLowerCase().endsWith('.md')
  const download = () => {
    const a = document.createElement('a')
    a.href = api.downloadUrl(path, scope)
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
  const counts = file?.kind === 'text' && file.content != null
    ? { lines: file.content.split('\n').length, chars: file.content.length }
    : null

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div className="pv-tabbar">
        <span className="pv-tab">
          <span>{iconFor(name)}</span>
          <span>{name}</span>
          <span className="pv-x" onClick={onClose}>×</span>
        </span>
      </div>
      <div className="pv-body">
        {error && <div className="pe-empty" style={{ padding: '60px 20px' }}>无法打开：{error}</div>}
        {!error && !file && <div className="ov-empty" style={{ padding: '20px 9px' }}>加载中…</div>}
        {file && file.kind === 'binary' && (
          <div className="pe-empty" style={{ padding: '60px 20px' }}>
            二进制文件（{file.mime}），{file.size ?? 0} 字节
          </div>
        )}
        {file && file.kind === 'text' && isMd && (
          <div className="pv-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(file.content ?? '') }} />
        )}
        {file && file.kind === 'text' && !isMd && (
          <div className="code-ln">
            {(file.content ?? '').split('\n').map((line, i) => (
              <div className="cl" key={i}>
                <span className="ln">{i + 1}</span>
                <span dangerouslySetInnerHTML={{ __html: esc(line) || '&nbsp;' }} />
              </div>
            ))}
          </div>
        )}
      </div>
      {file && (
        <div className="pv-count">
          {counts && <span>行数 {counts.lines}</span>}
          {counts && <span>字数 {counts.chars}</span>}
          <span className="sp" />
          <span className="pv-dl" onClick={download}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></svg>下载
          </span>
        </div>
      )}
    </div>
  )
}
