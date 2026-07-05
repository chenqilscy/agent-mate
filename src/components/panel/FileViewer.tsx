import { useEffect, useState } from 'react'
import { api, type FileContent } from '../../lib/api'
import { renderMarkdown } from '../../lib/markdown'

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

export function FileViewer({ path, onClose }: { path: string; onClose: () => void }) {
  const [file, setFile] = useState<FileContent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const name = path.split('/').pop() ?? path

  useEffect(() => {
    let alive = true
    setFile(null)
    setError(null)
    api
      .fileContent(path)
      .then((f) => alive && setFile(f))
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [path])

  const isMd = name.toLowerCase().endsWith('.md')

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
    </div>
  )
}
