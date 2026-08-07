import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { ArtifactManifest, ChatMessage, RunPlanStatus, RunStatus } from '../../lib/types'
import { api } from '../../lib/api'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { FileTree } from './FileTree'
import { FileViewer } from './FileViewer'
import { Popover } from '../ui/Popover'
import { WbButton } from '../ui/Primitives'
import { clickable } from '../../lib/a11y'
import { IcPanel } from '../../lib/icons'
import { platform } from '../../platform'
import { useAuthStore } from '../../stores/authStore'
import { toast } from '../../stores/toastStore'

// Project task workbench. The overview mirrors WorkBuddy's task-progress/product
// navigator while every row still comes from persisted Run Plan / Artifact / diff
// events. AgentMate's workspace and change views remain available as richer tabs.
type Tab = 'prod' | 'files' | 'diff'

interface Diff { op: string; file: string; add: number; del: number }
interface Artifact { path: string; openPath: string; name: string; meta: string; primary: boolean; assetId?: string; remote?: boolean }
interface ProgressItem {
  key: string
  title: string
  status: RunPlanStatus | 'message'
  messageId: string
}

function allDiffs(messages: ChatMessage[]): Diff[] {
  const out: Diff[] = []
  for (const message of messages) {
    if (message.role !== 'assistant') continue
    for (const trace of message.trace) {
      if (trace.kind === 'diff') out.push({ op: trace.op, file: trace.file, add: trace.add, del: trace.del })
    }
  }
  return out
}

function taskProgress(messages: ChatMessage[]): ProgressItem[] {
  const planned: ProgressItem[] = []
  for (const message of messages) {
    if (message.role !== 'assistant') continue
    const plan = [...message.trace].reverse().find((trace) => trace.kind === 'plan_snapshot' || trace.kind === 'plan_patch')
    if (!plan || (plan.kind !== 'plan_snapshot' && plan.kind !== 'plan_patch')) continue
    for (const item of plan.items) {
      planned.push({
        key: `${message.runId ?? message.id}-${item.id}`,
        title: item.title,
        status: item.status,
        messageId: message.id,
      })
    }
  }
  if (planned.length) return planned

  // Older conversations predate durable Run Plans. Their real user turns are a
  // useful, honest fallback instead of manufacturing a synthetic task list.
  return messages
    .filter((message) => message.role === 'user' && message.content.trim())
    .map((message) => ({
      key: message.id,
      title: message.content.trim().replace(/\s+/g, ' '),
      status: 'message' as const,
      messageId: message.id,
    }))
}

function tracedArtifacts(messages: ChatMessage[], runId?: string): Artifact[] {
  const byPath = new Map<string, Artifact>()
  for (const message of messages) {
    if (message.role !== 'assistant') continue
    for (const trace of message.trace) {
      if (trace.kind === 'artifact') {
        if (runId && trace.artifact.run_id && trace.artifact.run_id !== runId) continue
        const status = trace.artifact.acceptance_status === 'accepted' ? '已验收' : trace.artifact.acceptance_status === 'rejected' ? '已驳回' : '待验收'
        byPath.set(trace.artifact.path, {
          path: trace.artifact.path,
          openPath: trace.artifact.path,
          name: trace.artifact.name,
          meta: `历史交付记录 · ${status}`,
          primary: byPath.size === 0,
        })
      }
    }
  }
  return [...byPath.values()]
}

function manifestArtifacts(items: ArtifactManifest[]): Artifact[] {
  return items.map((item) => {
    const accepted = item.acceptance_status === 'accepted' ? '已验收' : item.acceptance_status === 'rejected' ? '已驳回' : '待验收'
    const verified = item.verification?.exists && item.verification.hash_matches
      ? '文件与哈希已核验'
      : item.validation_status === 'passed' ? '生成校验通过' : '校验待确认'
    return {
      path: item.path,
      openPath: item.preview_path || item.path,
      name: item.name,
      meta: `${item.is_primary ? '主产物 · ' : ''}${verified} · ${accepted}`,
      primary: item.is_primary,
      assetId: item.id,
      remote: item.path.startsWith('object://'),
    }
  })
}

function latestRun(messages: ChatMessage[]): { id: string; status?: RunStatus } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role === 'assistant' && message.runId) {
      return { id: message.runId, status: message.runStatus }
    }
  }
  return null
}

function badge(name: string): string {
  return (name.split('.').pop()?.toUpperCase() ?? '').slice(0, 3) || 'F'
}

