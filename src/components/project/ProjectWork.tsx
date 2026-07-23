import { WbButton, WbInput, WbTextArea } from '../ui/Primitives'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type FileEntry } from '../../lib/api'
import { useWorkItemStore } from '../../stores/workItemStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { toast } from '../../stores/toastStore'
import { Popover } from '../ui/Popover'
import type { WorkAttachment, WorkItem, WorkItemDelivery, WorkPriority, WorkStatus } from '../../lib/types'
import { AntModalBridge } from '../ui/AntModalBridge'
import { App as AntApp, Empty, Input, Select, Table, Tag } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../../lib/a11y'

const COLS: { key: WorkStatus; label: string }[] = [
  { key: 'todo', label: '待开始' },
  { key: 'doing', label: '进行中' },
  { key: 'paused', label: '暂停' },
  { key: 'done', label: '完成' },
]
// 优先级（WB-108，与 Server 对齐）。'' = 未设；颜色沿用状态点的调色。
const PRIORITY_OPTS: { key: WorkPriority; label: string; color: string }[] = [
  { key: '', label: '无优先级', color: '#9AA0A6' },
  { key: 'low', label: '低', color: '#16B37A' },
  { key: 'medium', label: '中', color: '#3D6BFF' },
  { key: 'high', label: '高', color: '#F0A020' },
  { key: 'urgent', label: '紧急', color: '#E5484D' },
]
const PRIO: Record<WorkPriority, { label: string; color: string }> = Object.fromEntries(
  PRIORITY_OPTS.map((o) => [o.key, { label: o.label, color: o.color }]),
) as Record<WorkPriority, { label: string; color: string }>
// Fuller labels for the status dropdowns (detail / batch), matching the target design.
const STATUS_OPTS: { key: WorkStatus; label: string }[] = [
  { key: 'todo', label: '待开始' },
  { key: 'doing', label: '进行中' },
  { key: 'paused', label: '已暂停' },
  { key: 'done', label: '已完成' },
]
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
// 任务模板（WB-122，per-project localStorage，对齐 Console WB-114）。
type WorkTemplate = { name: string; priority: WorkPriority; labels: string[]; milestone_id: string; description: string }
function getTpl(pid: string | null): WorkTemplate[] {
  if (!pid) return []
  try { return JSON.parse(localStorage.getItem(`pm.tpl.${pid}`) || '[]') || [] } catch { return [] }
}
function setTpl(pid: string, t: WorkTemplate[]): void {
  try { localStorage.setItem(`pm.tpl.${pid}`, JSON.stringify(t)) } catch { /* quota */ }
}
// 看板 WIP 上限 + 保存视图（WB-123，per-project localStorage，对齐 Console WB-113）。
function getWip(pid: string | null): Record<string, number> {
  if (!pid) return {}
  try { return JSON.parse(localStorage.getItem(`pm.wip.${pid}`) || '{}') || {} } catch { return {} }
}
function setWip(pid: string, w: Record<string, number>): void {
  try { localStorage.setItem(`pm.wip.${pid}`, JSON.stringify(w)) } catch { /* quota */ }
}
type KView = { name: string; assignee: string; source: string; q: string; group: string }
function getKViews(pid: string | null): KView[] {
  if (!pid) return []
  try { return JSON.parse(localStorage.getItem(`pm.kview.${pid}`) || '[]') || [] } catch { return [] }
}
function setKViews(pid: string, v: KView[]): void {
  try { localStorage.setItem(`pm.kview.${pid}`, JSON.stringify(v)) } catch { /* quota */ }
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
  return <Select className="mf-type" aria-label={label} value="" placeholder={label} options={options.map((o) => ({ value: o.key, label: o.label }))} onChange={onPick} />
}

function StatusPill({ status, onPick }: { status: WorkStatus; dir?: 'up' | 'down'; onPick: (s: WorkStatus) => void }) {
  return <Select className="wb-pill" value={status} onChange={(value) => onPick(value as WorkStatus)} options={STATUS_OPTS.map((s) => ({ value: s.key, label: <span><span className="wb-dot" style={{ background: DOT[s.key] }} />{s.label}</span> }))} />
}

function DueDatePill({ value, dir = 'up', onChange }: { value: string | null; dir?: 'up' | 'down'; onChange: (v: string | null) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <WbButton ref={ref} type="button" className="wb-pill" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden>📅</span>{value || '截止日期'}{IcCaret}
      </WbButton>
      <Popover open={open} anchor={ref.current} dir={dir} onClose={() => setOpen(false)} minWidth={200}>
        <div style={{ padding: 6 }}>
          <WbInput
            type="date" className="wb-date" aria-label="截止日期" value={value ?? ''}
            onChange={(e) => { onChange(e.target.value || null); setOpen(false) }} autoFocus
          />
          {value && (
            <div className="pop-item danger" {...clickable} onClick={() => { onChange(null); setOpen(false) }}>清除截止日期</div>
          )}
        </div>
      </Popover>
    </>
  )
}

function PriorityPill({ value, onPick }: { value: WorkPriority; dir?: 'up' | 'down'; onPick: (p: WorkPriority) => void }) {
  return <Select className="wb-pill" value={value} onChange={(next) => onPick(next as WorkPriority)} options={PRIORITY_OPTS.map((o) => ({ value: o.key, label: <span><span className="wb-dot" style={{ background: o.color }} />{o.label}</span> }))} />
}

