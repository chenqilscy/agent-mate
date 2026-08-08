// Server-owned Run event reader. The App commits one atomic Turn, then follows
// events that the Local Agent durably delivered through its WAL/ACK transport.

import { authHeaders, type RawMessage } from './api'
import { SSE_EVENT_TYPES } from './types'
import type { AgentRun, Orchestration, SSEEvent, SessionInfo, TraceItem } from './types'
import { LOCAL_API_BASE, serverGet, serverGetAll, serverSend } from './channels'
import { platform } from '../platform'
import { useAuthStore } from '../stores/authStore'

export interface ChatStreamOptions {
  text: string
  sessionId?: string
  title?: string
  space?: string
  model?: string
  plan?: boolean
  ask?: boolean
  projectId?: string
  experts?: string[]
  skills?: string[]
  skillBundles?: string[]
  connectors?: string[]
  knowledgeIds?: string[]
  refs?: { name: string; content: string; kind?: 'file' | 'todo'; itemId?: string }[]
  idempotencyKey?: string
  retryOf?: string
  automationId?: string
  signal?: AbortSignal
  onEvent: (ev: SSEEvent) => void
}

export interface FollowServerRunOptions {
  runId: string
  sessionId: string
  signal?: AbortSignal
  onEvent: (ev: SSEEvent) => void
}

export async function startWorkItemRun(opts: {
  projectId: string
  workItemId: string
  title: string
  description: string
  model?: string | null
  idempotencyKey?: string
}): Promise<{
  session: SessionInfo & { version: number }
  user_message: RawMessage
  run: AgentRun & { version: number }
  duplicate: boolean
}> {
  const key = opts.idempotencyKey || requestKey('work-item')
  const targetDeviceId = await stageLocalRunInput(key, [{
    name: opts.title,
    content: opts.description.trim() ? `${opts.title}\n\n${opts.description}` : opts.title,
    kind: 'todo', itemId: opts.workItemId,
  }])
  if (!targetDeviceId) throw new Error('Local Agent 未返回可执行设备身份')
  return serverSend('POST', `/projects/${opts.projectId}/work-items/${opts.workItemId}/execute`, {
    target_device_id: targetDeviceId,
    local_input_key: key,
    model_ref: opts.model || null,
  }, { headers: { 'Idempotency-Key': key } })
}

export async function streamChat(opts: ChatStreamOptions): Promise<void> {
  let serverTurn: Awaited<ReturnType<typeof prepareServerTurn>> | null = null
  let assistantTrace: TraceItem[] = []

  const onRunEvent = (event: SSEEvent) => {
    if (event.type === 'run_recovered') assistantTrace = []
    else if (event.type === 'think') assistantTrace.push({ kind: 'think', text: event.data.text })
    else if (event.type === 'step') assistantTrace.push({ kind: 'step', tool: event.data.tool, label: event.data.label })
    else if (event.type === 'file_read') assistantTrace.push({ kind: 'file_read', path: event.data.path, range: event.data.range })
    else if (event.type === 'diff') assistantTrace.push({ kind: 'diff', ...event.data })
    else if (event.type === 'todo') assistantTrace.push({ kind: 'todo', text: event.data.text })
    else if (event.type === 'plan_snapshot' || event.type === 'plan_patch') {
      assistantTrace = [
        ...assistantTrace.filter((item) => !['todo', 'plan_snapshot', 'plan_patch'].includes(item.kind)),
        { kind: event.type, version: event.data.version, items: event.data.items, project_id: event.data.project_id },
      ]
    } else if (event.type === 'qa_summary') assistantTrace.push({ kind: 'qa', qa: event.data.qa })
    else if (event.type === 'context_degraded') assistantTrace.push({ kind: 'context_degraded', ...event.data })
    else if (event.type === 'artifact') assistantTrace.push({ kind: 'artifact', artifact: event.data })
    opts.onEvent(event)
  }

  // The whole request lives in the try: a failed fetch (backend down / network
  // error) must surface as error+done to the caller, not reject out of streamChat
  // and become an unhandled rejection with the bot bubble stuck 'running' (WB-001).
  try {
    serverTurn = await prepareServerTurn(opts)
    opts.onEvent({
      type: 'session',
      data: { id: serverTurn.session.id, title: serverTurn.session.title },
    })
    opts.onEvent({
      type: 'run',
      data: { run: serverTurn.run, user_message_id: serverTurn.userMessage.id },
    })
    await followServerRun({
      runId: serverTurn.run.id,
      sessionId: serverTurn.session.id,
      signal: opts.signal,
      onEvent: onRunEvent,
    })
    await commitRunArtifacts(serverTurn, assistantTrace)
  } catch (e) {
    // AbortError is an expected outcome of the stop button — the caller's stop()
    // already finalised the bubble, so stay silent (and keep one-shot refs).
    if ((e as Error).name !== 'AbortError') {
      opts.onEvent({ type: 'error', data: { message: String(e) } })
      opts.onEvent({ type: 'done', data: {} })
    }
  }
}

