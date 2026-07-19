import { create } from 'zustand'
import { api } from '../lib/api'
import type { SystemSettings } from '../lib/types'
import { useSettingsStore } from './settingsStore'

const DEFAULTS: SystemSettings = {
  interface_scale: 100,
  reduce_motion: false,
  default_permission: 'default',
  startup_page: 'home',
}

function apply(settings: SystemSettings) {
  document.body.dataset.uiScale = String(settings.interface_scale)
  document.body.classList.toggle('reduce-motion', settings.reduce_motion)
  useSettingsStore.getState().setPerm(settings.default_permission === 'full' ? '完全访问权限' : '默认权限')
}

interface SystemSettingsState extends SystemSettings {
  loaded: boolean
  load: () => Promise<SystemSettings>
  save: (patch: Partial<SystemSettings>) => Promise<SystemSettings>
}

export const useSystemSettingsStore = create<SystemSettingsState>((set, get) => ({
  ...DEFAULTS,
  loaded: false,
  load: async () => {
    try {
      const settings = await api.systemSettings()
      apply(settings)
      set({ ...settings, loaded: true })
      return settings
    } catch {
      const settings = {
        interface_scale: get().interface_scale,
        reduce_motion: get().reduce_motion,
        default_permission: get().default_permission,
        startup_page: get().startup_page,
      }
      apply(settings)
      set({ loaded: true })
      return settings
    }
  },
  save: async (patch) => {
    const settings = await api.saveSystemSettings(patch)
    apply(settings)
    set({ ...settings, loaded: true })
    return settings
  },
}))
