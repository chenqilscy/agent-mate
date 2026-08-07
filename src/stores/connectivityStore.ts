import { create } from 'zustand'
import {
  channelSnapshot, probeServer, refreshLocalAgentStatus, subscribeChannels,
  type ServerConnectionState,
} from '../lib/channels'
import type { LocalAgentStatus } from '../platform'

interface ConnectivityState {
  server: ServerConnectionState
  localAgent: LocalAgentStatus | null
  localAgentChecked: boolean
  localAgentError: string
  start: () => () => void
  refresh: () => Promise<void>
}

const initial = channelSnapshot()

export const useConnectivityStore = create<ConnectivityState>((set, get) => ({
  ...initial,
  start: () => {
    const unsubscribe = subscribeChannels((value) => set(value))
    void get().refresh()
    const timer = window.setInterval(() => { void get().refresh() }, 15_000)
    return () => {
      window.clearInterval(timer)
      unsubscribe()
    }
  },
  refresh: async () => {
    await Promise.allSettled([probeServer(), refreshLocalAgentStatus()])
  },
}))
