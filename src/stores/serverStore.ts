// serverStore — 前端接 AgentMate Server 的连接态（WB-067 Slice 2）。
//
// 「连接 Server」= 用 Server 账号登录：本地 backend 代理到 Server 拿 token，存为 app 自己的 token
// （与 WB-070 syncFromServer 一致——app token 即 Server token，本地 auth 桥认它）。之后评论/在线/通知
// 都经本地 backend 代理转发到 Server。Server 是唯一账号源；未接 Server 时仅保留匿名访客的本机能力。
import { create } from 'zustand'
import { api } from '../lib/api'
import { TOKEN_KEY } from '../lib/api'

interface ServerState {
  enabled: boolean // 本地 backend 是否已配 AGENTMATE_SERVER_URL
  linked: { account_id: string; name: string } | null // 是否已绑定某 Server 账号
  checked: boolean
  refreshStatus: () => Promise<void>
  connect: (name: string, password: string, register: boolean) => Promise<void> // 失败抛错
  disconnect: () => void
}

export const useServerStore = create<ServerState>((set) => ({
  enabled: false,
  linked: null,
  checked: false,
  refreshStatus: async () => {
    try {
      const s = await api.serverStatus()
      set({ enabled: s.enabled, linked: s.linked, checked: true })
    } catch {
      set({ checked: true }) // 后端未连：保留访客态，不推断出本地账号
    }
  },
  connect: async (name, password, register) => {
    const r = await api.serverLogin(name.trim(), password, register) // 401/不可达 → 抛错，调用方显示
    localStorage.setItem(TOKEN_KEY, r.token) // 以 Server 账号身份操作
    try { await api.serverPull() } catch { /* 拉镜像失败不阻断 */ }
    // 换了身份 token（后端据此识别用户）→ reload，让 projects/sessions/notifications 等 per-user
    // store 在新身份下重新拉取，否则残留旧（本地）身份的陈旧数据（对齐 authStore.login/logout，WB-159）。
    window.location.reload()
  },
  disconnect: () => {
    localStorage.removeItem(TOKEN_KEY)
    set({ linked: null })
    window.location.reload()
  },
}))
