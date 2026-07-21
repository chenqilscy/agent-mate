import { WbButton, WbInput, WbTextArea, WbSelect } from '../ui/Primitives'
import { useEffect, useState } from 'react'
import { api, type Assistant, type AssistantMode } from '../../lib/api'
import type { ProjectInfo } from '../../lib/types'
import { PickerOverlay } from '../project/NewProjectModal'
import { toast } from '../../stores/toastStore'
import { skillDisplayName, useSkillStore } from '../../stores/skillStore'

// 助理设置表单（WB-088）。权限映射 run_chat 三态；工作空间 default/dedicated/project:<id>。
// 专家/技能/连接器 复用 PickerOverlay。套 .np-* 表单类，天然暗色。
const MODES: { v: AssistantMode; label: string; hint: string }[] = [
  { v: 'exec', label: '执行', hint: '全工具，可读写工作区、跑命令' },
  { v: 'plan', label: '计划', hint: '只规划不改动，遇关键决策提问' },
  { v: 'ask', label: '问答', hint: '只回答，不调用任何工具' },
]

export function AssistantSettingsForm({ assistant, onSaved }: {
  assistant: Assistant
  onSaved: (a: Assistant) => void
}) {
  useSkillStore((s) => s.builtin)
  useSkillStore((s) => s.installed)
  const [avatar, setAvatar] = useState(assistant.avatar || '🤖')
  const [name, setName] = useState(assistant.name)
  const [instruction, setInstruction] = useState(assistant.instruction)
  const [model, setModel] = useState(assistant.model)
  const [mode, setMode] = useState<AssistantMode>(assistant.mode)
  const initWsKind = assistant.workspace.startsWith('project:') ? 'project'
    : assistant.workspace === 'dedicated' ? 'dedicated' : 'default'
  const [wsKind, setWsKind] = useState<'default' | 'dedicated' | 'project'>(initWsKind)
  const [wsProject, setWsProject] = useState(assistant.workspace.startsWith('project:') ? assistant.workspace.slice(8) : '')
  const [experts, setExperts] = useState<string[]>(assistant.experts)
  const [skills, setSkills] = useState<string[]>(assistant.skills)
  const [connectors, setConnectors] = useState<string[]>(assistant.connectors)
  const [picker, setPicker] = useState<'exp' | 'skill' | 'conn' | null>(null)
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.listProjects().then((r) => setProjects(r.projects)).catch(() => {}) }, [])

  const toggle = (kind: 'exp' | 'skill' | 'conn', n: string) => {
    const [arr, set] = kind === 'exp' ? [experts, setExperts] : kind === 'skill' ? [skills, setSkills] : [connectors, setConnectors]
    set(arr.includes(n) ? arr.filter((x) => x !== n) : [...arr, n])
  }

  const save = async () => {
    if (!name.trim() || busy) return
    const workspace = wsKind === 'project' ? (wsProject ? `project:${wsProject}` : 'default') : wsKind
    setBusy(true)
    try {
      const a = await api.updateAssistant(assistant.id, {
        name: name.trim(), avatar: avatar.trim() || '🤖', instruction, model: model.trim(),
        mode, workspace, experts, skills, connectors,
      })
      toast('已保存')
      onSaved(a)
    } catch {
      toast('保存失败')
    } finally {
      setBusy(false)
    }
  }

  const chips = (kind: 'exp' | 'skill' | 'conn', arr: string[]) => (
    <div className="asst-chips">
      {arr.length === 0 && <span className="asst-empty">未选</span>}
      {arr.map((n) => (
        <span className="np-chip" key={n} title={n}><span className="np-lbl">{kind === 'skill' ? skillDisplayName(n) : n}</span><span className="x" onClick={() => toggle(kind, n)}>×</span></span>
      ))}
      <WbButton className="asst-addchip" onClick={() => setPicker(kind)}>＋ 编辑</WbButton>
    </div>
  )

  return (
    <div className="asst-form">
      <div className="np-lbl">头像与名字</div>
      <div style={{ display: 'flex', gap: 10 }}>
        <WbInput className="np-input" style={{ width: 60, textAlign: 'center', flexShrink: 0 }} value={avatar} onChange={(e) => setAvatar(e.target.value)} maxLength={4} aria-label="头像 emoji" />
        <WbInput className="np-input" style={{ flex: 1 }} value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="助理名字" />
      </div>

      <div className="np-lbl">指令 / 人格<small className="asst-hint">注入系统提示，决定它怎么回答</small></div>
      <WbTextArea className="np-ta" value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={8000} placeholder="如：语气简洁、条列作答、结论先行。留空则用默认风格。" />

      <div className="np-lbl">大模型<small className="asst-hint">留空跟随后端默认</small></div>
      <WbInput className="np-input" value={model} onChange={(e) => setModel(e.target.value)} maxLength={120} placeholder="如：deepseek-chat" />

      <div className="np-lbl">权限</div>
      <div className="asst-seg">
        {MODES.map((m) => (
          <WbButton key={m.v} className={mode === m.v ? 'on' : ''} title={m.hint} onClick={() => setMode(m.v)}>{m.label}</WbButton>
        ))}
      </div>
      <div className="asst-hint2">{MODES.find((m) => m.v === mode)?.hint}</div>

      <div className="np-lbl">工作空间</div>
      <div className="asst-seg">
        <WbButton className={wsKind === 'default' ? 'on' : ''} onClick={() => setWsKind('default')}>默认</WbButton>
        <WbButton className={wsKind === 'dedicated' ? 'on' : ''} onClick={() => setWsKind('dedicated')}>专属</WbButton>
        <WbButton className={wsKind === 'project' ? 'on' : ''} onClick={() => setWsKind('project')}>项目</WbButton>
      </div>
      {wsKind === 'project' && (
        <WbSelect className="np-input" style={{ marginTop: 8 }} value={wsProject} onChange={(e) => setWsProject(e.target.value)}>
          <option value="">选择项目…</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </WbSelect>
      )}
      <div className="asst-hint2">{wsKind === 'default' ? '共享默认工作区' : wsKind === 'dedicated' ? '本助理专属工作区（workspace/assistants/<id>）' : '复用所选项目的工作区'}</div>

      <div className="np-lbl">专家</div>{chips('exp', experts)}
      <div className="np-lbl">技能</div>{chips('skill', skills)}
      <div className="np-lbl">连接器</div>{chips('conn', connectors)}

      <div style={{ marginTop: 18 }}>
        <WbButton className="btn-dark" disabled={!name.trim() || busy} onClick={save}>保存设置</WbButton>
      </div>

      {picker && (
        <PickerOverlay
          kind={picker}
          sel={new Set(picker === 'exp' ? experts : picker === 'skill' ? skills : connectors)}
          onToggle={(n) => toggle(picker, n)}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  )
}
