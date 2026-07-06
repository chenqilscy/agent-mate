// skillStore — SkillHub「技能」页的已安装/已关闭状态，客户端本地持久化。
//
// SkillHub 商店是静态产品目录（catalog.ts 的 SKILLHUB_*）。用户对某个技能的
// 安装 / 卸载 / 关闭（停用）是纯客户端目录状态，落在浏览器 localStorage —— 真实
// 持久化、跨刷新保留，但与后端技能系统解耦（会话内实际挂载的技能仍走 loadoutStore）。
// 初次装载以内置 INSTALLED 作为「已安装」种子，和原型「已安装 N」计数对齐。
import { create } from 'zustand'
import { INSTALLED } from '../data/catalog'

const LS_KEY = 'wb.skills.v1'

interface Persisted {
  installed: string[]
  disabled: string[]
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) {
      const p = JSON.parse(raw) as Partial<Persisted>
      if (Array.isArray(p.installed)) {
        return { installed: p.installed, disabled: Array.isArray(p.disabled) ? p.disabled : [] }
      }
    }
  } catch {
    /* 坏数据/无 localStorage：回落到种子 */
  }
  return { installed: INSTALLED.map((x) => x[2]), disabled: [] }
}

function persist(installed: string[], disabled: string[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ installed, disabled }))
  } catch {
    /* 忽略写入失败（隐私模式等） */
  }
}

interface SkillState extends Persisted {
  install: (name: string) => void
  uninstall: (name: string) => void
  // 关闭/启用：停用一个已安装技能而不卸载它。
  toggleDisabled: (name: string) => void
}

export const useSkillStore = create<SkillState>((set) => {
  const init = load()
  return {
    installed: init.installed,
    disabled: init.disabled,

    install: (name) =>
      set((s) => {
        if (s.installed.includes(name)) return {}
        const installed = [...s.installed, name]
        persist(installed, s.disabled)
        return { installed }
      }),

    uninstall: (name) =>
      set((s) => {
        const installed = s.installed.filter((n) => n !== name)
        const disabled = s.disabled.filter((n) => n !== name)
        persist(installed, disabled)
        return { installed, disabled }
      }),

    toggleDisabled: (name) =>
      set((s) => {
        const disabled = s.disabled.includes(name)
          ? s.disabled.filter((n) => n !== name)
          : [...s.disabled, name]
        persist(s.installed, disabled)
        return { disabled }
      }),
  }
})
