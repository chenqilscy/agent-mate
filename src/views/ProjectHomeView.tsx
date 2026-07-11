import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ProjectInfo, SessionInfo } from '../lib/types'
import { useProjectStore } from '../stores/projectStore'
import { useChatStore } from '../stores/chatStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { Composer } from '../components/composer/Composer'
import { PickerOverlay } from '../components/project/NewProjectModal'
import { KanbanBoard, TaskList, WorkloadView, GanttView } from '../components/project/ProjectWork'
import { AssetsManager } from '../components/project/AssetsManager'
import { MembersModal } from '../components/project/MembersModal'
import { HubCommentsPanel } from '../components/hub/HubCommentsPanel'
import { useWorkItemStore } from '../stores/workItemStore'
import { useCatalogStore } from '../stores/catalogStore'

type Tab = '动态' | '计划' | '任务' | '负载' | '甘特' | '资产' | '讨论'
type Kind = 'conn' | 'exp' | 'skill'
const FIELD: Record<Kind, 'connectors' | 'experts' | 'skills'> = { conn: 'connectors', exp: 'experts', skill: 'skills' }

function iconOf(kind: Kind, name: string): string {
  const cat = useCatalogStore.getState()
  if (kind === 'conn') return cat.NP_CONNS.find((c) => c[1] === name)?.[0] ?? '🔗'
  if (kind === 'exp') return cat.NP_EXPERTS.find((e) => e[1] === name)?.[0] ?? '🧑'
  return cat.SK_GRID.find((s) => s[1] === name)?.[0] ?? '🧩'
}

const IC_ADD = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
const IC_EDIT = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 14, height: 14 }}><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>

