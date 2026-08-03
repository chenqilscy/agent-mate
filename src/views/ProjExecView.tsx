import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { ChatSearch } from '../components/chat/ChatSearch'
import { PePanel } from '../components/panel/PePanel'
import { Popover } from '../components/ui/Popover'
import { WbButton } from '../components/ui/Primitives'
import { api } from '../lib/api'
import { useChatStore } from '../stores/chatStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../lib/exportChat'
import { IcSearch, IcShare, IcFlow, IcPanel } from '../lib/icons'
import { clickable } from '../lib/a11y'

// Project execution view — a chat scoped to a project (the agent runs with the
// project's instruction injected as background). Right panel = 产物/工作空间文件/变更.
export function ProjExecView() {
  const project = useProjectStore((s) => s.active)
  const title = useChatStore((s) => s.title)
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const send = useChatStore((s) => s.send)
  const stop = useChatStore((s) => s.stop)
  const retry = useChatStore((s) => s.retry)
  const readOnly = useChatStore((s) => s.readOnly)
  const ownerName = useChatStore((s) => s.ownerName)
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const activeId = useChatStore((s) => s.activeId)
  const openSession = useChatStore((s) => s.openSession)
  const setView = useUIStore((s) => s.setView)
  const panelOpen = useUIStore((s) => s.ovOpen)
  const setPanel = useUIStore((s) => s.setOv)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [showDn, setShowDn] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [flowOpen, setFlowOpen] = useState(false)
  const [flowBusy, setFlowBusy] = useState('')
  const shareAnchor = useRef<HTMLElement | null>(null)
  const flowAnchor = useRef<HTMLElement | null>(null)

  const flowItems = useMemo(() => messages.flatMap((message) => {
    if (message.role !== 'assistant') return []
    const plan = [...message.trace].reverse().find((trace) => trace.kind === 'plan_snapshot' || trace.kind === 'plan_patch')
    if (!plan || (plan.kind !== 'plan_snapshot' && plan.kind !== 'plan_patch')) return []
    return plan.items.map((item) => ({ ...item, runId: message.runId }))
  }), [messages])

  useEffect(() => {
    setPanel(true)
    return () => setPanel(false)
  }, [setPanel])

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

  const exportMd = () => conversationToMarkdown(title, messages)
  const copyTask = async () => {
    setShareOpen(false)
    if (!messages.length) { toast('还没有任务内容'); return }
    toast((await copyText(exportMd())) ? '已复制任务 Markdown' : '复制失败')
  }
  const downloadTask = () => {
    setShareOpen(false)
    if (!messages.length) { toast('还没有任务内容'); return }
    const name = safeFilename(`${project?.name ?? '项目'}-${title || '任务'}`)
    downloadText(name, exportMd())
    toast('已下载 · ' + name)
  }
  const openProjectPlan = () => {
    setFlowOpen(false)
    if (project?.id) setView('project', { projectId: project.id, projectTab: '计划' })
  }
  const promotePlanItem = async (runId: string | undefined, itemId: string) => {
    if (!runId || !activeId || readOnly || streaming || flowBusy) return
    setFlowBusy(itemId)
    try {
      const result = await api.promoteRunPlanItem(runId, itemId)
      toast(result.created ? '已流转到项目计划' : '该项目任务已存在')
      await openSession(activeId)
    } catch (error) {
      toast(error instanceof Error ? error.message : '流转失败')
    } finally {
      setFlowBusy('')
    }
  }

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
            <span className="pe-crumb-link" {...clickable} onClick={() => setView('projects')}>项目</span>
            <span className="ps">/</span>
            <span className="pe-crumb-link project" {...clickable} onClick={() => setView('project', { projectId: project?.id })}>{project?.name ?? '项目'}</span>
            <span className="ps">/</span><b>{title || '开始执行'}</b>
            <span className="pe-badge">{project?.origin === 'server' ? '团队' : '本地'}</span>
            {streaming && <span className="pe-badge spin" aria-label="执行中"><span className="run-ic" /></span>}
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" {...clickable} onClick={() => setSearchOpen((v) => !v)}><IcSearch /></div>
            <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} data-tip="分享任务" aria-label="分享任务" {...clickable} onClick={(event) => { shareAnchor.current = event.currentTarget; setShareOpen((value) => !value) }}><IcShare /></div>
            <div className={`fic ${flowOpen ? 'on' : ''}`.trim()} data-tip="流转" aria-label="流转" {...clickable} onClick={(event) => { flowAnchor.current = event.currentTarget; setFlowOpen((value) => !value) }}><IcFlow /></div>
            {!panelOpen && <div className="fic" data-tip="打开任务工作台" aria-label="打开任务工作台" {...clickable} onClick={() => setPanel(true)}><IcPanel /></div>}
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
            <MessageList messages={messages} streaming={streaming} onRetry={retry} />
          )}
        </div>
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" {...clickable} onClick={() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight }}>
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

      <Popover open={shareOpen} anchor={shareAnchor.current} dir="down" onClose={() => setShareOpen(false)} minWidth={176}>
        <div className="pop-item" {...clickable} onClick={() => void copyTask()}>
          <span className="pi-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg></span>
          复制任务 Markdown
        </div>
        <div className="pop-item" {...clickable} onClick={downloadTask}>
          <span className="pi-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12M7 11l5 5 5-5M5 21h14" /></svg></span>
          下载 .md 文件
        </div>
      </Popover>

      <Popover open={flowOpen} anchor={flowAnchor.current} dir="down" onClose={() => setFlowOpen(false)} className="pe-flow-pop" minWidth={286}>
        <div className="pop-h">流转到项目计划</div>
        {flowItems.length ? flowItems.map((item) => (
          <WbButton
            key={`${item.runId ?? 'run'}-${item.id}`}
            className="pe-flow-item"
            disabled={Boolean(item.work_item_id) || readOnly || streaming || Boolean(flowBusy)}
            onClick={() => void promotePlanItem(item.runId, item.id)}
          >
            <span className={`pe-flow-status ${item.status}`}>{item.status === 'completed' ? '✓' : item.status === 'blocked' ? '!' : '○'}</span>
            <span title={item.title}>{item.title}</span>
            <small>{item.work_item_id ? '已在计划' : flowBusy === item.id ? '流转中…' : '流转'}</small>
          </WbButton>
        )) : <div className="pop-item pop-empty">当前任务尚未生成可流转的执行计划</div>}
        <div className="pop-div" />
        <div className="pop-item" {...clickable} onClick={openProjectPlan}>
          <span className="pi-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h10" /></svg></span>
          打开项目计划
        </div>
      </Popover>
    </section>
  )
}
