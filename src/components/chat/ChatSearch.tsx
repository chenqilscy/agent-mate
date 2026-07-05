import { useEffect, useRef, useState, type RefObject } from 'react'
import type { ChatMessage } from '../../lib/types'

// 对话内搜索 (M6): a browser-style find bar over the current conversation.
//
// Uses the CSS Custom Highlight API (Chromium/Tauri webview) so we never mutate
// the message DOM — matches are painted via Range objects + ::highlight() rules,
// which survives React re-renders and the markdown `dangerouslySetInnerHTML`.
const HL = 'wb-search'
const HL_CUR = 'wb-search-cur'
// The Highlight API isn't in the TS DOM lib yet; access through a narrow shim.
const hl = (CSS as unknown as { highlights?: Map<string, unknown> }).highlights
const HighlightCtor = (globalThis as unknown as { Highlight?: new (...r: Range[]) => { priority: number } }).Highlight
const supported = !!hl && !!HighlightCtor

function clearHighlights() {
  hl?.delete(HL)
  hl?.delete(HL_CUR)
}

// Walk the text nodes under `root` and return a Range for every case-insensitive
// occurrence of `query`, in document order.
function collectRanges(root: HTMLElement, query: string): Range[] {
  const out: Range[] = []
  if (!query) return out
  const q = query.toLowerCase()
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node: Node | null
  while ((node = walker.nextNode())) {
    const value = node.nodeValue
    if (!value) continue
    const text = value.toLowerCase()
    let idx = text.indexOf(q)
    while (idx !== -1) {
      const r = document.createRange()
      r.setStart(node, idx)
      r.setEnd(node, idx + q.length)
      out.push(r)
      idx = text.indexOf(q, idx + q.length)
    }
  }
  return out
}

export function ChatSearch({ containerRef, messages, onClose }: {
  containerRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [count, setCount] = useState(0)
  const [current, setCurrent] = useState(0) // 0-based index into matches
  const rangesRef = useRef<Range[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => () => clearHighlights(), [])

  // Recompute matches whenever the query or the conversation content changes
  // (the latter matters while a reply streams in).
  useEffect(() => {
    const root = containerRef.current
    const q = query.trim()
    if (!root || !supported || !q) {
      rangesRef.current = []
      setCount(0)
      clearHighlights()
      return
    }
    const ranges = collectRanges(root, q)
    rangesRef.current = ranges
    setCount(ranges.length)
    setCurrent((c) => (ranges.length ? Math.min(c, ranges.length - 1) : 0))
    if (ranges.length) hl!.set(HL, new HighlightCtor!(...ranges))
    else clearHighlights()
  }, [query, messages, containerRef])

  // Paint the active match on top and scroll it into view.
  useEffect(() => {
    if (!supported) return
    const ranges = rangesRef.current
    if (!ranges.length) { hl!.delete(HL_CUR); return }
    const cur = ranges[Math.min(current, ranges.length - 1)]
    const h = new HighlightCtor!(cur)
    h.priority = 1
    hl!.set(HL_CUR, h)
    const anchor = cur.startContainer.parentElement
    anchor?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [current, count])

  const go = (dir: number) => {
    if (!count) return
    setCurrent((c) => (c + dir + count) % count)
  }

  return (
    <div className="chat-search" role="search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="cs-mag"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
      <input
        ref={inputRef}
        placeholder={supported ? '在对话中查找' : '当前环境不支持高亮'}
        value={query}
        onChange={(e) => { setQuery(e.target.value); setCurrent(0) }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); go(e.shiftKey ? -1 : 1) }
          else if (e.key === 'Escape') { e.preventDefault(); onClose() }
        }}
      />
      <span className="cs-count">{count ? `${current + 1}/${count}` : query.trim() ? '无结果' : ''}</span>
      <button className="cs-btn" aria-label="上一个" disabled={!count} onClick={() => go(-1)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 15l-6-6-6 6" /></svg>
      </button>
      <button className="cs-btn" aria-label="下一个" disabled={!count} onClick={() => go(1)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      <button className="cs-btn" aria-label="关闭搜索" onClick={onClose}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </div>
  )
}
