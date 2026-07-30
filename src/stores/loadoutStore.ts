// loadoutStore — the composer ＋ menu's per-session loadout.
//
// experts / skills / connectors are picked ad-hoc from the ＋ menu and sent with
// every message of the current session (the backend merges them with the
// project's own loadout). They are sticky within a session and reset on session
// change. refs are files attached/referenced for the NEXT message only — cleared
// after each send so a large file body isn't re-fed on every turn.
import { create } from 'zustand'

export interface AttachedRef {
  // UI identity is separate from the display name: different source files may
  // legitimately share a basename and still need independent chips/removal.
  id: string
  name: string
  content: string
  // 'file' = @引用/添加文件（📎）；'todo' = 计划「添加到输入框」的待办（🔖）。默认 file。
  kind?: 'file' | 'todo'
  // 当 kind==='todo'：关联的 work_item id，让 agent 能回写其状态（WB-030）。
  itemId?: string
}

export type NewAttachedRef = Omit<AttachedRef, 'id'>

type Kind = 'exp' | 'skill' | 'conn' | 'kb'
const KEY: Record<Kind, 'experts' | 'skills' | 'connectors' | 'knowledgeIds'> = {
  exp: 'experts',
  skill: 'skills',
  conn: 'connectors',
  kb: 'knowledgeIds',
}

interface LoadoutState {
  experts: string[]
  skills: string[]
  skillBundles: string[]
  connectors: string[]
  // 挂载的知识库 id（WB-144）：随每条消息发给后端，agent 可用 knowledge_retrieve 检索。
  knowledgeIds: string[]
  refs: AttachedRef[]
  // 一次性草稿：下一个挂载的 Composer 读取后清空（用于「编辑技能」等预填输入框的场景）。
  draft: string

  toggle: (kind: Kind, name: string) => void
  // 召唤：清空本会话 loadout 并只保留给定专家（用于「召唤专家/专家团」，
  // 语义同 reset + 选中这些专家，配合 startDraft 开一段以这些专家为班底的干净对话）。
  summon: (experts: string[]) => void
  // 同 summon，但换成技能班底（用于「编辑技能」：只挂 skill-creator，清掉专家/连接器）。
  summonSkills: (skills: string[]) => void
  summonSkillBundle: (bundleId: string) => void
  // 同 summon，但换成连接器班底（用于连接器目录的「去试试」：进入新草稿时保持挂载）。
  summonConnectors: (connectors: string[]) => void
  addRef: (r: NewAttachedRef) => boolean
  removeRef: (id: string) => void
  clearRefs: () => void
  setDraft: (text: string) => void
  clearDraft: () => void
  setKnowledgeIds: (ids: string[]) => void
  reset: () => void
}

export const useLoadoutStore = create<LoadoutState>((set, get) => ({
  experts: [],
  skills: [],
  skillBundles: [],
  connectors: [],
  knowledgeIds: [],
  refs: [],
  draft: '',

  toggle: (kind, name) =>
    set((s) => {
      const key = KEY[kind]
      const cur = s[key]
      const next = cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name]
      return { [key]: next } as Partial<LoadoutState>
    }),

  summon: (experts) =>
    set({ experts: [...new Set(experts)], skills: [], skillBundles: [], connectors: [], knowledgeIds: [], refs: [], draft: '' }),

  summonSkills: (skills) =>
    set({ experts: [], skills: [...new Set(skills)], skillBundles: [], connectors: [], knowledgeIds: [], refs: [] }),

  summonSkillBundle: (bundleId) =>
    set({ experts: [], skills: [], skillBundles: [bundleId], connectors: [], knowledgeIds: [], refs: [] }),

  summonConnectors: (connectors) =>
    set({ experts: [], skills: [], skillBundles: [], connectors: [...new Set(connectors)], knowledgeIds: [], refs: [], draft: '' }),

  addRef: (r) => {
    const duplicate = get().refs.some((x) =>
      x.name === r.name && x.content === r.content
      && x.kind === r.kind && x.itemId === r.itemId,
    )
    if (duplicate) return false
    set((s) => ({ refs: [...s.refs, { ...r, id: crypto.randomUUID() }] }))
    return true
  },
  removeRef: (id) => set((s) => ({ refs: s.refs.filter((r) => r.id !== id) })),
  clearRefs: () => set({ refs: [] }),
  setDraft: (text) => set({ draft: text }),
  clearDraft: () => set({ draft: '' }),
  setKnowledgeIds: (ids) => set({ knowledgeIds: [...new Set(ids)] }),
  reset: () => set({ experts: [], skills: [], skillBundles: [], connectors: [], knowledgeIds: [], refs: [], draft: '' }),
}))
