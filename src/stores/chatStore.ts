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

function uuid(): string {
  return crypto.randomUUID ? crypto.randomUUID() : String(Math.random())
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

  loadSessions: () => Promise<void>
  openSession: (id: string) => Promise<void>
  startDraft: (title: string) => void
  startProject: (projectId: string, name: string) => void
  send: (text: string) => Promise<void>
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
        messages: messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          trace: (m.trace as TraceItem[]) ?? [],
          status: 'done',
          usage: m.usage,
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
    set({ activeId: null, activeProjectId: null, title, messages: [] })
  },

  // Open a project's execution: a fresh chat scoped to the project. The first
  // send creates a project-scoped session (kind=projexec) on the backend.
  startProject: (projectId, name) => {
    if (get().streaming) get().stop()
    useUIStore.getState().closeFile()
    set({ activeId: null, activeProjectId: projectId, title: name, messages: [] })
  },

  send: async (text) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming) return

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

    const onEvent = (ev: SSEEvent) => {
      switch (ev.type) {
        case 'session':
          set({ activeId: ev.data.id, title: ev.data.title })
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
        case 'ask_user':
          set({ pending: { questions: ev.data.questions } })
          break
        case 'qa_summary':
          set({ pending: null })
          patchBot((m) => ({ ...m, trace: [...m.trace, { kind: 'qa', qa: ev.data.qa }] }))
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
          patchBot((m) => ({ ...m, error: ev.data.message, status: 'done' }))
          break
        case 'done':
          patchBot((m) => ({ ...m, status: 'done' }))
          break
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
        connectors: loadout.connectors,
        refs: loadout.refs,
        signal: controller.signal,
        onEvent,
      })
    } finally {
      // Attachments are one-shot — the loadout personas/skills/connectors stay.
      useLoadoutStore.getState().clearRefs()
      set({ streaming: false, abort: null, pending: null })
      get().loadSessions()
    }
  },

  // Submit ask_user answers — POSTs to /answer, which wakes the suspended agent
  // on the still-open SSE stream (the qa_summary event will confirm).
  answer: (answers) => {
    const { activeId, pending } = get()
    if (!activeId || !pending) return
    set({ pending: null })
    api.answer(activeId, answers).catch(() => {})
  },

  stop: () => {
    const { abort, activeId } = get()
    abort?.abort()
    if (activeId) api.stopChat(activeId).catch(() => {})
    set({ streaming: false, abort: null, pending: null })
  },
}))
