import { WbButton, WbInput } from '../ui/Primitives'
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

// Build one searchable string per message, then map each match back to its text
// nodes. This lets a phrase cross inline Markdown elements (`strong`, `code`,
// links...) without ever joining the tail of one message to the next one.
export function collectRanges(root: HTMLElement, query: string): Range[] {
  const out: Range[] = []
  if (!query) return out
  const q = query.toLowerCase()
  const messages = Array.from(root.querySelectorAll<HTMLElement>('.msg'))
  const scopes = messages.length ? messages : [root]

  for (const scope of scopes) {
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT)
    const segments: { node: Text; start: number; end: number }[] = []
    let text = ''
    let node: Node | null
    while ((node = walker.nextNode())) {
      const value = node.nodeValue
      if (!value) continue
      const start = text.length
      text += value
      segments.push({ node: node as Text, start, end: text.length })
    }

    const haystack = text.toLowerCase()
    let idx = haystack.indexOf(q)
    while (idx !== -1) {
      const matchEnd = idx + q.length
      const first = segments.find((part) => part.start <= idx && idx < part.end)
      const last = segments.find((part) => part.start < matchEnd && matchEnd <= part.end)
      if (!first || !last) break
      const r = document.createRange()
      r.setStart(first.node, idx - first.start)
      r.setEnd(last.node, matchEnd - last.start)
      out.push(r)
      idx = haystack.indexOf(q, matchEnd)
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
  // Bumped every time ranges are recomputed, so the active-highlight paint re-runs
  // even when count/current are unchanged (e.g. "ab"→"cd", both 2 matches) — WB-007.
  const [rangesVersion, setRangesVersion] = useState(0)
  // Bumped only on an explicit scroll request (typing a new query / ▲▼ / Enter),
  // never by a streaming recompute — so the search never fights the pin-to-bottom.
  const [scrollToken, setScrollToken] = useState(0)
  const rangesRef = useRef<Range[]>([])
  const computedQueryRef = useRef('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => () => clearHighlights(), [])

  // Recompute matches whenever the query or the conversation content changes
  // (the latter matters while a reply streams in). Debounced so a streaming reply
  // — which changes `messages` on every token — doesn't rebuild every Range per
  // token (O(n) TreeWalker on long chats); recompute only after input settles.
  useEffect(() => {
    const root = containerRef.current
    const q = query.trim()
    if (!root || !supported || !q) {
      rangesRef.current = []
      computedQueryRef.current = q
      setCount(0)
      setRangesVersion((v) => v + 1)
      clearHighlights()
      return
    }
    const handle = window.setTimeout(() => {
      const ranges = collectRanges(root, q)
      rangesRef.current = ranges
      const queryChanged = q !== computedQueryRef.current
      computedQueryRef.current = q
      setCount(ranges.length)
      // A new query starts at the first match; a streaming recompute keeps the
      // user's position (clamped).
      setCurrent((c) => (queryChanged ? 0 : ranges.length ? Math.min(c, ranges.length - 1) : 0))
      if (ranges.length) hl!.set(HL, new HighlightCtor!(...ranges))
      else clearHighlights()
      setRangesVersion((v) => v + 1)
      // Jump to the first match on a query change (browser-find behaviour); a
      // streaming recompute must not scroll.
      if (queryChanged && ranges.length) setScrollToken((t) => t + 1)
    }, 150)
    return () => window.clearTimeout(handle)
  }, [query, messages, containerRef])

  // Paint the active match on top — no scrolling here, so streaming recomputes
  // repaint the current highlight without yanking the viewport.
  useEffect(() => {
    if (!supported) return
    const ranges = rangesRef.current
    if (!ranges.length) { hl!.delete(HL_CUR); return }
    const cur = ranges[Math.min(current, ranges.length - 1)]
    const h = new HighlightCtor!(cur)
    h.priority = 1
    hl!.set(HL_CUR, h)
  }, [current, rangesVersion])

  // Scroll the active match into view only on explicit navigation (query change /
  // ▲▼ / Enter), keyed on scrollToken. `current` is read from the same batched
  // render that bumped the token, so it is always the freshly-selected match.
  useEffect(() => {
    if (!supported || scrollToken === 0) return
    const ranges = rangesRef.current
    if (!ranges.length) return
    const cur = ranges[Math.min(current, ranges.length - 1)]
    cur.startContainer.parentElement?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollToken])

  const go = (dir: number) => {
    if (!count) return
    setCurrent((c) => (c + dir + count) % count)
    setScrollToken((t) => t + 1)
  }

  return (
    <div className="chat-search" role="search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="cs-mag"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
      <WbInput
        ref={inputRef}
        placeholder={supported ? '在对话中查找' : '当前环境不支持高亮'}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); go(e.shiftKey ? -1 : 1) }
          else if (e.key === 'Escape') { e.preventDefault(); onClose() }
        }}
      />
      <span className="cs-count">{count ? `${current + 1}/${count}` : query.trim() ? '无结果' : ''}</span>
      <WbButton className="cs-btn" aria-label="上一个" disabled={!count} onClick={() => go(-1)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 15l-6-6-6 6" /></svg>
      </WbButton>
      <WbButton className="cs-btn" aria-label="下一个" disabled={!count} onClick={() => go(1)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
      </WbButton>
      <WbButton className="cs-btn" aria-label="关闭搜索" onClick={onClose}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </WbButton>
    </div>
  )
}