export async function followServerRun(opts: FollowServerRunOptions): Promise<void> {
  const pageLimit = 1000
  let afterEpoch = 0
  let afterSequence = 0
  let currentEpoch = 0
  let sawError = false
  let terminalRun: AgentRun | null = null

  while (true) {
    if (opts.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const query = new URLSearchParams({
      after_epoch: String(afterEpoch),
      after_sequence: String(afterSequence),
      limit: String(pageLimit),
    })
    const result = await serverGet<{
      run: AgentRun
      events: Array<{
        event_id: string
        lease_epoch: number
        sequence: number
        type: string
        payload: Record<string, unknown>
      }>
    }>(`/runs/${opts.runId}/events?${query}`, { cache: false })
    terminalRun = result.run
    const serverEpoch = Math.max(0, Number(result.run.lease_epoch || 0))
    if (serverEpoch > currentEpoch) {
      if (currentEpoch > 0) {
        opts.onEvent({ type: 'run_recovered', data: { lease_epoch: serverEpoch } })
        sawError = false
      }
      currentEpoch = serverEpoch
    }

    for (const event of result.events) {
      afterEpoch = event.lease_epoch
      afterSequence = event.sequence
      if (event.lease_epoch < currentEpoch) continue
      if (event.lease_epoch > currentEpoch) {
        currentEpoch = event.lease_epoch
        opts.onEvent({ type: 'run_recovered', data: { lease_epoch: currentEpoch } })
        sawError = false
      }
      if (event.type.startsWith('ui.')) {
        const checked = checkedSSEEvent(event.type.slice(3), event.payload)
        if (checked) {
          if (checked.type === 'error') sawError = true
          opts.onEvent(checked)
        }
      } else if (event.type === 'run.waiting_user') {
        const checked = checkedSSEEvent('ask_user', {
          ...event.payload, question_event_id: event.event_id,
        })
        if (checked) opts.onEvent(checked)
      }
    }

    const terminal = ['completed', 'succeeded', 'failed', 'cancelled'].includes(result.run.status)
    if (terminal && result.events.length < pageLimit) break
    if (!result.events.length || result.events.length < pageLimit) {
      await abortableDelay(350, opts.signal)
    }
  }

  if (terminalRun?.status === 'failed' && !sawError) {
    opts.onEvent({
      type: 'error',
      data: { message: terminalRun.error_message || terminalRun.error_code || 'Local Agent 执行失败' },
    })
  }
  const messages = await serverGetAll<RawMessage>(
    `/sessions/${opts.sessionId}/messages`, 'messages', 500, { cache: false },
  )
  const message = [...messages].reverse().find(
    (item) => item.run_id === opts.runId && item.role === 'assistant',
  )
  opts.onEvent({ type: 'done', data: { message_id: message?.id } })
}

function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

async function commitRunArtifacts(
  turn: Awaited<ReturnType<typeof prepareServerTurn>>,
  trace: TraceItem[],
): Promise<void> {
  if (!platform.isDesktop) return
  const ownerId = useAuthStore.getState().me?.id
  if (!ownerId) return
  const paths = new Set<string>()
  for (const item of trace) {
    if (item.kind !== 'artifact' || !item.artifact.path || paths.has(item.artifact.path)) continue
    paths.add(item.artifact.path)
    try {
      await platform.localAgent.commitAsset({
        ownerId,
        localPath: item.artifact.path,
        projectId: turn.run.project_id || undefined,
        sessionId: turn.session.id,
        runId: turn.run.id,
        kind: 'artifact',
      })
    } catch {
      // The Core persisted local-only/uploading state before returning. A Server
      // outage must not invalidate an otherwise successful local Run.
    }
  }
}

function requestKey(prefix: string): string {
  return `${prefix}:${crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}:${Math.random()}`}`
}

async function stageLocalRunInput(
  requestKeyValue: string,
  refs: NonNullable<ChatStreamOptions['refs']>,
): Promise<string> {
  if (!refs.length) return ''
  const ownerId = useAuthStore.getState().me?.id
  if (!ownerId) throw new Error('Local Agent 尚未绑定 Server 身份')
  const payload = refs.map((item) => ({
    name: item.name, content: item.content,
    kind: item.kind || 'file', itemId: item.itemId || null,
  }))
  if (platform.isDesktop) {
    const deviceId = await platform.localAgent.stageRunInput(ownerId, requestKeyValue, payload)
    if (!deviceId) throw new Error('Local Agent 无法暂存本机输入')
    return deviceId
  }
  const response = await fetch(`${LOCAL_API_BASE}/local-run-inputs`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ request_key: requestKeyValue, refs: payload }),
  })
  if (!response.ok) throw new Error(`Local Agent 无法暂存本机输入（HTTP ${response.status}）`)
  const result = await response.json() as { device_id?: string }
  if (!result.device_id) throw new Error('Local Agent 未返回设备身份')
  return result.device_id
}

async function prepareServerTurn(opts: ChatStreamOptions): Promise<{
  session: SessionInfo & { version: number }
  userMessage: RawMessage
  run: AgentRun & { version: number }
}> {
  const mode = opts.ask ? 'ask' : opts.plan ? 'plan' : 'exec'
  const turnKey = opts.idempotencyKey || requestKey('run')
  const targetDeviceId = await stageLocalRunInput(turnKey, opts.refs || [])
  const turn = await serverSend<{
    session: SessionInfo & { version: number }
    user_message: RawMessage
    run: AgentRun & { version: number }
  }>('POST', '/turns', {
    text: opts.text,
    session_id: opts.sessionId || null,
    title: (opts.title || opts.text).slice(0, 500),
    project_id: opts.projectId || null,
    space: opts.space || null,
    kind: opts.projectId ? 'projexec' : 'chat',
    mode,
    workspace: opts.projectId ? `project:${opts.projectId}` : 'default',
    retry_of: opts.retryOf || null,
    model_ref: opts.model || null,
    target_device_id: targetDeviceId,
    required_capabilities: ['run_events_v1', 'llm.chat', ...(mode === 'ask' ? [] : ['agent.tools'])],
    request_snapshot: {
      automation_id: opts.automationId || null,
      loadout: {
        experts: opts.experts || [], skills: opts.skills || [],
        skill_bundles: opts.skillBundles || [], connectors: opts.connectors || [],
        knowledge_ids: opts.knowledgeIds || [],
      },
      refs: (opts.refs || []).map((item) => ({
        name: item.name,
        kind: item.kind || 'file', itemId: item.itemId || null,
      })),
      local_input_key: targetDeviceId ? turnKey : null,
    },
  }, { headers: { 'Idempotency-Key': turnKey } })
  return { session: turn.session, userMessage: turn.user_message, run: turn.run }
}

const SSE_EVENT_TYPE_SET = new Set<string>(SSE_EVENT_TYPES)

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function checkedSSEEvent(type: string, data: unknown): SSEEvent | null {
  if (!SSE_EVENT_TYPE_SET.has(type)) return null
  const value = record(data)
  if (!value) return null
  const text = (key: string) => typeof value[key] === 'string'
  const number = (key: string) => typeof value[key] === 'number' && Number.isFinite(value[key])
  let valid = false
  switch (type as SSEEvent['type']) {
    case 'session': valid = text('id') && text('title'); break
    case 'status': valid = value.state === 'running' || value.state === 'done'; break
    case 'run': valid = record(value.run) !== null; break
    case 'run_recovered': valid = number('lease_epoch'); break
    case 'think':
    case 'todo': valid = text('text'); break
    case 'step': valid = text('tool') && text('label'); break
    case 'file_read': valid = text('path') && text('range'); break
    case 'diff': valid = text('op') && text('file') && number('add') && number('del'); break
    case 'plan_snapshot':
    case 'plan_patch': valid = number('version') && Array.isArray(value.items); break
    case 'text': valid = text('md'); break
    case 'ask_user': valid = Array.isArray(value.questions); break
    case 'qa_summary': valid = Array.isArray(value.qa); break
    case 'context_degraded':
      valid = text('reason') && number('excerpt_messages') && value.retry_on_next_turn === true
      break
    case 'artifact': valid = text('name') && text('size') && text('path'); break
    case 'work_item': valid = record(value.item) !== null; break
    case 'usage': valid = number('pct') && number('used') && record(value.detail) !== null; break
    case 'error': valid = text('message'); break
    case 'done': valid = value.message_id === undefined || text('message_id'); break
  }
  return valid ? { type, data } as SSEEvent : null
}

function parseFrame(frame: string): { event: string; data: unknown } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  let data: unknown
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    return null
  }
  return { event, data }
}

export async function streamOrchestration(
  id: string,
  opts: { signal?: AbortSignal; onSnapshot: (item: Orchestration) => void },
): Promise<void> {
  const resp = await fetch(`${LOCAL_API_BASE}/orchestrations/${encodeURIComponent(id)}/events`, {
    headers: authHeaders(), signal: opts.signal,
  })
  if (!resp.ok || !resp.body) throw new Error(`专家团状态流不可用（HTTP ${resp.status}）`)

  const decoder = new TextDecoder()
  const reader = resp.body.getReader()
  let buffer = ''
  let completed = false
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const parsed = parseFrame(buffer.slice(0, idx))
        buffer = buffer.slice(idx + 2)
        if (!parsed) continue
        if (parsed.event === 'orchestration') {
          const payload = parsed.data as { orchestration?: Orchestration }
          if (payload?.orchestration) opts.onSnapshot(payload.orchestration)
        } else if (parsed.event === 'error') {
          const payload = parsed.data as { message?: string }
          throw new Error(payload?.message || '专家团状态流错误')
        } else if (parsed.event === 'done') {
          completed = true
        }
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) {
      const parsed = parseFrame(buffer)
      if (parsed?.event === 'orchestration') {
        const payload = parsed.data as { orchestration?: Orchestration }
        if (payload?.orchestration) opts.onSnapshot(payload.orchestration)
      } else if (parsed?.event === 'done') completed = true
    }
    if (!completed && !opts.signal?.aborted) throw new Error('专家团状态流意外断开')
  } finally {
    reader.releaseLock()
  }
}
