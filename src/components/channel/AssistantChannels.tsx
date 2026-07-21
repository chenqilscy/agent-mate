import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type Assistant, type AssistantChannel, type ChannelType } from '../../lib/api'
import { Popover } from '../ui/Popover'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'

// 助理渠道管理（WB-088/096）。类型化：Telegram + 邮件 可用，其它类型「敬请期待」占位（不造假）。
// 凭据（token / 邮箱密码）存 DB、本机可见（WB-093 决策）。

// ---- Telegram 渠道表单 ----
function TelegramForm({ assistantId, channel, onClose, onSaved }: {
  assistantId: string; channel: AssistantChannel | null; onClose: () => void; onSaved: () => void
}) {
  const editing = !!channel
  const [token, setToken] = useState(channel?.token ?? '')
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
      toast(editing ? '渠道已更新' : '渠道已添加'); onSaved(); onClose()
    } catch { toast('保存失败') } finally { setBusy(false) }
  }

  return (
    <Modal label="Telegram 渠道" title={`${editing ? '编辑' : '新增'} Telegram 渠道`} onClose={onClose} busy={busy} onSave={save}>
      <label className="np-lbl" style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
        <WbInput type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        启用（收到消息即用本助理处理）
      </label>
      <div className="np-lbl">Bot Token<small className="asst-hint">@BotFather 获取 · 仅存本机</small></div>
      <div style={{ display: 'flex', gap: 8 }}>
        <WbInput className="np-input" style={{ flex: 1 }} type={showToken ? 'text' : 'password'} autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} maxLength={200} placeholder="粘贴 bot token" />
        <WbButton className="asst-addchip" type="button" onClick={() => setShowToken((v) => !v)}>{showToken ? '隐藏' : '显示'}</WbButton>
      </div>
      <div className="np-lbl">白名单 chat_id<small className="asst-hint">留空则第一个 /start 的人配对</small></div>
      <WbInput className="np-input" value={chatId} onChange={(e) => setChatId(e.target.value)} maxLength={64} placeholder="如你的 Telegram user id（可留空）" />
    </Modal>
  )
}

// ---- 邮件渠道表单（WB-096）----
const MAIL_PRESETS: Record<string, { imap_host: string; imap_port: string; smtp_host: string; smtp_port: string }> = {
  Gmail: { imap_host: 'imap.gmail.com', imap_port: '993', smtp_host: 'smtp.gmail.com', smtp_port: '465' },
  Outlook: { imap_host: 'outlook.office365.com', imap_port: '993', smtp_host: 'smtp.office365.com', smtp_port: '587' },
  QQ: { imap_host: 'imap.qq.com', imap_port: '993', smtp_host: 'smtp.qq.com', smtp_port: '465' },
  '163': { imap_host: 'imap.163.com', imap_port: '993', smtp_host: 'smtp.163.com', smtp_port: '465' },
}