// Project home = a workbench (§11): breadcrumb + 4 tabs + a live 项目配置 sidebar.
// Execution is a sub-item — the composer starts one; the 动态 tab lists them.
export function ProjectHomeView() {
  const active = useProjectStore((s) => s.active)
  const setActive = useProjectStore((s) => s.setActive)
  const reloadProjects = useProjectStore((s) => s.load)
  const setView = useUIStore((s) => s.setView)
  const startProject = useChatStore((s) => s.startProject)
  const openSession = useChatStore((s) => s.openSession)
  const send = useChatStore((s) => s.send)

  const [project, setProject] = useState<ProjectInfo | null>(active)
  const [tab, setTab] = useState<Tab>('动态')
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [editInstr, setEditInstr] = useState(false)
  const [instrDraft, setInstrDraft] = useState('')
  const [picker, setPicker] = useState<Kind | null>(null)
  const [pickerSet, setPickerSet] = useState<Set<string>>(new Set())
  const [membersOpen, setMembersOpen] = useState(false)
  const loadWork = useWorkItemStore((s) => s.load)

  const pid = active?.id

  useEffect(() => {
    if (!pid) return
    // Entering a project is a fresh execution context — drop any ad-hoc loadout the
    // previous chat picked from the ＋ menu, so it can't leak into this project's run
    // (WB-003). Reset happens on entry, before the user picks in the project composer,
    // so the "pick-then-launch" path here is preserved.
    useLoadoutStore.getState().reset()
    api.getProject(pid).then((p) => { setProject(p); setActive(p) }).catch(() => {})
    api.projectSessions(pid).then((r) => setSessions(r.sessions)).catch(() => {})
    loadWork(pid)
  }, [pid, setActive, loadWork])

  if (!project) return <section className="view active" data-view="project" />

  const applyProject = (p: ProjectInfo) => { setProject(p); setActive(p); reloadProjects() }
  // The caller's role in this project (M7 C2) drives the badge + management access.
  const ROLE_LABEL: Record<string, string> = { Owner: '所有者', Admin: '管理员', Member: '成员', Viewer: '只读' }
  const canManage = project.role === 'Owner' || project.role === 'Admin'
  const isShared = !!project.role && project.role !== 'Owner'
  const onLeft = () => { setMembersOpen(false); toast('已退出项目'); reloadProjects(); setView('projects') }

  const saveInstruction = async () => {
    setEditInstr(false)
    const p = await api.updateProject(project.id, { instruction: instrDraft })
    applyProject(p)
    toast('指令已更新')
  }

  const openPicker = (k: Kind) => { setPickerSet(new Set(project[FIELD[k]])); setPicker(k) }
  const closePicker = async () => {
    const k = picker!
    setPicker(null)
    const p = await api.updateProject(project.id, { [FIELD[k]]: [...pickerSet] })
    applyProject(p)
    toast('项目配置已更新')
  }

  const launch = (text: string) => {
    // 执行计划项时，待办以 🔖 ref 只注入本轮 LLM 输入、不进正文/标题；此时用计划项名
    // 作会话标题，让「动态」feed 能认出执行的是哪个计划项，而非随手指令（WB-047）。
    const todoRef = useLoadoutStore.getState().refs.find((r) => r.kind === 'todo')
    const raw = todoRef?.name ?? text
    startProject(project.id, raw.length > 26 ? raw.slice(0, 26) + '…' : raw)
    setView('projexec')
    void send(text)
  }
  const openExec = (id: string) => { openSession(id); setView('projexec') }

  const cfgSection = (k: Kind, label: string) => {
    const items = project[FIELD[k]]
    return (
      <div className="pjcfg-sec">
        <div className="pjcfg-h">
          {label}<span className="n">{items.length}</span>
          <span className="add" onClick={() => openPicker(k)}>{IC_ADD}</span>
        </div>
        {items.length ? (
          <div className="pjcfg-icons">
            {items.map((n) => <span className="pjcfg-ic" key={n} title={n}>{iconOf(k, n)}</span>)}
          </div>
        ) : (
          <div className="pjcfg-sub">未配置，点 ＋ 添加</div>
        )}
      </div>
    )
  }

  return (
    <section className="view active" data-view="project">
      <div className="chat-head">
        <div className="pe-crumb">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
          <span style={{ cursor: 'pointer' }} onClick={() => setView('projects')}>项目</span>
          <span className="ps">/</span><b>{project.name}</b>
          {isShared && <span className="pj-rolebadge" title={`你在本项目的角色：${ROLE_LABEL[project.role!] || project.role}`}>协作 · {ROLE_LABEL[project.role!] || project.role}</span>}
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn-dark" style={{ height: 32 }} onClick={() => setMembersOpen(true)}>{canManage ? '邀请' : '成员'}</button>
        </div>
      </div>

      <div className="pjh">
        <div className="pjh-main">
          <div className="pjh-tabs">
            {(['动态', '计划', '任务', '负载', '甘特', '资产', '讨论'] as Tab[]).map((t) => (
              <div key={t} className={`pjh-tab ${tab === t ? 'active' : ''}`.trim()} onClick={() => setTab(t)}>{t}</div>
            ))}
          </div>

          <div className="pjh-body">
            {tab === '动态' && (
              sessions.length ? (
                sessions.map((s) => (
                  <div className="pj-feed-row" key={s.id} onClick={() => openExec(s.id)}>
                    <span className="fi"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16v12H5.2L4 17.2z" /></svg></span>
                    <span className="ft">{s.title}</span>
                    <span className="fa">{s.owner_name ? `${s.owner_name} · ` : ''}{s.status === 'running' ? '执行中' : s.ago}</span>
                  </div>
                ))
              ) : (
                <div className="pj-empty">还没有执行记录。在下方描述任务，开始项目的第一次执行。</div>
              )
            )}

            {tab === '计划' && <KanbanBoard />}

            {tab === '任务' && <TaskList />}

            {tab === '负载' && <WorkloadView />}

            {tab === '甘特' && <GanttView />}

            {tab === '资产' && <AssetsManager scope={{ project: project.id }} />}

            {tab === '讨论' && <HubCommentsPanel projectId={project.id} />}
          </div>

          <div className="chat-foot">
            <Composer variant="chat" onSend={launch} placeholder={`在「${project.name}」里开始一次执行…`} />
            <div className="disc">内容由 AI 生成，请核实重要信息</div>
          </div>
        </div>

        <aside className="pjcfg">
          <h3>项目配置</h3>
          <div className="pjcfg-sec">
            <div className="pjcfg-h">
              指令
              {!editInstr && <span className="add" onClick={() => { setInstrDraft(project.instruction); setEditInstr(true) }}>{IC_EDIT}</span>}
            </div>
            {editInstr ? (
              <>
                <textarea className="pjcfg-ta" aria-label="项目指令" placeholder="项目指令" value={instrDraft} onChange={(e) => setInstrDraft(e.target.value)} autoFocus />
                <div className="pjcfg-edit-f">
                  <button className="btn-ghost" style={{ height: 28, padding: '0 12px' }} onClick={() => setEditInstr(false)}>取消</button>
                  <button className="btn-dark" style={{ height: 28, padding: '0 14px' }} onClick={saveInstruction}>保存</button>
                </div>
              </>
            ) : (
              <div className="pjcfg-instr">{project.instruction || '未设置项目指令，点右上角编辑。'}</div>
            )}
          </div>

          {cfgSection('conn', '连接器')}
          {cfgSection('exp', '专家')}
          {cfgSection('skill', '技能')}

          <div className="pjcfg-sec">
            <div className="pjcfg-h">
              成员
              <span className="add" onClick={() => setMembersOpen(true)}>{canManage ? IC_ADD : IC_EDIT}</span>
            </div>
            <div className="pjcfg-sub">
              {canManage ? '邀请队友、分配角色（所有者/管理员/成员/只读）' : `你的角色：${ROLE_LABEL[project.role!] || project.role}`}
            </div>
          </div>

          <div className="pjcfg-sec">
            <div className="pjcfg-h">自动化</div>
            <div className="pjcfg-sub">让 AI 按计划自动执行任务（阶段 B）</div>
          </div>
        </aside>
      </div>

      {membersOpen && <MembersModal project={project} onClose={() => setMembersOpen(false)} onLeft={onLeft} />}

      {picker && (
        <PickerOverlay
          kind={picker}
          sel={pickerSet}
          onToggle={(n) => setPickerSet((prev) => { const nx = new Set(prev); nx.has(n) ? nx.delete(n) : nx.add(n); return nx })}
          onClose={closePicker}
        />
      )}
    </section>
  )
}
