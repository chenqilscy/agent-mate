import { useEffect, useState } from 'react'
import { Avatar, Empty, Spin, Tag } from 'antd'
import { api, type Assistant } from '../../lib/api'
import type { Automation, ProjectInfo } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { WbButton, WbInput } from '../ui/Primitives'

export type ProjectBindingKind = 'assistant' | 'automation'

interface Props {
  kind: ProjectBindingKind
  project: ProjectInfo
  projects: ProjectInfo[]
  onClose: () => void
  onSaved: (assistants: Assistant[], automations: Automation[]) => void
  onNavigate: (kind: ProjectBindingKind) => void
}

function projectName(projects: ProjectInfo[], id: string): string {
  return projects.find((project) => project.id === id)?.name ?? '其他项目'
}

/**
 * Maintains the existing execution-plane relationships instead of inventing a
 * second project config model: assistants use workspace=project:<id>, while
 * automations use project_id. Objects already owned by another workspace are
 * visible but deliberately cannot be stolen from here.
 */
export function ProjectBindingsModal({ kind, project, projects, onClose, onSaved, onNavigate }: Props) {
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [automations, setAutomations] = useState<Automation[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const projectWorkspace = `project:${project.id}`

  const readBack = async () => {
    const [assistantResult, automationResult] = await Promise.all([
      api.listAssistants(),
      api.listAutomations(),
    ])
    setAssistants(assistantResult.assistants)
    setAutomations(automationResult.automations)
    const current = kind === 'assistant'
      ? assistantResult.assistants.filter((item) => item.workspace === projectWorkspace)
      : automationResult.automations.filter((item) => item.project_id === project.id)
    setSelected(new Set(current.map((item) => item.id)))
    onSaved(assistantResult.assistants, automationResult.automations)
    return { assistants: assistantResult.assistants, automations: automationResult.automations }
  }

  useEffect(() => {
    let current = true
    setLoading(true)
    Promise.all([api.listAssistants(), api.listAutomations()])
      .then(([assistantResult, automationResult]) => {
        if (!current) return
        setAssistants(assistantResult.assistants)
        setAutomations(automationResult.automations)
        const bound = kind === 'assistant'
          ? assistantResult.assistants.filter((item) => item.workspace === projectWorkspace)
          : automationResult.automations.filter((item) => item.project_id === project.id)
        setSelected(new Set(bound.map((item) => item.id)))
      })
      .catch(() => { if (current) toast('项目配置加载失败，请稍后重试') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [kind, project.id, projectWorkspace])

  const toggle = (id: string, disabled: boolean) => {
    if (disabled || saving) return
    setSelected((previous) => {
      const next = new Set(previous)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      if (kind === 'assistant') {
        const changes = assistants.flatMap((item) => {
          const belongsHere = item.workspace === projectWorkspace
          const canBind = item.workspace === 'default' || !item.workspace
          if (belongsHere && !selected.has(item.id)) return [api.updateAssistant(item.id, { workspace: 'default' })]
          if (canBind && selected.has(item.id)) return [api.updateAssistant(item.id, { workspace: projectWorkspace })]
          return []
        })
        await Promise.all(changes)
      } else {
        const changes = automations.flatMap((item) => {
          const belongsHere = item.project_id === project.id
          if (belongsHere && !selected.has(item.id)) return [api.updateAutomation(item.id, { project_id: null })]
          if (!item.project_id && selected.has(item.id)) return [api.updateAutomation(item.id, { project_id: project.id })]
          return []
        })
        await Promise.all(changes)
      }
      await readBack()
      toast(`${kind === 'assistant' ? '助手' : '自动化'}配置已更新`)
      onClose()
    } catch {
      try { await readBack() } catch { /* Preserve the original error message. */ }
      toast('保存失败，已重新读取当前配置')
    } finally {
      setSaving(false)
    }
  }

  const title = kind === 'assistant' ? '配置项目助手' : '配置项目自动化'
  const items = kind === 'assistant' ? assistants : automations

  return (
    <AntModalBridge onClose={saving ? () => {} : onClose} closeOnMask={!saving} keyboard={!saving}>
      <div className="np-modal pj-bind-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="np-h">
          {title}
          <WbButton className="np-x" aria-label="关闭" disabled={saving} onClick={onClose}>×</WbButton>
        </div>
        <div className="pj-bind-intro">
          {kind === 'assistant'
            ? '选择在这个项目工作区运行的助手。属于其他项目或专属工作区的助手需先在助手页调整。'
            : '选择按计划在这个项目中执行的自动化。已属于其他项目的自动化不会被转移。'}
        </div>
        <div className="np-body pj-bind-list">
          {loading ? (
            <Spin className="pj-bind-empty" description="加载中…" />
          ) : items.length === 0 ? (
            <Empty
              className="pj-bind-empty"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={kind === 'assistant' ? '还没有助手' : '还没有自动化'}
            >
              <WbButton className="btn-ghost" onClick={() => onNavigate(kind)}>
                去创建{kind === 'assistant' ? '助手' : '自动化'}
              </WbButton>
            </Empty>
          ) : kind === 'assistant' ? assistants.map((item) => {
            const otherProjectId = item.workspace.startsWith('project:') ? item.workspace.slice(8) : ''
            const occupied = item.workspace === 'dedicated' || (!!otherProjectId && item.workspace !== projectWorkspace)
            const occupancy = item.workspace === 'dedicated'
              ? '专属工作区'
              : otherProjectId && item.workspace !== projectWorkspace
                ? `已属于 ${projectName(projects, otherProjectId)}`
                : null
            return (
              <label className={`pj-bind-row${occupied ? ' disabled' : ''}`} key={item.id}>
                <WbInput
                  type="checkbox"
                  checked={selected.has(item.id)}
                  disabled={occupied || saving}
                  aria-label={`选择助手 ${item.name}`}
                  onChange={() => toggle(item.id, occupied)}
                />
                <Avatar className="pj-bind-avatar">{item.avatar || '🤖'}</Avatar>
                <span className="pj-bind-main">
                  <b>{item.name}</b>
                  <small>{item.enabled ? '已启用' : '已停用'} · {item.mode === 'exec' ? '执行模式' : item.mode === 'plan' ? '计划模式' : '问答模式'}</small>
                </span>
                {occupancy && <Tag className="pj-bind-tag">{occupancy}</Tag>}
              </label>
            )
          }) : automations.map((item) => {
            const occupied = !!item.project_id && item.project_id !== project.id
            return (
              <label className={`pj-bind-row${occupied ? ' disabled' : ''}`} key={item.id}>
                <WbInput
                  type="checkbox"
                  checked={selected.has(item.id)}
                  disabled={occupied || saving}
                  aria-label={`选择自动化 ${item.name}`}
                  onChange={() => toggle(item.id, occupied)}
                />
                <Avatar className="pj-bind-avatar">⏰</Avatar>
                <span className="pj-bind-main">
                  <b>{item.name}</b>
                  <small>{item.enabled ? item.next_run_label || '等待调度' : '已停用'}</small>
                </span>
                {occupied && <Tag className="pj-bind-tag">已属于 {projectName(projects, item.project_id!)}</Tag>}
              </label>
            )
          })}
        </div>
        <div className="np-foot pj-bind-foot">
          <span className="pj-bind-count">已选择 {selected.size} 项</span>
          <WbButton className="btn-ghost" disabled={saving} onClick={onClose}>取消</WbButton>
          <WbButton className="btn-dark" disabled={loading || saving} onClick={save}>{saving ? '保存中…' : '保存'}</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
