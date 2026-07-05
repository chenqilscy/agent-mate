import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type FileEntry } from '../../lib/api'
import { useWorkItemStore } from '../../stores/workItemStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { Popover } from '../ui/Popover'
import type { WorkAttachment, WorkItem, WorkStatus } from '../../lib/types'

const COLS: { key: WorkStatus; label: string }[] = [
  { key: 'todo', label: '待开始' },
  { key: 'doing', label: '进行中' },
  { key: 'paused', label: '暂停' },
  { key: 'done', label: '完成' },
]
// Fuller labels for the status dropdowns (detail / batch), matching the target design.
const STATUS_OPTS: { key: WorkStatus; label: string }[] = [
  { key: 'todo', label: '待开始' },
  { key: 'doing', label: '进行中' },
  { key: 'paused', label: '已暂停' },
  { key: 'done', label: '已完成' },
]
const LABEL: Record<WorkStatus, string> = { todo: '待开始', doing: '进行中', paused: '暂停', done: '完成' }
const DOT: Record<WorkStatus, string> = { todo: '#9AA0A6', doing: '#3D6BFF', paused: '#F0A020', done: '#16B37A' }

// 添加数据源 (WB-028): honest placeholder — the picker UI is real, but wiring a live
// TAPD/CNB/GitHub sync is a large external integration, so the actions say「敬请期待」
// rather than faking an authorization/import (铁律 #1 不模拟).
const DATA_SOURCES: { key: string; icon: string; name: string; mode: string; desc: string; action: string }[] = [
  { key: 'tapd', icon: 'T', name: 'TAPD', mode: '定时导入', desc: 'TAPD 敏捷项目管理平台，支持缺陷、需求同步到当前项目', action: '去授权' },
  { key: 'cnb', icon: 'C', name: 'CNB', mode: '定时导入', desc: 'CNB 代码托管平台，支持仓库、Issue 同步到当前项目', action: '去授权' },
  { key: 'github', icon: 'G', name: 'GitHub', mode: '事件触发', desc: '代码仓库操作，按事件触发同步', action: '选择' },
]

const IcCaret = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
const IcSearch = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>

function fmtDate(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function flattenFiles(entries: FileEntry[]): { name: string; path: string }[] {
  const out: { name: string; path: string }[] = []
  for (const e of entries) {
    if (e.type === 'd') out.push(...flattenFiles(e.children ?? []))
    else out.push({ name: e.name, path: e.path })
  }
  return out
}

// ---- small reusable dropdowns / pills -----------------------------------

function FilterDropdown({ label, options, onPick }: {
  label: string
  options: { key: string; label: string }[]
  onPick: (key: string) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <div ref={ref} className="mf-type" role="button" tabIndex={0} onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen((v) => !v) } }}>
        <span className="ft-lb">{label}</span>{IcCaret}
      </div>
      <Popover open={open} anchor={ref.current} dir="down" onClose={() => setOpen(false)} minWidth={148}>
        {options.map((o) => (
          <div className="pop-item" key={o.key} onClick={() => { onPick(o.key); setOpen(false) }}>{o.label}</div>
        ))}
      </Popover>
    </>
  )
}

function StatusPill({ status, dir = 'up', onPick }: { status: WorkStatus; dir?: 'up' | 'down'; onPick: (s: WorkStatus) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <button ref={ref} type="button" className="wb-pill" onClick={() => setOpen((v) => !v)}>
        <span className="wb-dot" style={{ background: DOT[status] }} />
        {STATUS_OPTS.find((s) => s.key === status)?.label}{IcCaret}
      </button>
      <Popover open={open} anchor={ref.current} dir={dir} onClose={() => setOpen(false)} minWidth={132}>
        {STATUS_OPTS.map((s) => (
          <div className="pop-item" key={s.key} onClick={() => { onPick(s.key); setOpen(false) }}>
            <span className="wb-dot" style={{ background: DOT[s.key] }} />{s.label}
          </div>
        ))}
      </Popover>
    </>
  )
}

function DueDatePill({ value, dir = 'up', onChange }: { value: string | null; dir?: 'up' | 'down'; onChange: (v: string | null) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <button ref={ref} type="button" className="wb-pill" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden>📅</span>{value || '截止日期'}{IcCaret}
      </button>
      <Popover open={open} anchor={ref.current} dir={dir} onClose={() => setOpen(false)} minWidth={200}>
        <div style={{ padding: 6 }}>
          <input
            type="date" className="wb-date" aria-label="截止日期" value={value ?? ''}
            onChange={(e) => { onChange(e.target.value || null); setOpen(false) }} autoFocus
          />
          {value && (
            <div className="pop-item danger" onClick={() => { onChange(null); setOpen(false) }}>清除截止日期</div>
          )}
        </div>
      </Popover>
    </>
  )
}

