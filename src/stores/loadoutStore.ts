// loadoutStore — the composer ＋ menu's per-session loadout.
//
// experts / skills / connectors are picked ad-hoc from the ＋ menu and sent with
// every message of the current session (the backend merges them with the
// project's own loadout). They are sticky within a session and reset on session
// change. refs are files attached/referenced for the NEXT message only — cleared
// after each send so a large file body isn't re-fed on every turn.
import { create } from 'zustand'

export interface AttachedRef {
  name: string
  content: string
}

type Kind = 'exp' | 'skill' | 'conn'
const KEY: Record<Kind, 'experts' | 'skills' | 'connectors'> = {
  exp: 'experts',
  skill: 'skills',
  conn: 'connectors',
}

interface LoadoutState {
  experts: string[]
  skills: string[]
  connectors: string[]
  refs: AttachedRef[]

  toggle: (kind: Kind, name: string) => void
  addRef: (r: AttachedRef) => void
  removeRef: (name: string) => void
  clearRefs: () => void
  reset: () => void
}

export const useLoadoutStore = create<LoadoutState>((set) => ({
  experts: [],
  skills: [],
  connectors: [],
  refs: [],

  toggle: (kind, name) =>
    set((s) => {
      const key = KEY[kind]
      const cur = s[key]
      const next = cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name]
      return { [key]: next } as Partial<LoadoutState>
    }),

  addRef: (r) =>
    set((s) => (s.refs.some((x) => x.name === r.name) ? {} : { refs: [...s.refs, r] })),
  removeRef: (name) => set((s) => ({ refs: s.refs.filter((r) => r.name !== name) })),
  clearRefs: () => set({ refs: [] }),
  reset: () => set({ experts: [], skills: [], connectors: [], refs: [] }),
}))
