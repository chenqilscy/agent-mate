import { useEffect, useMemo, useState } from 'react'
import { App as AntApp, Empty, Input, Modal, Progress, Select, Table, Tag } from 'antd'
import type { Milestone, ServerProjectSprint, WorkItem, WorkPriority, WorkStatus } from '../../lib/types'
import { api } from '../../lib/api'
import { useWorkItemStore, type NewWorkItem } from '../../stores/workItemStore'
import { toast } from '../../stores/toastStore'
import { clickable } from '../../lib/a11y'
import { WbButton } from '../ui/Primitives'
import { TodoDetailModal } from './ProjectWork'

type CenterView = 'tasks' | 'milestones' | 'sprints'
type MilestoneDraft = Pick<Milestone, 'name' | 'description' | 'due_date' | 'status'> & { id?: string }
type SprintDraft = Omit<ServerProjectSprint, 'id'> & { id?: string; milestone_id?: string }

const STATUS_OPTIONS: { value: WorkStatus; label: string }[] = [
  { value: 'todo', label: '待开始' },
  { value: 'doing', label: '进行中' },
  { value: 'paused', label: '已暂停' },
  { value: 'review', label: '待验收' },
  { value: 'done', label: '已完成' },
]
const PRIORITY_LABEL: Record<WorkPriority, string> = { '': '无', low: '低', medium: '中', high: '高', urgent: '紧急' }
const SPRINT_STATUS: Record<string, { label: string; color: string }> = {
  active: { label: '进行中', color: 'processing' },
  planned: { label: '计划中', color: 'default' },
  closed: { label: '已结束', color: 'success' },
}

