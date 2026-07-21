import { WbButton } from '../ui/Primitives'
import { useEffect } from 'react'
import { api } from '../../lib/api'
import type { AppNotification } from '../../lib/types'
import { useNotificationStore } from '../../stores/notificationStore'
import { useProjectStore } from '../../stores/projectStore'
import { useUIStore } from '../../stores/uiStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'

// Message center (M7 C4) — lists real collaboration events. Opening refreshes the
// list; "全部已读" clears the badge. Clicking an event with a project jumps there.
const KIND_ICON: Record<string, string> = {
  member_added: '👋',
  role_changed: '🔁',
  member_removed: '🚪',
}

function ago(ts: number): string {
  const diff = Math.max(0, Date.now() / 1000 - ts)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

export function MessageCenter({ onClose }: { onClose: () => void }) {
  const items = useNotificationStore((s) => s.items)
  const unread = useNotificationStore((s) => s.unread)
  const load = useNotificationStore((s) => s.load)
  const markAllRead = useNotificationStore((s) => s.markAllRead)
  const setActive = useProjectStore((s) => s.setActive)
  const setView = useUIStore((s) => s.setView)

  useEffect(() => { void load() }, [load])

  const openProject = async (n: AppNotification) => {
    if (!n.project_id) return
    try {
      const p = await api.getProject(n.project_id)
      setActive(p)
      setView('project', { projectId: p.id })
      void markAllRead()
      onClose()
    } catch {
      // project gone / no longer a member — just dismiss
    }
  }

  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal msg-center" role="dialog" aria-modal="true" aria-label="消息中心">
        <div className="np-h">
          消息中心{unread > 0 && <span className="msg-unread">{unread}</span>}
          <WbButton className="np-x" onClick={onClose}>×</WbButton>
        </div>

        <div className="np-body msg-body">
          {items.length === 0 ? (
            <div className="msg-empty">
              <span className="msg-empty-ic">🔔</span>
              还没有消息。加入项目、角色变更等协作事件会出现在这里。
            </div>
          ) : (
            items.map((n) => (
              <div
                key={n.id}
                className={`msg-row ${n.read ? '' : 'unread'} ${n.project_id ? 'clickable' : ''}`.trim()}
                {...(n.project_id ? clickable : {})}
                aria-disabled={!n.project_id}
                onClick={() => openProject(n)}
              >
                <span className="msg-ic">{KIND_ICON[n.kind] || '🔔'}</span>
                <div className="msg-main">
                  <div className="msg-title">{n.title}</div>
                  {n.body && <div className="msg-sub">{n.body}</div>}
                  <div className="msg-meta">{ago(n.created_at)}</div>
                </div>
                {!n.read && <span className="msg-dot" aria-label="未读" />}
              </div>
            ))
          )}
        </div>

        <div className="np-foot">
          <span className="np-hint" style={{ marginRight: 'auto' }} />
          <WbButton className="btn-ghost" disabled={unread === 0} onClick={() => void markAllRead()}>全部标记已读</WbButton>
          <WbButton className="btn-ghost" onClick={onClose}>关闭</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
