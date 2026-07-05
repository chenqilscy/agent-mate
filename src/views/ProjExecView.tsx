import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
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
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const setView = useUIStore((s) => s.setView)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [showDn, setShowDn] = useState(false)

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
            <div className="fic" aria-label="搜索" onClick={() => toast('对话内搜索')}><IcSearch /></div>
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
          {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
          <Composer variant="chat" streaming={streaming} onSend={send} onStop={stop} autoFocus />
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
      </div>

      <PePanel messages={messages} />
    </section>
  )
}