function localDateAfter(days: number) {
  const value = new Date()
  value.setDate(value.getDate() + days)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function progressOf(items: WorkItem[]) {
  const completed = items.filter((item) => item.status === 'done').length
  return { completed, percent: items.length ? Math.round((completed / items.length) * 100) : 0 }
}

function errorText(error: unknown, fallback: string) {
  const message = String((error as Error)?.message || '')
  if (message.includes('→ 503')) return 'Server 暂不可达，本次修改未保存'
  if (message.includes('→ 403')) return '当前项目角色没有这项编辑权限'
  return message || fallback
}

export function ProjectTaskCenter({
  projectId,
  projectName,
  canWrite,
  sourceLabel,
  loading,
  error,
  onRetry,
}: {
  projectId: string
  projectName: string
  canWrite: boolean
  sourceLabel: string
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  const { modal } = AntApp.useApp()
  const items = useWorkItemStore((state) => state.items)
  const milestones = useWorkItemStore((state) => state.milestones)
  const add = useWorkItemStore((state) => state.add)
  const update = useWorkItemStore((state) => state.update)
  const loadMilestones = useWorkItemStore((state) => state.loadMilestones)
  const [view, setView] = useState<CenterView>('tasks')
  const [sprints, setSprints] = useState<ServerProjectSprint[]>([])
  const [sprintsLoading, setSprintsLoading] = useState(true)
  const [sprintsError, setSprintsError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<string>('all')
  const [milestoneId, setMilestoneId] = useState('all')
  const [sprintId, setSprintId] = useState('all')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [taskOpen, setTaskOpen] = useState(false)
  const [taskSaving, setTaskSaving] = useState(false)
  const [taskDraft, setTaskDraft] = useState<NewWorkItem>({ title: '', status: 'todo', priority: '', milestone_id: '', sprint_id: '' })
  const [milestoneOpen, setMilestoneOpen] = useState(false)
  const [milestoneSaving, setMilestoneSaving] = useState(false)
  const [milestoneDraft, setMilestoneDraft] = useState<MilestoneDraft>({ name: '', description: '', due_date: null, status: 'open' })
  const [sprintOpen, setSprintOpen] = useState(false)
  const [sprintSaving, setSprintSaving] = useState(false)
  const [sprintDraft, setSprintDraft] = useState<SprintDraft>({ name: '', goal: '', start_date: localDateAfter(0), end_date: localDateAfter(14), status: 'planned', milestone_id: '' })

  const loadSprints = async () => {
    setSprintsLoading(true)
    setSprintsError('')
    try {
      const result = await api.serverProjectSprints(projectId)
      setSprints(result.sprints || [])
    } catch (reason) {
      setSprintsError(errorText(reason, 'Sprint 读取失败'))
    } finally {
      setSprintsLoading(false)
    }
  }

  useEffect(() => { void loadSprints() }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((item) =>
      (!needle || `${item.title} ${item.description} ${item.labels.join(' ')}`.toLowerCase().includes(needle))
      && (status === 'all' || item.status === status)
      && (milestoneId === 'all' || item.milestone_id === milestoneId)
      && (sprintId === 'all' || item.sprint_id === sprintId),
    )
  }, [items, milestoneId, query, sprintId, status])

  const milestoneStats = useMemo(() => new Map(milestones.map((milestone) => {
    const related = items.filter((item) => item.milestone_id === milestone.id)
    return [milestone.id, { total: related.length, ...progressOf(related) }]
  })), [items, milestones])

  const sprintStats = useMemo(() => new Map(sprints.map((sprint) => {
    const related = items.filter((item) => item.sprint_id === sprint.id)
    return [sprint.id, { total: related.length, ...progressOf(related), estimate: related.reduce((sum, item) => sum + Number(item.estimate_h || 0), 0), spent: related.reduce((sum, item) => sum + Number(item.spent_h || 0), 0) }]
  })), [items, sprints])

  const orderedSprints = useMemo(() => [...sprints].sort((left, right) => {
    const rank: Record<string, number> = { active: 0, planned: 1, closed: 2 }
    return (rank[left.status] ?? 9) - (rank[right.status] ?? 9) || left.start_date.localeCompare(right.start_date)
  }), [sprints])

  const openTasksFor = (kind: 'milestone' | 'sprint', id: string) => {
    setMilestoneId(kind === 'milestone' ? id : 'all')
    setSprintId(kind === 'sprint' ? id : 'all')
    setView('tasks')
  }

  const saveTask = async () => {
    if (!taskDraft.title.trim()) { toast('请输入任务标题'); return }
    setTaskSaving(true)
    const created = await add(taskDraft)
    setTaskSaving(false)
    if (!created) return
    setTaskOpen(false)
    setTaskDraft({ title: '', status: 'todo', priority: '', milestone_id: '', sprint_id: '' })
    setDetailId(created.id)
  }

  const saveMilestone = async () => {
    if (!milestoneDraft.name.trim()) { toast('请输入里程碑名称'); return }
    setMilestoneSaving(true)
    try {
      const body = { ...milestoneDraft, name: milestoneDraft.name.trim() }
      if (milestoneDraft.id) await api.updateMilestone(projectId, milestoneDraft.id, body)
      else await api.createMilestone({ project_id: projectId, ...body })
      await loadMilestones(projectId)
      setMilestoneOpen(false)
      toast(milestoneDraft.id ? '里程碑已更新' : '里程碑已创建')
    } catch (reason) {
      toast(errorText(reason, '里程碑保存失败'))
    } finally {
      setMilestoneSaving(false)
    }
  }

  const deleteMilestone = (milestone: Milestone) => modal.confirm({
    title: `删除里程碑“${milestone.name}”？`,
    content: '关联任务会保留并回到未关联里程碑状态。',
    okText: '删除里程碑',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: async () => {
      await api.deleteMilestone(projectId, milestone.id)
      await loadMilestones(projectId)
    },
  })

  const saveSprint = async () => {
    if (!sprintDraft.name.trim()) { toast('请输入 Sprint 名称'); return }
    if (!sprintDraft.start_date || !sprintDraft.end_date || sprintDraft.end_date < sprintDraft.start_date) { toast('Sprint 日期范围无效'); return }
    setSprintSaving(true)
    try {
      const body = { ...sprintDraft, name: sprintDraft.name.trim() }
      if (sprintDraft.id) await api.serverUpdateProjectSprint(projectId, sprintDraft.id, body)
      else await api.serverCreateProjectSprint(projectId, body)
      await loadSprints()
      setSprintOpen(false)
      toast(sprintDraft.id ? 'Sprint 已更新' : 'Sprint 已创建')
    } catch (reason) {
      toast(errorText(reason, 'Sprint 保存失败'))
    } finally {
      setSprintSaving(false)
    }
  }

  const deleteSprint = (sprint: ServerProjectSprint) => modal.confirm({
    title: `删除 Sprint“${sprint.name}”？`,
    content: '关联任务会保留并回到 Backlog，不会被删除。',
    okText: '删除 Sprint',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: async () => {
      await api.serverDeleteProjectSprint(projectId, sprint.id)
      await loadSprints()
    },
  })

  const tabItems: { key: CenterView; label: string; count: number }[] = [
    { key: 'tasks', label: '全部任务', count: items.length },
    { key: 'milestones', label: '里程碑', count: milestones.length },
    { key: 'sprints', label: 'Sprint', count: sprints.length },
  ]

  return (
    <div className="pe-task-center">
      <div className="pe-task-center-head">
        <div className="pe-task-center-title"><span aria-hidden>📁</span><div><b>{projectName}</b><small>{sourceLabel}</small></div></div>
        <div className="pe-task-center-tabs" role="tablist" aria-label="项目任务中心视图">
          {tabItems.map((tab) => <WbButton key={tab.key} className={`pe-task-center-tab ${view === tab.key ? 'active' : ''}`.trim()} role="tab" aria-selected={view === tab.key} onClick={() => setView(tab.key)}>{tab.label}<span>{tab.count}</span></WbButton>)}
        </div>
        {canWrite && view === 'tasks' && <WbButton className="btn-dark pe-task-center-create" onClick={() => setTaskOpen(true)}>＋ 新建任务</WbButton>}
        {canWrite && view === 'milestones' && <WbButton className="btn-dark pe-task-center-create" onClick={() => { setMilestoneDraft({ name: '', description: '', due_date: null, status: 'open' }); setMilestoneOpen(true) }}>＋ 新建里程碑</WbButton>}
        {canWrite && view === 'sprints' && <WbButton className="btn-dark pe-task-center-create" onClick={() => { setSprintDraft({ name: '', goal: '', start_date: localDateAfter(0), end_date: localDateAfter(14), status: 'planned', milestone_id: '' }); setSprintOpen(true) }}>＋ 新建 Sprint</WbButton>}
      </div>

      {(error || sprintsError) && <div className="pe-task-center-warning" role="status"><span>{error || sprintsError}</span><WbButton onClick={() => { onRetry(); void loadSprints() }}>重新同步</WbButton></div>}

      <div className="pe-task-center-body" role="tabpanel">
        {view === 'tasks' && <>
          <div className="pe-task-center-filter">
            <Input.Search allowClear value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、描述或标签" />
            <Select aria-label="任务状态" value={status} onChange={setStatus} options={[{ value: 'all', label: '全部状态' }, ...STATUS_OPTIONS]} />
            <Select aria-label="任务里程碑" value={milestoneId} onChange={setMilestoneId} options={[{ value: 'all', label: '全部里程碑' }, ...milestones.map((milestone) => ({ value: milestone.id, label: milestone.name }))]} />
            <Select aria-label="任务 Sprint" value={sprintId} onChange={setSprintId} options={[{ value: 'all', label: '全部 Sprint' }, ...orderedSprints.map((sprint) => ({ value: sprint.id, label: sprint.name }))]} />
            <span>{filteredItems.length} / {items.length} 项</span>
          </div>
          <Table<WorkItem>
            className="pj-task-table pe-task-center-table"
            rowKey="id"
            loading={loading && items.length === 0}
            dataSource={filteredItems}
            pagination={false}
            scroll={{ x: 860 }}
            onRow={(item) => ({ ...clickable, onClick: () => setDetailId(item.id) })}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前范围暂无任务" /> }}
            columns={[
              { title: '任务', dataIndex: 'title', width: 290, render: (title, item) => <div className="pe-task-title"><b>{title}</b><small>{item.description || '暂无描述'}</small></div> },
              { title: '负责人', dataIndex: 'assignee_name', width: 100, render: (value) => value || '未指派' },
              { title: '优先级', dataIndex: 'priority', width: 90, render: (value: WorkPriority) => PRIORITY_LABEL[value] || '无' },
              { title: '里程碑', dataIndex: 'milestone_id', width: 150, render: (value) => milestones.find((item) => item.id === value)?.name || '—' },
              { title: 'Sprint', dataIndex: 'sprint_id', width: 150, render: (value) => sprints.find((item) => item.id === value)?.name || 'Backlog' },
              { title: '状态', dataIndex: 'status', width: 120, render: (value: WorkStatus, item) => canWrite ? <Select className="pe-task-status" size="small" value={value} onClick={(event) => event.stopPropagation()} onChange={(next) => void update(item.id, { status: next })} options={STATUS_OPTIONS} /> : STATUS_OPTIONS.find((option) => option.value === value)?.label },
            ]}
          />
        </>}

        {view === 'milestones' && <div className="pe-plan-list">
          {milestones.length === 0 ? <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有里程碑" /> : milestones.map((milestone) => {
            const stats = milestoneStats.get(milestone.id) || { total: 0, completed: 0, percent: 0 }
            return <div className="pe-plan-row" key={milestone.id} {...clickable} onClick={() => openTasksFor('milestone', milestone.id)}>
              <div className="pe-plan-copy"><div><b>{milestone.name}</b><Tag>{milestone.status === 'closed' ? '已关闭' : '开放'}</Tag></div><small>{milestone.description || '暂无说明'}{milestone.due_date ? ` · 截止 ${milestone.due_date}` : ''}</small></div>
              <div className="pe-plan-progress"><span>{stats.completed}/{stats.total} 已完成</span><Progress percent={stats.percent} showInfo={false} /></div>
              {canWrite && <div className="pe-plan-actions"><WbButton className="btn-ghost" onClick={(event) => { event.stopPropagation(); setMilestoneDraft({ id: milestone.id, name: milestone.name, description: milestone.description, due_date: milestone.due_date, status: milestone.status }); setMilestoneOpen(true) }}>编辑</WbButton><WbButton className="btn-ghost danger-b" onClick={(event) => { event.stopPropagation(); deleteMilestone(milestone) }}>删除</WbButton></div>}
            </div>
          })}
        </div>}

        {view === 'sprints' && <div className="pe-plan-list">
          {sprintsLoading && sprints.length === 0 ? <div className="pe-task-center-loading">正在读取 Sprint…</div> : orderedSprints.length === 0 ? <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有 Sprint" /> : orderedSprints.map((sprint) => {
            const stats = sprintStats.get(sprint.id) || { total: 0, completed: 0, percent: 0, estimate: 0, spent: 0 }
            const milestone = milestones.find((item) => item.id === sprint.milestone_id)
            const meta = SPRINT_STATUS[sprint.status] || { label: sprint.status, color: 'default' }
            return <div className="pe-plan-row" key={sprint.id} {...clickable} onClick={() => openTasksFor('sprint', sprint.id)}>
              <div className="pe-plan-copy"><div><b>{sprint.name}</b><Tag color={meta.color}>{meta.label}</Tag>{milestone && <Tag>{milestone.name}</Tag>}</div><small>{sprint.goal || '暂无目标'} · {sprint.start_date} — {sprint.end_date}</small></div>
              <div className="pe-plan-progress"><span>{stats.completed}/{stats.total} 已完成 · {stats.spent}/{stats.estimate || 0}h</span><Progress percent={stats.percent} showInfo={false} /></div>
              {canWrite && sprint.status !== 'closed' && <div className="pe-plan-actions"><WbButton className="btn-ghost" onClick={(event) => { event.stopPropagation(); setSprintDraft({ ...sprint }); setSprintOpen(true) }}>编辑</WbButton>{sprint.status === 'planned' && <WbButton className="btn-ghost danger-b" onClick={(event) => { event.stopPropagation(); deleteSprint(sprint) }}>删除</WbButton>}</div>}
            </div>
          })}
        </div>}
      </div>

      {detailId && <TodoDetailModal itemId={detailId} canWrite={canWrite} mode="execute" onClose={() => setDetailId(null)} />}

      <Modal title="新建任务" open={taskOpen} onCancel={() => setTaskOpen(false)} onOk={() => void saveTask()} confirmLoading={taskSaving} okText="创建任务" cancelText="取消">
        <div className="pe-task-form"><label>标题<Input value={taskDraft.title} maxLength={200} autoFocus onChange={(event) => setTaskDraft({ ...taskDraft, title: event.target.value })} /></label><label>描述<Input.TextArea value={taskDraft.description || ''} rows={4} onChange={(event) => setTaskDraft({ ...taskDraft, description: event.target.value })} /></label><div><label>状态<Select value={taskDraft.status} onChange={(value) => setTaskDraft({ ...taskDraft, status: value })} options={STATUS_OPTIONS} /></label><label>优先级<Select value={taskDraft.priority || ''} onChange={(value) => setTaskDraft({ ...taskDraft, priority: value })} options={Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }))} /></label></div><div><label>里程碑<Select allowClear value={taskDraft.milestone_id || undefined} onChange={(value) => setTaskDraft({ ...taskDraft, milestone_id: value || '' })} options={milestones.map((item) => ({ value: item.id, label: item.name }))} /></label><label>Sprint<Select allowClear value={taskDraft.sprint_id || undefined} onChange={(value) => { const sprint = sprints.find((item) => item.id === value); setTaskDraft({ ...taskDraft, sprint_id: value || '', milestone_id: sprint?.milestone_id || taskDraft.milestone_id }) }} options={orderedSprints.filter((item) => item.status !== 'closed').map((item) => ({ value: item.id, label: item.name }))} /></label></div></div>
      </Modal>

      <Modal title={milestoneDraft.id ? '编辑里程碑' : '新建里程碑'} open={milestoneOpen} onCancel={() => setMilestoneOpen(false)} onOk={() => void saveMilestone()} confirmLoading={milestoneSaving} okText="保存" cancelText="取消">
        <div className="pe-task-form"><label>名称<Input value={milestoneDraft.name} autoFocus maxLength={200} onChange={(event) => setMilestoneDraft({ ...milestoneDraft, name: event.target.value })} /></label><label>说明<Input.TextArea value={milestoneDraft.description} rows={4} maxLength={5000} onChange={(event) => setMilestoneDraft({ ...milestoneDraft, description: event.target.value })} /></label><div><label>截止日期<Input type="date" value={milestoneDraft.due_date || ''} onChange={(event) => setMilestoneDraft({ ...milestoneDraft, due_date: event.target.value || null })} /></label><label>状态<Select value={milestoneDraft.status} onChange={(value) => setMilestoneDraft({ ...milestoneDraft, status: value })} options={[{ value: 'open', label: '开放' }, { value: 'closed', label: '已关闭' }]} /></label></div></div>
      </Modal>

      <Modal title={sprintDraft.id ? '编辑 Sprint' : '新建 Sprint'} open={sprintOpen} onCancel={() => setSprintOpen(false)} onOk={() => void saveSprint()} confirmLoading={sprintSaving} okText="保存" cancelText="取消">
        <div className="pe-task-form"><label>名称<Input value={sprintDraft.name} autoFocus maxLength={200} onChange={(event) => setSprintDraft({ ...sprintDraft, name: event.target.value })} /></label><label>目标<Input.TextArea value={sprintDraft.goal} rows={3} maxLength={5000} onChange={(event) => setSprintDraft({ ...sprintDraft, goal: event.target.value })} /></label><label>所属里程碑<Select allowClear value={sprintDraft.milestone_id || undefined} onChange={(value) => setSprintDraft({ ...sprintDraft, milestone_id: value || '' })} options={milestones.map((item) => ({ value: item.id, label: item.name }))} /></label><div><label>开始日期<Input type="date" value={sprintDraft.start_date} onChange={(event) => setSprintDraft({ ...sprintDraft, start_date: event.target.value })} /></label><label>结束日期<Input type="date" value={sprintDraft.end_date} onChange={(event) => setSprintDraft({ ...sprintDraft, end_date: event.target.value })} /></label></div><label>状态<Select value={sprintDraft.status} onChange={(value) => setSprintDraft({ ...sprintDraft, status: value })} options={[{ value: 'planned', label: '计划中' }, { value: 'active', label: '进行中' }, { value: 'closed', label: '已结束' }]} /></label></div>
      </Modal>
    </div>
  )
}
