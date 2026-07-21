import { WbButton } from '../ui/Primitives'
import { useRef, useState } from 'react'
import type { ChatMessage } from '../../lib/types'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { Popover } from '../ui/Popover'
import { FileTree } from './FileTree'
import { FileViewer } from './FileViewer'
import { clickable } from '../../lib/a11y'

// Overview panel (概览 / 工作空间文件 / 浏览器). Switching is a real dropdown; the
// 目录 / 产物 sections fold; the panel itself collapses with a width animation
// (it stays mounted — ChatView toggles the `open` class).
type Tab = '概览' | '工作空间文件' | '浏览器'

interface OutlineItem { text: string; msgId: string; sub: boolean }
interface Artifact { path: string; name: string; op: string }

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
    if (m.role === 'user') items.push({ text: m.content, msgId: m.id, sub: false })
    else for (const h of headings(m.content)) items.push({ text: h, msgId: m.id, sub: true })
  }
  return items
}

function buildArtifacts(messages: ChatMessage[]): Artifact[] {
  const byPath = new Map<string, Artifact>()
  for (const m of messages) {
    if (m.role !== 'assistant') continue
    for (const t of m.trace) {
      if (t.kind === 'diff') byPath.set(t.file, { path: t.file, name: t.file.split('/').pop() ?? t.file, op: t.op })
    }
  }
  return [...byPath.values()]
}

function badge(name: string): string {
  return (name.split('.').pop()?.toUpperCase() ?? '').slice(0, 3) || 'F'
}

const TABS: { id: Tab; icon: string }[] = [
  { id: '概览', icon: '▦' },
  { id: '工作空间文件', icon: '🗂️' },
  { id: '浏览器', icon: '🌐' },
]

// A section header that folds its content (rotating chevron).
function SectionHead({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <div className="ov-h" style={{ cursor: 'pointer' }} {...clickable} onClick={onToggle}>
      {label}
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ transition: 'transform .18s', transform: open ? 'none' : 'rotate(-90deg)' }}>
        <path d="M6 9l6 6 6-6" />
      </svg>
    </div>
  )
}

export function OvPanel({ open, messages }: { open: boolean; messages: ChatMessage[] }) {
  const setOv = useUIStore((s) => s.setOv)
  const viewerPath = useUIStore((s) => s.viewerPath)
  const openFile = useUIStore((s) => s.openFile)
  const closeFile = useUIStore((s) => s.closeFile)
  const ovExpanded = useUIStore((s) => s.ovExpanded)
  const toggleExpand = useUIStore((s) => s.toggleExpand)
  const activeId = useChatStore((s) => s.activeId)
  const scope = activeId ? { session: activeId } : undefined
  const [tab, setTab] = useState<Tab>('概览')
  const [ddOpen, setDdOpen] = useState(false)
  const [dirOpen, setDirOpen] = useState(true)
  const [prodOpen, setProdOpen] = useState(true)
  const ddRef = useRef<HTMLButtonElement>(null)

  const outline = buildOutline(messages)
  const artifacts = buildArtifacts(messages)

  const jump = (id: string) => {
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const collapse = () => {
    setDdOpen(false)
    setOv(false)
  }

  return (
    <aside className={`ovpanel ${open ? 'open' : ''} ${open && ovExpanded ? 'expanded' : ''}`.trim()}>
      <div className="ov-inner">
        <div className="ov-top">
          <span className="fic" aria-label="目录" {...clickable} onClick={() => { setTab('概览'); closeFile() }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
          </span>
          <span style={{ flex: 1 }} />
          <span className="fic" aria-label={ovExpanded ? '收起为侧栏' : '全屏展开'} {...clickable} onClick={toggleExpand}>
            {ovExpanded ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 20H4v-6M4 20l9-9" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 4h6v6M20 4l-9 9" /></svg>
            )}
          </span>
          <span className="fic" aria-label="收起面板" style={{ background: 'var(--chip)' }} {...clickable} onClick={collapse}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></svg>
          </span>
        </div>

        {viewerPath ? (
          <FileViewer path={viewerPath} onClose={closeFile} scope={scope} />
        ) : (
          <>
            <WbButton ref={ddRef} className="ov-dd" onClick={() => setDdOpen((v) => !v)}>
              <span className="ov-dd-lb">{tab}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
            </WbButton>
            <Popover open={ddOpen} anchor={ddRef.current} dir="down" onClose={() => setDdOpen(false)} minWidth={168}>
              {TABS.map((t) => (
                <div className="pop-item" key={t.id} {...clickable} onClick={() => { setTab(t.id); setDdOpen(false) }}>
                  <span className="pi-ic">{t.icon}</span>{t.id}
                  {tab === t.id && <span className="chk">✓</span>}
                </div>
              ))}
            </Popover>

            {tab === '概览' && (
              <div style={{ flex: 1, overflowY: 'auto' }}>
                <SectionHead label="目录" open={dirOpen} onToggle={() => setDirOpen((v) => !v)} />
                {dirOpen && (
                  <div className="ov-outline">
                    {outline.length ? (
                      outline.map((it, i) => (
                        <div className={`ov-oi ${it.sub ? 'oh' : ''}`.trim()} key={`${it.msgId}-${i}`} title={it.text} {...clickable} onClick={() => jump(it.msgId)}>
                          {it.text.length > 16 ? it.text.slice(0, 16) + '…' : it.text}
                        </div>
                      ))
                    ) : (
                      <div className="ov-empty" style={{ padding: '2px 9px' }}>暂无内容</div>
                    )}
                  </div>
                )}
                <SectionHead label="产物" open={prodOpen} onToggle={() => setProdOpen((v) => !v)} />
                {prodOpen && (artifacts.length ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '0 4px' }}>
                    {artifacts.map((a) => (
                      <div className="ov-art" key={a.path} {...clickable} onClick={() => openFile(a.path)}>
                        <span className="oa-ic">{badge(a.name)}</span>
                        <div style={{ minWidth: 0 }}>
                          <div className="oa-n">{a.name}</div>
                          <div className="oa-m">{a.op} · 工作空间产物</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="ov-empty">暂无内容</div>
                ))}
              </div>
            )}

            {tab === '工作空间文件' && <FileTree scope={scope} />}

            {tab === '浏览器' && (
              <div className="ov-center">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" /></svg>
                暂无页面<small>任务执行时的网页操作会显示在这里</small>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
