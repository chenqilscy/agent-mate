import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { ChatSearch } from '../components/chat/ChatSearch'
import { OvPanel } from '../components/panel/OvPanel'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { IcSearch, IcShare, IcHistory, IcPanel } from '../lib/icons'

export function ChatView() {
  const title = useChatStore((s) => s.title)
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const send = useChatStore((s) => s.send)
  const stop = useChatStore((s) => s.stop)
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const ovOpen = useUIStore((s) => s.ovOpen)
  const toggleOv = useUIStore((s) => s.toggleOv)

  const scrollRef = useRef<HTMLDivElement>(null)
  const [showDn, setShowDn] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const stickRef = useRef(true)

  // ⌘F / Ctrl+F opens 对话内搜索 (intercepts the browser's own find while a chat
  // is on screen). Esc-to-close lives in ChatSearch.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'f' || e.key === 'F')) {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Keep pinned to the bottom while streaming, unless the user scrolled up.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages, streaming])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80
      stickRef.current = atBottom
      setShowDn(!atBottom)
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  return (
    <section className={`view active split ${ovOpen ? '' : ''}`.trim()} data-view="chat">
      <div className="chat-col">
        {searchOpen && <ChatSearch containerRef={scrollRef} messages={messages} onClose={() => setSearchOpen(false)} />}
        <div className="chat-head">
          <div className="ch-t">{title}</div>
          <div className="ch-r">
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" onClick={() => setSearchOpen((v) => !v)}><IcSearch /></div>
            <div className="fic" aria-label="分享" onClick={() => toast('分享对话')}><IcShare /></div>
            <div className="fic" aria-label="历史提问" onClick={() => toast('历史提问')}><IcHistory /></div>
            <div className="fic" aria-label="产物面板" onClick={toggleOv}><IcPanel /></div>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="ov-center" style={{ paddingTop: 120 }}>
              <span style={{ fontSize: 34 }}>💬</span>
              开始一段新对话
              <small>输入下方问题，与真实模型流式对话</small>
            </div>
          ) : (
            <MessageList messages={messages} streaming={streaming} />
          )}
        </div>
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" onClick={scrollToBottom}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </div>

        <div className="chat-foot">
          {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
          <Composer variant="chat" streaming={streaming} onSend={send} onStop={stop} autoFocus />
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
      </div>

      <OvPanel open={ovOpen} messages={messages} />
    </section>
  )
}
