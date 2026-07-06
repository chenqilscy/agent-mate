// Message center (M7 C4). Holds the current user's notifications + unread count.
// Loaded on app start and polled lightly so the sidebar bell badge stays live;
// switching account reloads the whole app, so no cross-user leakage here.
import { create } from 'zustand'
import { api } from '../lib/api'
import type { AppNotification } from '../lib/types'

interface NotifState {
  items: AppNotification[]
  unread: number
  load: () => Promise<void>
  markAllRead: () => Promise<void>
}

export const useNotificationStore = create<NotifState>((set, get) => ({
  items: [],
  unread: 0,

  load: async () => {
    try {
      const { notifications, unread } = await api.listNotifications()
      set({ items: notifications, unread })
    } catch {
      /* backend down — keep what we have */
    }
  },

  markAllRead: async () => {
    if (get().unread === 0) return
    // Optimistic: clear the badge immediately, then persist.
    set((s) => ({ unread: 0, items: s.items.map((n) => ({ ...n, read: 1 })) }))
    try {
      await api.markNotificationsRead()
    } catch {
      void get().load() // reconcile on failure
    }
  },
}))
