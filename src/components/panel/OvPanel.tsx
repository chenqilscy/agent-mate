import { useState } from 'react'
import type { ChatMessage } from '../../lib/types'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'

// Overview panel (概览 / 工作空间文件 / 浏览器). The 目录 (outline) lists real user
// questions plus the chapter headings from the assistant's Markdown answers.
interface OutlineItem {
  text: string
  msgId: string
  sub: boolean
}

// Extract h2–h4 headings from Markdown source (chapters).
function headings(md: string): string[] {
  const out: string[] = []
  for (const line of md.split('\n')) {
    const m = /^#{2,4}\s+(.+?)\s*#*$/.exec(line)
    if (m) out.push(m[1].trim())
  }
  return out
}

function buildOutline(messages: ChatMessage[]): OutlineItem[] {
  const items: OutlineItem[] = []
  for (const m of messages) {
    if (m.role === 'user') {
      items.push({ text: m.content, msgId: m.id, sub: false })
    } else {
      for (const h of headings(m.content)) items.push({ text: h, msgId: m.id, sub: true })
    }
  }
  return items
}

export function OvPanel({ messages }: { messages: ChatMessage[] }) {
  const setOv = useUIStore((s) => s.setOv)
  const [tab, setTab] = useState<'概览' | '工作空间文件' | '浏览器'>('概览')
  const outline = buildOutline(messages)

  const jump = (id: string) => {
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <aside className="ovpanel open">
      <div className="ov-inner">
        <div className="ov-top">
          <span className="fic" aria-label="目录"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h10" /></svg></span>
          <span style={{ flex: 1 }} />
          <span className="fic" aria-label="展开" onClick={() => toast('全屏展开')}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 4h6v6M20 4l-9 9" /></svg></span>
          <span className="fic" aria-label="收起面板" style={{ background: 'var(--chip)' }} onClick={() => setOv(false)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></svg>
          </span>
        </div>

        <button className="ov-dd" onClick={() => {
          const order: typeof tab[] = ['概览', '工作空间文件', '浏览器']
          setTab(order[(order.indexOf(tab) + 1) % order.length])
        }}>
          <span className="ov-dd-lb">{tab}</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </button>

        {tab === '概览' && (
          <>
            <div className="ov-h">目录 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg></div>
            <div className="ov-outline">
              {outline.length ? (
                outline.map((it, i) => (
                  <div
                    className={`ov-oi ${it.sub ? 'oh' : ''}`.trim()}
                    key={`${it.msgId}-${i}`}
                    title={it.text}
                    onClick={() => jump(it.msgId)}
                  >
                    {it.text.length > 16 ? it.text.slice(0, 16) + '…' : it.text}
                  </div>
                ))
              ) : (
                <div className="ov-empty" style={{ padding: '2px 9px' }}>暂无内容</div>
              )}
            </div>
            <div className="ov-h">产物 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg></div>
            <div className="ov-empty">暂无内容</div>
          </>
        )}
        {tab === '工作空间文件' && (
          <div className="ov-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
            暂无文件<small>任务产出的文件会显示在这里</small>
          </div>
        )}
        {tab === '浏览器' && (
          <div className="ov-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" /></svg>
            暂无页面<small>任务执行时的网页操作会显示在这里</small>
          </div>
        )}
      </div>
    </aside>
  )
}
