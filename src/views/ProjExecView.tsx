import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { MessageList } from '../components/chat/MessageList'
import { AskUserCard } from '../components/chat/AskUserCard'
import { ChatSearch } from '../components/chat/ChatSearch'
import { PePanel } from '../components/panel/PePanel'
import { TodoDetailModal } from '../components/project/ProjectWork'
import { ProjectTaskCenter } from '../components/project/ProjectTaskCenter'
import { Popover } from '../components/ui/Popover'
import { WbButton } from '../components/ui/Primitives'
import { api } from '../lib/api'
import { useChatStore } from '../stores/chatStore'
import { useProjectStore } from '../stores/projectStore'
import { useWorkItemStore } from '../stores/workItemStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { conversationToMarkdown, copyText, downloadText, safeFilename } from '../lib/exportChat'
import { IcSearch, IcShare, IcFlow, IcPanel } from '../lib/icons'
import { clickable } from '../lib/a11y'

const TASK_STATUS_LABEL = { todo: '待开始', doing: '进行中', paused: '已暂停', review: '待验收', done: '已完成' } as const

// Project execution view — a chat scoped to a project (the agent runs with the
// project's instruction injected as background). Right panel = 产物/工作空间文件/变更.
export function ProjExecView() {
  const project = useProjectStore((s) => s.active)
  const title = useChatStore((s) => s.title)
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const send = useChatStore((s) => s.send)
  const pause = useChatStore((s) => s.pause)
  const resume = useChatStore((s) => s.resume)
  const cancel = useChatStore((s) => s.cancel)
  const retry = useChatStore((s) => s.retry)
  const readOnly = useChatStore((s) => s.readOnly)
  const ownerName = useChatStore((s) => s.ownerName)
  const pending = useChatStore((s) => s.pending)
  const answer = useChatStore((s) => s.answer)
  const controlStatus = [...messages].reverse().find((message) => message.status === 'running' && message.runId)?.runStatus
  const activeId = useChatStore((s) => s.activeId)
  const openSession = useChatStore((s) => s.openSession)
  const startProject = useChatStore((s) => s.startProject)
  const setView = useUIStore((s) => s.setView)
  const panelOpen = useUIStore((s) => s.ovOpen)
  const setPanel = useUIStore((s) => s.setOv)
  const workItems = useWorkItemStore((s) => s.items)
  const workItemProjectId = useWorkItemStore((s) => s.projectId)
  const workItemsLoading = useWorkItemStore((s) => s.loading)
  const workItemsError = useWorkItemStore((s) => s.error)
  const workItemsUpdatedAt = useWorkItemStore((s) => s.updatedAt)
  const loadWorkItems = useWorkItemStore((s) => s.load)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const [showDn, setShowDn] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [flowOpen, setFlowOpen] = useState(false)
  const [flowBusy, setFlowBusy] = useState('')
  const [taskOpen, setTaskOpen] = useState(false)
  const [taskDetailId, setTaskDetailId] = useState<string | null>(null)
  const shareAnchor = useRef<HTMLElement | null>(null)
  const flowAnchor = useRef<HTMLElement | null>(null)
  const taskAnchor = useRef<HTMLElement | null>(null)

  const pendingServerTasks = useMemo(
    () => workItemProjectId === project?.id ? workItems.filter((item) => item.status !== 'done') : [],
    [workItemProjectId, project?.id, workItems],
  )
  const canWriteProject = project?.role !== 'Viewer'
  const executionReadOnly = readOnly || !canWriteProject
  const hasExecution = Boolean(activeId || messages.length)
  const taskSourceLabel = workItemsError
    ? workItemsUpdatedAt ? 'Server 暂不可达 · 显示缓存' : 'Server 任务读取失败'
    : workItemsLoading ? '正在同步 Server 权威任务' : 'Server 权威任务 · 已同步'

  const flowItems = useMemo(() => messages.flatMap((message) => {
    if (message.role !== 'assistant') return []
    const plan = [...message.trace].reverse().find((trace) => trace.kind === 'plan_snapshot' || trace.kind === 'plan_patch')
    if (!plan || (plan.kind !== 'plan_snapshot' && plan.kind !== 'plan_patch')) return []
    return plan.items.map((item) => ({ ...item, runId: message.runId }))
  }), [messages])

  useEffect(() => {
    // The workbench explains an active Run. A fresh project task inbox should
    // use the full canvas instead of reserving a permanently empty right rail.
    setPanel(hasExecution)
    return () => setPanel(false)
  }, [hasExecution, setPanel])

  useEffect(() => {
    if (!project?.id || project.origin !== 'server') return
    let alive = true
    const refresh = () => {
      if (!alive) return
      void loadWorkItems(project.id)
    }
    refresh()
    window.addEventListener('focus', refresh)
    return () => { alive = false; window.removeEventListener('focus', refresh) }
  }, [project?.id, project?.origin, loadWorkItems])

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
    if (!runId || !activeId || executionReadOnly || streaming || flowBusy) return
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

  const openTaskDetail = (itemId: string) => {
    setTaskOpen(false)
    setTaskDetailId(itemId)
  }

  const openProjectTasks = () => {
    if (!project?.id) return
    startProject(project.id, project.name)
    setView('projexec', { projectId: project.id })
  }

  const taskList = (emptyText: string) => (
    <div className="pe-server-task-list">
      {workItemsError && (
        <div className="pe-task-state warning">
          <span>{workItemsUpdatedAt ? `显示 ${new Date(workItemsUpdatedAt).toLocaleTimeString()} 的缓存` : workItemsError}</span>
          <WbButton onClick={() => project?.id && void loadWorkItems(project.id)}>重新同步</WbButton>
        </div>
      )}
      {workItemsLoading && workItems.length > 0 && <div className="pe-task-state"><span>正在刷新，当前保留上次结果</span></div>}
      {workItemsLoading && workItems.length === 0 ? (
        <div className="pe-server-task-empty">正在读取 Server 任务…</div>
      ) : pendingServerTasks.length === 0 ? (
        <div className="pe-server-task-empty">{emptyText}</div>
      ) : pendingServerTasks.map((item) => (
        <WbButton className="pe-server-task" key={item.id} onClick={() => openTaskDetail(item.id)}>
          <span className="pe-server-task-copy">
            <b>{item.title}</b>
            {item.description && <small>{item.description}</small>}
          </span>
          <span className="pe-server-task-meta">
            <span>{TASK_STATUS_LABEL[item.status]}</span>
            <span>{item.assignee_name || '未指派'}</span>
            {item.due_date && <span>截止 {item.due_date.slice(5)}</span>}
          </span>
          <span className="pe-server-task-go">查看详情</span>
        </WbButton>
      ))}
    </div>
  )

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
            <span className="pe-crumb-link project" {...clickable} onClick={openProjectTasks}>{project?.name ?? '项目'}</span>
            <span className="ps">/</span><b>{title || '开始执行'}</b>
            <span className="pe-badge">Server</span>
            {streaming && <span className="pe-badge spin" aria-label="执行中"><span className="run-ic" /></span>}
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            {hasExecution && (
              <WbButton
                className={`pe-task-trigger ${taskOpen ? 'on' : ''}`.trim()}
                aria-label={`Server 待执行任务 ${pendingServerTasks.length} 项${workItemsError ? '，当前为缓存' : ''}`}
                onClick={(event) => { taskAnchor.current = event.currentTarget; setTaskOpen((value) => !value) }}
              >
                Server 任务 <span>{pendingServerTasks.length}</span>
              </WbButton>
            )}
            <div className={`fic ${searchOpen ? 'on' : ''}`.trim()} data-tip="对话内搜索（⌘F / Ctrl+F）" aria-label="搜索" {...clickable} onClick={() => setSearchOpen((v) => !v)}><IcSearch /></div>
            <div className={`fic ${shareOpen ? 'on' : ''}`.trim()} data-tip="分享任务" aria-label="分享任务" {...clickable} onClick={(event) => { shareAnchor.current = event.currentTarget; setShareOpen((value) => !value) }}><IcShare /></div>
            <div className={`fic ${flowOpen ? 'on' : ''}`.trim()} data-tip="流转" aria-label="流转" {...clickable} onClick={(event) => { flowAnchor.current = event.currentTarget; setFlowOpen((value) => !value) }}><IcFlow /></div>
            {hasExecution && !panelOpen && <div className="fic" data-tip="打开任务工作台" aria-label="打开任务工作台" {...clickable} onClick={() => setPanel(true)}><IcPanel /></div>}
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            project?.id ? <ProjectTaskCenter
              projectId={project.id}
              projectName={project.name}
              canWrite={canWriteProject}
              sourceLabel={`${taskSourceLabel} · 本机负责执行`}
              loading={workItemsLoading}
              error={workItemsError}
              onRetry={() => void loadWorkItems(project.id)}
            /> : null
          ) : (
            <MessageList messages={messages} streaming={streaming} onRetry={retry} />
          )}
        </div>
        <div className={`scrolldn ${showDn ? 'show' : ''}`.trim()} aria-label="回到底部" {...clickable} onClick={() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
        </div>

        <div className="chat-foot">
          {executionReadOnly ? (
            // M7 C3: a teammate's run is read-only — you can view its trace/output
            // but not continue it. The owner drives their own session.
            <div className="pe-readonly">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 15a2 2 0 100-4 2 2 0 000 4z" /><path d="M6 10V7a6 6 0 0112 0v3" /><rect x="4" y="10" width="16" height="11" rx="2" /></svg>
              {project?.role === 'Viewer' && !readOnly ? <>Viewer 权限 · 只读查看 Server 任务与执行</> : <>由 <b>{ownerName || '队友'}</b> 执行 · 只读查看</>}
            </div>
          ) : (
            <>
              {pending && <AskUserCard questions={pending.questions} onAnswer={answer} />}
              <Composer variant="chat" streaming={streaming} controlStatus={controlStatus} onSend={send} onPause={pause} onResume={resume} onCancel={cancel} autoFocus />
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
            disabled={Boolean(item.work_item_id) || executionReadOnly || streaming || Boolean(flowBusy)}
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

      <Popover open={taskOpen} anchor={taskAnchor.current} dir="down" onClose={() => setTaskOpen(false)} className="pe-task-pop" minWidth={360}>
        <div className="pop-h">Server 待执行任务</div>
        {taskList('当前项目没有待执行任务')}
      </Popover>

      {taskDetailId && (
        <TodoDetailModal
          itemId={taskDetailId}
          canWrite={canWriteProject}
          mode="execute"
          onClose={() => setTaskDetailId(null)}
        />
      )}
    </section>
  )
}
