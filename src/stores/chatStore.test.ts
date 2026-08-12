import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({
  api: {
    getMessages: vi.fn(),
    listSessions: vi.fn(),
  },
}))
vi.mock('../lib/sse', () => ({ followServerRun: vi.fn(), streamChat: vi.fn() }))
vi.mock('./settingsStore', () => ({
  useSettingsStore: { getState: () => ({ setUsage: vi.fn() }) },
}))
vi.mock('./loadoutStore', () => ({
  useLoadoutStore: { getState: () => ({ reset: vi.fn() }) },
}))
vi.mock('./uiStore', () => ({
  useUIStore: { getState: () => ({ closeFile: vi.fn() }) },
}))
vi.mock('./workItemStore', () => ({
  useWorkItemStore: { getState: () => ({ applyRemote: vi.fn() }) },
}))
vi.mock('./toastStore', () => ({ toast: vi.fn() }))

import { api } from '../lib/api'
import { useChatStore } from './chatStore'

const getMessages = vi.mocked(api.getMessages)

describe('chatStore.openSession', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.setState({
      activeId: 'existing',
      activeProjectId: null,
      title: '现有执行',
      messages: [{ id: 'old', role: 'assistant', content: '保留内容', trace: [], status: 'done' }],
      streaming: false,
      abort: null,
      pending: null,
      readOnly: false,
      ownerName: null,
    })
  })

  it('rejects when the requested session cannot be read and preserves the current session', async () => {
    const failure = new Error('session unavailable')
    getMessages.mockRejectedValueOnce(failure)

    await expect(useChatStore.getState().openSession('missing')).rejects.toBe(failure)

    const state = useChatStore.getState()
    expect(state.activeId).toBe('existing')
    expect(state.title).toBe('现有执行')
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.content).toBe('保留内容')
  })

  it('commits the requested session after the response succeeds', async () => {
    getMessages.mockResolvedValueOnce({
      session: {
        id: 'ready', title: '已恢复执行', kind: 'chat', status: 'active', project_id: null,
        created_at: 1, updated_at: 2, owner_id: 'owner', read_only: false,
      },
      messages: [{
        id: 'user-1', role: 'user', content: '继续', actor: 'owner', trace: [], usage: null,
        run_status: undefined, run_plan: undefined, run_plan_version: undefined,
        run_project_id: undefined, run_queue_context: undefined, created_at: 1,
      }],
      runs: [],
    })

    await useChatStore.getState().openSession('ready')

    const state = useChatStore.getState()
    expect(state.activeId).toBe('ready')
    expect(state.title).toBe('已恢复执行')
    expect(state.messages.map((message) => message.content)).toEqual(['继续'])
  })
})
