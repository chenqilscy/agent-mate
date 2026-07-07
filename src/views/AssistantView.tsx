import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { IcSearch, IcShare, IcHistory, IcPanel, IcGear } from '../lib/icons'
import { api, type TelegramChannel } from '../lib/api'
import type { ChatMessage } from '../lib/types'
import { toast } from '../stores/toastStore'

// Assistant (external-channel) view — WB-072. The Telegram bridge is the real
// backend; this view shows the REAL channel status + the REAL assistant transcript
// (shared with Telegram — same session), and its composer drives the SAME assistant
// from the App. Not configured → setup guidance instead of the old canned mock.
export function AssistantView() {
  const [ch, setCh] = useState<TelegramChannel | null>(null)
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
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

  const onGear = () => {
    if (!ch?.configured) { toast('在 backend/.env 配置 TELEGRAM_BOT_TOKEN 并设 TELEGRAM_ASSISTANT=1，重启后端'); return }
    toast(ch.bound_chat_id
      ? `已绑定 Telegram chat：${ch.bound_chat_id}`
      : `在 Telegram 给 ${ch.bot_username ? '@' + ch.bot_username : 'bot'} 发 /start 完成配对`)
  }

  return (
    <section className="view active split" data-view="assistant">
      <div className="chat-col">
        <div className="chat-head">
          <div className="ast-conn">
            已连接：<span className="ac-chip">{chip.dot} {chip.label}</span>
            <IcGear onClick={onGear} />
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className="fic" aria-label="搜索" onClick={() => toast('对话内搜索')}><IcSearch /></div>
            <div className="fic" aria-label="分享" onClick={() => toast('分享对话')}><IcShare /></div>
            <div className="fic" aria-label="历史提问" onClick={() => toast('历史提问')}><IcHistory /></div>
            <div className="fic" aria-label="产物面板" onClick={() => toast('产物面板')}><IcPanel /></div>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {ch && !ch.configured ? (
            <div className="ov-center" style={{ paddingTop: 100 }}>
              <span style={{ fontSize: 34 }}>📡</span>
              助理外部渠道未连接
              <small>在 <b>backend/.env</b> 配置 TELEGRAM_BOT_TOKEN，并设 TELEGRAM_ASSISTANT=1，重启后端；
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
            : <div className="disc">配置并开启 Telegram 渠道后，即可在此与助理对话</div>}
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
      </div>
    </section>
  )
}
