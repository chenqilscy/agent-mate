// chatStore — the heart of M1.
//
// Holds sessions, the active session's messages, and streaming state. Each SSE
// event is folded into the active assistant message by type (text appends prose,
// think/step/diff/todo append trace items, status/usage/done finalise). React
// renders from this state, so the stream reproduces the prototype's live trace —
// but driven by real events.
import { create } from 'zustand'
import { api } from '../lib/api'
import { streamChat } from '../lib/sse'
import type { AskQuestion, ChatMessage, SessionInfo, SSEEvent, TraceItem } from '../lib/types'
import { useSettingsStore } from './settingsStore'
import { useLoadoutStore } from './loadoutStore'
import { useUIStore } from './uiStore'
import { useWorkItemStore } from './workItemStore'
import { toast } from './toastStore'

function uuid(): string {
  return crypto.randomUUID ? crypto.randomUUID() : String(Math.random())
}

function withRunPlan(
  trace: TraceItem[], version: number, items: import('../lib/types').RunPlanItem[],
  projectId?: string | null, kind: 'plan_snapshot' | 'plan_patch' = 'plan_snapshot',
): TraceItem[] {
  if (!items.length && !version) return trace
  return [
    ...trace.filter((item) => !['todo', 'plan_snapshot', 'plan_patch'].includes(item.kind)),
    { kind, version, items, project_id: projectId },
  ]
}

interface ChatState {
  sessions: SessionInfo[]
  activeId: string | null
  title: string
  messages: ChatMessage[]
  streaming: boolean
  abort: AbortController | null
  // ask_user: questions awaiting the user's answer (null = none pending).
  pending: { questions: AskQuestion[] } | null
  // project scope: when set, a new session is created under this project.
  activeProjectId: string | null
  // M7 C3: viewing a teammate's project session is read-only (you can't drive it).
  readOnly: boolean
  ownerName: string | null

  loadSessions: () => Promise<void>
  openSession: (id: string) => Promise<void>
  startDraft: (title: string) => void
  startProject: (projectId: string, name: string) => void
  send: (text: string, retryOf?: string) => Promise<void>
  retry: (messageId: string) => Promise<void>
  answer: (answers: string[]) => void
  stop: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeId: null,
  title: '对话',
  messages: [],
  streaming: false,
  abort: null,
  pending: null,
  activeProjectId: null,
  readOnly: false,
  ownerName: null,

  loadSessions: async () => {
    try {
      const { sessions } = await api.listSessions()
      set({ sessions })
    } catch {
      /* backend down — keep whatever we have */
    }
  },

