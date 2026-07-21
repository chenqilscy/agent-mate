import { WbButton, WbInput } from '../ui/Primitives'
// 连接 Server 弹窗（WB-067 Slice 2）：登录/注册到中心服务，之后以 Server 账号身份协作。
// 已连接则展示账号 + 导入本地项目到 Server + 团队通知 + 断开。
// 视觉零重设计：复用 LoginModal / MessageCenter 的 .np-* / .msg-* / .btn-* 类，暗色天然继承；
// 错误走 toast（与 LoginModal 一致），不新增共享 CSS。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useServerStore } from '../../stores/serverStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'

type Notif = { id: string; title: string; body: string; created_at: number; read: number }

export function ServerConnectModal({ onClose }: { onClose: () => void }) {
  const { linked, connect, disconnect } = useServerStore()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [notifs, setNotifs] = useState<Notif[]>([])

  useEffect(() => {
    if (!linked) return
    api.serverNotifications().then((r) => setNotifs(r.notifications || [])).catch(() => {})
  }, [linked])

  const submit = async () => {
    if (!name.trim() || password.length < 4 || busy) return
    setBusy(true)
    try {
      await connect(name.trim(), password, mode === 'register')
      toast('已连接 AgentMate Server · ' + name.trim())
    } catch {
      toast(mode === 'login' ? '连接失败：用户名或密码错误，或 AgentMate Server 不可达' : '注册失败：用户名可能已被占用，或密码太短（≥4 位）')
      setBusy(false)
    }
  }

  const onKey = (e: { key: string }) => { if (e.key === 'Enter') void submit() }

  const doImport = async () => {
    try {
      const r = await api.serverImport()
      toast(`已导入 ${r.imported} 个本地项目到 Server（跳过 ${r.skipped}）`)
    } catch { toast('导入失败') }
  }

  const markRead = async () => {
    try { await api.serverMarkNotifs(); setNotifs((ns) => ns.map((n) => ({ ...n, read: 1 }))) } catch { /* ignore */ }
  }

  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy}>
      <div className="np-modal auth-modal" role="dialog" aria-modal="true" aria-label="连接 AgentMate Server">
        <div className="np-h">连接 AgentMate Server<WbButton className="np-x" onClick={onClose}>×</WbButton></div>

        {linked ? (
          <>
            <div className="np-body">
              <div className="np-lbl">已连接为 {linked.name}</div>
              <div className="auth-switch">项目 / 成员 / 评论 / 在线状态经中心 Server 协作。</div>
              <div className="np-lbl">团队通知</div>
              {notifs.length === 0 ? (
                <div className="msg-empty"><span className="msg-empty-ic">🔔</span>暂无通知</div>
              ) : (
                notifs.slice(0, 12).map((n) => (
                  <div key={n.id} className={`msg-row ${n.read ? '' : 'unread'}`.trim()}>
                    <span className="msg-ic">🔔</span>
                    <div className="msg-main">
                      <div className="msg-title">{n.title}</div>
                      {n.body && <div className="msg-sub">{n.body}</div>}
                    </div>
                    {!n.read && <span className="msg-dot" aria-label="未读" />}
                  </div>
                ))
              )}
            </div>
            <div className="np-foot">
              <WbButton className="btn-ghost" onClick={markRead}>标记已读</WbButton>
              <WbButton className="btn-ghost" onClick={doImport}>导入本地项目</WbButton>
              <WbButton className="btn-ghost danger-b" onClick={() => { disconnect(); toast('已断开 Server'); onClose() }}>断开</WbButton>
            </div>
          </>
        ) : (
          <>
            <div className="np-body">
              <div className="subtabs">
                <div className={`subtab ${mode === 'login' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setMode('login')}>登录</div>
                <div className={`subtab ${mode === 'register' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setMode('register')}>注册</div>
              </div>
              <div className="np-lbl">AgentMate Server 用户名</div>
              <WbInput className="np-input" value={name} autoFocus placeholder="你的 Server 用户名" onChange={(e) => setName(e.target.value)} onKeyDown={onKey} />
              <div className="np-lbl">密码</div>
              <WbInput className="np-input" type="password" value={password} placeholder={mode === 'register' ? '至少 4 位' : '密码'} onChange={(e) => setPassword(e.target.value)} onKeyDown={onKey} />
              <div className="auth-switch">连接后以 Server 账号身份协作；不连接则一切照常本地运行。</div>
            </div>
            <div className="np-foot">
              <span className="np-hint">中心服务 · 团队协作</span>
              <WbButton className="btn-ghost" onClick={onClose}>取消</WbButton>
              <WbButton className="btn-dark" disabled={!name.trim() || password.length < 4 || busy} onClick={submit}>{busy ? '连接中…' : mode === 'login' ? '登录并连接' : '注册并连接'}</WbButton>
            </div>
          </>
        )}
      </div>
    </AntModalBridge>
  )
}