// 里程碑选择器：从项目里程碑里选，或就地新建一个（WB-108）。
function MilestonePill({ value, dir = 'up', onPick }: { value: string; dir?: 'up' | 'down'; onPick: (id: string) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState('')
  const milestones = useWorkItemStore((s) => s.milestones)
  const addMilestone = useWorkItemStore((s) => s.addMilestone)
  const cur = milestones.find((m) => m.id === value)
  const doCreate = async () => {
    const m = await addMilestone(draft)
    if (m) { onPick(m.id); setDraft(''); setCreating(false); setOpen(false) }
    else toast('新建里程碑失败')
  }
  return (
    <>
      <WbButton ref={ref} type="button" className="wb-pill" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden>🚩</span>{cur ? cur.name : '里程碑'}{IcCaret}
      </WbButton>
      <Popover open={open} anchor={ref.current} dir={dir} onClose={() => { setOpen(false); setCreating(false) }} minWidth={200}>
        <div className="pop-item" {...clickable} onClick={() => { onPick(''); setOpen(false) }}>无里程碑</div>
        {milestones.map((m) => (
          <div className="pop-item" key={m.id} {...clickable} onClick={() => { onPick(m.id); setOpen(false) }}>🚩 {m.name}</div>
        ))}
        {creating ? (
          <div style={{ padding: 6, display: 'flex', gap: 6 }}>
            <WbInput className="np-input" style={{ height: 30 }} placeholder="里程碑名称" value={draft} autoFocus
              onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void doCreate() }} />
            <WbButton className="btn-dark" style={{ height: 30, padding: '0 12px' }} onClick={() => void doCreate()}>建</WbButton>
          </div>
        ) : (
          <div className="pop-item" {...clickable} onClick={() => setCreating(true)}>＋ 新建里程碑</div>
        )}
      </Popover>
    </>
  )
}

// 标签编辑器：回车/失焦加标签，× 删（WB-108）。
function LabelsEditor({ labels, onChange }: { labels: string[]; onChange: (l: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const t = draft.trim().slice(0, 40)
    if (t && !labels.includes(t)) onChange([...labels, t])
    setDraft('')
  }
  return (
    <div className="wb-labels-ed">
      {labels.map((l, i) => (
        <span className="wb-label-chip" key={l}>#{l}<span className="x" {...clickable} onClick={() => onChange(labels.filter((_, j) => j !== i))}>×</span></span>
      ))}
      <WbInput className="wb-label-in" placeholder="加标签…" value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} onBlur={add} />
    </div>
  )
}

