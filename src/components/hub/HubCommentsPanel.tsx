// 项目讨论面板（WB-067 Slice 2）：在线成员 + 评论 + @提及，全走本地 backend 代理到 Hub。
// v1 传输 = REST + 15s 轮询（无 WebSocket，见 WB-065 决策）。
// 三态：未接入 Hub（HUB_URL 空）→ 本地模式提示；已接入未登录 → 连接引导；已登录 → 讨论。
// 视觉：复用 .pj-empty / .msg-* / .np-input / .btn-dark，暗色天然继承；仅在线状态条用少量内联（与本仓库惯例一致）。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useHubStore } from '../../stores/hubStore'
import { toast } from '../../stores/toastStore'
import { HubConnectModal } from './HubConnectModal'

type Comment = { id: string; author_name: string; body: string; created_at: number }
type Presence = { account_id: string; name: string; role: string; online: boolean; last_seen: number }

function ago(ts: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return '刚刚'
  if (s < 3600) return Math.floor(s / 60) + ' 分钟前'
  if (s < 86400) return Math.floor(s / 3600) + ' 小时前'
  return Math.floor(s / 86400) + ' 天前'
}

export function HubCommentsPanel({ projectId }: { projectId: string }) {
  const { enabled, linked, checked, refreshStatus } = useHubStore()
  const [comments, setComments] = useState<Comment[]>([])
  const [presence, setPresence] = useState<Presence[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [connectOpen, setConnectOpen] = useState(false)

  useEffect(() => { if (!checked) void refreshStatus() }, [checked, refreshStatus])

  // 已登录 Hub 才拉取；每 15s 轮询一次评论 + 在线状态。Hub 暂不可达则静默（不打断本地使用）。
  useEffect(() => {
    if (!enabled || !linked) return
    let alive = true
    const pull = async () => {
      try {
        const [c, p] = await Promise.all([api.hubComments(projectId), api.hubPresence(projectId)])
        if (!alive) return
        setComments(c.comments || [])
        setPresence(p.presence || [])
      } catch { /* Hub 暂不可达，静默重试下一轮 */ }
    }
    void pull()
    const t = setInterval(pull, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [enabled, linked, projectId])

  const send = async () => {
    const body = draft.trim()
    if (!body || sending) return
    setSending(true)
    try {
      const r = await api.hubPostComment(projectId, body)
      setDraft('')
      if (r.mentioned) toast(`已 @ ${r.mentioned} 位成员`)
      const c = await api.hubComments(projectId)
      setComments(c.comments || [])
    } catch {
      toast('发送失败：Hub 不可达')
    } finally {
      setSending(false)
    }
  }
  const onKey = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }

  if (!enabled) {
    return <div className="pj-empty">本地模式：未接入 Hub。讨论、@提及、在线状态需要连接中心服务（后端配置 HUB_URL）。</div>
  }
  if (!linked) {
    return (
      <>
        <div className="pj-empty">连接 Hub 账号后，即可在此与项目成员讨论、@提及、看谁在线。</div>
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <button className="btn-dark" onClick={() => setConnectOpen(true)}>连接 Hub</button>
        </div>
        {connectOpen && <HubConnectModal onClose={() => { setConnectOpen(false); void refreshStatus() }} />}
      </>
    )
  }

  return (
    <div>
      {presence.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
          {presence.map((m) => (
            <span key={m.account_id} title={m.online ? '在线' : `最后活跃 ${ago(m.last_seen)}`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 20, border: '1px solid var(--border)', fontSize: 12.5, opacity: m.online ? 1 : 0.6 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: m.online ? '#2FBE6E' : 'var(--text-3)' }} />
              {m.name}
            </span>
          ))}
        </div>
      )}

      <div className="hub-cmt-box" style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <input className="np-input" style={{ flex: 1 }} value={draft} placeholder="写条评论…用 @用户名 提及成员"
          onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
        <button className="btn-dark" disabled={!draft.trim() || sending} onClick={send}>发送</button>
      </div>

      {comments.length === 0 ? (
        <div className="pj-empty">还没有评论。说点什么，开启这个项目的讨论。</div>
      ) : (
        comments.map((c) => (
          <div className="msg-row" key={c.id}>
            <span className="msg-ic">{(c.author_name || '?').slice(0, 1)}</span>
            <div className="msg-main">
              <div className="msg-title">{c.author_name}<span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: 6 }}>· {ago(c.created_at)}</span></div>
              <div className="msg-sub" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
