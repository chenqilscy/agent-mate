// skillStore — SkillHub 已安装技能（WB-055），后端为准。
//
// 「安装/卸载/关闭」是**真实**的：安装走后端 skillhub CLI 下载解压进 ~/.agentmate/skills/，
// 清单来自后端对该目录的磁盘扫描（不再是 localStorage 假状态）。已安装且未关闭的技能进
// 会话 loadout 时，后端会注入其真实 SKILL.md（agent/skills_store.py）。
import { create } from 'zustand'
import { api, API_BASE, authHeaders } from '../lib/api'
import type { InstalledSkill } from '../lib/types'
import { toast } from './toastStore'

// 一个目录卡（按展示名）是否已安装：按 name / slug / key 任一匹配。
export function matchSkill(installed: InstalledSkill[], name: string): InstalledSkill | undefined {
  return installed.find((s) => s.name === name || s.slug === name || s.key === name)
}

// AgentMate 目录技能（兼容旧 API 名 builtin）：只有真实安装且启用后才会返回（WB-216）。
export interface BuiltinSkill {
  slug: string
  name: string
  description: string
  tools: string[]
}

interface SkillState {
  installed: InstalledSkill[]
  builtin: BuiltinSkill[]
  loaded: boolean
  loading: boolean
  cliAvailable: boolean
  installing: string[] // 正在安装的展示名（卡片转圈用）

  load: (force?: boolean) => Promise<void>
  install: (name: string, slug?: string) => Promise<void>
  installCatalog: (name: string, slug: string) => Promise<void>
  upgradeCatalog: (name: string, slug: string) => Promise<void>
  uninstall: (key: string) => Promise<void>
  toggle: (key: string, disabled: boolean) => Promise<void>
}

export const useSkillStore = create<SkillState>((set, get) => ({
  installed: [],
  builtin: [],
  loaded: false,
  loading: false,
  cliAvailable: true,
  installing: [],

  load: async (force = false) => {
    if (get().loading || (get().loaded && !force)) return
    set({ loading: true })
    try {
      const { skills, cli } = await api.listSkills()
      set({ installed: skills, cliAvailable: cli, loaded: true })
      // 内置技能另取（WB-180）：它们不在磁盘上，listSkills 的扫描列不出。失败不影响已装清单。
      try {
        const r = await fetch(`${API_BASE}/skills/builtin`, { headers: authHeaders() })
        if (r.ok) set({ builtin: ((await r.json()) as { skills?: BuiltinSkill[] }).skills ?? [] })
      } catch { /* 内置清单拿不到就只列已装，不阻塞 */ }
    } catch {
      /* 后端未连接：保留现状 */
    } finally {
      set({ loading: false })
    }
  },

  // 真实安装：无 slug 时后端用展示名去 SkillHub 搜索解析。
  install: async (name, slug) => {
    if (get().installing.includes(name)) return
    set((s) => ({ installing: [...s.installing, name] }))
    try {
      const r = await fetch(`${API_BASE}/skills/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ name, slug: slug ?? '' }),
      })
      if (!r.ok) {
        let msg = `安装失败（${r.status}）`
        try { const j = await r.json(); if (j?.detail) msg = String(j.detail) } catch { /* ignore */ }
        toast(msg)
        return
      }
      const data = (await r.json()) as { skill?: InstalledSkill }
      toast('已安装 · ' + (data.skill?.name || name))
      await get().load(true)
    } catch {
      toast('安装失败（后端未连接？）')
    } finally {
      set((s) => ({ installing: s.installing.filter((n) => n !== name) }))
    }
  },

  installCatalog: async (name, slug) => {
    if (get().installing.includes(slug)) return
    set((s) => ({ installing: [...s.installing, slug] }))
    try {
      await api.installCatalogSkill(slug)
      toast('已安装 · ' + name)
      await get().load(true)
    } catch (error) {
      toast(error instanceof Error ? error.message : '安装失败')
    } finally {
      set((s) => ({ installing: s.installing.filter((key) => key !== slug) }))
    }
  },

  upgradeCatalog: async (name, slug) => {
    if (get().installing.includes(slug)) return
    set((s) => ({ installing: [...s.installing, slug] }))
    try {
      await api.upgradeCatalogSkill(slug)
      toast('已升级 · ' + name)
      await get().load(true)
    } catch (error) {
      toast(error instanceof Error ? error.message : '升级失败')
    } finally {
      set((s) => ({ installing: s.installing.filter((key) => key !== slug) }))
    }
  },

  uninstall: async (key) => {
    try {
      await api.uninstallSkill(key)
      toast('已卸载')
      await get().load(true)
    } catch {
      toast('卸载失败')
    }
  },

  // 乐观更新 disabled；失败回滚。
  toggle: async (key, disabled) => {
    set((s) => ({ installed: s.installed.map((x) => (x.key === key ? { ...x, disabled } : x)) }))
    try {
      await api.toggleSkill(key, disabled)
      toast(disabled ? '已关闭' : '已启用')
      await get().load(true)
    } catch {
      set((s) => ({ installed: s.installed.map((x) => (x.key === key ? { ...x, disabled: !disabled } : x)) }))
      toast('操作失败')
    }
  },
}))

// 运行时与持久化都存 slug；展示名只在渲染边界反查，避免同名技能覆盖身份（WB-183 Phase B）。
export function skillDisplayName(key: string): string {
  const state = useSkillStore.getState()
  return state.builtin.find((s) => s.slug === key || s.name === key)?.name
    ?? matchSkill(state.installed, key)?.name
    ?? key
}

export function skillStableKey(key: string): string {
  const state = useSkillStore.getState()
  const builtin = state.builtin.find((s) => s.slug === key || s.name === key)
  if (builtin) return builtin.slug
  const installed = matchSkill(state.installed, key)
  return installed?.slug || installed?.key || key
}