// ---- attachments (shared by 详情 / 新建) ----------------------------------

function AssetPickerOverlay({ projectId, onPick, onClose }: {
  projectId: string | null
  onPick: (a: WorkAttachment) => void
  onClose: () => void
}) {
  const [files, setFiles] = useState<{ name: string; path: string }[]>([])
  const [q, setQ] = useState('')
  useEffect(() => {
    if (!projectId) return
    api.filesTree({ project: projectId }).then((r) => setFiles(flattenFiles(r.entries))).catch(() => {})
  }, [projectId])
  const rows = files.filter((f) => f.name.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div className="np-overlay open" style={{ zIndex: 170 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal pk-modal" role="dialog" aria-modal="true" aria-label="选择项目资产">
        <div className="np-h">
          选择项目资产
          <div className="search-box" style={{ marginLeft: 'auto', width: 220 }}>{IcSearch}
            <input placeholder="搜索文件…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <button className="np-x" onClick={onClose}>×</button>
        </div>
        <div className="np-body" style={{ paddingTop: 2 }}>
          {rows.length ? rows.map((f) => (
            <div className="pkc-row" key={f.path} onClick={() => onPick({ name: f.name, kind: 'asset', path: f.path })}>
              <span className="pi">📄</span>
              <div style={{ flex: 1, minWidth: 0 }}><div className="pn">{f.name}</div><div className="pd">{f.path}</div></div>
            </div>
          )) : (
            <div className="pj-empty">项目云盘暂无文件，去「资产」上传或让 Agent 生成产物。</div>
          )}
        </div>
      </div>
    </div>
  )
}

function AttachmentAdder({ projectId, onAdd, dir = 'up' }: {
  projectId: string | null
  onAdd: (a: WorkAttachment) => void
  dir?: 'up' | 'down'
}) {
  const ref = useRef<HTMLButtonElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [menu, setMenu] = useState(false)
  const [pickAsset, setPickAsset] = useState(false)

  const onLocal = () => { setMenu(false); fileRef.current?.click() }
  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f || !projectId) return
    try {
      // 本地文件真实落地到项目云盘（不伪造），再作为资产引用挂到待办上。
      await api.uploadFile(f.name, f, { project: projectId })
      onAdd({ name: f.name, kind: 'local', path: f.name })
      toast('已添加 · ' + f.name)
    } catch {
      toast('上传失败 · ' + f.name)
    }
  }
  return (
    <>
      <button ref={ref} type="button" className="wb-attach-btn" title="添加附件" aria-label="添加附件" onClick={() => setMenu((v) => !v)}>📎</button>
      <input ref={fileRef} type="file" hidden onChange={onFileChosen} />
      <Popover open={menu} anchor={ref.current} dir={dir} onClose={() => setMenu(false)} minWidth={120}>
        <div className="pop-item" onClick={onLocal}>本地文件</div>
        <div className="pop-item" onClick={() => { setMenu(false); setPickAsset(true) }}>项目资产</div>
      </Popover>
      {pickAsset && <AssetPickerOverlay projectId={projectId} onPick={(a) => { onAdd(a); setPickAsset(false) }} onClose={() => setPickAsset(false)} />}
    </>
  )
}

function AttachmentChips({ list, projectId, onRemove }: {
  list: WorkAttachment[]
  projectId: string | null
  onRemove?: (i: number) => void
}) {
  if (!list.length) return null
  const download = (a: WorkAttachment) => {
    if (!a.path || !projectId) return
    const el = document.createElement('a')
    el.href = api.downloadUrl(a.path, { project: projectId })
    el.download = a.name
    el.click()
  }
  return (
    <div className="wb-attach-list">
      {list.map((a, i) => (
        <span className="wb-attach-chip" key={i} title={a.name}>
          <span className="ic" aria-hidden>📎</span>
          <span className="nm" onClick={() => download(a)}>{a.name}</span>
          {onRemove && <span className="x" onClick={() => onRemove(i)}>×</span>}
        </span>
      ))}
    </div>
  )
}

// ---- 待办详情 modal -------------------------------------------------------