function EmailForm({ assistantId, channel, onClose, onSaved }: {
  assistantId: string; channel: AssistantChannel | null; onClose: () => void; onSaved: () => void
}) {
  const editing = !!channel
  const c = channel?.config ?? {}
  const [f, setF] = useState({
    imap_host: c.imap_host ?? '', imap_port: c.imap_port ?? '993',
    smtp_host: c.smtp_host ?? '', smtp_port: c.smtp_port ?? '465',
    username: c.username ?? '', password: c.password ?? '',
    allow_from: c.allow_from ?? '', secret: c.secret ?? '',
  })
  const [showPw, setShowPw] = useState(false)
  const [enabled, setEnabled] = useState(channel?.enabled ?? true)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f, v: string) => setF((s) => ({ ...s, [k]: v }))
  const preset = (name: string) => setF((s) => ({ ...s, ...MAIL_PRESETS[name] }))

  const save = async () => {
    if (busy) return
    if (!f.imap_host.trim() || !f.username.trim()) { toast('至少填 IMAP 主机与账号'); return }
    setBusy(true)
    try {
      const body = { config: { ...f }, enabled }
      if (editing) await api.updateAssistantChannel(assistantId, channel!.id, body)
      else await api.addAssistantChannel(assistantId, { type: 'email', ...body })
      toast(editing ? '渠道已更新' : '渠道已添加'); onSaved(); onClose()
    } catch { toast('保存失败') } finally { setBusy(false) }
  }

  return (
    <Modal label="邮件渠道" title={`${editing ? '编辑' : '新增'} 邮件渠道`} onClose={onClose} busy={busy} onSave={save} width={480}>
      <label className="np-lbl" style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
        <WbInput type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        启用（IMAP 轮询收件 → 本助理处理 → SMTP 回信）
      </label>
      <div className="np-lbl">服务商预设<small className="asst-hint">点一下自动填主机/端口</small></div>
      <div className="asst-chips">
        {Object.keys(MAIL_PRESETS).map((n) => <WbButton key={n} className="asst-addchip" type="button" onClick={() => preset(n)}>{n}</WbButton>)}
      </div>
      <div className="np-lbl">IMAP 主机 / 端口</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <WbInput className="np-input" style={{ flex: 2 }} value={f.imap_host} onChange={(e) => set('imap_host', e.target.value)} placeholder="imap.gmail.com" />
        <WbInput className="np-input" style={{ width: 80 }} value={f.imap_port} onChange={(e) => set('imap_port', e.target.value)} placeholder="993" />
      </div>
      <div className="np-lbl">SMTP 主机 / 端口<small className="asst-hint">465=SSL，其它=STARTTLS</small></div>
      <div style={{ display: 'flex', gap: 8 }}>
        <WbInput className="np-input" style={{ flex: 2 }} value={f.smtp_host} onChange={(e) => set('smtp_host', e.target.value)} placeholder="smtp.gmail.com" />
        <WbInput className="np-input" style={{ width: 80 }} value={f.smtp_port} onChange={(e) => set('smtp_port', e.target.value)} placeholder="465" />
      </div>
      <div className="np-lbl">邮箱账号</div>
      <WbInput className="np-input" value={f.username} onChange={(e) => set('username', e.target.value)} placeholder="you@example.com" />
      <div className="np-lbl">应用专用密码<small className="asst-hint">邮箱开 2FA 后生成 · 仅存本机</small></div>
      <div style={{ display: 'flex', gap: 8 }}>
        <WbInput className="np-input" style={{ flex: 1 }} type={showPw ? 'text' : 'password'} autoComplete="off" value={f.password} onChange={(e) => set('password', e.target.value)} placeholder="应用专用密码" />
        <WbButton className="asst-addchip" type="button" onClick={() => setShowPw((v) => !v)}>{showPw ? '隐藏' : '显示'}</WbButton>
      </div>
      <div className="np-lbl">白名单发件人<small className="asst-hint">逗号分隔；留空则第一个来信者配对</small></div>
      <WbInput className="np-input" value={f.allow_from} onChange={(e) => set('allow_from', e.target.value)} placeholder="me@example.com, boss@example.com" />
      <div className="np-lbl">暗号（可选）<small className="asst-hint">只处理主题/正文含此暗号的邮件，抗 From 伪造</small></div>
      <WbInput className="np-input" value={f.secret} onChange={(e) => set('secret', e.target.value)} placeholder="留空则不校验暗号" />
    </Modal>
  )
}

// ---- 通用弹窗壳 ----
function Modal({ label, title, onClose, busy, onSave, width = 440, children }: {
  label: string; title: string; onClose: () => void; busy: boolean; onSave: () => void; width?: number; children: ReactNode
}) {
  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy} zIndex={160}>
      <div className="np-modal" style={{ width }} role="dialog" aria-modal="true" aria-label={label}>
        <div className="np-h">{title}<WbButton className="np-x" onClick={onClose}>×</WbButton></div>
        <div className="np-body">{children}</div>
        <div className="np-foot">
          <div style={{ flex: 1 }} />
          <WbButton className="btn-ghost" onClick={onClose}>取消</WbButton>
          <WbButton className="btn-dark" disabled={busy} onClick={onSave}>保存</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}

const TYPE_LABEL: Record<string, string> = { telegram: 'Telegram', email: '邮件' }

