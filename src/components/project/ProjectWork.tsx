import { useState } from 'react'
import { useWorkItemStore } from '../../stores/workItemStore'
import { toast } from '../../stores/toastStore'
import type { WorkStatus } from '../../lib/types'

const COLS: { key: WorkStatus; label: string }[] = [
  { key: 'todo', label: '待开始' },
  { key: 'doing', label: '进行中' },
  { key: 'paused', label: '暂停' },
  { key: 'done', label: '完成' },
]
const LABEL: Record<WorkStatus, string> = { todo: '待开始', doing: '进行中', paused: '暂停', done: '完成' }
const DOT: Record<WorkStatus, string> = { todo: '#9AA0A6', doing: '#3D6BFF', paused: '#F0A020', done: '#16B37A' }

// 计划: kanban with HTML5 drag-and-drop between columns (drop → PATCH status).
export function KanbanBoard() {
  const items = useWorkItemStore((s) => s.items)
  const add = useWorkItemStore((s) => s.add)
  const move = useWorkItemStore((s) => s.move)
  const remove = useWorkItemStore((s) => s.remove)
  const [addingIn, setAddingIn] = useState<WorkStatus | null>(null)
  const [draft, setDraft] = useState('')
  const [dropCol, setDropCol] = useState<WorkStatus | null>(null)

  const submit = (status: WorkStatus) => {
    if (draft.trim()) void add(draft, status)
    setDraft('')
    setAddingIn(null)
  }

  return (
    <>
      <div className="pj-plan-top">
        <button className="btn-dark" style={{ height: 34 }} onClick={() => { setAddingIn('todo'); setDraft('') }}>＋ 新建待办</button>
        <button className="btn-ghost" style={{ height: 34 }} onClick={() => toast('添加数据源（后续接连接器）')}>添加数据源</button>
      </div>
      <div className="pj-kanban">
        {COLS.map((col) => {
          const colItems = items.filter((i) => i.status === col.key)
          return (
            <div
              key={col.key}
              className={`pj-kcol ${dropCol === col.key ? 'drop' : ''}`.trim()}
              onDragOver={(e) => { e.preventDefault(); setDropCol(col.key) }}
              onDragLeave={() => setDropCol((c) => (c === col.key ? null : c))}
              onDrop={(e) => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); if (id) void move(id, col.key); setDropCol(null) }}
            >
              <div className="pj-kcol-h">
                {col.label}<span className="cnt">{colItems.length}</span>
                <span className="plus" onClick={() => { setAddingIn(col.key); setDraft('') }}>＋</span>
              </div>
              {addingIn === col.key && (
                <input
                  className="pj-kadd"
                  autoFocus
                  placeholder="输入标题，回车创建"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submit(col.key); if (e.key === 'Escape') { setAddingIn(null); setDraft('') } }}
                  onBlur={() => { if (!draft.trim()) setAddingIn(null) }}
                />
              )}
              {colItems.map((i) => (
                <div
                  key={i.id}
                  className="pj-card"
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', i.id)}
                >
                  <span className="del" onClick={() => void remove(i.id)}>×</span>
                  <div className="t">{i.title}</div>
                  <div className="m">
                    <span className="av">{i.assignee_name?.[0] ?? '奇'}</span>
                    <span className="ago">{i.ago}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </>
  )
}

// 任务: the same work items as a private list (spec: 你的任务是私密的).
export function TaskList() {
  const items = useWorkItemStore((s) => s.items)
  const remove = useWorkItemStore((s) => s.remove)
  const [q, setQ] = useState('')
  const filtered = items.filter((i) => i.title.toLowerCase().includes(q.trim().toLowerCase()))

  return (
    <>
      <div className="mf-filter" style={{ marginTop: 0, marginBottom: 10 }}>
        <div className="mf-type" onClick={() => toast('筛选归属')}>
          <span className="ft-lb">全部任务</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
        </div>
        <div className="mf-type" onClick={() => toast('筛选来源')}>
          <span className="ft-lb">全部来源</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>你的任务是私密的，除非你共享它们</span>
        <span style={{ flex: 1 }} />
        <div className="search-box" style={{ margin: 0, width: 220 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <input placeholder="搜索任务标题" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {filtered.length ? (
        filtered.map((i) => (
          <div className="pj-task" key={i.id}>
            <span className="st" style={{ background: DOT[i.status] }} />
            <span className="tt">{i.title}</span>
            <span className="stx">{LABEL[i.status]}</span>
            <span className="ago">{i.ago}</span>
            <span className="del" title="删除" onClick={() => void remove(i.id)}>×</span>
          </div>
        ))
      ) : (
        <div className="pj-empty">暂无任务，去「计划」看板新建。</div>
      )}
    </>
  )
}
