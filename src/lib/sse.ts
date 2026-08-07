// SSE-over-POST reader.
//
// /api/chat is a POST that returns text/event-stream, so the browser's
// EventSource (GET-only) can't consume it. We read the fetch body stream and
// parse `event:`/`data:` frames ourselves, dispatching typed events. An
// AbortController lets the Composer's stop button cancel the request client-side
// (the /stop endpoint stops it server-side too).

import { API_BASE, authHeaders, type RawMessage } from './api'
import { SSE_EVENT_TYPES } from './types'
import type { AgentRun, Orchestration, SSEEvent, SessionInfo, TraceItem } from './types'
import {
  localExecutionSession, rememberLocalExecutionSession, serverGet, serverGetAll, serverSend,
} from './channels'
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

export async function streamChat(opts: ChatStreamOptions): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  let serverTurn: Awaited<ReturnType<typeof prepareServerTurn>> | null = null
  let assistantContent = ''
  let assistantTrace: TraceItem[] = []
  let assistantUsage: { prompt: number; completion: number } | null = null
  let assistantError = ''
  let localDone = false

  const onLocalEvent = (event: SSEEvent) => {
    if (!serverTurn) return
    if (event.type === 'session') {
      rememberLocalExecutionSession(serverTurn.session.id, event.data.id)
      return
    }
    if (event.type === 'run') {
      opts.onEvent({
        type: 'run',
        data: { run: serverTurn.run, user_message_id: serverTurn.userMessage.id },
      })
      return
    }
    if (event.type === 'text') assistantContent += event.data.md
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
    else if (event.type === 'usage') {
      assistantUsage = {
        prompt: Number(event.data.detail.prompt_tokens || event.data.used || 0),
        completion: Number(event.data.detail.completion_tokens || 0),
      }
    } else if (event.type === 'error') assistantError = event.data.message
    else if (event.type === 'done') {
      localDone = true
      return
    }
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
    const resp = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        text: opts.text,
        session_id: localExecutionSession(serverTurn.session.id),
        title: opts.title,
        space: opts.space,
        model: opts.model,
        plan: opts.plan,
        ask: opts.ask,
        project_id: opts.projectId,
        experts: opts.experts,
        skills: opts.skills,
        skill_bundles: opts.skillBundles,
        connectors: opts.connectors,
        knowledge_ids: opts.knowledgeIds,
        refs: opts.refs,
        idempotency_key: opts.idempotencyKey,
        // retryOf is a Server Run id and must never be passed into the local
        // compatibility database as if it were a local Run foreign key.
        retry_of: undefined,
        history: serverTurn.history.slice(-200).map((message) => ({ role: message.role, content: message.content })),
      }),
      signal: opts.signal,
    })

    if (!resp.ok || !resp.body) {
      const detail = await resp.text().catch(() => '')
      opts.onEvent({ type: 'error', data: { message: `HTTP ${resp.status} ${detail}` } })
      opts.onEvent({ type: 'done', data: {} })
      return
    }

    reader = resp.body.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by a blank line.
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        dispatchFrame(frame, onLocalEvent)
      }
    }

    // Stream closed cleanly. Flush any trailing multibyte bytes, then dispatch a
    // final frame the server didn't terminate with a blank line (WB-020) — else a
    // last `done` frame is dropped and the bubble stays 'running'.
    buffer += decoder.decode()
    if (buffer.trim()) dispatchFrame(buffer, onLocalEvent)
    if (!localDone) throw new Error('Local Agent 执行流意外断开')
    await commitRunArtifacts(serverTurn, assistantTrace)
    const message = await finalizeServerTurn(
      serverTurn, assistantContent, assistantTrace, assistantUsage, assistantError,
    )
    opts.onEvent({ type: 'done', data: { message_id: message.id } })
  } catch (e) {
    // AbortError is an expected outcome of the stop button — the caller's stop()
    // already finalised the bubble, so stay silent (and keep one-shot refs).
    if ((e as Error).name !== 'AbortError') {
      if (serverTurn) {
        try {
          await failServerTurn(serverTurn.run.id, e instanceof Error ? e.message : String(e))
        } catch {
          // The original failure remains the one shown to the user.
        }
      }
      opts.onEvent({ type: 'error', data: { message: String(e) } })
      opts.onEvent({ type: 'done', data: {} })
    } else if (serverTurn) {
      void cancelServerTurn(serverTurn.run.id)
    }
  } finally {
    reader?.releaseLock?.()
  }
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