  openSession: async (id) => {
    if (get().streaming) get().stop()
    useUIStore.getState().closeFile()
    useLoadoutStore.getState().reset()
    try {
      const { session, messages } = await api.getMessages(id)
      set({
        activeId: id,
        activeProjectId: session.project_id ?? null,
        title: session.title,
        readOnly: session.read_only ?? false,
        ownerName: session.owner_name ?? null,
        messages: messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          trace: withRunPlan(
            (m.trace as TraceItem[]) ?? [],
            m.run_plan_version ?? 0,
            m.run_plan ?? [],
            m.run_project_id,
          ),
          status: 'done',
          usage: m.usage,
          runId: m.run_id ?? undefined,
          runStatus: m.run_status ?? undefined,
          pendingQuestion: m.pending_question ?? undefined,
          error: m.error ?? undefined,
        })),
      })
    } catch {
      /* ignore */
    }
  },

  // Home → Chat: reset to an empty conversation. The backend session is created
  // lazily on the first send (returned via the `session` event).
  // NB: startDraft/startProject do NOT reset the loadout — the composer's ＋-menu
  // picks are made just before send() calls these, so wiping here would drop them.
  // Fresh-start reset happens on the sidebar's 新建任务 action; opening a different
  // existing session resets in openSession.
  startDraft: (title) => {
    if (get().streaming) get().stop()
    useUIStore.getState().closeFile()
    set({ activeId: null, activeProjectId: null, title, messages: [], readOnly: false, ownerName: null })
  },

  // Open a project's execution: a fresh chat scoped to the project. The first
  // send creates a project-scoped session (kind=projexec) on the backend.
  startProject: (projectId, name) => {
    if (get().streaming) get().stop()
    useUIStore.getState().closeFile()
    set({ activeId: null, activeProjectId: projectId, title: name, messages: [], readOnly: false, ownerName: null })
  },

  send: async (text, retryOf) => {
    const trimmed = text.trim()
    // Read-only = viewing a teammate's session (M7 C3); the backend would 404 a
    // drive attempt anyway, so refuse locally and keep the view clean.
    if (!trimmed || get().streaming || get().readOnly) return

    const userMsg: ChatMessage = { id: uuid(), role: 'user', content: trimmed, trace: [] }
    const botMsg: ChatMessage = {
      id: uuid(),
      role: 'assistant',
      content: '',
      trace: [],
      status: 'running',
    }
    set((s) => ({
      messages: [...s.messages, userMsg, botMsg],
      streaming: true,
    }))

    const botId = botMsg.id
    const patchBot = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => ({ messages: s.messages.map((m) => (m.id === botId ? fn(m) : m)) }))

    const controller = new AbortController()
    set({ abort: controller })

    // Success tracking: refs are one-shot but must survive a failed/stopped send
    // (WB-006). We only clear them when the stream finished cleanly (done, no error).
    let errored = false
    let doneOk = false

    const onEvent = (ev: SSEEvent) => {
      // Drop frames from a superseded stream: after stop()/openSession the active
      // controller changes, but a last buffered chunk of the old stream can still
      // dispatch and clobber the new session's session/usage/ask_user state (WB-019).
      if (get().abort !== controller) return
      switch (ev.type) {
        case 'session':
          set({ activeId: ev.data.id, title: ev.data.title })
          {
            const projectId = get().activeProjectId ?? undefined
            useUIStore.getState().setView(projectId ? 'projexec' : 'chat', {
              projectId,
              sessionId: ev.data.id,
              replace: true,
            })
          }
          break
        case 'run':
          patchBot((m) => ({
            ...m,
            runId: ev.data.run.id,
            runStatus: 'running',
            trace: withRunPlan(
              m.trace, ev.data.run.plan_version, ev.data.run.plan,
              ev.data.run.project_id,
            ),
          }))
          break
        case 'text':
          patchBot((m) => ({ ...m, content: m.content + ev.data.md }))
          break
        case 'think':
          patchBot((m) => ({ ...m, trace: [...m.trace, { kind: 'think', text: ev.data.text }] }))
          break
        case 'step':
          patchBot((m) => ({
            ...m,
            trace: [...m.trace, { kind: 'step', tool: ev.data.tool, label: ev.data.label }],
          }))
          break
        case 'file_read':
          patchBot((m) => ({
            ...m,
            trace: [...m.trace, { kind: 'file_read', path: ev.data.path, range: ev.data.range }],
          }))
          break
        case 'diff':
          patchBot((m) => ({
            ...m,
            trace: [
              ...m.trace,
              { kind: 'diff', op: ev.data.op, file: ev.data.file, add: ev.data.add, del: ev.data.del },
            ],
          }))
          break
        case 'todo':
          patchBot((m) => ({ ...m, trace: [...m.trace, { kind: 'todo', text: ev.data.text }] }))
          break
        case 'plan_snapshot':
        case 'plan_patch':
          patchBot((m) => ({
            ...m,
            trace: withRunPlan(
              m.trace, ev.data.version, ev.data.items, ev.data.project_id, ev.type,
            ),
          }))
          break
        case 'artifact':
          patchBot((m) => ({
            ...m,
            artifacts: [...(m.artifacts ?? []), ev.data],
            trace: [...m.trace, { kind: 'artifact', artifact: ev.data }],
          }))
          break
        case 'ask_user':
          set({ pending: { questions: ev.data.questions } })
          break
        case 'qa_summary':
          set({ pending: null })
          patchBot((m) => ({ ...m, trace: [...m.trace, { kind: 'qa', qa: ev.data.qa }] }))
          break
        case 'context_degraded':
          patchBot((m) => ({
            ...m,
            trace: [...m.trace, {
              kind: 'context_degraded',
              reason: ev.data.reason,
              excerpt_messages: ev.data.excerpt_messages,
              retry_on_next_turn: true,
            }],
          }))
          break
        case 'work_item':
          // Agent changed a plan item's status (WB-031) — sync the kanban live.
          useWorkItemStore.getState().applyRemote(ev.data.item)
          break
        case 'usage':
          useSettingsStore.getState().setUsage({
            pct: ev.data.pct,
            used: ev.data.used,
            detail: ev.data.detail,
          })
          break
        case 'status':
          patchBot((m) => ({ ...m, status: ev.data.state, secs: ev.data.secs ?? m.secs }))
          break
        case 'error':
          errored = true
          patchBot((m) => ({ ...m, error: ev.data.message, status: 'done', runStatus: 'failed' }))
          break
        case 'done':
          doneOk = !errored
          patchBot((m) => ({ ...m, status: 'done', runStatus: errored ? m.runStatus : 'completed' }))
          break
        default: {
          const exhaustive: never = ev
          return exhaustive
        }
      }
    }

    const settings = useSettingsStore.getState()
    const loadout = useLoadoutStore.getState()
    try {
      await streamChat({
        text: trimmed,
        sessionId: get().activeId ?? undefined,
        title: get().title,
        model: settings.model,
        plan: settings.planMode,
        ask: settings.askMode,
        projectId: get().activeProjectId ?? undefined,
        experts: loadout.experts,
        skills: loadout.skills,
        skillBundles: loadout.skillBundles,
        connectors: loadout.connectors,
        knowledgeIds: loadout.knowledgeIds,
        refs: loadout.refs,
        retryOf,
        signal: controller.signal,
        onEvent,
      })
    } catch (e) {
      // streamChat is designed not to reject, but finalise defensively so the
      // bubble never stays 'running' on an unexpected throw (WB-001).
      patchBot((m) => ({ ...m, status: 'done', error: m.error ?? String(e) }))
    } finally {
      // Attachments are one-shot — but only consume them on a clean finish, so a
      // failed/stopped send keeps the refs for retry (WB-006). Personas/skills/
      // connectors stay across sends regardless.
      if (doneOk) useLoadoutStore.getState().clearRefs()
      // 只有仍是本流的 controller 时才复位流状态，否则被 stop 后一个已被取代的旧流的 finally
      // 会把新流的 streaming/abort/pending 一起清掉（WB-159，与 onEvent 的迟到帧守卫同源）。
      set((s) => (s.abort === controller ? { streaming: false, abort: null, pending: null } : {}))
      get().loadSessions()
    }
  },

  retry: async (messageId) => {
    const state = get()
    if (state.streaming || state.readOnly) return
    const index = state.messages.findIndex((message) => message.id === messageId)
    const message = index >= 0 ? state.messages[index] : undefined
    if (!message?.runId || !message.runStatus || !['failed', 'cancelled', 'paused'].includes(message.runStatus)) return
    const userMessage = state.messages.slice(0, index).reverse().find((candidate) => candidate.role === 'user')
    if (!userMessage) return
    await get().send(userMessage.content, message.runId)
  },

  // Submit ask_user answers — POSTs to /answer, which wakes the suspended agent
  // on the still-open SSE stream (the qa_summary event will confirm).
  answer: (answers) => {
    const { activeId, pending } = get()
    if (!activeId || !pending) return
    set({ pending: null })
    // 提交失败 → 还原问题卡，否则卡片消失但后端 agent 仍挂在 asyncio.Event 上等答，流挂死（WB-159）。
    api.answer(activeId, answers).catch(() => {
      set({ pending })
      toast('提交回答失败，请重试')
    })
  },

  stop: () => {
    const { abort, activeId } = get()
    abort?.abort()
    if (activeId) api.stopChat(activeId).catch(() => {})
    // abort() makes the SSE reader throw AbortError, which is swallowed and never
    // dispatches `done` — so finalise the in-flight bubble here, else it stays a
    // zombie 'running' spinner with no actions until the session is reopened (WB-001).
    set((s) => ({
      messages: s.messages.map((m) => (m.status === 'running' ? { ...m, status: 'done', runStatus: 'paused' } : m)),
      streaming: false,
      abort: null,
      pending: null,
    }))
  },
}))
