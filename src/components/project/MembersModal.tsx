import { WbButton, WbInput, WbSelect } from '../ui/Primitives'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { ProjectInfo, ProjectMember } from '../../lib/types'
import { useAuthStore } from '../../stores/authStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'

// Project members & roles (M7 C2). Owner/Admin can invite by username, change a
// member's role, and remove members; everyone else sees the roster read-only and
// can leave. "Invite" on a shared backend = add an existing account by name.
const ROLE_LABEL: Record<string, string> = { Owner: '所有者', Admin: '管理员', Member: '成员', Viewer: '只读' }
const ASSIGNABLE = ['Admin', 'Member', 'Viewer'] as const

function addError(e: unknown): string {
  const m = String((e as Error)?.message || '')
  if (m.includes('404')) return '找不到该用户名'
  if (m.includes('400')) return '无法添加：可能已是所有者，或角色无效'
  if (m.includes('403')) return '你没有管理成员的权限'
  return '操作失败，请重试'
}

export function MembersModal({ project, onClose, onLeft }: {
  project: ProjectInfo
  onClose: () => void
  onLeft: () => void
}) {
  const meId = useAuthStore((s) => s.me?.id)
  const loadMe = useAuthStore((s) => s.load)
  const [members, setMembers] = useState<ProjectMember[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [role, setRole] = useState<string>('Member')
  const [busy, setBusy] = useState(false)

  const canManage = project.role === 'Owner' || project.role === 'Admin'
  const canLeave = !!project.role && project.role !== 'Owner'

  useEffect(() => {
    if (!meId) void loadMe()
    api.listMembers(project.id)
      .then((r) => setMembers(r.members))
      .catch(() => toast('无法加载成员列表'))
      .finally(() => setLoading(false))
  }, [project.id, meId, loadMe])

  const add = async () => {
    const n = name.trim()
    if (!n || busy) return
    setBusy(true)
    try {
      const r = await api.addMember(project.id, n, role)
      setMembers(r.members)
      setName('')
      toast(`已把「${n}」加入项目`)
    } catch (e) {
      toast(addError(e))
    } finally {
      setBusy(false)
    }
  }

  const changeRole = async (userId: string, next: string) => {
    try {
      const r = await api.updateMemberRole(project.id, userId, next)
      setMembers(r.members)
    } catch {
      toast('修改角色失败')
    }
  }

  const remove = async (m: ProjectMember) => {
    const isSelf = m.user_id === meId
    try {
      await api.removeMember(project.id, m.user_id)
      if (isSelf) { onLeft(); return }
      setMembers((prev) => prev.filter((x) => x.user_id !== m.user_id))
      toast(`已移除「${m.name}」`)
    } catch {
      toast('移除失败')
    }
  }

  const leaveSelf = async () => {
    if (!meId) return
    try {
      await api.removeMember(project.id, meId)
      onLeft()
    } catch {
      toast('退出失败')
    }
  }

  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal members-modal" role="dialog" aria-modal="true" aria-label="项目成员">
        <div className="np-h">项目成员<WbButton className="np-x" onClick={onClose}>×</WbButton></div>

        <div className="np-body">
          {canManage && (
            <>
              <div className="np-lbl">邀请成员（按用户名）</div>
              <div className="mm-add">
                <WbInput
                  className="np-input" value={name} placeholder="对方的用户名"
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void add() }}
                />
                <WbSelect className="mm-role-sel" value={role} onChange={(e) => setRole(e.target.value)} aria-label="角色">
                  {ASSIGNABLE.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </WbSelect>
                <WbButton className="btn-dark" disabled={!name.trim() || busy} onClick={add}>添加</WbButton>
              </div>
            </>
          )}

          <div className="np-lbl">成员 {members.length ? <span className="mm-count">{members.length}</span> : null}</div>
          <div className="mm-list">
            {loading && <div className="mm-empty">加载中…</div>}
            {!loading && members.map((m) => (
              <div className="mm-row" key={m.user_id}>
                <span className="mm-av">{m.name.slice(0, 1)}</span>
                <div className="mm-info">
                  <div className="mm-name">{m.name}{m.user_id === meId && <span className="mm-you">你</span>}</div>
                  <div className="mm-sub">{m.is_owner ? '项目所有者' : ROLE_LABEL[m.role] || m.role}</div>
                </div>
                {canManage && !m.is_owner ? (
                  <>
                    <WbSelect
                      className="mm-role-sel" value={m.role}
                      onChange={(e) => changeRole(m.user_id, e.target.value)} aria-label={`${m.name} 的角色`}
                    >
                      {ASSIGNABLE.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </WbSelect>
                    <WbButton className="mm-x" title="移除" onClick={() => remove(m)}>×</WbButton>
                  </>
                ) : (
                  <span className="mm-badge">{m.is_owner ? ROLE_LABEL.Owner : ROLE_LABEL[m.role] || m.role}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="np-foot">
          {canLeave && <WbButton className="btn-ghost danger-b" onClick={leaveSelf}>退出项目</WbButton>}
          <span className="np-hint" style={{ marginLeft: canLeave ? 0 : 'auto' }} />
          <WbButton className="btn-ghost" onClick={onClose}>关闭</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
