// Global toast (the prototype's `toast()` — now a real store).
import { create } from 'zustand'

interface ToastState {
  message: string
  visible: boolean
  show: (message: string) => void
  hide: () => void
}

let timer: ReturnType<typeof setTimeout> | undefined

export const useToastStore = create<ToastState>((set) => ({
  message: '',
  visible: false,
  show: (message) => {
    set({ message, visible: true })
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => set({ visible: false }), 2000)
  },
  hide: () => set({ visible: false }),
}))

// Imperative helper so non-component code can toast too.
export const toast = (message: string) => useToastStore.getState().show(message)
