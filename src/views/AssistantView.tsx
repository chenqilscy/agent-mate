import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { ChatSearch } from '../components/chat/ChatSearch'
import { AssistantSettingsModal } from '../components/channel/AssistantSettingsModal'
import { Popover } from '../components/ui/Popover'
import { IcSearch, IcShare, IcHistory, IcPanel, IcGear } from '../lib/icons'
import { api, type TelegramChannel } from '../lib/api'
import type { ChatMessage } from '../lib/types'
import { toast } from '../stores/toastStore'
import { activate } from '../lib/a11y'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../lib/exportChat'

// Assistant (external-channel) view — WB-072/077/085. The Telegram bridge is the
// real backend; this view shows the REAL channel status + the REAL assistant
// transcript (shared with Telegram — same session), drives the SAME assistant from
// the App, and its toolbar (search / share / history) works on the real transcript
// by reusing ChatView's components (WB-085). Not configured → setup guidance.
export function AssistantView() {
  const [ch, setCh] = useState<TelegramChannel | null>(null)
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const shareAnchor = useRef<HTMLElement | null>(null)
  const [histOpen, setHistOpen] = useState(false)
  const histAnchor = useRef<HTMLElement | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const load = async () => {
    try { setCh(await api.getTelegramChannel()) } catch { /* backend down — keep last */ }
  }

  useEffect(() => { load() }, [])

  // Telegram messages arrive out-of-band (from the phone), so poll to reflect them.
  // Pause while sending (optimistic UI) and when the tab is hidden.
  useEffect(() => {
    const id = setInterval(() => {
      if (!sending && document.visibilityState === 'visible') load()
    }, 4000)
    return () => clearInterval(id)
  }, [sending])

  const onSend = async (text: string) => {
    if (sending) return
    setPending(text)
    setSending(true)
    try {
      await api.telegramSay(text)
      await load() // reload transcript (now includes this turn + the reply)
    } catch {
      toast('发送失败，请重试')
    } finally {
      setSending(false)
      setPending(null)
    }
  }

  // Real transcript → ChatMessage[]; while sending, append the optimistic user turn
  // and a running bot bubble (MessageList renders the typing indicator for it).
  const base: ChatMessage[] = (ch?.messages ?? []).map((m) => ({
    id: m.id, role: m.role, content: m.content, trace: [], status: 'done' as const,
  }))
  const display: ChatMessage[] = sending && pending != null
    ? [
        ...base,
        { id: '_pending_u', role: 'user', content: pending, trace: [], status: 'done' as const },
        { id: '_pending_b', role: 'assistant', content: '', trace: [], status: 'running' as const },
      ]
    : base

  // 分享 / 历史 都基于真实 transcript（base，不含发送中的乐观占位）。
  const title = `助理${ch?.bot_username ? ' · @' + ch.bot_username : ''}`
  const questions = base.filter((m) => m.role === 'user' && m.content.trim())

  const jumpTo = (id: string) => {
    setHistOpen(false)
    document.getElementById(`msg-${id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
  const openHist = (anchor: HTMLElement) => { histAnchor.current = anchor; setHistOpen((v) => !v) }

  const exportMd = () => conversationToMarkdown(title, base)
  const onCopy = async () => {
    setShareOpen(false)
    if (!base.length) { toast('还没有对话内容'); return }
    toast((await copyText(exportMd())) ? '已复制为 Markdown' : '复制失败')
  }
  const onDownload = () => {
    setShareOpen(false)
    if (!base.length) { toast('还没有对话内容'); return }
    const name = safeFilename(title)
    downloadText(name, exportMd())
    toast('已下载 · ' + name)
  }
  const openShare = (anchor: HTMLElement) => { shareAnchor.current = anchor; setShareOpen((v) => !v) }

  // ⌘F / Ctrl+F opens 对话内搜索 while the assistant view is on screen.
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

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [display.length, sending])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      stickRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 80
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const chip = !ch
    ? { dot: '⚪', label: '加载中…' }
    : !ch.configured
      ? { dot: '⚪', label: '未连接' }
      : ch.connected
        ? { dot: '🟢', label: `已连接 @${ch.bot_username}` }
        : ch.enabled
          ? { dot: '🟡', label: '连接中…' }
          : { dot: '🟡', label: '已配置（未开启）' }

  const onGear = () => setSettingsOpen(true) // 助理设置面板（WB-077）

  return (
    <section className="view active split" data-view="assistant">
      <div className="chat-col">
        {searchOpen && <ChatSearch containerRef={scrollRef} messages={display} onClose={() => setSearchOpen(false)} />}
        <div className="chat-head">
          <div className="ast-conn">
            已连接：<span className="ac-chip">{chip.dot} {chip.label}</span>
            <IcGear onClick={onGear} />
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" onClick={() => setSearchOpen((v) => !v)} {...activate(() => setSearchOpen((v) => !v))}><IcSearch /></div>
            <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} aria-label="分享" data-tip="分享 / 导出对话" onClick={(e) => openShare(e.currentTarget)} {...activate((e) => e && openShare(e.currentTarget))}><IcShare /></div>
            <div className={`fic ${histOpen ? 'on' : ''}`.trim()} aria-label="历史提问" data-tip="历史提问" onClick={(e) => openHist(e.currentTarget)} {...activate((e) => e && openHist(e.currentTarget))}><IcHistory /></div>
            <div className="fic" aria-label="产物面板" onClick={() => toast('产物面板')}><IcPanel /></div>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {ch && !ch.configured ? (
            <div className="ov-center" style={{ paddingTop: 100 }}>
              <span style={{ fontSize: 34 }}>📡</span>
              助理外部渠道未连接
              <small>点右上角 <b>⚙️</b> 打开助理设置，填入 bot token 并启用；
                再在 Telegram 给你的 bot 发 /start，即可随时从手机与助理对话。</small>
            </div>
          ) : ch && display.length === 0 ? (
            <div className="ov-center" style={{ paddingTop: 100 }}>
              <span style={{ fontSize: 34 }}>💬</span>
              还没有对话
              <small>在 Telegram 给 {ch.bot_username ? '@' + ch.bot_username : 'bot'} 发 /start，或直接在下面和助理开始对话。</small>
            </div>
          ) : (
            <MessageList messages={display} streaming={sending} />
          )}
        </div>

        <div className="chat-foot">
          {ch?.configured
            ? <Composer variant="chat" streaming={sending} onSend={onSend} autoFocus />
            : <div className="disc">点右上角 ⚙️ 配置并开启助理后，即可在此与助理对话</div>}
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
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

      {settingsOpen && ch && (
        <AssistantSettingsModal
          open
          ch={ch}
          onClose={() => setSettingsOpen(false)}
          onSaved={(updated) => setCh(updated)}
        />
      )}
    </section>
  )
}
