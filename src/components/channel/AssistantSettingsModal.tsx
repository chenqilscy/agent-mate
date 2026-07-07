import { useState } from 'react'
import { api, type TelegramChannel } from '../../lib/api'
import { toast } from '../../stores/toastStore'

// 助理设置（WB-077）。套现有 .np-* 弹窗/表单类，天然继承暗色覆盖。
// token 为 write-only：留空则不改；后端绝不回传其值，这里只据 ch.configured 显示是否已配。
export function AssistantSettingsModal({ open, ch, onClose, onSaved }: {
  open: boolean
  ch: TelegramChannel | null
  onClose: () => void
  onSaved: (updated: TelegramChannel) => void
}) {
  const [name, setName] = useState(ch?.name ?? '')
  const [persona, setPersona] = useState(ch?.persona ?? '')
  const [model, setModel] = useState(ch?.model ?? '')
  const [enabled, setEnabled] = useState(ch?.enabled ?? false)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)

  if (!open || !ch) return null

  const save = async () => {
    if (busy) return
    setBusy(true)
    try {
      const updated = await api.patchTelegramConfig({
        name, persona, model, enabled,
        token: token.trim() || undefined, // 留空 = 不改 token
      })
      toast('助理设置已保存')
      onSaved(updated)
      onClose()
    } catch {
      toast('保存失败')
    } finally {
      setBusy(false)
    }
  }

  const unbind = async () => {
    if (busy) return
    setBusy(true)
    try {
      const updated = await api.telegramUnbind()
      toast('已解绑，下一个 /start 将重新配对')
      onSaved(updated)
    } catch {
      toast('解绑失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="np-overlay open" style={{ zIndex: 160 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" style={{ width: 480 }} role="dialog" aria-modal="true" aria-label="助理设置">
        <div className="np-h">助理设置<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <label className="np-lbl" style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            启用助理（Telegram 收到消息即用本机 agent 处理）
          </label>

          <div className="np-lbl">名字<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>助手怎么自称</small></div>
          <input className="np-input" placeholder="如：小助 / WorkBuddy" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />

          <div className="np-lbl">人格 / 风格<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>注入系统提示，决定它怎么回答</small></div>
          <textarea className="np-ta" placeholder="如：语气简洁、条列作答、结论先行；遇到不确定先反问。留空则用默认风格。" value={persona} onChange={(e) => setPersona(e.target.value)} maxLength={4000} />

          <div className="np-lbl">模型<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>留空跟随后端默认</small></div>
          <input className="np-input" placeholder="如：deepseek-chat（留空用 .env 默认）" value={model} onChange={(e) => setModel(e.target.value)} maxLength={120} />

          <div className="np-lbl">Bot Token<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>{ch.configured ? '已配置 · 留空不修改' : '未配置'}</small></div>
          <input className="np-input" type="password" autoComplete="off" placeholder={ch.configured ? '已配置 · 留空则保持不变' : '粘贴 @BotFather 的 bot token'} value={token} onChange={(e) => setToken(e.target.value)} maxLength={200} />

          <div className="np-lbl">绑定的 Telegram chat</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input className="np-input" style={{ flex: 1 }} readOnly value={ch.bound_chat_id ?? '（未绑定 · 让对方给 bot 发 /start）'} />
            <button className="btn-ghost" disabled={busy || !ch.bound_chat_id} onClick={unbind}>解绑</button>
          </div>
        </div>
        <div className="np-foot">
          <div style={{ flex: 1 }} />
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-dark" disabled={busy} onClick={save}>保存</button>
        </div>
      </div>
    </div>
  )
}
