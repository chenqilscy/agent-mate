// UI shell state: current view, overview-panel open/close, theme, popover stack.
import { create } from 'zustand'
import type { ViewId } from '../lib/types'

type Theme = 'light' | 'dark'

interface UIState {
  view: ViewId
  ovOpen: boolean
  theme: Theme
  // popover stack: id of the currently open popover (null = none). One-at-a-time
  // is enough for M1; the Esc-level stack lands with the full popover system.
  openPopover: string | null

  setView: (v: ViewId) => void
  toggleOv: () => void
  setOv: (open: boolean) => void
  setTheme: (t: Theme) => void
  setPopover: (id: string | null) => void
}

const THEME_KEY = 'wb.theme'

function initialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY) as Theme | null
  if (saved) return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(t: Theme) {
  document.body.classList.toggle('dark', t === 'dark')
}

const startTheme = initialTheme()
applyTheme(startTheme)

export const useUIStore = create<UIState>((set) => ({
  view: 'home',
  ovOpen: false,
  theme: startTheme,
  openPopover: null,

  setView: (v) => set({ view: v, openPopover: null }),
  toggleOv: () => set((s) => ({ ovOpen: !s.ovOpen })),
  setOv: (open) => set({ ovOpen: open }),
  setTheme: (t) => {
    localStorage.setItem(THEME_KEY, t)
    applyTheme(t)
    set({ theme: t })
  },
  setPopover: (id) => set((s) => ({ openPopover: s.openPopover === id ? null : id })),
}))
