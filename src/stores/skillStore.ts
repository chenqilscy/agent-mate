// skillStore — SkillHub 已安装技能（WB-055），后端为准。
//
// 「安装/卸载/关闭」是**真实**的：安装走后端 skillhub CLI 下载解压进 ~/.workbuddy/skills/，
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

// 内置技能（WB-180）：不在磁盘上，`GET /api/skills` 的磁盘扫描列不出，只能问 /skills/builtin。
// tools 为空 = 纯提示词技能（按本项目定义「技能 = 提示词 + 工具包」，同样是真技能）。
export interface BuiltinSkill {
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
    } catch {
      set((s) => ({ installed: s.installed.map((x) => (x.key === key ? { ...x, disabled: !disabled } : x)) }))
      toast('操作失败')
    }
  },
}))