async function prepareServerTurn(opts: ChatStreamOptions): Promise<{
  session: SessionInfo & { version: number }
  history: RawMessage[]
  userMessage: RawMessage
  run: AgentRun & { version: number }
}> {
  let session: SessionInfo & { version: number }
  if (opts.sessionId) {
    session = await serverGet<SessionInfo & { version: number }>(`/sessions/${opts.sessionId}`, { cache: false })
  } else {
    const result = await serverSend<{ session: SessionInfo & { version: number } }>('POST', '/sessions', {
      title: (opts.title || opts.text).slice(0, 500),
      project_id: opts.projectId || null,
      space: opts.space || null,
      kind: opts.projectId ? 'projexec' : 'chat',
    }, { headers: { 'Idempotency-Key': requestKey('session') } })
    session = result.session
  }

  const history = await serverGetAll<RawMessage>(
    `/sessions/${session.id}/messages`, 'messages', 500, { cache: false },
  )
  const messageResult = await serverSend<{ message: RawMessage }>(
    'POST', `/sessions/${session.id}/messages`,
    { role: 'user', content: opts.text },
    { headers: { 'Idempotency-Key': requestKey('message') } },
  )
  const mode = opts.ask ? 'ask' : opts.plan ? 'plan' : 'exec'
  const runResult = await serverSend<{ run: AgentRun & { version: number } }>('POST', '/runs', {
    session_id: session.id,
    mode,
    workspace: opts.projectId ? `project:${opts.projectId}` : 'default',
    retry_of: opts.retryOf || null,
    model_ref: opts.model || null,
    required_capabilities: mode === 'ask' ? ['llm.chat'] : ['llm.chat', 'agent.tools'],
    request_snapshot: {
      automation_id: opts.automationId || null,
      loadout: {
        experts: opts.experts || [], skills: opts.skills || [],
        skill_bundles: opts.skillBundles || [], connectors: opts.connectors || [],
        knowledge_ids: opts.knowledgeIds || [],
      },
      refs: (opts.refs || []).map((item) => ({ name: item.name, kind: item.kind || 'file', item_id: item.itemId || null })),
    },
  }, { headers: { 'Idempotency-Key': opts.idempotencyKey || requestKey('run') } })
  return { session, history, userMessage: messageResult.message, run: runResult.run }
}

async function latestRun(runId: string): Promise<AgentRun & { version: number }> {
  return serverGet<AgentRun & { version: number }>(`/runs/${runId}`, { cache: false })
}

async function patchRun(runId: string, patch: Record<string, unknown>): Promise<void> {
  const current = await latestRun(runId)
  await serverSend('PATCH', `/runs/${runId}`, { ...patch, expected_version: current.version })
}

async function finalizeServerTurn(
  turn: Awaited<ReturnType<typeof prepareServerTurn>>,
  content: string,
  trace: TraceItem[],
  usage: { prompt: number; completion: number } | null,
  error: string,
): Promise<RawMessage> {
  await patchRun(turn.run.id, {
    status: error ? 'failed' : 'completed',
    error_code: error ? 'local_execution_failed' : null,
    error_message: error || null,
    prompt_tokens: usage?.prompt || 0,
    completion_tokens: usage?.completion || 0,
    ended_at: Date.now() / 1000,
  })
  const result = await serverSend<{ message: RawMessage }>(
    'POST', `/sessions/${turn.session.id}/messages`,
    { role: 'assistant', content, run_id: turn.run.id, trace, usage, error: error || null },
    { headers: { 'Idempotency-Key': requestKey('assistant-message') } },
  )
  return result.message
}

async function failServerTurn(runId: string, message: string): Promise<void> {
  await patchRun(runId, {
    status: 'failed', error_code: 'desktop_execution_bridge_failed',
    error_message: message.slice(0, 20_000), ended_at: Date.now() / 1000,
  })
}

async function cancelServerTurn(runId: string): Promise<void> {
  try {
    await serverSend('POST', `/runs/${runId}/cancel`)
  } catch {
    await patchRun(runId, { status: 'cancelled', ended_at: Date.now() / 1000 })
  }
}

function dispatchFrame(frame: string, onEvent: (ev: SSEEvent) => void): void {
  const parsed = parseFrame(frame)
  if (!parsed) {
    if (frame.split('\n').some((line) => line.startsWith('data:'))) {
      onEvent({ type: 'error', data: { message: 'SSE 协议错误：事件数据不是有效 JSON' } })
    }
    return
  }
  const event = checkedSSEEvent(parsed.event, parsed.data)
  if (!event) {
    onEvent({
      type: 'error',
      data: { message: `SSE 协议错误：未知事件或无效数据（${parsed.event || 'message'}）` },
    })
    return
  }
  onEvent(event)
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
  const resp = await fetch(`${API_BASE}/orchestrations/${encodeURIComponent(id)}/events`, {
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