function TodoDetailModal({ itemId, onClose }: { itemId: string; onClose: () => void }) {
  const item = useWorkItemStore((s) => s.items.find((i) => i.id === itemId))
  const projectId = useWorkItemStore((s) => s.projectId)
  const update = useWorkItemStore((s) => s.update)
  const setPrefill = useUIStore((s) => s.setComposerPrefill)
  const [editDesc, setEditDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')

  // If the item vanishes (deleted elsewhere), close.
  useEffect(() => { if (!item) onClose() }, [item, onClose])
  if (!item) return null

  const startEdit = () => { setDescDraft(item.description); setEditDesc(true) }
  const saveDesc = () => { setEditDesc(false); if (descDraft !== item.description) void update(item.id, { description: descDraft }) }
  const addToInput = () => {
    const text = item.description.trim() ? `${item.title}\n\n${item.description}` : item.title
    setPrefill(text)
    toast('已添加到输入框')
    onClose()
  }
  const addAttach = (a: WorkAttachment) => void update(item.id, { attachments: [...item.attachments, a] })
  const rmAttach = (i: number) => void update(item.id, { attachments: item.attachments.filter((_, j) => j !== i) })

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal wb-td" role="dialog" aria-modal="true" aria-label="待办详情">
        <div className="wb-td-top">
          <span className="wb-td-kicker">待办详情</span>
          <span style={{ flex: 1 }} />
          <button className="btn-ghost wb-td-addbtn" onClick={addToInput}>＋ 添加到输入框</button>
          <button className="np-x" onClick={onClose}>×</button>
        </div>
        <div className="np-body">
          <div className="wb-td-title">{item.title}</div>
          <div className="wb-td-meta">
            由 {item.assignee_name} 创建 · {fmtDate(item.created_at)}
            {item.updated_at && item.updated_at !== item.created_at ? ` · 更新于 ${fmtDate(item.updated_at)}` : ''}
          </div>

          <div className="wb-td-sec-h">
            描述
            {!editDesc && <button className="wb-td-editlink" onClick={startEdit}>✎ 编辑</button>}
          </div>
          {editDesc ? (
            <>
              <textarea className="np-ta" value={descDraft} onChange={(e) => setDescDraft(e.target.value)} autoFocus />
              <div className="pjcfg-edit-f">
                <button className="btn-ghost" style={{ height: 28, padding: '0 12px' }} onClick={() => setEditDesc(false)}>取消</button>
                <button className="btn-dark" style={{ height: 28, padding: '0 14px' }} onClick={saveDesc}>保存</button>
              </div>
            </>
          ) : (
            <div className={`wb-td-desc ${item.description ? '' : 'empty'}`.trim()}>{item.description || '暂无描述，点「编辑」补充。'}</div>
          )}

          {item.attachments.length > 0 && <div className="wb-td-sec-h">附件 {item.attachments.length}</div>}
          <AttachmentChips list={item.attachments} projectId={projectId} onRemove={rmAttach} />
          <div style={{ marginTop: 10 }}>
            <AttachmentAdder projectId={projectId} onAdd={addAttach} dir="up" />
          </div>
        </div>
        <div className="wb-td-foot">
          <span className="wb-av" title={item.assignee_name}>{item.assignee_name?.[0] ?? '奇'}</span>
          <StatusPill status={item.status} dir="up" onPick={(s) => void update(item.id, { status: s })} />
          <DueDatePill value={item.due_date} dir="up" onChange={(v) => void update(item.id, { due_date: v })} />
        </div>
      </div>
    </div>
  )
}

// ---- 新建待办 modal -------------------------------------------------------

function NewTodoModal({ status, onClose, onCreated }: {
  status: WorkStatus
  onClose: () => void
  onCreated: (wi: WorkItem) => void
}) {
  const projectId = useWorkItemStore((s) => s.projectId)
  const add = useWorkItemStore((s) => s.add)
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [due, setDue] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<WorkAttachment[]>([])
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!title.trim() || busy) return
    setBusy(true)
    try {
      const wi = await add({ title, status, description: desc, due_date: due, attachments })
      if (wi) { toast('待办已创建'); onCreated(wi) }
      onClose()
    } catch {
      toast('创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="新建待办">
        <div className="np-h">新建待办<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">标题</div>
          <input className="np-input" placeholder="请输入待办标题" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter') void create() }} />
          <div className="np-lbl">描述（可选）</div>
          <textarea className="np-ta" placeholder="请输入待办描述" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <AttachmentChips list={attachments} projectId={projectId} onRemove={(i) => setAttachments((a) => a.filter((_, j) => j !== i))} />
        </div>
        <div className="np-foot">
          <AttachmentAdder projectId={projectId} onAdd={(a) => setAttachments((prev) => [...prev, a])} dir="up" />
          <DueDatePill value={due} dir="up" onChange={setDue} />
          <span style={{ flex: 1 }} />
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-dark" disabled={!title.trim() || busy} onClick={create}>创建</button>
        </div>
      </div>
    </div>
  )
}

