// hubStore — 前端接 WorkBuddy Hub 的连接态（WB-067 Slice 2）。
//
// 「连接 Hub」= 用 Hub 账号登录：本地 backend 代理到 Hub 拿 token，存为 app 自己的 token
// （与 WB-070 syncFromHub 一致——app token 即 Hub token，本地 auth 桥认它）。之后评论/在线/通知
// 都经本地 backend 代理转发到 Hub。未接 Hub（HUB_URL 空）→ enabled=false，前端隐藏协作入口、本机照旧。
import { create } from 'zustand'
import { api } from '../lib/api'
import { TOKEN_KEY } from '../lib/api'

interface HubState {
  enabled: boolean // 本地 backend 是否已配 HUB_URL
  linked: { account_id: string; name: string } | null // 是否已绑定某 Hub 账号
  checked: boolean
  refreshStatus: () => Promise<void>
  connect: (name: string, password: string, register: boolean) => Promise<void> // 失败抛错
  disconnect: () => void
}

export const useHubStore = create<HubState>((set) => ({
  enabled: false,
  linked: null,
  checked: false,
  refreshStatus: async () => {
    try {
      const s = await api.hubStatus()
      set({ enabled: s.enabled, linked: s.linked, checked: true })
    } catch {
      set({ checked: true }) // 后端未连：当作未接 Hub，前端回退纯本地
    }
  },
  connect: async (name, password, register) => {
    const r = await api.hubLogin(name.trim(), password, register) // 401/不可达 → 抛错，调用方显示
    localStorage.setItem(TOKEN_KEY, r.token) // 以 Hub 账号身份操作
    try { await api.hubPull() } catch { /* 拉镜像失败不阻断 */ }
    // 换了身份 token（后端据此识别用户）→ reload，让 projects/sessions/notifications 等 per-user
    // store 在新身份下重新拉取，否则残留旧（本地）身份的陈旧数据（对齐 authStore.login/logout，WB-159）。
    window.location.reload()
  },
  disconnect: () => {
    localStorage.removeItem(TOKEN_KEY)
    set({ linked: null })
  },
}))
