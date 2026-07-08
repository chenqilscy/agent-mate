import { useEffect, useState } from 'react'
import { api, type Assistant, type AssistantChannel, type ChannelType } from '../../lib/api'
import { toast } from '../../stores/toastStore'

// 助理渠道管理（WB-088）。类型化：Telegram 可用，其它类型「敬请期待」占位（不造假）。
// token write-only：编辑时留空不改；后端绝不回传 token 值。

function ChannelForm({ assistantId, channel, onClose, onSaved }: {
  assistantId: string
  channel: AssistantChannel | null   // null = 新建（Telegram）
  onClose: () => void
  onSaved: () => void
}) {
  const editing = !!channel
  const [token, setToken] = useState(channel?.token ?? '')  // WB-093：预填真实 token（本机可见）
  const [showToken, setShowToken] = useState(false)
  const [chatId, setChatId] = useState(channel?.chat_id ?? '')
  const [enabled, setEnabled] = useState(channel?.enabled ?? true)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    if (busy) return
    setBusy(true)
    try {
      const body = { config: { chat_id: chatId.trim() }, token: token.trim() || undefined, enabled }
      if (editing) await api.updateAssistantChannel(assistantId, channel!.id, body)
      else await api.addAssistantChannel(assistantId, { type: 'telegram', ...body })
      toast(editing ? '渠道已更新' : '渠道已添加')
      onSaved()
      onClose()
    } catch {
      toast('保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="np-overlay open" style={{ zIndex: 160 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" style={{ width: 440 }} role="dialog" aria-modal="true" aria-label="Telegram 渠道">
        <div className="np-h">{editing ? '编辑' : '新增'} Telegram 渠道<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <label className="np-lbl" style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            启用（收到消息即用本助理处理）
          </label>
          <div className="np-lbl">Bot Token<small className="asst-hint">@BotFather 获取 · 仅存本机</small></div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="np-input" style={{ flex: 1 }} type={showToken ? 'text' : 'password'} autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} maxLength={200} placeholder="粘贴 bot token" />
            <button className="asst-addchip" type="button" onClick={() => setShowToken((v) => !v)}>{showToken ? '隐藏' : '显示'}</button>
          </div>
          <div className="np-lbl">白名单 chat_id<small className="asst-hint">留空则第一个 /start 的人配对</small></div>
          <input className="np-input" value={chatId} onChange={(e) => setChatId(e.target.value)} maxLength={64} placeholder="如你的 Telegram user id（可留空）" />
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

export function AssistantChannels({ assistant, onChanged }: {
  assistant: Assistant
  onChanged: () => void
}) {
  const [types, setTypes] = useState<ChannelType[]>([])
  const [form, setForm] = useState<{ channel: AssistantChannel | null } | null>(null)
  const [typePick, setTypePick] = useState(false)

  useEffect(() => { api.channelTypes().then((r) => setTypes(r.types)).catch(() => {}) }, [])

  const del = async (ch: AssistantChannel) => {
    try { await api.deleteAssistantChannel(assistant.id, ch.id); toast('渠道已删除'); onChanged() }
    catch { toast('删除失败') }
  }
  const unbind = async (ch: AssistantChannel) => {
    try { await api.unbindAssistantChannel(assistant.id, ch.id); toast('已解绑，下一个 /start 重新配对'); onChanged() }
    catch { toast('解绑失败') }
  }
  const toggleEnabled = async (ch: AssistantChannel) => {
    try { await api.updateAssistantChannel(assistant.id, ch.id, { enabled: !ch.enabled }); onChanged() }
    catch { toast('操作失败') }
  }

  const dot = (ch: AssistantChannel) =>
    ch.running ? { c: '#16B37A', t: '运行中' } : ch.enabled ? (ch.has_token ? { c: '#E5A400', t: '启动中/未连接' } : { c: '#E5A400', t: '未配 token' }) : { c: '#9AA0A6', t: '已停用' }

  return (
    <div className="asst-form">
      {assistant.channels.length === 0 && (
        <div className="asst-empty" style={{ padding: '10px 0' }}>还没有渠道。点下方「新增渠道」接入 Telegram。</div>
      )}
      {assistant.channels.map((ch) => {
        const d = dot(ch)
        return (
          <div className="asst-ch" key={ch.id}>
            <span className="asst-dot" style={{ background: d.c }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600 }}>{ch.type === 'telegram' ? 'Telegram' : ch.type} · {d.t}</div>
              <div className="asst-hint" style={{ marginLeft: 0 }}>
                {ch.has_token ? 'token 已配 · ' : '未配 token · '}
                {ch.bound_chat_id ? `已绑定 ${ch.bound_chat_id}` : ch.chat_id ? `白名单 ${ch.chat_id}` : '未绑定'}
              </div>
            </div>
            <button className="asst-addchip" onClick={() => toggleEnabled(ch)}>{ch.enabled ? '停用' : '启用'}</button>
            <button className="asst-addchip" onClick={() => setForm({ channel: ch })}>编辑</button>
            {ch.bound_chat_id && <button className="asst-addchip" onClick={() => unbind(ch)}>解绑</button>}
            <button className="asst-addchip danger" onClick={() => del(ch)}>删除</button>
          </div>
        )
      })}

      <div style={{ marginTop: 12, position: 'relative', display: 'inline-block' }}>
        <button className="btn-dark" onClick={() => setTypePick((v) => !v)}>＋ 新增渠道</button>
        {typePick && (
          <div className="asst-typemenu">
            {types.map((t) => (
              <button key={t.type} disabled={!t.available}
                      onClick={() => { setTypePick(false); if (t.available) setForm({ channel: null }) }}>
                {t.label}{t.available ? '' : ' · 敬请期待'}
              </button>
            ))}
          </div>
        )}
      </div>

      {form && (
        <ChannelForm assistantId={assistant.id} channel={form.channel}
                     onClose={() => setForm(null)} onSaved={onChanged} />
      )}
    </div>
  )
}