// ---- 添加数据源 modal (placeholder) --------------------------------------

function DataSourceModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<'empty' | 'list'>('empty')
  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="添加数据源">
        <div className="np-h">添加数据源<button className="np-x" onClick={onClose}>×</button></div>
        {step === 'empty' ? (
          <div className="np-body" style={{ paddingBottom: 22 }}>
            <div className="pj-ds-empty">
              <div className="t">还没有外部数据源</div>
              <div className="s">先添加一个数据源，把外部系统中的信息按规则同步到当前协作项目。</div>
              <button className="btn-dark" onClick={() => setStep('list')}>添加</button>
            </div>
          </div>
        ) : (
          <>
            <div className="np-body" style={{ paddingTop: 2 }}>
              <div className="pj-ds-sub">选择一个外部系统作为数据来源</div>
              <div className="pj-ds-grid">
                {DATA_SOURCES.map((d) => (
                  <div className="pkc-row pj-ds-card" key={d.key}>
                    <span className="pi">{d.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="pn">{d.name} <span className="pj-ds-badge">{d.mode}</span></div>
                      <div className="pd">{d.desc}</div>
                    </div>
                    <button className="pj-ds-act" onClick={() => toast(`${d.name} 数据源接入 · 敬请期待`)}>{d.action} ↗</button>
                  </div>
                ))}
              </div>
            </div>
            <div className="np-foot" style={{ justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={() => setStep('empty')}>返回</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function BatchMove({ disabled, onPick }: { disabled: boolean; onPick: (s: WorkStatus) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <button ref={ref} type="button" className="btn-ghost" disabled={disabled} onClick={() => setOpen((v) => !v)}>移动到 ▾</button>
      <Popover open={open} anchor={ref.current} dir="down" onClose={() => setOpen(false)} minWidth={132}>
        {STATUS_OPTS.map((s) => (
          <div className="pop-item" key={s.key} onClick={() => { onPick(s.key); setOpen(false) }}>
            <span className="wb-dot" style={{ background: DOT[s.key] }} />{s.label}
          </div>
        ))}
      </Popover>
    </>
  )
}

// 计划: kanban with HTML5 drag-and-drop between columns (drop → PATCH status),
// per-card detail modal, a full new-todo modal, a top toolbar (filter/batch/search)
// and a placeholder 添加数据源 picker.
export function KanbanBoard() {
  const items = useWorkItemStore((s) => s.items)
  const add = useWorkItemStore((s) => s.add)
  const move = useWorkItemStore((s) => s.move)
  const remove = useWorkItemStore((s) => s.remove)

  const [detailId, setDetailId] = useState<string | null>(null)
  const [newIn, setNewIn] = useState<WorkStatus | null>(null)
  const [dsOpen, setDsOpen] = useState(false)
  const [dropCol, setDropCol] = useState<WorkStatus | null>(null)
  const [quickIn, setQuickIn] = useState<WorkStatus | null>(null)
  const [quickDraft, setQuickDraft] = useState('')
  // toolbar
  const [fAssignee, setFAssignee] = useState('all')
  const [fSource, setFSource] = useState('all')
  const [q, setQ] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  // batch
  const [batch, setBatch] = useState(false)
  const [sel, setSel] = useState<Set<string>>(new Set())

  const assigneeOpts = useMemo(() => {
    const m = new Map<string, string>()
    items.forEach((i) => m.set(i.assignee, i.assignee_name))
    return [{ key: 'all', label: '全部归属' }, ...[...m].map(([k, v]) => ({ key: k, label: v }))]
  }, [items])
  const sourceOpts = useMemo(() => {
    const s = new Set(items.map((i) => i.source))
    return [{ key: 'all', label: '全部来源' }, ...[...s].map((v) => ({ key: v, label: v }))]
  }, [items])

  const visible = items.filter((i) =>
    (fAssignee === 'all' || i.assignee === fAssignee) &&
    (fSource === 'all' || i.source === fSource) &&
    (!q.trim() || i.title.toLowerCase().includes(q.trim().toLowerCase())),
  )

  const quickSubmit = (status: WorkStatus) => {
    if (quickDraft.trim()) void add({ title: quickDraft, status })
    setQuickDraft(''); setQuickIn(null)
  }
  const toggleSel = (id: string) => setSel((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  const exitBatch = () => { setBatch(false); setSel(new Set()) }
  const batchMove = (s: WorkStatus) => { sel.forEach((id) => void move(id, s)); exitBatch() }
  const batchDelete = () => { sel.forEach((id) => void remove(id)); exitBatch() }
  const cardClick = (i: WorkItem) => { if (batch) toggleSel(i.id); else setDetailId(i.id) }

  return (
    <>
      <div className="pj-plan-top">
        <button className="btn-dark" style={{ height: 34 }} onClick={() => { setNewIn('todo') }}>＋ 新建待办</button>
        <button className="btn-ghost" style={{ height: 34 }} onClick={() => setDsOpen(true)}>＋ 添加数据源</button>
        <span style={{ flex: 1 }} />
        <FilterDropdown label={assigneeOpts.find((o) => o.key === fAssignee)?.label ?? '全部归属'} options={assigneeOpts} onPick={setFAssignee} />
        <FilterDropdown label={sourceOpts.find((o) => o.key === fSource)?.label ?? '全部来源'} options={sourceOpts} onPick={setFSource} />
        <button className={`hub-act ${batch ? 'on' : ''}`.trim()} onClick={() => (batch ? exitBatch() : setBatch(true))}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
          批量操作
        </button>
        <button className="hub-act wb-icon-btn" aria-label="搜索待办" onClick={() => setShowSearch((v) => !v)}>{IcSearch}</button>
      </div>

      {showSearch && (
        <div className="pj-plan-search">
          <div className="search-box" style={{ margin: 0, width: 280 }}>{IcSearch}
            <input placeholder="搜索待办标题" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          </div>
        </div>
      )}

      {batch && (
        <div className="pj-batchbar">
          <span className="cnt">已选 {sel.size}</span>
          <BatchMove disabled={!sel.size} onPick={batchMove} />
          <button className="btn-ghost danger-b" disabled={!sel.size} onClick={batchDelete}>删除</button>
          <span style={{ flex: 1 }} />
          <button className="btn-ghost" onClick={exitBatch}>退出批量</button>
        </div>
      )}

      <div className="pj-kanban">
        {COLS.map((col) => {
          const colItems = visible.filter((i) => i.status === col.key)
          return (
            <div
              key={col.key}
              className={`pj-kcol ${dropCol === col.key ? 'drop' : ''}`.trim()}
              onDragOver={(e) => { if (batch) return; e.preventDefault(); setDropCol(col.key) }}
              onDragLeave={() => setDropCol((c) => (c === col.key ? null : c))}
              onDrop={(e) => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); if (id) void move(id, col.key); setDropCol(null) }}
            >
              <div className="pj-kcol-h">
                <span className="wb-dot" style={{ background: DOT[col.key] }} />
                {col.label}<span className="cnt">{colItems.length}</span>
                <span className="plus" onClick={() => { setQuickIn(col.key); setQuickDraft('') }}>＋</span>
              </div>
              {quickIn === col.key && (
                <input
                  className="pj-kadd"
                  autoFocus
                  placeholder="输入标题，回车创建"
                  value={quickDraft}
                  onChange={(e) => setQuickDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') quickSubmit(col.key); if (e.key === 'Escape') { setQuickIn(null); setQuickDraft('') } }}
                  onBlur={() => { if (!quickDraft.trim()) setQuickIn(null) }}
                />
              )}
              {colItems.map((i) => (
                <div
                  key={i.id}
                  className={`pj-card ${batch && sel.has(i.id) ? 'sel' : ''}`.trim()}
                  draggable={!batch}
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', i.id)}
                  onClick={() => cardClick(i)}
                >
                  {batch ? (
                    <span className={`pj-card-chk ${sel.has(i.id) ? 'on' : ''}`.trim()}>{sel.has(i.id) ? '✓' : ''}</span>
                  ) : (
                    <span className="del" onClick={(e) => { e.stopPropagation(); void remove(i.id) }}>×</span>
                  )}
                  <div className="t">{i.title}</div>
                  {i.description && <div className="wb-card-d">{i.description}</div>}
                  <div className="m">
                    <span className="av">{i.assignee_name?.[0] ?? '奇'}</span>
                    {i.attachments.length > 0 && <span className="wb-badge">📎 {i.attachments.length}</span>}
                    {i.due_date && <span className="wb-badge due">📅 {i.due_date.slice(5)}</span>}
                    <span style={{ flex: 1 }} />
                    <span className="ago">{i.ago}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {detailId && <TodoDetailModal itemId={detailId} onClose={() => setDetailId(null)} />}
      {newIn && <NewTodoModal status={newIn} onClose={() => setNewIn(null)} onCreated={(wi) => setDetailId(wi.id)} />}
      {dsOpen && <DataSourceModal onClose={() => setDsOpen(false)} />}
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
            {i.due_date && <span className="wb-badge due">📅 {i.due_date.slice(5)}</span>}
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