function ProgressMark({ status }: { status: ProgressItem['status'] }) {
  if (status === 'completed' || status === 'message') return <span className="pe-progress-mark done">✓</span>
  if (status === 'in_progress') return <span className="pe-progress-mark active"><i /></span>
  if (status === 'blocked') return <span className="pe-progress-mark blocked">!</span>
  return <span className="pe-progress-mark" />
}

const IC_PEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>

export function PePanel({ messages }: { messages: ChatMessage[] }) {
  const [tab, setTab] = useState<Tab>('prod')
  const [overviewOpen, setOverviewOpen] = useState(false)
  const [progressOpen, setProgressOpen] = useState(true)
  const [productOpen, setProductOpen] = useState(true)
  const [manifest, setManifest] = useState<{ runId: string; items: ArtifactManifest[] } | null>(null)
  const [manifestFailedRunId, setManifestFailedRunId] = useState<string | null>(null)
  const overviewAnchor = useRef<HTMLButtonElement>(null)
  const autoFocusedRun = useRef<string | null>(null)
  const viewerPath = useUIStore((state) => state.viewerPath)
  const openFile = useUIStore((state) => state.openFile)
  const closeFile = useUIStore((state) => state.closeFile)
  const panelOpen = useUIStore((state) => state.ovOpen)
  const panelExpanded = useUIStore((state) => state.ovExpanded)
  const setPanel = useUIStore((state) => state.setOv)
  const toggleExpand = useUIStore((state) => state.toggleExpand)
  const activeId = useChatStore((state) => state.activeId)
  const activeProjectId = useChatStore((state) => state.activeProjectId)
  const ownerId = useAuthStore((state) => state.me?.id)
  const scope = activeId ? { session: activeId } : undefined

  const diffs = allDiffs(messages)
  const run = latestRun(messages)
  const artifactSignal = messages
    .flatMap((message) => message.trace)
    .filter((trace) => trace.kind === 'artifact')
    .map((trace) => trace.kind === 'artifact'
      ? `${trace.artifact.id ?? trace.artifact.path}:${trace.artifact.acceptance_status}`
      : '')
    .join('|')
  const products = run && manifest?.runId === run.id
    ? manifestArtifacts(manifest.items)
    : run && manifestFailedRunId === run.id
      ? tracedArtifacts(messages, run.id)
      : run ? [] : tracedArtifacts(messages)
  const progress = taskProgress(messages)

  const openProduct = async (product: Artifact) => {
    if (!product.remote || !product.assetId) {
      openFile(product.openPath)
      return
    }
    if (!platform.isDesktop || !ownerId) {
      toast('该产物在 Server，请使用桌面端下载 working copy')
      return
    }
    const safeName = product.name.replace(/[\\/]/g, '_')
    const relativePath = `.agentmate/assets/${product.assetId}/${safeName}`
    try {
      await platform.localAgent.downloadAsset(product.assetId, {
        ownerId, relativePath, projectId: activeProjectId || undefined,
      })
      openFile(relativePath)
    } catch {
      toast('Server 产物下载或哈希校验失败')
    }
  }

  useEffect(() => {
    let active = true
    if (!run) {
      setManifest(null)
      setManifestFailedRunId(null)
      return () => { active = false }
    }
    setManifest((current) => current?.runId === run.id ? current : null)
    setManifestFailedRunId(null)
    void api.listRunArtifacts(run.id).then(({ artifacts: items }) => {
      if (!active) return
      setManifest({ runId: run.id, items })
    }).catch(() => {
      if (!active) return
      setManifestFailedRunId(run.id)
    })
    return () => { active = false }
  }, [run?.id, run?.status, artifactSignal])

  useEffect(() => {
    if (
      !run || !panelOpen || viewerPath || manifest?.runId !== run.id || !products.length
      || !['completed', 'accepted'].includes(run.status ?? '')
      || autoFocusedRun.current === run.id
    ) return
    autoFocusedRun.current = run.id
    setTab('prod')
    const product = products.find((item) => item.primary) ?? products[0]
    if (!product.remote) openFile(product.openPath)
  }, [manifest?.runId, openFile, panelOpen, products, run, viewerPath])

  const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: 'prod', label: '产物', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg> },
    { id: 'files', label: '工作空间文件', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg> },
    { id: 'diff', label: `变更${diffs.length ? ` (${diffs.length})` : ''}`, icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6" /></svg> },
  ]

  const jump = (messageId: string) => {
    setOverviewOpen(false)
    document.getElementById(`msg-${messageId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const selectTab = (next: Tab) => {
    setTab(next)
    closeFile()
  }

  return (
    <aside
      className={`ovpanel pe ${panelOpen ? 'open' : ''} ${panelOpen && panelExpanded ? 'expanded' : ''}`.trim()}
      aria-label="任务工作台"
      aria-hidden={!panelOpen}
    >
      {panelOpen && <div className="ov-inner">
        <div className="pe-top">
          <WbButton ref={overviewAnchor} className={`pe-top-btn ${overviewOpen ? 'on' : ''}`.trim()} aria-label="任务概览" data-tip="任务概览" onClick={() => setOverviewOpen((value) => !value)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
          </WbButton>
          <span className="pe-top-title">{viewerPath ? viewerPath.split('/').pop() : '任务工作台'}</span>
          <WbButton className="pe-top-btn" aria-label={panelExpanded ? '收起为侧栏' : '展开任务工作台'} data-tip={panelExpanded ? '收起为侧栏' : '展开任务工作台'} onClick={toggleExpand}>
            {panelExpanded ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 20H4v-6M4 20l9-9" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 4h6v6M20 4l-9 9" /></svg>
            )}
          </WbButton>
          <WbButton className="pe-top-btn on" aria-label="收起任务工作台" data-tip="收起任务工作台" onClick={() => setPanel(false)}><IcPanel /></WbButton>
        </div>

        <Popover open={overviewOpen} anchor={overviewAnchor.current} dir="down" onClose={() => setOverviewOpen(false)} className="pe-overview-pop" minWidth={304}>
          <div className="pe-overview-title">概览</div>
          <div className="pe-overview-section">
            <div className="pe-overview-head" {...clickable} onClick={() => setProgressOpen((value) => !value)}>
              任务进程
              <svg className={progressOpen ? '' : 'collapsed'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
            </div>
            {progressOpen && (
              <div className="pe-progress-list">
                {progress.length ? progress.map((item) => (
                  <div className="pe-progress-item" key={item.key} title={item.title} {...clickable} onClick={() => jump(item.messageId)}>
                    <ProgressMark status={item.status} />
                    <span>{item.title}</span>
                  </div>
                )) : <div className="pe-overview-empty">执行计划尚未生成</div>}
              </div>
            )}
          </div>
          <div className="pe-overview-section">
            <div className="pe-overview-head" {...clickable} onClick={() => setProductOpen((value) => !value)}>
              产物
              <svg className={productOpen ? '' : 'collapsed'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
            </div>
            {productOpen && (
              <div className="pe-product-list">
                {products.length ? products.map((product) => (
                  <div className={`pe-product-item ${viewerPath === product.openPath ? 'active' : ''}`.trim()} key={product.path} {...clickable} onClick={() => { void openProduct(product); setTab('prod'); setOverviewOpen(false) }}>
                    <span className="pe-product-badge">{badge(product.name)}</span>
                    <span title={product.name}>{product.name}</span>
                  </div>
                )) : <div className="pe-overview-empty">暂无产物</div>}
              </div>
            )}
          </div>
        </Popover>

        <div className="pe-tabs" role="tablist" aria-label="任务工作台视图">
          {TABS.map((item) => (
            <WbButton key={item.id} className={`pe-tab ${tab === item.id ? 'active' : ''}`.trim()} role="tab" aria-selected={tab === item.id} onClick={() => selectTab(item.id)}>
              {item.icon}{item.label}
            </WbButton>
          ))}
        </div>

        {viewerPath ? (
          <FileViewer path={viewerPath} onClose={closeFile} scope={scope} />
        ) : tab === 'prod' ? (
          products.length ? (
            <div className="pe-artifacts">
              {products.map((product) => (
                <div className="ov-art" key={product.path} {...clickable} onClick={() => void openProduct(product)}>
                  <span className="oa-ic">{badge(product.name)}</span>
                  <div className="pe-artifact-copy"><div className="oa-n">{product.name}</div><div className="oa-m">{product.meta}</div></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pe-empty">请开始执行，任务产出的产物会显示在这里</div>
          )
        ) : tab === 'files' ? (
          <FileTree scope={scope} />
        ) : diffs.length ? (
          <div className="pe-diffs">
            {diffs.map((diff, index) => (
              <div className="step" key={`${diff.file}-${index}`} {...clickable} onClick={() => openFile(diff.file)}>
                {IC_PEN}<span className="op">{diff.op}</span>
                <a>{diff.file}</a>
                <span className="add">+{diff.add}</span><span className="del">-{diff.del}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="pe-empty">暂无变更</div>
        )}
      </div>}
    </aside>
  )
}
