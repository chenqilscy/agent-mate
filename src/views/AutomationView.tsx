import { useCallback, useEffect, useRef, useState } from 'react'
import { useCatalog, useCatalogStore } from '../stores/catalogStore'
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
  return useCatalogStore.getState().AUTO.find((a) => a[1] === name)?.[0] ?? '⏰'
}

function triggerLabel(a: Automation): string {
  return a.trigger_kind === 'daily' ? `每天 ${a.at_time}` : `每 ${a.interval_min} 分钟`
}

// A run's human label: kind (测试运行 / 定时运行) + outcome (完成 / 失败) — WB-043.
function runLabel(r: SessionInfo): string {
  if (r.run_status === 'running') return '运行中'
  const kind = r.run_kind === 'test' ? '测试运行' : '定时运行'
  return kind + (r.run_status === 'error' ? '失败' : '完成')
}

// created_at (epoch seconds) → day bucket / HH:MM / full timestamp for 运行记录.
function pad(n: number): string { return String(n).padStart(2, '0') }
function dayLabel(ts?: number): string {
  if (!ts) return '更早'
  const d = new Date(ts * 1000), now = new Date()
  const same = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  if (same(d, now)) return '今天'
  const y = new Date(now); y.setDate(now.getDate() - 1)
  if (same(d, y)) return '昨天'
  return `${d.getMonth() + 1}月${d.getDate()}日`
}
function hhmm(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function fullTime(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// What the editor is opened with: an existing automation (edit) or a template
// prefill (create).
type EditState = { auto?: Automation; prefill?: Partial<CreateAutomationInput> }

export function AutomationView() {
  const items = useAutomationStore((s) => s.items)
  const load = useAutomationStore((s) => s.load)
  const { AUTO } = useCatalog()
  const toggle = useAutomationStore((s) => s.toggle)
  const remove = useAutomationStore((s) => s.remove)
  const runNow = useAutomationStore((s) => s.runNow)
  const openSession = useChatStore((s) => s.openSession)
  const setView = useUIStore((s) => s.setView)
  const projects = useProjectStore((s) => s.projects)
  const loadProjects = useProjectStore((s) => s.load)

  const [editing, setEditing] = useState<EditState | null>(null)
  const [templatesOpen, setTemplatesOpen] = useState(false)
  const [tab, setTab] = useState<'schedule' | 'runs'>('schedule')
  const [query, setQuery] = useState('')
  const [menuId, setMenuId] = useState<string | null>(null)
  const menuAnchor = useRef<HTMLElement | null>(null)
  // Per-automation run history popover (WB-035); shares the menu anchor.
  const [histId, setHistId] = useState<string | null>(null)
  const [histRuns, setHistRuns] = useState<SessionInfo[]>([])
  const [detail, setDetail] = useState<SessionInfo | null>(null) // run detail modal (WB-043)

  useEffect(() => { load(); loadProjects() }, [load, loadProjects])

  // Keep the board live; paused while a full-page sub-view (editor / templates) is up.
  const anyRunning = items.some((a) => a.last_status === 'running')
  useEffect(() => {
    if (editing || templatesOpen) return
    const t = setInterval(() => { load() }, anyRunning ? 3000 : 15000)
    return () => clearInterval(t)
  }, [anyRunning, load, editing, templatesOpen])

  const projName = (pid?: string | null): string | null =>
    pid ? (projects.find((p) => p.id === pid)?.name ?? '工作空间') : null

  const openRun = async (a: Automation) => {
    if (!a.last_session_id) { toast('尚未运行'); return }
    await openSession(a.last_session_id); setView('chat')
  }
  const doRun = async (a: Automation) => { setMenuId(null); toast('已触发运行 · ' + a.name); await runNow(a.id) }
  const openHistory = async (a: Automation) => {
    setMenuId(null)
    try { const { runs } = await api.listAutomationRuns(a.id); setHistRuns(runs); setHistId(a.id) }
    catch { toast('加载运行记录失败') }
  }
  const openRunSession = async (id: string) => { setHistId(null); setDetail(null); await openSession(id); setView('chat') }
  const pickTemplate = (n: string, d: string) => { setTemplatesOpen(false); setEditing({ prefill: { name: n, prompt: d } }) }

  const templateGrid = (
    <div className="card-grid g3">
      {AUTO.map(([ic, n, d]) => (
        <div className="tpl" key={n} {...activate(() => pickTemplate(n, d))} onClick={() => pickTemplate(n, d)}>
          <span className="t-ic">{ic}</span>
          <div><div className="t-n">{n}</div><div className="t-d">{d}</div></div>
        </div>
      ))}
    </div>
  )

  // ---- full-page sub-views -------------------------------------------------
  if (editing) {
    return (
      <section className="view active" data-view="automation">
        <div className="page-scroll">
          <AutomationEditor auto={editing.auto} prefill={editing.prefill} onClose={() => setEditing(null)} onOpenSession={openRunSession} />
        </div>
      </section>
    )
  }

  if (templatesOpen) {
    return (
      <section className="view active" data-view="automation">
        <div className="page-scroll">
          <div className="ph auto-ed-top">
            <div className="ph-l auto-ed-crumb">
              <span className="t-ic">⏰</span>
              <span className="crumb-dim">自动化 /</span>
              <span className="crumb-cur">从模版添加</span>
            </div>
            <button className="btn-ghost" onClick={() => setTemplatesOpen(false)}>返回</button>
          </div>
          <div style={{ marginTop: 18 }}>{templateGrid}</div>
        </div>
      </section>
    )
  }

  // ---- empty state ---------------------------------------------------------
  if (items.length === 0) {
    return (
      <section className="view active" data-view="automation">
        <div className="page-scroll">
          <div className="auto-empty">
            <div className="auto-empty-ic">⏰</div>
            <div className="auto-empty-t">开启你的第一个自动化任务吧</div>
            <button className="btn-dark auto-empty-add" onClick={() => setEditing({})}>{IC_ADD}添加自动化</button>
          </div>
          <div className="sec-title">自动化任务模版</div>
          {templateGrid}
        </div>
      </section>
    )
  }

  // ---- main: tabs + toolbar + (schedule list | runs) -----------------------
  const q = query.trim().toLowerCase()
  const shownItems = items.filter((a) => !q || a.name.toLowerCase().includes(q))

  return (
    <section className="view active" data-view="automation">
      <div className="page-scroll">
        <div className="auto-hd">
          <div className="auto-tabs">
            <button className={`auto-tab ${tab === 'schedule' ? 'on' : ''}`.trim()} onClick={() => setTab('schedule')}>定时任务</button>
            <button className={`auto-tab ${tab === 'runs' ? 'on' : ''}`.trim()} onClick={() => setTab('runs')}>运行记录</button>
          </div>
          <div className="auto-tools">
            <div className="auto-search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
              <input placeholder="搜索自动化/记录" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button className="btn-line" style={{ marginTop: 0 }} onClick={() => setTemplatesOpen(true)}>从模版添加</button>
            <button className="btn-dark auto-add" onClick={() => setEditing({})}>{IC_ADD}添加自动化</button>
          </div>
        </div>

        {tab === 'schedule' ? (
          <>
            <div className="sec-title">当前</div>
            <div className="auto-list">
              {shownItems.length === 0 && <div className="auto-row-empty">无匹配自动化</div>}
              {shownItems.map((a) => (
                <div className="auto-row" key={a.id} {...activate(() => setEditing({ auto: a }))} onClick={() => setEditing({ auto: a })}>
                  <span className="t-ic">{iconOf(a.name)}</span>
                  <div className="auto-row-main">
                    <div className="auto-row-n">{a.name}</div>
                    <div className="auto-row-sub">
                      {projName(a.project_id) && <><span className="ws">{projName(a.project_id)}</span><span className="dot">·</span></>}
                      {triggerLabel(a)}
                    </div>
                  </div>
                  <div className="auto-row-right" onClick={(e) => e.stopPropagation()}>
                    {a.last_status === 'running'
                      ? <span className="auto-chip run"><i className="run-ic" />运行中</span>
                      : a.enabled ? <span className="auto-next">{a.next_run_label}执行</span>
                        : <span className="auto-next off">已停用</span>}
                    <span
                      className={`sw ${a.enabled ? 'on' : ''}`.trim()}
                      role="switch" aria-checked={a.enabled ? 'true' : 'false'} aria-label={a.enabled ? '停用' : '启用'}
                      onClick={() => toggle(a.id, !a.enabled)}
                    />
                    <button
                      className="auto-more" aria-label="更多"
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

                  <Popover open={histId === a.id} anchor={menuAnchor.current} dir="down" onClose={() => setHistId(null)} minWidth={200}>
                    <div className="pop-h">运行历史（{histRuns.length}）</div>
                    {histRuns.length === 0 && <div className="pop-item pop-empty">还没有运行记录</div>}
                    {histRuns.map((r) => (
                      <div className="pop-item hist-item" key={r.id} {...activate(() => openRunSession(r.id))} onClick={() => openRunSession(r.id)}>
                        {r.run_status === 'error' ? '⚠ ' : r.run_status === 'running' ? '运行中 · ' : ''}{r.ago}
                      </div>
                    ))}
                  </Popover>
                </div>
              ))}
            </div>
          </>
        ) : (
          <RunsTab query={q} onOpenDetail={setDetail} />
        )}
      </div>

      {detail && (
        <RunDetailModal
          run={detail}
          onClose={() => setDetail(null)}
          onOpenSession={openRunSession}
          workspaceName={projName(detail.project_id)}
        />
      )}
    </section>
  )
}

function RunStatusIcon({ status }: { status?: string | null }) {
  if (status === 'error') return <span className="run-st err" title="失败">!</span>
  if (status === 'running') return <span className="run-st run" title="运行中"><i className="run-ic" /></span>
  return <span className="run-st ok" title="完成">✓</span>
}

// 运行记录 tab (WB-043): cross-automation run feed, grouped by day, each with its
// per-run outcome; click a row for the detail modal.
function RunsTab({ query, onOpenDetail }: { query: string; onOpenDetail: (r: SessionInfo) => void }) {
  const [runs, setRuns] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    api.listAllAutomationRuns().then(({ runs }) => setRuns(runs)).catch(() => {}).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // reflect running → done without a manual refresh
    return () => clearInterval(t)
  }, [load])

  const shown = runs.filter((r) => !query || r.title.toLowerCase().includes(query) || runLabel(r).toLowerCase().includes(query))
  const groups: { label: string; runs: SessionInfo[] }[] = []
  for (const r of shown) {
    const lbl = dayLabel(r.created_at)
    const g = groups.find((x) => x.label === lbl) ?? (groups.push({ label: lbl, runs: [] }), groups[groups.length - 1])
    g.runs.push(r)
  }

  return (
    <div className="auto-runs">
      {loading && runs.length === 0 && <div className="auto-row-empty">加载中…</div>}
      {!loading && shown.length === 0 && <div className="auto-row-empty">{query ? '无匹配运行记录' : '还没有运行记录'}</div>}
      {groups.map((g) => (
        <div key={g.label}>
          <div className="auto-day">{g.label}</div>
          {g.runs.map((r) => (
            <div className="auto-run" key={r.id} {...activate(() => onOpenDetail(r))} onClick={() => onOpenDetail(r)}>
              <div className="auto-run-main">
                <span className="auto-run-n">{r.title}</span>
                <span className="auto-run-lb">{runLabel(r)}</span>
              </div>
              <div className="auto-run-right">
                <span className="auto-run-time">{hhmm(r.created_at)}</span>
                <RunStatusIcon status={r.run_status} />
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// Run detail modal (WB-043): the saved execution summary + run detail for one run.
function RunDetailModal({ run, onClose, onOpenSession, workspaceName }: {
  run: SessionInfo
  onClose: () => void
  onOpenSession: (id: string) => void
  workspaceName: string | null
}) {
  const failed = run.run_status === 'error'
  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal auto-detail" role="dialog" aria-modal="true" aria-label="运行详情">
        <div className="np-h">{run.title}<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="auto-detail-msg">
            {failed ? '本次任务已启动，但在生成结果前中断，以下为保存下来的执行摘要。' : '本次运行已完成，以下为执行摘要。'}
          </div>
          <div className="auto-detail-badges">
            <span className={`auto-chip ${failed ? 'err' : 'ok'}`}>{runLabel(run)}</span>
            <span className="auto-detail-time">{fullTime(run.created_at)}</span>
          </div>
          <div className="np-lbl">摘要</div>
          <div className="auto-detail-box">{run.run_summary || (failed ? '运行失败' : '运行完成')}</div>
          <div className="np-lbl">运行明细</div>
          <div className="auto-detail-box">
            <div className="auto-detail-path">
              <span className="p">{run.workspace || workspaceName || '默认工作区'}</span>
              <span className={failed ? 'err' : 'ok'}>{failed ? '失败' : '完成'}</span>
            </div>
            {run.run_summary && <div className={`auto-detail-err ${failed ? 'err' : ''}`.trim()}>{run.run_summary}</div>}
          </div>
        </div>
        <div className="np-foot">
          <span className="np-hint" />
          <button className="btn-ghost" onClick={onClose}>关闭</button>
          <button className="btn-dark" onClick={() => onOpenSession(run.id)}>打开会话</button>
        </div>
      </div>
    </div>
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
  // Editing keeps the automation's real model (may be null = follow default); only a
  // fresh create defaults to the current global pick — so editing other fields never
  // silently pins a null-model automation to a model (WB-038).
  const [model, setModel] = useState<string | null>(auto ? auto.model : (prefill?.model ?? defaultModel))
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

  const loadRuns = useCallback(() => {
    if (!auto) return
    api.listAutomationRuns(auto.id).then(({ runs }) => setRuns(runs)).catch(() => {})
  }, [auto])

  useEffect(() => { loadProjects() }, [loadProjects])
  // Keep the run-history side panel live while editing (WB-039): fetch on open, then
  // poll lightly so a run triggered here (and its running→done) shows without reopening.
  useEffect(() => {
    if (!auto) return
    loadRuns()
    const t = setInterval(loadRuns, 4000)
    return () => clearInterval(t)
  }, [auto, loadRuns])

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
          <button className="btn-ghost" onClick={async () => { toast('已触发运行 · ' + auto.name); await runNow(auto.id); loadRuns() }}>立即运行</button>
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
              <span className="model-lb">{model ?? '跟随默认模型'}</span>
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
                {r.run_status === 'error' ? '⚠ ' : r.run_status === 'running' ? '运行中 · ' : ''}{r.ago}
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
        <div className="mrow" onClick={() => { setModel(null); setModelOpen(false) }}>
          <span className="mi">⚙</span>
          <span className="mname">跟随默认模型</span>
          {model === null && <span className="chk">✓</span>}
        </div>
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