// 卡片上的标签徽标（只读，最多显示几枚）。
function LabelBadges({ labels }: { labels: string[] }) {
  if (!labels.length) return null
  return (
    <>
      {labels.slice(0, 3).map((l) => <span className="wb-label-chip sm" key={l}>#{l}</span>)}
      {labels.length > 3 && <span className="wb-label-chip sm">+{labels.length - 3}</span>}
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
    <AntModalBridge onClose={onClose} zIndex={170}>
      <div className="np-modal pk-modal" role="dialog" aria-modal="true" aria-label="选择项目资产">
        <div className="np-h">
          选择项目资产
          <div className="search-box" style={{ marginLeft: 'auto', width: 220 }}>{IcSearch}
            <WbInput placeholder="搜索文件…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <WbButton className="np-x" onClick={onClose}>×</WbButton>
        </div>
        <div className="np-body" style={{ paddingTop: 2 }}>
          {rows.length ? rows.map((f) => (
            <div className="pkc-row" key={f.path} {...clickable} onClick={() => onPick({ name: f.name, kind: 'asset', path: f.path })}>
              <span className="pi">📄</span>
              <div style={{ flex: 1, minWidth: 0 }}><div className="pn">{f.name}</div><div className="pd">{f.path}</div></div>
            </div>
          )) : (
            <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="项目云盘暂无文件，去「资产」上传或让 Agent 生成产物。" />
          )}
        </div>
      </div>
    </AntModalBridge>
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
      <WbButton ref={ref} type="button" className="wb-attach-btn" title="添加附件" aria-label="添加附件" onClick={() => setMenu((v) => !v)}>📎</WbButton>
      <WbInput ref={fileRef} type="file" hidden onChange={onFileChosen} />
      <Popover open={menu} anchor={ref.current} dir={dir} onClose={() => setMenu(false)} minWidth={120}>
        <div className="pop-item" {...clickable} onClick={onLocal}>本地文件</div>
        <div className="pop-item" {...clickable} onClick={() => { setMenu(false); setPickAsset(true) }}>项目资产</div>
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
    void api.downloadFile(a.path, a.name, { project: projectId })
  }
  return (
    <div className="wb-attach-list">
      {list.map((a, i) => (
        <span className="wb-attach-chip" key={i} title={a.name}>
          <span className="ic" aria-hidden>📎</span>
          <span className="nm" {...clickable} onClick={() => download(a)}>{a.name}</span>
          {onRemove && <span className="x" {...clickable} onClick={() => onRemove(i)}>×</span>}
        </span>
      ))}
    </div>
  )
}

// ---- 待办详情 modal -------------------------------------------------------

function TodoDetailModal({ itemId, onClose, canWrite }: { itemId: string; onClose: () => void; canWrite: boolean }) {
  const item = useWorkItemStore((s) => s.items.find((i) => i.id === itemId))
  const projectId = useWorkItemStore((s) => s.projectId)
  const update = useWorkItemStore((s) => s.update)
  const addRef = useLoadoutStore((s) => s.addRef)
  const [editDesc, setEditDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')
  // 任务级评论（WB-118）：经 Server 代理，server-origin/已连 Server 项目可用。
  const [comments, setComments] = useState<{ id: string; author_name: string; body: string; created_at: number }[]>([])
  const [cbody, setCbody] = useState('')
  const [serverOn, setServerOn] = useState(true)

  const [delivery, setDelivery] = useState<WorkItemDelivery | null>(null)
  const [deliveryBusy, setDeliveryBusy] = useState(false)
  // If the item vanishes (deleted elsewhere), close.
  useEffect(() => { if (!item) onClose() }, [item, onClose])
  useEffect(() => {
    if (!projectId) return
    let alive = true
    void api.serverItemComments(projectId, itemId).then((r) => { if (alive) { setComments(r.comments || []); setServerOn(r.server) } }).catch(() => {})
    return () => { alive = false }
  }, [projectId, itemId])
  const loadDelivery = () => {
    void api.getWorkItemDelivery(itemId).then((value) => {
      setDelivery(value)
      if (projectId && value.work_item.status !== item?.status) {
        useWorkItemStore.getState().applyRemote({
          id: itemId, project_id: projectId, status: value.work_item.status,
        })
      }
    }).catch(() => {})
  }
  useEffect(() => { loadDelivery() }, [itemId]) // eslint-disable-line react-hooks/exhaustive-deps
  const deliveryActive = delivery?.launches.some((launch) => ['queued', 'running'].includes(launch.status)) ?? false
  useEffect(() => {
    if (!deliveryActive) return
    const timer = setInterval(loadDelivery, 2500)
    return () => clearInterval(timer)
  }, [deliveryActive, itemId]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!item) return null

  const startEdit = () => { setDescDraft(item.description); setEditDesc(true) }
  const saveDesc = () => { setEditDesc(false); if (descDraft !== item.description) void update(item.id, { description: descDraft }) }
  const addToInput = () => {
    // 作为独立引用 chip 加入 Composer（🔖），与正文/文件引用区分；随下条消息真实注入并在发送后清空。
    // 带上 work_item id，让 agent 能在处理完成后回写它的状态（WB-030）。
    const content = item.description.trim() ? `${item.title}\n\n${item.description}` : item.title
    const added = addRef({ name: item.title, content, kind: 'todo', itemId: item.id })
    toast(added ? '已添加到输入框' : '该待办已在输入框')
    onClose()
  }
  const addAttach = (a: WorkAttachment) => void update(item.id, { attachments: [...item.attachments, a] })
  const rmAttach = (i: number) => void update(item.id, { attachments: item.attachments.filter((_, j) => j !== i) })
  const saveAsTemplate = () => {
    if (!projectId || !item) return
    const t = getTpl(projectId)
    t.push({ name: item.title, priority: item.priority, labels: item.labels, milestone_id: item.milestone_id, description: item.description })
    setTpl(projectId, t)
    toast(`已存为模板「${item.title}」`)
  }
  const sendComment = async () => {
    const v = cbody.trim(); if (!v || !projectId) return
    try {
      await api.serverPostItemComment(projectId, itemId, v)
      setCbody('')
      const r = await api.serverItemComments(projectId, itemId)
      setComments(r.comments || [])
    } catch { toast('评论失败') }
  }

  const executeWithAgent = async () => {
    setDeliveryBusy(true)
    try {
      await api.executeWorkItem(item.id, crypto.randomUUID())
      if (projectId) useWorkItemStore.getState().applyRemote({ id: item.id, project_id: projectId, status: 'doing' })
      toast('已交给 Agent 执行')
      loadDelivery()
    } catch { toast('发起执行失败') } finally { setDeliveryBusy(false) }
  }
  const acceptDelivery = async (runId: string) => {
    setDeliveryBusy(true)
    try {
      await api.acceptWorkItemDelivery(item.id, runId)
      if (projectId) useWorkItemStore.getState().applyRemote({ id: item.id, project_id: projectId, status: 'done' })
      toast('交付已验收，工作项已完成')
      loadDelivery()
    } catch { toast('验收失败，请检查产物完整性') } finally { setDeliveryBusy(false) }
  }
  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal wb-td" role="dialog" aria-modal="true" aria-label="待办详情">
        <div className="wb-td-top">
          <span className="wb-td-kicker">待办详情</span>
          <span style={{ flex: 1 }} />
          {canWrite && <WbButton className="btn-ghost wb-td-addbtn" onClick={saveAsTemplate}>存为模板</WbButton>}
          {canWrite && <WbButton className="btn-ghost wb-td-addbtn" onClick={addToInput}>＋ 添加到输入框</WbButton>}
          <WbButton className="np-x" onClick={onClose}>×</WbButton>
        </div>
        <div className="np-body">
          <div className="wb-td-title">{item.title}</div>
          <div className="wb-td-meta">
            由 {item.assignee_name} 创建 · {fmtDate(item.created_at)}
            {item.updated_at && item.updated_at !== item.created_at ? ` · 更新于 ${fmtDate(item.updated_at)}` : ''}
          </div>

          <div className="wb-td-sec-h">
            描述
            {canWrite && !editDesc && <WbButton className="wb-td-editlink" onClick={startEdit}>✎ 编辑</WbButton>}
          </div>
          {editDesc ? (
            <>
              <WbTextArea className="np-ta" value={descDraft} onChange={(e) => setDescDraft(e.target.value)} autoFocus />
              <div className="pjcfg-edit-f">
                <WbButton className="btn-ghost" style={{ height: 28, padding: '0 12px' }} onClick={() => setEditDesc(false)}>取消</WbButton>
                <WbButton className="btn-dark" style={{ height: 28, padding: '0 14px' }} onClick={saveDesc}>保存</WbButton>
              </div>
            </>
          ) : (
            <div className={`wb-td-desc ${item.description ? '' : 'empty'}`.trim()}>{item.description || '暂无描述，点「编辑」补充。'}</div>
          )}

          <div className="wb-td-sec-h">
            Agent 交付
            {canWrite && delivery?.can_write && (
              <WbButton className="wb-td-editlink" disabled={deliveryBusy || deliveryActive} onClick={() => void executeWithAgent()}>
                {deliveryActive ? '执行中…' : '交给 Agent 执行'}
              </WbButton>
            )}
          </div>
          {!delivery || (delivery.runs.length === 0 && delivery.launches.length === 0) ? (
            <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有关联执行与交付物" />
          ) : (
            <div className="auto-runs">
              {delivery.runs.map((run) => (
                <ProCard className="section-card" key={run.id} size="small" variant="outlined">
                  <div className="wb-td-meta">
                    <Tag color={run.status === 'failed' ? 'error' : run.status === 'accepted' ? 'success' : 'processing'}>{run.status}</Tag>
                    {run.prompt_tokens + run.completion_tokens} tokens · {run.tool_calls} 次工具调用
                  </div>
                  {run.error_message && <div className="auto-detail-err err">{run.error_code}: {run.error_message}</div>}
                  {(run.artifacts ?? []).map((artifact) => (
                    <div className="wb-attach-chip" key={artifact.id}>
                      <span className="ic" aria-hidden>📦</span>
                      <span className="nm" {...clickable} onClick={() => projectId && void api.downloadFile(artifact.path, artifact.name, { project: projectId })}>{artifact.name}</span>
                      <Tag color={artifact.acceptance_status === 'accepted' ? 'success' : 'default'}>{artifact.acceptance_status === 'accepted' ? '已验收' : '待验收'}</Tag>
                    </div>
                  ))}
                  {canWrite && delivery.can_write && run.status === 'completed' && (run.artifacts?.length ?? 0) > 0 && (
                    <WbButton className="btn-dark" disabled={deliveryBusy} onClick={() => void acceptDelivery(run.id)}>验收全部产物并完成</WbButton>
                  )}
                </ProCard>
              ))}
              {delivery.launches.filter((launch) => !launch.run_id && launch.status !== 'completed').map((launch) => (
                <div className="auto-detail-box" key={launch.id}>
                  {launch.status === 'failed' ? `发起失败：${launch.error_code || ''}` : 'Agent 正在准备执行…'}
                </div>
              ))}
            </div>
          )}

          <div className="wb-td-sec-h">标签</div>
          {canWrite ? <LabelsEditor labels={item.labels} onChange={(l) => void update(item.id, { labels: l })} /> : <LabelBadges labels={item.labels} />}

          {item.attachments.length > 0 && <div className="wb-td-sec-h">附件 {item.attachments.length}</div>}
          <AttachmentChips list={item.attachments} projectId={projectId} onRemove={canWrite ? rmAttach : undefined} />
          {canWrite && <div style={{ marginTop: 10 }}>
            <AttachmentAdder projectId={projectId} onAdd={addAttach} dir="up" />
          </div>}

          <div className="wb-td-sec-h">工时（小时）</div>
          <div style={{ display: 'flex', gap: 12 }}>
            <label style={{ flex: 1, fontSize: 12, color: 'var(--wb-dim, #93a0b8)' }}>预估
              <WbInput className="np-input" type="number" min={0} step={0.5} style={{ height: 30, marginTop: 4 }} disabled={!canWrite}
                defaultValue={item.estimate_h || ''} key={`est-${item.id}-${item.estimate_h}`}
                onBlur={(e) => { const v = parseFloat(e.target.value) || 0; if (v !== item.estimate_h) void update(item.id, { estimate_h: v }) }} />
            </label>
            <label style={{ flex: 1, fontSize: 12, color: 'var(--wb-dim, #93a0b8)' }}>已投入
              <WbInput className="np-input" type="number" min={0} step={0.5} style={{ height: 30, marginTop: 4 }} disabled={!canWrite}
                defaultValue={item.spent_h || ''} key={`spent-${item.id}-${item.spent_h}`}
                onBlur={(e) => { const v = parseFloat(e.target.value) || 0; if (v !== item.spent_h) void update(item.id, { spent_h: v }) }} />
            </label>
          </div>

          <div className="wb-td-sec-h">评论{comments.length > 0 ? ` ${comments.length}` : ''}</div>
          {!serverOn ? (
            <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="连接 AgentMate Server 账号后可在任务下评论、@ 队友。" />
          ) : (
            <>
              {canWrite ? <div className="cap-cmt-box" style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <WbInput className="np-input" style={{ flex: 1 }} value={cbody} placeholder="写条评论…用 @用户名 提及成员"
                  onChange={(e) => setCbody(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void sendComment() }} />
                <WbButton className="btn-dark" disabled={!cbody.trim()} onClick={() => void sendComment()}>发送</WbButton>
              </div> : <Tag className="pj-rolebadge" style={{ marginBottom: 10 }}>只读成员可查看评论</Tag>}
              {comments.length === 0 ? (
                <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有评论" />
              ) : (
                comments.map((c) => (
                  <div className="msg-row" key={c.id}>
                    <span className="msg-ic">{(c.author_name || '?').slice(0, 1)}</span>
                    <div className="msg-main">
                      <div className="msg-title">{c.author_name}<span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: 6 }}>· {fmtDate(c.created_at)}</span></div>
                      <div className="msg-sub" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
        <div className="wb-td-foot">
          <span className="wb-av" title={item.assignee_name}>{item.assignee_name?.[0] ?? '奇'}</span>
          {canWrite ? (
            <>
              <StatusPill status={item.status} dir="up" onPick={(s) => void update(item.id, { status: s })} />
              <PriorityPill value={item.priority} dir="up" onPick={(p) => void update(item.id, { priority: p })} />
              <DueDatePill value={item.due_date} dir="up" onChange={(v) => void update(item.id, { due_date: v })} />
              <MilestonePill value={item.milestone_id} dir="up" onPick={(id) => void update(item.id, { milestone_id: id })} />
            </>
          ) : (
            <Tag className="pj-rolebadge">只读 · {STATUS_OPTS.find((status) => status.key === item.status)?.label} · {PRIO[item.priority].label}</Tag>
          )}
        </div>
      </div>
    </AntModalBridge>
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
  const [priority, setPriority] = useState<WorkPriority>('')
  const [labels, setLabels] = useState<string[]>([])
  const [milestoneId, setMilestoneId] = useState('')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!title.trim() || busy) return
    setBusy(true)
    try {
      const wi = await add({ title, status, description: desc, due_date: due, attachments, priority, labels, milestone_id: milestoneId })
      if (wi) { toast('待办已创建'); onCreated(wi) }
      onClose()
    } catch {
      toast('创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="新建待办">
        <div className="np-h">新建待办<WbButton className="np-x" onClick={onClose}>×</WbButton></div>
        <div className="np-body">
          <div className="np-lbl">标题</div>
          <WbInput className="np-input" placeholder="请输入待办标题" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter') void create() }} />
          <div className="np-lbl">描述（可选）</div>
          <WbTextArea className="np-ta" placeholder="请输入待办描述" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <div className="np-lbl">标签（可选）</div>
          <LabelsEditor labels={labels} onChange={setLabels} />
          <AttachmentChips list={attachments} projectId={projectId} onRemove={(i) => setAttachments((a) => a.filter((_, j) => j !== i))} />
        </div>
        <div className="np-foot">
          <AttachmentAdder projectId={projectId} onAdd={(a) => setAttachments((prev) => [...prev, a])} dir="up" />
          <PriorityPill value={priority} dir="up" onPick={setPriority} />
          <DueDatePill value={due} dir="up" onChange={setDue} />
          <MilestonePill value={milestoneId} dir="up" onPick={setMilestoneId} />
          <span style={{ flex: 1 }} />
          <WbButton className="btn-ghost" onClick={onClose}>取消</WbButton>
          <WbButton className="btn-dark" disabled={!title.trim() || busy} onClick={create}>创建</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}

// ---- 添加数据源 modal (placeholder) --------------------------------------

function DataSourceModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<'empty' | 'list'>('empty')
  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="添加数据源">
        <div className="np-h">添加数据源<WbButton className="np-x" onClick={onClose}>×</WbButton></div>
        {step === 'empty' ? (
          <div className="np-body" style={{ paddingBottom: 22 }}>
            <div className="pj-ds-empty">
              <div className="t">还没有外部数据源</div>
              <div className="s">先添加一个数据源，把外部系统中的信息按规则同步到当前协作项目。</div>
              <WbButton className="btn-dark" onClick={() => setStep('list')}>添加</WbButton>
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
                    <WbButton className="pj-ds-act" onClick={() => toast(`${d.name} 数据源接入 · 敬请期待`)}>{d.action} ↗</WbButton>
                  </div>
                ))}
              </div>
            </div>
            <div className="np-foot" style={{ justifyContent: 'flex-end' }}>
              <WbButton className="btn-ghost" onClick={() => setStep('empty')}>返回</WbButton>
            </div>
          </>
        )}
      </div>
    </AntModalBridge>
  )
}

function BatchMove({ disabled, onPick }: { disabled: boolean; onPick: (s: WorkStatus) => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <WbButton ref={ref} type="button" className="btn-ghost" disabled={disabled} onClick={() => setOpen((v) => !v)}>移动到 ▾</WbButton>
      <Popover open={open} anchor={ref.current} dir="down" onClose={() => setOpen(false)} minWidth={132}>
        {STATUS_OPTS.map((s) => (
          <div className="pop-item" key={s.key} {...clickable} onClick={() => { onPick(s.key); setOpen(false) }}>
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
export function KanbanBoard({ canWrite = true }: { canWrite?: boolean }) {
  const { message, modal } = AntApp.useApp()
  const items = useWorkItemStore((s) => s.items)
  const add = useWorkItemStore((s) => s.add)
  const move = useWorkItemStore((s) => s.move)
  const remove = useWorkItemStore((s) => s.remove)
  const milestones = useWorkItemStore((s) => s.milestones)
  const projectId = useWorkItemStore((s) => s.projectId)
  const msName = useMemo(() => Object.fromEntries(milestones.map((m) => [m.id, m.name])), [milestones])
  const templates = getTpl(projectId)

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
  // 看板增强（WB-123）：分组泳道 / WIP 编辑态 / 保存视图。tick 强制重渲染（WIP/视图写 localStorage 后）。
  const [group, setGroup] = useState<'none' | 'assignee' | 'milestone'>('none')
  const [wipEdit, setWipEdit] = useState(false)
  const [, setTick] = useState(0)
  const wip = getWip(projectId)
  const kviews = getKViews(projectId)

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
  const lanes = group === 'none' ? [] : (() => {
    const m = new Map<string, { label: string; items: WorkItem[] }>()
    visible.forEach((i) => {
      const k = group === 'assignee' ? (i.assignee || '') : (i.milestone_id || '')
      if (!m.has(k)) m.set(k, { label: group === 'assignee' ? (k ? (i.assignee_name || k) : '未指派') : (k ? (msName[k] || '里程碑') : '无里程碑'), items: [] })
      m.get(k)!.items.push(i)
    })
    return [...m.entries()].map(([id, g]) => ({ id, label: g.label, items: g.items })).sort((a, b) => (a.id ? 0 : 1) - (b.id ? 0 : 1))
  })()

  const quickSubmit = (status: WorkStatus) => {
    if (quickDraft.trim()) void add({ title: quickDraft, status })
    setQuickDraft(''); setQuickIn(null)
  }
  const toggleSel = (id: string) => setSel((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  const exitBatch = () => { setBatch(false); setSel(new Set()) }
  const newFromTpl = async (idx: string) => {
    const t = templates[Number(idx)]; if (!t) return
    const wi = await add({ title: t.name, priority: t.priority, labels: t.labels, milestone_id: t.milestone_id, description: t.description })
    if (wi) setDetailId(wi.id)
  }
  const saveWip = (k: string, v: number) => { const w = getWip(projectId); if (v > 0) w[k] = v; else delete w[k]; if (projectId) setWip(projectId, w); setTick((t) => t + 1) }
  const applyKView = (idx: string) => { const v = kviews[Number(idx)]; if (!v) return; setFAssignee(v.assignee); setFSource(v.source); setQ(v.q); setGroup((v.group as 'none' | 'assignee' | 'milestone') || 'none') }
  const saveKView = () => {
    if (!projectId) return
    let name = ''
    modal.confirm({
      title: '保存当前视图',
      content: <Input autoFocus maxLength={40} placeholder="输入视图名称" onChange={(e) => { name = e.target.value }} />,
      okText: '保存',
      cancelText: '取消',
      onOk: () => {
        const trimmed = name.trim()
        if (!trimmed) {
          void message.warning('请输入视图名称')
          return Promise.reject(new Error('view name required'))
        }
        const views = getKViews(projectId)
        views.push({ name: trimmed, assignee: fAssignee, source: fSource, q, group })
        setKViews(projectId, views)
        setTick((t) => t + 1)
      },
    })
  }
  const batchMove = (s: WorkStatus) => { sel.forEach((id) => void move(id, s)); exitBatch() }
  const batchDelete = () => { sel.forEach((id) => void remove(id)); exitBatch() }
  const cardClick = (i: WorkItem) => { if (batch) toggleSel(i.id); else setDetailId(i.id) }

  // 单块四列看板（WB-123 抽出，供整体或每条泳道复用）。WIP：列头 count/limit + 超限标红 + 编辑态数字输入。
  const renderKanban = (source: WorkItem[]) => (
    <div className="pj-kanban">
      {COLS.map((col) => {
        const colItems = source.filter((i) => i.status === col.key)
        const lim = wip[col.key]; const over = !!lim && colItems.length > lim
        return (
          <div
            key={col.key}
            className={`pj-kcol ${dropCol === col.key ? 'drop' : ''}`.trim()}
            onDragOver={(e) => { if (!canWrite || batch) return; e.preventDefault(); setDropCol(col.key) }}
            onDragLeave={() => setDropCol((c) => (c === col.key ? null : c))}
            onDrop={(e) => { if (!canWrite) return; e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); if (id) void move(id, col.key); setDropCol(null) }}
          >
            <div className="pj-kcol-h">
              <span className="wb-dot" style={{ background: DOT[col.key] }} />
              {col.label}
              <span className="cnt" style={over ? { background: '#EF4444', color: '#fff' } : undefined}>{lim ? `${colItems.length}/${lim}` : colItems.length}</span>
              {wipEdit
                ? <WbInput type="number" min={0} className="np-input" style={{ width: 46, height: 22, padding: '0 6px', marginLeft: 6, fontSize: 11 }} defaultValue={lim || ''} placeholder="∞" onBlur={(e) => saveWip(col.key, parseInt(e.target.value, 10) || 0)} />
                : canWrite ? <span className="plus" {...clickable} onClick={() => { setQuickIn(col.key); setQuickDraft('') }}>＋</span> : null}
            </div>
            {quickIn === col.key && (
              <WbInput
                className="pj-kadd" autoFocus placeholder="输入标题，回车创建" value={quickDraft}
                onChange={(e) => setQuickDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') quickSubmit(col.key); if (e.key === 'Escape') { setQuickIn(null); setQuickDraft('') } }}
                onBlur={() => { if (!quickDraft.trim()) setQuickIn(null) }}
              />
            )}
            {colItems.map((i) => (
              <ProCard
                key={i.id}
                className={`pj-card ${batch && sel.has(i.id) ? 'sel' : ''}`.trim()}
                styles={{ body: { display: 'contents' } }}
                draggable={canWrite && !batch}
                onDragStart={(e) => e.dataTransfer.setData('text/plain', i.id)}
                {...clickable}
                onClick={() => cardClick(i)}
              >
                {canWrite && batch ? (
                  <span className={`pj-card-chk ${sel.has(i.id) ? 'on' : ''}`.trim()}>{sel.has(i.id) ? '✓' : ''}</span>
                ) : canWrite ? (
                  <span className="del" {...clickable} onClick={(e) => { e.stopPropagation(); void remove(i.id) }}>×</span>
                ) : null}
                <div className="t">
                  {i.priority && <span className="wb-dot" style={{ background: PRIO[i.priority].color, marginRight: 6, verticalAlign: 'middle' }} title={`优先级：${PRIO[i.priority].label}`} />}
                  {i.title}
                </div>
                {i.description && <div className="wb-card-d">{i.description}</div>}
                {i.labels.length > 0 && <div className="wb-card-labels"><LabelBadges labels={i.labels} /></div>}
                <div className="m">
                  <span className="av">{i.assignee_name?.[0] ?? '奇'}</span>
                  {i.milestone_id && msName[i.milestone_id] && <span className="wb-badge">🚩 {msName[i.milestone_id]}</span>}
                  {i.attachments.length > 0 && <span className="wb-badge">📎 {i.attachments.length}</span>}
                  {i.due_date && <span className="wb-badge due">📅 {i.due_date.slice(5)}</span>}
                  <span style={{ flex: 1 }} />
                  <span className="ago">{i.ago}</span>
                </div>
              </ProCard>
            ))}
          </div>
        )
      })}
    </div>
  )

  return (
    <>
      <div className="pj-plan-top">
        {canWrite && <WbButton className="btn-dark" style={{ height: 34 }} onClick={() => { setNewIn('todo') }}>＋ 新建待办</WbButton>}
        {canWrite && <WbButton className="btn-ghost" style={{ height: 34 }} onClick={() => setDsOpen(true)}>＋ 添加数据源</WbButton>}
        {!canWrite && <Tag className="pj-rolebadge">只读模式</Tag>}
        <span style={{ flex: 1 }} />
        <FilterDropdown label={assigneeOpts.find((o) => o.key === fAssignee)?.label ?? '全部归属'} options={assigneeOpts} onPick={setFAssignee} />
        <FilterDropdown label={sourceOpts.find((o) => o.key === fSource)?.label ?? '全部来源'} options={sourceOpts} onPick={setFSource} />
        {canWrite && templates.length > 0 && <FilterDropdown label="🧩 从模板" options={templates.map((t, i) => ({ key: String(i), label: t.name }))} onPick={(k) => void newFromTpl(k)} />}
        <FilterDropdown label={group === 'none' ? '不分组' : group === 'assignee' ? '按负责人' : '按里程碑'} options={[{ key: 'none', label: '不分组' }, { key: 'assignee', label: '按负责人' }, { key: 'milestone', label: '按里程碑' }]} onPick={(k) => setGroup(k as 'none' | 'assignee' | 'milestone')} />
        {kviews.length > 0 && <FilterDropdown label="📑 视图" options={kviews.map((v, i) => ({ key: String(i), label: v.name }))} onPick={applyKView} />}
        <WbButton className="btn-ghost" style={{ height: 34 }} onClick={saveKView}>保存视图</WbButton>
        <WbButton className={`cap-act ${wipEdit ? 'on' : ''}`.trim()} onClick={() => setWipEdit((v) => !v)}>WIP</WbButton>
        {canWrite && <WbButton className={`cap-act ${batch ? 'on' : ''}`.trim()} onClick={() => (batch ? exitBatch() : setBatch(true))}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
          批量操作
        </WbButton>}
        <WbButton className="cap-act wb-icon-btn" aria-label="搜索待办" onClick={() => setShowSearch((v) => !v)}>{IcSearch}</WbButton>
      </div>

      {showSearch && (
        <div className="pj-plan-search">
          <div className="search-box" style={{ margin: 0, width: 280 }}>{IcSearch}
            <WbInput placeholder="搜索待办标题" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          </div>
        </div>
      )}

      {batch && (
        <div className="pj-batchbar">
          <span className="cnt">已选 {sel.size}</span>
          <BatchMove disabled={!sel.size} onPick={batchMove} />
          <WbButton className="btn-ghost danger-b" disabled={!sel.size} onClick={batchDelete}>删除</WbButton>
          <span style={{ flex: 1 }} />
          <WbButton className="btn-ghost" onClick={exitBatch}>退出批量</WbButton>
        </div>
      )}

      {group === 'none'
        ? renderKanban(visible)
        : (lanes.length
          ? lanes.map((l) => (
            <div key={l.id || '_none'} style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, margin: '4px 0 8px' }}>{l.label}<span className="cnt">{l.items.length}</span></div>
              {renderKanban(l.items)}
            </div>
          ))
          : <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="无任务" />)}

      {detailId && <TodoDetailModal itemId={detailId} canWrite={canWrite} onClose={() => setDetailId(null)} />}
      {canWrite && newIn && <NewTodoModal status={newIn} onClose={() => setNewIn(null)} onCreated={(wi) => setDetailId(wi.id)} />}
      {canWrite && dsOpen && <DataSourceModal onClose={() => setDsOpen(false)} />}
    </>
  )
}

// 负载: 按负责人聚合工作量（WB-119，对齐 Console pmViewWorkload）。含工时 est/spent 汇总。
export function WorkloadView() {
  const items = useWorkItemStore((s) => s.items).filter((i) => !i.parent_id)
  const today = (() => { const d = new Date(); const p = (n: number) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` })()
  const groups = new Map<string, { name: string; items: WorkItem[] }>()
  items.forEach((i) => {
    const k = i.assignee || ''
    if (!groups.has(k)) groups.set(k, { name: k ? (i.assignee_name || k) : '未指派', items: [] })
    groups.get(k)!.items.push(i)
  })
  const rows = [...groups.entries()].map(([id, g]) => {
    const t = g.items.length
    const c = (s: WorkStatus) => g.items.filter((x) => x.status === s).length
    const done = c('done')
    const overdue = g.items.filter((x) => x.due_date && x.due_date < today && x.status !== 'done').length
    const est = g.items.reduce((a, x) => a + (x.estimate_h || 0), 0)
    const spent = g.items.reduce((a, x) => a + (x.spent_h || 0), 0)
    return { id, name: g.name, t, todo: c('todo'), doing: c('doing'), paused: c('paused'), done, overdue, pct: t ? Math.round((done / t) * 100) : 0, est, spent }
  }).sort((a, b) => (a.id === '' ? 1 : 0) - (b.id === '' ? 1 : 0) || b.t - a.t)

  if (rows.length === 0) return <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有任务" />
  const seg = (n: number, color: string) => (n > 0 ? <div style={{ flex: n, background: color }} /> : null)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 12 }}>
      {rows.map((r) => (
        <div key={r.id || '_none'} style={{ border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px', background: 'var(--card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
            <span className="wb-av">{r.id ? (r.name?.[0] ?? '?') : '∅'}</span>
            <span style={{ flex: 1, fontWeight: 700, fontSize: 13.5 }}>{r.name}</span>
            <span className="wb-label-chip sm">{r.t} 项</span>
          </div>
          <div style={{ display: 'flex', height: 9, borderRadius: 99, overflow: 'hidden', background: 'var(--border-2)', marginBottom: 9 }}>
            {r.t > 0 && <>{seg(r.todo, DOT.todo)}{seg(r.doing, DOT.doing)}{seg(r.paused, DOT.paused)}{seg(r.done, DOT.done)}</>}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 11.5, color: 'var(--text-3)' }}>
            <span>待办 {r.todo}</span><span style={{ color: DOT.doing }}>进行 {r.doing}</span><span style={{ color: DOT.done }}>完成 {r.done} · {r.pct}%</span>{r.overdue > 0 && <span style={{ color: '#EF4444' }}>逾期 {r.overdue}</span>}
          </div>
          {(r.est > 0 || r.spent > 0) && <div style={{ marginTop: 6, fontSize: 11.5, color: 'var(--text-3)' }}>⏱ 预估 {r.est}h · 投入 {r.spent}h</div>}
        </div>
      ))}
    </div>
  )
}

// 甘特: 按 start/due 相对时间画横条（对齐 Console pmViewGantt，WB-121）。今天线 + 月度刻度 + 优先级色条。
export function GanttView({ canWrite = true }: { canWrite?: boolean }) {
  const items = useWorkItemStore((s) => s.items).filter((i) => !i.parent_id)
  const [detailId, setDetailId] = useState<string | null>(null)
  const dated = items.filter((i) => i.due_date || i.start_date)
  if (!dated.length) return <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="无排期任务 —— 给任务设开始/截止日期即可在此按时间轴排布。" />
  const toD = (s: string) => { const a = s.split('-').map(Number); return Date.UTC(a[0], (a[1] || 1) - 1, a[2] || 1) / 86400000 }
  const today = (() => { const d = new Date(); const p = (n: number) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` })()
  let min = Infinity, max = -Infinity
  dated.forEach((x) => { const s = toD((x.start_date || x.due_date) as string); const e = toD((x.due_date || x.start_date) as string); if (s < min) min = s; if (e > max) max = e })
  const tD = toD(today); if (tD < min) min = tD; if (tD > max) max = tD
  if (max <= min) max = min + 1
  const pad = Math.max((max - min) * 0.04, 1); min -= pad; max += pad
  const range = max - min
  const fmt = (n: number) => { const d = new Date(n * 86400000); return `${d.getUTCMonth() + 1}/${d.getUTCDate()}` }
  const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1]
  const todayL = (((tD - min) / range) * 100).toFixed(1)
  return (
    <>
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ width: 160, flexShrink: 0 }} />
        <div style={{ position: 'relative', flex: 1, height: 18, marginBottom: 8 }}>
          {ticks.map((f) => <span key={f} style={{ position: 'absolute', left: `${(f * 100).toFixed(1)}%`, transform: 'translateX(-50%)', fontSize: 10, color: 'var(--text-3)' }}>{fmt(min + f * range)}</span>)}
        </div>
      </div>
      {dated.map((x) => {
        const s = toD((x.start_date || x.due_date) as string), e = toD((x.due_date || x.start_date) as string)
        const left = (((s - min) / range) * 100).toFixed(1), w = Math.max(((e - s) / range) * 100, 1.2).toFixed(1)
        const color = (PRIO[x.priority] ?? PRIO['']).color
        return (
          <div key={x.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 7 }}>
            <div style={{ width: 160, flexShrink: 0, fontSize: 12.5, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} {...clickable} onClick={() => setDetailId(x.id)}>{x.title}</div>
            <div style={{ position: 'relative', flex: 1, height: 24, background: 'var(--border-2)', borderRadius: 6, overflow: 'hidden' }}>
              {ticks.map((f) => <div key={f} style={{ position: 'absolute', top: 0, bottom: 0, left: `${(f * 100).toFixed(1)}%`, width: 1, background: 'var(--border)' }} />)}
              <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${todayL}%`, width: 2, background: '#3D6BFF', zIndex: 2 }} />
              <div title={`${x.start_date || ''} → ${x.due_date || ''}`} {...clickable} onClick={() => setDetailId(x.id)} style={{ position: 'absolute', top: 4, bottom: 4, left: `${left}%`, width: `${w}%`, background: color, borderRadius: 5, cursor: 'pointer', opacity: 0.92 }} />
            </div>
          </div>
        )
      })}
      {detailId && <TodoDetailModal itemId={detailId} canWrite={canWrite} onClose={() => setDetailId(null)} />}
    </>
  )
}

// 任务：与「计划」共用同一批项目 work_items，只是列表视图；项目成员均可见。
export function TaskList({ canWrite = true }: { canWrite?: boolean }) {
  const items = useWorkItemStore((s) => s.items)
  const remove = useWorkItemStore((s) => s.remove)
  const update = useWorkItemStore((s) => s.update)
  const [q, setQ] = useState('')
  const filtered = items.filter((i) => i.title.toLowerCase().includes(q.trim().toLowerCase()))

  return (
    <>
      <div className="mf-filter" style={{ marginTop: 0, marginBottom: 10 }}>
        <div className="mf-type" {...clickable} onClick={() => toast('筛选归属')}>
          <span className="ft-lb">全部任务</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
        </div>
        <div className="mf-type" {...clickable} onClick={() => toast('筛选来源')}>
          <span className="ft-lb">全部来源</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>项目任务对成员可见；这里与「计划」共用同一批工作项</span>
        <span style={{ flex: 1 }} />
        <Input.Search className="search-box" allowClear style={{ margin: 0, width: 220 }} placeholder="搜索任务标题" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Table<WorkItem>
        className="pj-task-table"
        rowKey="id"
        dataSource={filtered}
        pagination={false}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务，去「计划」看板新建" /> }}
        columns={[
          { title: '任务', dataIndex: 'title', render: (title, item) => <span className="tt">{title}<span className="wb-card-labels"><LabelBadges labels={item.labels} /></span></span> },
          { title: '截止日期', dataIndex: 'due_date', width: 110, render: (value) => value ? <Tag className="wb-badge due">📅 {String(value).slice(5)}</Tag> : '—' },
          { title: '负责人', dataIndex: 'assignee_name', width: 100, render: (name) => name || '—' },
          { title: '优先级', dataIndex: 'priority', width: 130, render: (value, item) => canWrite ? <PriorityPill value={value} onPick={(priority) => void update(item.id, { priority })} /> : (PRIO[value as WorkPriority]?.label || '无优先级') },
          { title: '状态', dataIndex: 'status', width: 130, render: (value, item) => canWrite ? <StatusPill status={value} onPick={(status) => void update(item.id, { status })} /> : (STATUS_OPTS.find((status) => status.key === value)?.label || value) },
          ...(canWrite ? [{ title: '操作', key: 'action', width: 70, render: (_: unknown, item: WorkItem) => <WbButton className="del danger-b" onClick={() => void remove(item.id)}>删除</WbButton> }] : []),
        ]}
      />
    </>
  )
}
