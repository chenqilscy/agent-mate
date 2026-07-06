import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { ChatSearch } from '../components/chat/ChatSearch'
import { PePanel } from '../components/panel/PePanel'
import { useChatStore } from '../stores/chatStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { IcSearch, IcPanel } from '../lib/icons'

// Project execution view — a chat scoped to a project (the agent runs with the
// project's instruction injected as background). Right panel = 产物/工作空间文件/变更.
export function ProjExecView() {
  const project = useProjectStore((s) => s.active)
  const title = useChatStore((s) => s.title)
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const send = useChatStore((s) => s.send)
  const stop = useChatStore((s) => s.stop)
  const readOnly = useChatStore((s) => s.readOnly)
  const ownerName = useChatStore((s) => s.ownerName)
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const setView = useUIStore((s) => s.setView)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [showDn, setShowDn] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

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
  }, [messages, streaming, pending])

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

  return (
    <section className="view active split" data-view="projexec">
      <div className="chat-col">
        {searchOpen && <ChatSearch containerRef={scrollRef} messages={messages} onClose={() => setSearchOpen(false)} />}
        <div className="chat-head">
          <div className="pe-crumb">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
            <span style={{ cursor: 'pointer' }} onClick={() => setView('projects')}>项目</span>
            <span className="ps">/</span>
            <span style={{ cursor: 'pointer' }} onClick={() => setView('project')}>{project?.name ?? '项目'}</span>
            <span className="ps">/</span><b>{title || '开始执行'}</b>
            {streaming ? (
              <span className="pe-badge spin"><span className="run-ic" /></span>
            ) : (
              <span className="pe-badge">就绪<i /></span>
            )}
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" onClick={() => setSearchOpen((v) => !v)}><IcSearch /></div>
            <div className="fic" aria-label="邀请成员" onClick={() => toast('邀请成员（M7 协作版）')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="10" cy="8" r="4" /><path d="M2 21c0-4 4-6 8-6M19 8v6M16 11h6" /></svg>
            </div>
            <div className="fic" aria-label="产物面板"><IcPanel /></div>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="ov-center" style={{ paddingTop: 120 }}>
              <span style={{ fontSize: 34 }}>📁</span>
              {project?.name ?? '项目'}
              <small>在下方描述任务，Agent 会带着本项目的指令与规范执行</small>
            </div>
          ) : (
            <MessageList messages={messages} streaming={streaming} />
          )}
        </div>
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" onClick={() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </div>

        <div className="chat-foot">
          {readOnly ? (
            // M7 C3: a teammate's run is read-only — you can view its trace/output
            // but not continue it. The owner drives their own session.
            <div className="pe-readonly">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 15a2 2 0 100-4 2 2 0 000 4z" /><path d="M6 10V7a6 6 0 0112 0v3" /><rect x="4" y="10" width="16" height="11" rx="2" /></svg>
              由 <b>{ownerName || '队友'}</b> 执行 · 只读查看
            </div>
          ) : (
            <>
              {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
              <Composer variant="chat" streaming={streaming} onSend={send} onStop={stop} autoFocus />
              <div className="disc">内容由 AI 生成，请核实重要信息</div>
            </>
          )}
        </div>
      </div>

      <PePanel messages={messages} />
    </section>
  )
}
