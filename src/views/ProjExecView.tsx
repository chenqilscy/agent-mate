import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { RunLaunchHandoff } from '../components/chat/RunLaunchHandoff'
import { ChatSearch } from '../components/chat/ChatSearch'
import { PePanel } from '../components/panel/PePanel'
import { Popover } from '../components/ui/Popover'
import { openServerConsole } from '../lib/console'
import { useChatStore } from '../stores/chatStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../lib/exportChat'
import { IcSearch, IcShare, IcPanel } from '../lib/icons'
import { clickable } from '../lib/a11y'
import type { RunQueueContext } from '../lib/types'

// Local execution view: observe an existing Server Run, answer/approve it and
// inspect local artifacts. Project/task governance stays in Server Workspace.
export function ProjExecView() {
  const project = useProjectStore((s) => s.active)
  const title = useChatStore((s) => s.title)
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const pause = useChatStore((s) => s.pause)
  const resume = useChatStore((s) => s.resume)
  const cancel = useChatStore((s) => s.cancel)
  const retry = useChatStore((s) => s.retry)
  const readOnly = useChatStore((s) => s.readOnly)
  const ownerName = useChatStore((s) => s.ownerName)
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const controlStatus = [...messages].reverse().find((message) => message.status === 'running' && message.runId)?.runStatus
  const openSession = useChatStore((s) => s.openSession)
  const setView = useUIStore((s) => s.setView)
  const panelOpen = useUIStore((s) => s.ovOpen)
  const setPanel = useUIStore((s) => s.setOv)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [showDn, setShowDn] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const shareAnchor = useRef<HTMLElement | null>(null)

  const executionReadOnly = readOnly || project?.role === 'Viewer'

  useEffect(() => {
    setPanel(messages.length > 0)
    return () => setPanel(false)
  }, [messages.length, setPanel])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && (event.key === 'f' || event.key === 'F')) {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useLayoutEffect(() => {
    const element = scrollRef.current
    if (element && stickRef.current) element.scrollTop = element.scrollHeight
  }, [messages, streaming, pending])

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const onScroll = () => {
      const atBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 80
      stickRef.current = atBottom
      setShowDn(!atBottom)
    }
    element.addEventListener('scroll', onScroll)
    return () => element.removeEventListener('scroll', onScroll)
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
  const openBlockingRun = async (run: NonNullable<RunQueueContext['blocking_run']>) => {
    await openSession(run.session_id)
    setView(run.project_id ? 'projexec' : 'chat', {
      projectId: run.project_id || undefined,
      sessionId: run.session_id,
    })
  }
  const openProject = async () => {
    try {
      await openServerConsole(project?.id ? `/projects/${project.id}` : '/projects')
    } catch {
      toast('无法打开 Server Workspace，请检查 Server 地址和连接状态')
    }
  }

  return (
    <section className="view active split" data-view="projexec">
      <div className="chat-col">
        {searchOpen && <ChatSearch containerRef={scrollRef} messages={messages} onClose={() => setSearchOpen(false)} />}
        <div className="chat-head">
          <div className="pe-crumb">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
            <span className="pe-crumb-link" {...clickable} onClick={() => void openProject()}>Server Workspace</span>
            <span className="ps">/</span>
            <span className="pe-crumb-link project" {...clickable} onClick={() => void openProject()}>{project?.name ?? '项目'}</span>
            <span className="ps">/</span><b>{title || '执行记录'}</b>
            <span className="pe-badge">执行节点</span>
            {streaming && <span className="pe-badge spin" aria-label="执行中"><span className="run-ic" /></span>}
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" {...clickable} onClick={() => setSearchOpen((value) => !value)}><IcSearch /></div>
            <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} data-tip="分享任务" aria-label="分享任务" {...clickable} onClick={(event) => { shareAnchor.current = event.currentTarget; setShareOpen((value) => !value) }}><IcShare /></div>
            {messages.length > 0 && !panelOpen && <div className="fic" data-tip="打开执行工件" aria-label="打开执行工件" {...clickable} onClick={() => setPanel(true)}><IcPanel /></div>}
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="ov-center" style={{ paddingTop: 120 }}>
              <span style={{ fontSize: 34 }}>🖥️</span>
              没有可观察的项目执行
              <small>项目任务和新的 Run 请从 Server Workspace 发起</small>
            </div>
          ) : (
            <MessageList messages={messages} streaming={streaming} onRetry={retry} onOpenBlockingRun={(run) => void openBlockingRun(run)} />
          )}
        </div>
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" {...clickable} onClick={() => { const element = scrollRef.current; if (element) element.scrollTop = element.scrollHeight }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </div>

        <div className="chat-foot">
          {executionReadOnly ? (
            <div className="pe-readonly">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 15a2 2 0 100-4 2 2 0 000 4z" /><path d="M6 10V7a6 6 0 0112 0v3" /><rect x="4" y="10" width="16" height="11" rx="2" /></svg>
              {project?.role === 'Viewer' && !readOnly ? <>Viewer 权限 · 只读查看执行</> : <>由 <b>{ownerName || '队友'}</b> 执行 · 只读查看</>}
            </div>
          ) : (
            <>
              {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
              {streaming ? (
                <Composer variant="chat" streaming controlStatus={controlStatus} onSend={() => toast('新的 Run 请从 Server Workspace 发起')} onPause={pause} onResume={resume} onCancel={cancel} autoFocus />
              ) : !pending ? <RunLaunchHandoff projectId={project?.id} /> : null}
              {messages.length > 0 && <div className="disc">内容由 AI 生成，请核实重要信息</div>}
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
    </section>
  )
}