export function AssistantChannels({ assistant, onChanged }: {
  assistant: Assistant; onChanged: () => void
}) {
  const [types, setTypes] = useState<ChannelType[]>([])
  const [form, setForm] = useState<{ type: string; channel: AssistantChannel | null } | null>(null)
  const [typePick, setTypePick] = useState(false)
  const typeAnchor = useRef<HTMLElement | null>(null)

  useEffect(() => { api.channelTypes().then((r) => setTypes(r.types)).catch(() => {}) }, [])

  const del = async (ch: AssistantChannel) => {
    try { await api.deleteAssistantChannel(assistant.id, ch.id); toast('渠道已删除'); onChanged() } catch { toast('删除失败') }
  }
  const unbind = async (ch: AssistantChannel) => {
    try { await api.unbindAssistantChannel(assistant.id, ch.id); toast('已解绑，等待重新配对'); onChanged() } catch { toast('解绑失败') }
  }
  const toggleEnabled = async (ch: AssistantChannel) => {
    try { await api.updateAssistantChannel(assistant.id, ch.id, { enabled: !ch.enabled }); onChanged() } catch { toast('操作失败') }
  }

  const dot = (ch: AssistantChannel) =>
    ch.running ? { c: '#16B37A', t: '运行中' } : ch.enabled ? { c: '#E5A400', t: ch.has_token ? '启动中/未连接' : '未配置' } : { c: '#9AA0A6', t: '已停用' }

  const sub = (ch: AssistantChannel) => {
    if (ch.type === 'email') {
      const acct = ch.config?.username || '未配账号'
      return `${acct}${ch.bound_chat_id ? ` · 已收 ${ch.bound_chat_id}` : ch.config?.allow_from ? ` · 白名单 ${ch.config.allow_from}` : ''}`
    }
    return `${ch.has_token ? 'token 已配' : '未配 token'} · ${ch.bound_chat_id ? `已绑定 ${ch.bound_chat_id}` : ch.chat_id ? `白名单 ${ch.chat_id}` : '未绑定'}`
  }

  return (
    <div className="asst-form">
      {assistant.channels.length === 0 && (
        <div className="asst-empty" style={{ padding: '10px 0' }}>还没有渠道。点下方「新增渠道」接入 Telegram 或邮件。</div>
      )}
      {assistant.channels.map((ch) => {
        const d = dot(ch)
        return (
          <div className="asst-ch" key={ch.id}>
            <span className="asst-dot" style={{ background: d.c }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600 }}>{TYPE_LABEL[ch.type] ?? ch.type} · {d.t}</div>
              <div className="asst-hint" style={{ marginLeft: 0 }}>{sub(ch)}</div>
            </div>
            <WbButton className="asst-addchip" onClick={() => toggleEnabled(ch)}>{ch.enabled ? '停用' : '启用'}</WbButton>
            <WbButton className="asst-addchip" onClick={() => setForm({ type: ch.type, channel: ch })}>编辑</WbButton>
            {ch.bound_chat_id && <WbButton className="asst-addchip" onClick={() => unbind(ch)}>解绑</WbButton>}
            <WbButton className="asst-addchip danger" onClick={() => del(ch)}>删除</WbButton>
          </div>
        )
      })}

      <div style={{ marginTop: 12 }}>
        <WbButton className="btn-dark" onClick={(e) => { typeAnchor.current = e.currentTarget; setTypePick((v) => !v) }}>＋ 新增渠道</WbButton>
      </div>
      <Popover open={typePick} anchor={typeAnchor.current} dir="down" onClose={() => setTypePick(false)} minWidth={180}>
        {types.map((t) => (
          <div key={t.type} className={`pop-item ${t.available ? '' : 'pop-empty'}`.trim()}
               {...(t.available ? clickable : {})}
               aria-disabled={!t.available}
               onClick={() => { if (t.available) { setTypePick(false); setForm({ type: t.type, channel: null }) } }}>
            {t.label}{t.available ? '' : ' · 敬请期待'}
          </div>
        ))}
      </Popover>

      {form && form.type === 'telegram' && (
        <TelegramForm assistantId={assistant.id} channel={form.channel} onClose={() => setForm(null)} onSaved={onChanged} />
      )}
      {form && form.type === 'email' && (
        <EmailForm assistantId={assistant.id} channel={form.channel} onClose={() => setForm(null)} onSaved={onChanged} />
      )}
    </div>
  )
}
