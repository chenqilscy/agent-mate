import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { ChatSearch } from '../components/chat/ChatSearch'
import { OvPanel } from '../components/panel/OvPanel'
import { Popover } from '../components/ui/Popover'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { activate, clickable } from '../lib/a11y'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../lib/exportChat'
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
  const [shareOpen, setShareOpen] = useState(false)
  const shareAnchor = useRef<HTMLElement | null>(null)
  const [histOpen, setHistOpen] = useState(false)
  const histAnchor = useRef<HTMLElement | null>(null)
  const stickRef = useRef(true)

  // 历史提问: a quick table-of-contents of the user's own questions in this
  // conversation — click one to jump to it (distinct from ⌘F text search).
  const questions = messages.filter((m) => m.role === 'user' && m.content.trim())
  const openHist = (anchor: HTMLElement) => {
    histAnchor.current = anchor
    setHistOpen((v) => !v)
  }
  const jumpTo = (id: string) => {
    setHistOpen(false)
    document.getElementById(`msg-${id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  // 分享对话: export the conversation to Markdown (clipboard or .md download).
  const exportMd = () => conversationToMarkdown(title, messages)
  const onCopy = async () => {
    setShareOpen(false)
    if (!messages.length) { toast('还没有对话内容'); return }
    toast((await copyText(exportMd())) ? '已复制为 Markdown' : '复制失败')
  }
  const onDownload = () => {
    setShareOpen(false)
    if (!messages.length) { toast('还没有对话内容'); return }
    const name = safeFilename(title)
    downloadText(name, exportMd())
    toast('已下载 · ' + name)
  }
  const openShare = (anchor: HTMLElement) => {
    shareAnchor.current = anchor
    setShareOpen((v) => !v)
  }

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
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" onClick={() => setSearchOpen((v) => !v)} {...activate(() => setSearchOpen((v) => !v))}><IcSearch /></div>
            <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} aria-label="分享" data-tip="分享 / 导出对话" onClick={(e) => openShare(e.currentTarget)} {...activate((e) => e && openShare(e.currentTarget))}><IcShare /></div>
            <div className={`fic ${histOpen ? 'on' : ''}`.trim()} aria-label="历史提问" data-tip="历史提问" onClick={(e) => openHist(e.currentTarget)} {...activate((e) => e && openHist(e.currentTarget))}><IcHistory /></div>
            <div className="fic" aria-label="产物面板" onClick={toggleOv} {...activate(toggleOv)}><IcPanel /></div>
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
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" {...clickable} onClick={scrollToBottom}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </div>

        <div className="chat-foot">
          {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
          <Composer variant="chat" streaming={streaming} onSend={send} onStop={stop} autoFocus />
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
      </div>

      <OvPanel open={ovOpen} messages={messages} />

      <Popover open={shareOpen} anchor={shareAnchor.current} dir="down" onClose={() => setShareOpen(false)} minWidth={176}>
        <div className="pop-item" {...activate(onCopy)} onClick={onCopy}>
          <span className="pi-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg></span>
          复制为 Markdown
        </div>
        <div className="pop-item" {...activate(onDownload)} onClick={onDownload}>
          <span className="pi-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12M7 11l5 5 5-5M5 21h14" /></svg></span>
          下载 .md 文件
        </div>
      </Popover>

      <Popover open={histOpen} anchor={histAnchor.current} dir="down" onClose={() => setHistOpen(false)} minWidth={240}>
        <div className="pop-h">历史提问（{questions.length}）</div>
        {questions.length === 0 && <div className="pop-item pop-empty">还没有提问</div>}
        {questions.map((m) => (
          <div className="pop-item hist-item" key={m.id} {...activate(() => jumpTo(m.id))} onClick={() => jumpTo(m.id)}>
            {m.content.trim()}
          </div>
        ))}
      </Popover>
    </section>
  )
}
