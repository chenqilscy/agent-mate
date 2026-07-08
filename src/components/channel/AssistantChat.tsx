import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../composer/Composer'
import { MessageList } from '../chat/MessageList'
import { ChatSearch } from '../chat/ChatSearch'
import { Popover } from '../ui/Popover'
import { IcSearch, IcShare, IcHistory } from '../../lib/icons'
import type { ChatMessage } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { activate } from '../../lib/a11y'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../../lib/exportChat'

// 助理对话面板（WB-088）—— 从 WB-072/085 的助理页对话部分抽出，供每个助理复用。
// messages 已含发送中的乐观占位；toolbar 搜索/分享/历史 复用 ChatView 组件。
export function AssistantChat({ title, messages, sending, onSend, emptyHint }: {
  title: string
  messages: ChatMessage[]
  sending: boolean
  onSend: (text: string) => void
  emptyHint?: string
}) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const shareAnchor = useRef<HTMLElement | null>(null)
  const [histOpen, setHistOpen] = useState(false)
  const histAnchor = useRef<HTMLElement | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const real = messages.filter((m) => !m.id.startsWith('_pending_'))
  const questions = real.filter((m) => m.role === 'user' && m.content.trim())

  const jumpTo = (id: string) => {
    setHistOpen(false)
    document.getElementById(`msg-${id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
  const openHist = (anchor: HTMLElement) => { histAnchor.current = anchor; setHistOpen((v) => !v) }

  const exportMd = () => conversationToMarkdown(title, real)
  const onCopy = async () => {
    setShareOpen(false)
    if (!real.length) { toast('还没有对话内容'); return }
    toast((await copyText(exportMd())) ? '已复制为 Markdown' : '复制失败')
  }
  const onDownload = () => {
    setShareOpen(false)
    if (!real.length) { toast('还没有对话内容'); return }
    const name = safeFilename(title)
    downloadText(name, exportMd())
    toast('已下载 · ' + name)
  }
  const openShare = (anchor: HTMLElement) => { shareAnchor.current = anchor; setShareOpen((v) => !v) }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); setSearchOpen(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages.length, sending])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => { stickRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 80 }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="chat-col">
      {searchOpen && <ChatSearch containerRef={scrollRef} messages={messages} onClose={() => setSearchOpen(false)} />}
      <div className="chat-head">
        <div className="ch-t">{title}</div>
        <div className="ch-r">
          <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" onClick={() => setSearchOpen((v) => !v)} {...activate(() => setSearchOpen((v) => !v))}><IcSearch /></div>
          <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} aria-label="分享" data-tip="分享 / 导出对话" onClick={(e) => openShare(e.currentTarget)} {...activate((e) => e && openShare(e.currentTarget))}><IcShare /></div>
          <div className={`fic ${histOpen ? 'on' : ''}`.trim()} aria-label="历史提问" data-tip="历史提问" onClick={(e) => openHist(e.currentTarget)} {...activate((e) => e && openHist(e.currentTarget))}><IcHistory /></div>
        </div>
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="ov-center" style={{ paddingTop: 90 }}>
            <span style={{ fontSize: 34 }}>💬</span>
            还没有对话
            <small>{emptyHint ?? '在下面直接和这个助理开始对话。'}</small>
          </div>
        ) : (
          <MessageList messages={messages} streaming={sending} />
        )}
      </div>

      <div className="chat-foot">
        <Composer variant="chat" streaming={sending} onSend={onSend} autoFocus />
        <div className="disc">内容由 AI 生成，请核实重要信息</div>
      </div>

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
    </div>
  )
}
