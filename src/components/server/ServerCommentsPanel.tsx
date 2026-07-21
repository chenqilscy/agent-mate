import { WbButton, WbInput } from '../ui/Primitives'
// 项目讨论面板（WB-067 Slice 2）：在线成员 + 评论 + @提及，全走本地 backend 代理到 Server。
// v1 传输 = REST + 15s 轮询（无 WebSocket，见 WB-065 决策）。
// 三态：未接入 Server（AGENTMATE_SERVER_URL 空）→ 本地模式提示；已接入未登录 → 连接引导；已登录 → 讨论。
// 视觉：复用 .pj-empty / .msg-* / .np-input / .btn-dark，暗色天然继承；仅在线状态条用少量内联（与本仓库惯例一致）。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useServerStore } from '../../stores/serverStore'
import { toast } from '../../stores/toastStore'
import { ServerConnectModal } from './ServerConnectModal'
import { Avatar, Badge, Empty, Result, Tag } from 'antd'
import { CompatList as List } from '../ui/CompatList'

type Comment = { id: string; author_name: string; body: string; created_at: number }
type Presence = { account_id: string; name: string; role: string; online: boolean; last_seen: number }

function ago(ts: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return '刚刚'
  if (s < 3600) return Math.floor(s / 60) + ' 分钟前'
  if (s < 86400) return Math.floor(s / 3600) + ' 小时前'
  return Math.floor(s / 86400) + ' 天前'
}

export function ServerCommentsPanel({ projectId }: { projectId: string }) {
  const { enabled, linked, checked, refreshStatus } = useServerStore()
  const [comments, setComments] = useState<Comment[]>([])
  const [presence, setPresence] = useState<Presence[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [connectOpen, setConnectOpen] = useState(false)

  useEffect(() => { if (!checked) void refreshStatus() }, [checked, refreshStatus])

  // 已登录 Server 才拉取；每 15s 轮询一次评论 + 在线状态。Server 暂不可达则静默（不打断本地使用）。
  useEffect(() => {
    if (!enabled || !linked) return
    let alive = true
    const pull = async () => {
      try {
        const [c, p] = await Promise.all([api.serverComments(projectId), api.serverPresence(projectId)])
        if (!alive) return
        setComments(c.comments || [])
        setPresence(p.presence || [])
      } catch { /* Server 暂不可达，静默重试下一轮 */ }
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
      const r = await api.serverPostComment(projectId, body)
      setDraft('')
      if (r.mentioned) toast(`已 @ ${r.mentioned} 位成员`)
      const c = await api.serverComments(projectId)
      setComments(c.comments || [])
    } catch {
      toast('发送失败：AgentMate Server 不可达')
    } finally {
      setSending(false)
    }
  }
  const onKey = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }

  if (!enabled) {
    return <Result className="pj-empty" status="info" title="当前为本地模式" subTitle="讨论、@提及、在线状态需要连接 AgentMate Server。" />
  }
  if (!linked) {
    return (
      <>
        <Result className="pj-empty" status="info" title="尚未连接 AgentMate Server" subTitle="连接账号后，即可与项目成员讨论、@提及并查看在线状态。" extra={<WbButton className="btn-dark" onClick={() => setConnectOpen(true)}>连接 AgentMate Server</WbButton>} />
        {connectOpen && <ServerConnectModal onClose={() => { setConnectOpen(false); void refreshStatus() }} />}
      </>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12.5, color: 'var(--text-3)' }}>🟢 已连接 AgentMate Server · {linked?.name}</span>
        <WbButton className="btn-line" style={{ marginLeft: 'auto', marginTop: 0, height: 28, padding: '0 12px' }} onClick={() => setConnectOpen(true)}>管理</WbButton>
      </div>

      {presence.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
          {presence.map((m) => (
            <Tag key={m.account_id} title={m.online ? '在线' : m.last_seen ? `最后活跃 ${ago(m.last_seen)}` : '从未上线'}><Badge status={m.online ? 'success' : 'default'} />{m.name}</Tag>
          ))}
        </div>
      )}

      <div className="cap-cmt-box" style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <WbInput className="np-input" style={{ flex: 1 }} value={draft} placeholder="写条评论…用 @用户名 提及成员"
          onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
        <WbButton className="btn-dark" disabled={!draft.trim() || sending} onClick={send}>发送</WbButton>
      </div>

      {comments.length === 0 ? (
        <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有评论。说点什么，开启这个项目的讨论。" />
      ) : (
        <List dataSource={comments} renderItem={(c) => (
          <List.Item className="msg-row" key={c.id}>
            <Avatar className="msg-ic">{(c.author_name || '?').slice(0, 1)}</Avatar>
            <div className="msg-main">
              <div className="msg-title">{c.author_name}<span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: 6 }}>· {ago(c.created_at)}</span></div>
              <div className="msg-sub" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>
            </div>
          </List.Item>
        )} />
      )}

      {connectOpen && <ServerConnectModal onClose={() => { setConnectOpen(false); void refreshStatus() }} />}
    </div>
  )
}
