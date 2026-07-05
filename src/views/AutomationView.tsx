import { useEffect, useRef, useState } from 'react'
import { AUTO } from '../data/catalog'
import { api } from '../lib/api'
import { activate } from '../lib/a11y'
import { IcChevronDown } from '../lib/icons'
import { useAutomationStore } from '../stores/automationStore'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { Popover } from '../components/ui/Popover'
import type { Automation, CreateAutomationInput, SessionInfo, TriggerKind } from '../lib/types'

const IC_ADD = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
)

function iconOf(name: string): string {
  return AUTO.find((a) => a[1] === name)?.[0] ?? '⏰'
}

function triggerLabel(a: Automation): string {
  return a.trigger_kind === 'daily' ? `每天 ${a.at_time}` : `每 ${a.interval_min} 分钟`
}

// What the editor is opened with: an existing automation (edit) or a template
// prefill (create). Both null → list/templates view.
type EditState = { auto?: Automation; prefill?: Partial<CreateAutomationInput> }

export function AutomationView() {
  const items = useAutomationStore((s) => s.items)
  const load = useAutomationStore((s) => s.load)
  const toggle = useAutomationStore((s) => s.toggle)
  const remove = useAutomationStore((s) => s.remove)
  const runNow = useAutomationStore((s) => s.runNow)
  const openSession = useChatStore((s) => s.openSession)
  const setView = useUIStore((s) => s.setView)

  const [editing, setEditing] = useState<EditState | null>(null)
  const [menuId, setMenuId] = useState<string | null>(null)
  const menuAnchor = useRef<HTMLElement | null>(null)
  // Run history (WB-035): automation runs are hidden from the sidebar by design, so
  // surface every run here. Fetched on demand when the history popover opens; the
  // menu popover shares the same anchor and closes first, so only one shows at a time.
  const [histId, setHistId] = useState<string | null>(null)
  const [histRuns, setHistRuns] = useState<SessionInfo[]>([])

  useEffect(() => { load() }, [load])

  // Keep the board live: a run (manual or a scheduler fire while this page is open)
  // flips a card to "running" on the backend, then to ok/error on completion. Poll
  // so the UI reflects it without a manual refresh — faster while a run is in flight,
  // slower when idle (also keeps the "下次 …/上次 …" relative labels fresh). Paused
  // while the editor is open (the list isn't visible then).
  const anyRunning = items.some((a) => a.last_status === 'running')
  useEffect(() => {
    if (editing) return
    const t = setInterval(() => { load() }, anyRunning ? 3000 : 15000)
    return () => clearInterval(t)
  }, [anyRunning, load, editing])

  const openRun = async (a: Automation) => {
    if (!a.last_session_id) { toast('尚未运行'); return }
    await openSession(a.last_session_id)
    setView('chat')
  }

  const doRun = async (a: Automation) => {
    setMenuId(null)
    toast('已触发运行 · ' + a.name)
    await runNow(a.id)
  }

  // Fetch first, then open — avoids flashing the empty state during the request.
  const openHistory = async (a: Automation) => {
    setMenuId(null)
    try {
      const { runs } = await api.listAutomationRuns(a.id)
      setHistRuns(runs)
      setHistId(a.id)
    } catch {
      toast('加载运行记录失败')
    }
  }

  const openRunSession = async (id: string) => {
    setHistId(null)
    await openSession(id)
    setView('chat')
  }

  if (editing) {
    return (
      <section className="view active" data-view="automation">
        <div className="page-scroll">
          <AutomationEditor
            auto={editing.auto}
            prefill={editing.prefill}
            onClose={() => setEditing(null)}
            onOpenSession={openRunSession}
          />
        </div>
      </section>
    )
  }

  return (
    <section className="view active" data-view="automation">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>自动化</h1>
            <div className="sub">管理自动化任务并查看近期运行记录。到点由真实智能体执行并产出会话。</div>
          </div>
          <button className="btn-line" style={{ marginTop: 0 }} onClick={() => setEditing({})}>
            {IC_ADD}新建
          </button>
        </div>

        {items.length > 0 && (
          <>
            <div className="sec-title">我的自动化（{items.length}）</div>
            <div className="card-grid g2">
              {items.map((a) => (
                <div className="auto-card" key={a.id}>
                  <div className="auto-h">
                    <span className="t-ic">{iconOf(a.name)}</span>
                    <div className="auto-tt">
                      <div className="auto-n">{a.name}</div>
                      <div className="auto-meta">
                        {triggerLabel(a)}
                        <span className="dot">·</span>
                        {a.enabled ? `下次 ${a.next_run_label}` : '已停用'}
                      </div>
                    </div>
                    <span
                      className={`sw ${a.enabled ? 'on' : ''}`.trim()}
                      role="switch"
                      aria-checked={a.enabled ? 'true' : 'false'}
                      aria-label={a.enabled ? '停用' : '启用'}
                      onClick={() => toggle(a.id, !a.enabled)}
                    />
                  </div>
                  <div className="auto-prompt">{a.prompt}</div>
                  <div className="auto-f">
                    {a.last_status === 'running' && <span className="auto-chip run"><i className="run-ic" />运行中</span>}
                    {a.last_status === 'ok' && <span className="auto-chip ok">上次成功 · {a.last_run_label}</span>}
                    {a.last_status === 'error' && <span className="auto-chip err">上次失败 · {a.last_run_label}</span>}
                    {!a.last_status && <span className="auto-chip">尚未运行</span>}
                    <button
                      className="auto-more"
                      aria-label="更多"
                      onClick={(e) => { menuAnchor.current = e.currentTarget; setMenuId(menuId === a.id ? null : a.id) }}
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
                    </button>
                  </div>

                  <Popover open={menuId === a.id} anchor={menuAnchor.current} dir="down" onClose={() => setMenuId(null)} minWidth={140}>
                    <div className="pop-item" onClick={() => doRun(a)}>立即运行</div>
                    <div className="pop-item" onClick={() => { setMenuId(null); setEditing({ auto: a }) }}>编辑</div>
                    <div className="pop-item" onClick={() => { setMenuId(null); openRun(a) }}>打开上次运行</div>
                    <div className="pop-item" onClick={() => openHistory(a)}>运行历史</div>
                    <div className="pop-item danger" onClick={() => { setMenuId(null); remove(a.id); toast('已删除 · ' + a.name) }}>删除</div>
                  </Popover>

                  {/* Run history (WB-035): every session this automation produced,
                      reusing the 历史提问 popover pattern (.pop-item.hist-item). */}
                  <Popover open={histId === a.id} anchor={menuAnchor.current} dir="down" onClose={() => setHistId(null)} minWidth={200}>
                    <div className="pop-h">运行历史（{histRuns.length}）</div>
                    {histRuns.length === 0 && <div className="pop-item pop-empty">还没有运行记录</div>}
                    {histRuns.map((r) => (
                      <div className="pop-item hist-item" key={r.id} {...activate(() => openRunSession(r.id))} onClick={() => openRunSession(r.id)}>
                        {r.status === 'running' ? '运行中 · ' : ''}{r.ago}
                      </div>
                    ))}
                  </Popover>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="sec-title">从模板入手</div>
        <div className="card-grid g3">
          {AUTO.map(([ic, n, d]) => (
            <div className="tpl" key={n} {...activate(() => setEditing({ prefill: { name: n, prompt: d } }))} onClick={() => setEditing({ prefill: { name: n, prompt: d } })}>
              <span className="t-ic">{ic}</span>
              <div>
                <div className="t-n">{n}</div>
                <div className="t-d">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// Full-page automation editor (WB-036). Create (from ＋新建 / a template) or edit an
// existing automation. Exposes workspace binding (project_id) and per-automation
// model — both already honoured by the scheduler → run_chat. Reuses the .np-* form
// vocabulary and .ctool/.mrow model picker so it matches the composer verbatim.
function AutomationEditor({ auto, prefill, onClose, onOpenSession }: {
  auto?: Automation
  prefill?: Partial<CreateAutomationInput>
  onClose: () => void
  onOpenSession: (id: string) => void
}) {
  const create = useAutomationStore((s) => s.create)
  const update = useAutomationStore((s) => s.update)
  const remove = useAutomationStore((s) => s.remove)
  const runNow = useAutomationStore((s) => s.runNow)
  const projects = useProjectStore((s) => s.projects)
  const loadProjects = useProjectStore((s) => s.load)
  const models = useSettingsStore((s) => s.models)
  const defaultModel = useSettingsStore((s) => s.model)

  const [name, setName] = useState(auto?.name ?? prefill?.name ?? '')
  const [prompt, setPrompt] = useState(auto?.prompt ?? prefill?.prompt ?? '')
  const [projectId, setProjectId] = useState<string | null>(auto?.project_id ?? prefill?.project_id ?? null)
  const [model, setModel] = useState<string>(auto?.model ?? prefill?.model ?? defaultModel)
  const [kind, setKind] = useState<TriggerKind>(auto?.trigger_kind ?? prefill?.trigger_kind ?? 'interval')
  const [interval, setInterval] = useState(auto?.interval_min ?? prefill?.interval_min ?? 60)
  const [atTime, setAtTime] = useState(auto?.at_time ?? prefill?.at_time ?? '09:00')
  const [busy, setBusy] = useState(false)

  const [wsOpen, setWsOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const wsAnchor = useRef<HTMLElement | null>(null)
  const modelAnchor = useRef<HTMLElement | null>(null)

  // Run history (edit mode only) — real sessions this automation produced (WB-035).
  const [runs, setRuns] = useState<SessionInfo[]>([])

  useEffect(() => { loadProjects() }, [loadProjects])
  useEffect(() => {
    if (!auto) return
    api.listAutomationRuns(auto.id).then(({ runs }) => setRuns(runs)).catch(() => {})
  }, [auto])

  const selectedProject = projects.find((p) => p.id === projectId)
  const canSave = name.trim().length > 0 && prompt.trim().length > 0 && !busy

  const save = async () => {
    if (!canSave) return
    setBusy(true)
    const payload: CreateAutomationInput = {
      name: name.trim(),
      prompt: prompt.trim(),
      trigger_kind: kind,
      interval_min: Math.max(1, interval),
      at_time: atTime,
      project_id: projectId,
      model,
    }
    try {
      if (auto) {
        await update(auto.id, payload)
        toast('已保存 · ' + payload.name)
      } else {
        await create(payload)
        toast('自动化已创建 · ' + payload.name)
      }
      onClose()
    } catch {
      toast(auto ? '保存失败' : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  const del = () => {
    if (!auto) return
    remove(auto.id)
    toast('已删除 · ' + auto.name)
    onClose()
  }

  return (
    <>
      <div className="ph auto-ed-top">
        <div className="ph-l auto-ed-crumb">
          <span className="t-ic">{iconOf(name)}</span>
          <span className="crumb-dim">自动化 /</span>
          <span className="crumb-cur">{name.trim() || '新建自动化'}</span>
        </div>
        {auto && (
          <button className="btn-ghost" onClick={() => { runNow(auto.id); toast('已触发运行 · ' + auto.name) }}>立即运行</button>
        )}
        {auto && (
          <button className="btn-ghost danger-b" onClick={del}>删除</button>
        )}
        <button className="btn-ghost" onClick={onClose}>取消</button>
        <button className="btn-dark" disabled={!canSave} onClick={save}>保存</button>
      </div>

      <div className="auto-ed">
        <div className="auto-ed-main">
          <div className="np-lbl">名称</div>
          <input className="np-input" placeholder="给这个自动化起个名字" value={name} onChange={(e) => setName(e.target.value)} autoFocus />

          <div className="np-lbl">工作空间<small className="np-opt">（可选）</small></div>
          <div className="np-row">
            <div className="np-chips">
              {projectId && (
                <span className="np-chip" title={selectedProject?.name ?? projectId}>
                  <span>🗂️</span>
                  <span className="np-lbl">{selectedProject?.name ?? '工作空间'}</span>
                  <span className="x" {...activate(() => setProjectId(null))} onClick={() => setProjectId(null)}>×</span>
                </span>
              )}
            </div>
            <button className="np-add" onClick={(e) => { wsAnchor.current = e.currentTarget; setWsOpen(true) }}>
              ＋ {projectId ? '更换' : '选择工作空间'}
            </button>
          </div>

          <div className="np-lbl">指令（到点会作为一次对话真实执行）</div>
          <textarea
            className="np-ta"
            placeholder="例如：关注当天 AI 领域的重要动态，筛选 3-5 条整理成中文简报"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="auto-ed-tb">
            <button className="ctool model" onClick={(e) => { modelAnchor.current = e.currentTarget; setModelOpen(true) }}>
              <span className="mk">🐋</span>
              <span className="model-lb">{model}</span>
              <IcChevronDown style={{ width: 10, height: 10 }} />
            </button>
          </div>

          <div className="np-lbl">触发方式</div>
          <div className="auto-trig">
            <div className="seg2">
              <b className={kind === 'interval' ? 'on' : ''} onClick={() => setKind('interval')}>每隔一段</b>
              <b className={kind === 'daily' ? 'on' : ''} onClick={() => setKind('daily')}>每天定时</b>
            </div>
            {kind === 'interval' ? (
              <div className="auto-trig-in">
                每
                <input type="number" min={1} aria-label="间隔分钟" value={interval} onChange={(e) => setInterval(Number(e.target.value) || 1)} />
                分钟运行一次
              </div>
            ) : (
              <div className="auto-trig-in">
                每天
                <input type="time" aria-label="每天运行时间" value={atTime} onChange={(e) => setAtTime(e.target.value)} />
                运行
              </div>
            )}
          </div>
        </div>

        {auto && (
          <aside className="auto-ed-side">
            <div className="pop-h">运行历史（{runs.length}）</div>
            {runs.length === 0 && <div className="pop-item pop-empty">还没有运行记录</div>}
            {runs.map((r) => (
              <div className="pop-item hist-item" key={r.id} {...activate(() => onOpenSession(r.id))} onClick={() => onOpenSession(r.id)}>
                {r.status === 'running' ? '运行中 · ' : ''}{r.ago}
              </div>
            ))}
          </aside>
        )}
      </div>

      <Popover open={wsOpen} anchor={wsAnchor.current} dir="down" onClose={() => setWsOpen(false)} minWidth={220}>
        <div className="pop-item" onClick={() => { setProjectId(null); setWsOpen(false) }}>
          不绑定（默认工作区）{projectId === null && <span className="chk">✓</span>}
        </div>
        {projects.length === 0 && <div className="pop-item pop-empty">暂无工作空间</div>}
        {projects.map((p) => (
          <div className="pop-item" key={p.id} onClick={() => { setProjectId(p.id); setWsOpen(false) }}>
            <span className="pi-ic">🗂️</span>{p.name}{projectId === p.id && <span className="chk">✓</span>}
          </div>
        ))}
      </Popover>

      <Popover open={modelOpen} anchor={modelAnchor.current} dir="down" onClose={() => setModelOpen(false)} className="model" minWidth={240}>
        {models.length === 0 && <div className="pop-item pop-empty">模型列表加载中…</div>}
        {models.map((m) => (
          <div className="mrow" key={m.name} onClick={() => { setModel(m.name); setModelOpen(false) }}>
            <span className="mi" style={m.color ? { background: m.color, color: '#fff' } : undefined}>{m.icon}</span>
            <span className="mname">{m.name}</span>
            <span className="mult">{m.mult}</span>
            {m.name === model && <span className="chk">✓</span>}
          </div>
        ))}
      </Popover>
    </>
  )
}
